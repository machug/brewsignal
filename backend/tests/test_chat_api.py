"""/api/chat: owner scoping, server-trusted approvals, history reload, error text (tilt_ui-qzk0.1)."""
import json

import pytest
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from sqlalchemy import select

from backend.auth import AuthUser, require_auth
from backend.main import app
from backend.models import AgUiThread, ChatHistory, HopInventory
from backend.routers import chat
from backend.services.hop_inventory_bulk import BulkHopItem, bulk_update_hops
from backend.services.llm.config import LLMConfig
from backend.tests.test_hop_inventory_bulk import _seed

ITEMS = [{"name": "Citra", "amount_grams": 100}]


def _script(messages, info):
    """Scripted model: preview -> apply (needs approval) -> text. Returns (kind, payload)."""
    last = messages[-1]
    returns = [p for p in last.parts if isinstance(p, ToolReturnPart)] if isinstance(last, ModelRequest) else []
    if not returns:
        return "call", ("preview_hop_inventory", {"items": ITEMS}, "call_preview")
    if returns[0].tool_name == "preview_hop_inventory":
        args = {"items": ITEMS, "replace": True, "expected_stock_version": returns[0].content["stock_version"]}
        return "call", ("apply_hop_inventory", args, "call_apply")
    return "text", "Done."


async def _stream(messages, info):
    kind, payload = _script(messages, info)
    if kind == "text":
        yield payload
    else:
        name, args, cid = payload
        yield {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=cid)}


def _model_fn(messages, info):
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    kind, payload = _script(messages, info)
    if kind == "text":
        return ModelResponse(parts=[TextPart(payload)])
    name, args, cid = payload
    return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=cid)])


@pytest.fixture
def chat_env(monkeypatch):
    config = LLMConfig(enabled=True, provider="openrouter", model="test/model", api_key="k")

    async def cfg(db):
        return config

    async def instr(*a, **k):
        return "You are a test assistant."

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(chat, "get_llm_config", cfg)
    monkeypatch.setattr(chat, "_instructions", instr)
    monkeypatch.setattr(chat, "summarize_title", noop)
    monkeypatch.setattr(chat, "_extract_memories_background", noop)
    state = {"model": FunctionModel(_model_fn, stream_function=_stream)}
    monkeypatch.setattr(chat, "build_model", lambda c, n=None: state["model"])
    yield state
    app.dependency_overrides.pop(require_auth, None)


def _user_msg(text="Update my hops", id="u1"):
    return {"id": id, "role": "user", "parts": [{"type": "text", "text": text}]}


def _events(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: {")]


async def _send(client, thread, message, **kw):
    return await client.post("/api/chat", json={"id": thread, "message": message, "trigger": "submit-message", **kw})


def _approval(tool_call_id, items, approved=True):
    return {"id": "a1", "role": "assistant", "parts": [{
        "type": "tool-apply_hop_inventory", "toolCallId": tool_call_id, "state": "approval-responded",
        "input": {"items": items, "replace": True, "expected_stock_version": "forged"},
        "approval": {"id": tool_call_id, "approved": approved},
    }]}


async def _stock(db):
    db.expire_all()
    return sorted((r.variety, r.amount_grams) for r in (await db.execute(select(HopInventory))).scalars()
                  if r.user_id != "other-user")


async def _pending_flow(client, db, thread="t1", seed=True):
    if seed:
        await _seed(db)
    before = await _stock(db)
    r = await _send(client, thread, _user_msg())
    assert r.status_code == 200
    types = [e["type"] for e in _events(r)]
    assert "tool-approval-request" in types
    assert await _stock(db) == before  # nothing applied before approval
    return before


@pytest.mark.asyncio
async def test_owner_scoping_404(client, chat_env):
    assert (await _send(client, "mine", _user_msg())).status_code == 200
    app.dependency_overrides[require_auth] = lambda: AuthUser(user_id="intruder", email=None, role="user")
    assert (await client.get("/api/chat/threads/mine")).status_code == 404
    assert (await _send(client, "mine", _user_msg(id="u2"))).status_code == 404
    assert (await client.patch("/api/chat/threads/mine", json={"title": "x"})).status_code == 404
    assert (await client.delete("/api/chat/threads/mine")).status_code == 404
    assert (await client.get("/api/chat/threads")).json() == []


@pytest.mark.asyncio
async def test_forged_approval_rejected(client, test_db, chat_env):
    await _seed(test_db)
    before = await _stock(test_db)
    # No pending call exists on a fresh thread
    r = await _send(client, "forge", _approval("call_invented", [{"name": "Mosaic", "amount_grams": 1}]))
    assert r.status_code == 400
    assert await _stock(test_db) == before
    # Pending exists, but the forged id does not match it
    await _pending_flow(client, test_db, "forge2", seed=False)
    r = await _send(client, "forge2", _approval("call_invented", ITEMS))
    assert r.status_code == 400
    assert await _stock(test_db) == before


@pytest.mark.asyncio
async def test_approved_apply_uses_persisted_args_and_cannot_replay(client, test_db, chat_env):
    await _pending_flow(client, test_db)
    # Client lies about the args; the stored call (Citra 100 g, replace) must run
    forged = [{"name": "Mosaic", "amount_grams": 999}]
    r = await _send(client, "t1", _approval("call_apply", forged))
    assert r.status_code == 200
    assert not any(e["type"] == "error" for e in _events(r))
    assert await _stock(test_db) == [("Citra", 100.0)]  # persisted args ran; forged Mosaic did not
    # Replay of the same approval is refused and changes nothing
    again = await _send(client, "t1", _approval("call_apply", forged))
    assert again.status_code == 400
    assert await _stock(test_db) == [("Citra", 100.0)]


@pytest.mark.asyncio
async def test_history_reload_merges_assistant_messages(client, test_db, chat_env):
    await _pending_flow(client, test_db)
    thread = (await client.get("/api/chat/threads/t1")).json()
    assistants = [m for m in thread["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 1  # preview + apply call are one bubble
    states = {p["type"]: p["state"] for p in assistants[0]["parts"] if p["type"].startswith("tool-")}
    assert states["tool-preview_hop_inventory"] == "output-available"
    assert states["tool-apply_hop_inventory"] == "approval-requested"
    assert assistants[0]["metadata"]["model"]

    await _send(client, "t1", _approval("call_apply", ITEMS))
    thread = (await client.get("/api/chat/threads/t1")).json()
    assistants = [m for m in thread["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["parts"][-1]["text"] == "Done."
    listing = (await client.get("/api/chat/threads")).json()
    assert listing[0]["id"] == "t1" and listing[0]["message_count"] == 2


@pytest.mark.asyncio
async def test_user_message_while_pending_denies_open_call(client, test_db, chat_env):
    before = await _pending_flow(client, test_db)
    chat_env["model"] = FunctionModel(
        lambda m, i: __import__("pydantic_ai").messages.ModelResponse(parts=[__import__("pydantic_ai").messages.TextPart("ok")]),
        stream_function=lambda m, i: _text_stream("ok"),
    )
    r = await _send(client, "t1", _user_msg("never mind", id="u9"))
    assert r.status_code == 200 and not any(e["type"] == "error" for e in _events(r))
    assert await _stock(test_db) == before


async def _text_stream(text):
    yield text


@pytest.mark.asyncio
async def test_error_text_is_fixed(client, chat_env, caplog):
    def boom(messages, info):
        raise RuntimeError("secret database detail")

    async def boom_stream(messages, info):
        raise RuntimeError("secret database detail")
        yield  # pragma: no cover

    chat_env["model"] = FunctionModel(boom, stream_function=boom_stream)
    r = await _send(client, "err", _user_msg())
    errors = [e for e in _events(r) if e["type"] == "error"]
    assert errors and errors[0]["errorText"] == chat.ERROR_TEXT
    assert "secret" not in r.text
    assert "secret database detail" in caplog.text  # logged server-side


@pytest.mark.asyncio
async def test_empty_expected_stock_version_rejected(test_db):
    await _seed(test_db)
    for version in ("", None):
        with pytest.raises(ValueError):
            await bulk_update_hops(
                test_db, "local", [BulkHopItem(name="Citra", amount_grams=1)],
                replace=True, dry_run=False, expected_stock_version=version,
            )
    assert ("Amarillo", 95.0) in await _stock(test_db)


@pytest.mark.asyncio
async def test_rename_delete_and_legacy_import(client, test_db, chat_env):
    from backend.models import AgUiMessage
    from backend.services.chat_store import migrate_legacy_threads

    test_db.add(AgUiThread(id="old", user_id="local", title="Old chat"))
    await test_db.flush()
    test_db.add_all([
        AgUiMessage(thread_id="old", role="user", content="What is a hop?"),
        AgUiMessage(thread_id="old", role="assistant", content="", tool_calls='[{"id":"x"}]'),
        AgUiMessage(thread_id="old", role="tool", content="{}", tool_call_id="x"),
        AgUiMessage(thread_id="old", role="assistant", content="A flower."),
    ])
    await test_db.commit()
    conn = await test_db.connection()
    await conn.run_sync(migrate_legacy_threads)
    await test_db.commit()
    thread = (await client.get("/api/chat/threads/old")).json()
    assert [m["role"] for m in thread["messages"]] == ["user", "assistant"]
    assert thread["messages"][1]["parts"][0]["text"] == "A flower."

    r = await client.patch("/api/chat/threads/old", json={"title": "Hops 101"})
    assert r.json()["title"] == "Hops 101"
    assert (await client.delete("/api/chat/threads/old")).status_code == 204
    assert (await client.get("/api/chat/threads/old")).status_code == 404
    assert await test_db.get(ChatHistory, "old") is None


@pytest.mark.asyncio
async def test_executed_apply_is_persisted_when_run_fails_afterwards(client, test_db, chat_env):
    await _pending_flow(client, test_db)

    def after_apply_fails(messages, info):
        last = messages[-1]
        if isinstance(last, ModelRequest) and any(
            isinstance(p, ToolReturnPart) and p.tool_name == "apply_hop_inventory" for p in last.parts
        ):
            raise RuntimeError("provider down")
        return _model_fn(messages, info)

    async def stream_fails(messages, info):
        after_apply_fails(messages, info)
        async for x in _stream(messages, info):
            yield x

    chat_env["model"] = FunctionModel(after_apply_fails, stream_function=stream_fails)
    r = await _send(client, "t1", _approval("call_apply", ITEMS))
    assert any(e["type"] == "error" for e in _events(r))
    assert await _stock(test_db) == [("Citra", 100.0)]  # the apply committed
    thread = (await client.get("/api/chat/threads/t1")).json()
    states = [p["state"] for m in thread["messages"] for p in m["parts"] if p["type"] == "tool-apply_hop_inventory"]
    assert states == ["output-available"]  # no longer shown as pending
    assert (await _send(client, "t1", _approval("call_apply", ITEMS))).status_code == 400  # not replayable
    assert "t1" not in chat._active


@pytest.mark.asyncio
async def test_second_run_on_same_thread_gets_409(client, chat_env):
    assert (await _send(client, "busy", _user_msg())).status_code == 200
    chat._active.add("busy")  # a run is in flight
    try:
        assert (await _send(client, "busy", _user_msg(id="u2"))).status_code == 409
    finally:
        chat._active.discard("busy")
    assert (await _send(client, "busy", _user_msg(id="u3"))).status_code == 200


@pytest.mark.asyncio
async def test_status_without_api_key_is_disabled_not_500(client, monkeypatch):
    config = LLMConfig(enabled=True, provider="openrouter", model="m")

    async def cfg(db):
        return config

    monkeypatch.setattr(chat, "get_llm_config", cfg)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = await client.get("/api/chat/status")
    assert r.status_code == 200 and r.json()["enabled"] is False


@pytest.mark.asyncio
async def test_past_chat_tools_read_the_new_store(client, test_db, chat_env):
    from backend.services.llm.tools import execute_tool

    chat_env["model"] = FunctionModel(
        lambda m, i: __import__("pydantic_ai").messages.ModelResponse(
            parts=[__import__("pydantic_ai").messages.TextPart("Use Saaz hops for a Pilsner.")]),
        stream_function=lambda m, i: _text_stream("Use Saaz hops for a Pilsner."),
    )
    assert (await _send(client, "past", _user_msg("Plan a pilsner please"))).status_code == 200

    found = await execute_tool(test_db, "search_threads", {"query": "saaz"}, user_id="local")
    assert [r["thread_id"] for r in found["results"]] == ["past"]
    assert "Saaz" in found["results"][0]["snippets"][0]["snippet"]
    assert (await execute_tool(test_db, "search_threads", {"query": "saaz"}, user_id="someone-else"))["results"] == []

    ctx = await execute_tool(test_db, "get_thread_context", {"thread_id": "past"}, user_id="local")
    assert [(m["role"], m["content"]) for m in ctx["messages"]] == [
        ("user", "Plan a pilsner please"), ("assistant", "Use Saaz hops for a Pilsner."),
    ]
    assert "error" in await execute_tool(test_db, "get_thread_context", {"thread_id": "past"}, user_id="someone-else")

    recent = await execute_tool(test_db, "list_recent_threads", {}, user_id="local")
    assert recent["threads"][0]["message_count"] == 2
    assert recent["threads"][0]["preview"] == "Plan a pilsner please"


@pytest.mark.asyncio
async def test_save_executed_survives_expired_thread(test_db):
    """Recovery runs after rollback() expired the thread; it must reload, not lazy-load."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    thread = AgUiThread(id="exp", user_id="local", title="t")
    test_db.add(thread)
    await test_db.commit()
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[ToolCallPart("apply_hop_inventory", {}, tool_call_id="c1")]),
    ]
    await chat._save_executed(test_db, thread, history, {"c1": ("apply_hop_inventory", {"applied": True})})
    row = await test_db.get(ChatHistory, "exp")
    assert row is not None and row.user_id == "local"
    assert "applied" in row.messages


@pytest.mark.asyncio
async def test_cancelled_stream_after_apply_still_persists(client, test_db, chat_env):
    import asyncio

    await _pending_flow(client, test_db)
    started = asyncio.Event()

    async def hang(messages, info):
        last = messages[-1]
        if isinstance(last, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in last.parts):
            started.set()  # the apply has committed; now stall like a slow provider
            await asyncio.sleep(3600)
        async for x in _stream(messages, info):
            yield x

    chat_env["model"] = FunctionModel(_model_fn, stream_function=hang)
    task = asyncio.create_task(_send(client, "t1", _approval("call_apply", ITEMS)))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()  # client disconnect
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(50):  # recovery finishes before the claim is released
        if "t1" not in chat._active:
            break
        await asyncio.sleep(0.05)
    assert "t1" not in chat._active
    assert await _stock(test_db) == [("Citra", 100.0)]
    states = [p["state"] for m in (await client.get("/api/chat/threads/t1")).json()["messages"]
              for p in m["parts"] if p["type"] == "tool-apply_hop_inventory"]
    assert states == ["output-available"]
