"""/api/chat recipe edits: checked before approval, applied only after it (tilt_ui-eevz.1)."""
import json

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from backend.routers import chat
from backend.services.llm.tools.recipe_v2 import get_recipe_document
from backend.tests.test_assistant_recipe_v2 import JASPER, _save
from backend.tests.test_chat_api import _events, _send, _user_msg, chat_env  # noqa: F401 (fixture)


def _scripted(ops_holder):
    def script(messages):
        last = messages[-1]
        returns = [p for p in last.parts if isinstance(p, ToolReturnPart)] if isinstance(last, ModelRequest) else []
        if not returns:
            return ("update_recipe", {"recipe_id": ops_holder["rid"], "operations": ops_holder["ops"],
                                      "summary": "Rename"}, "call_upd")
        return json.dumps(returns[0].content, default=str)

    async def stream(messages, info):
        out = script(messages)
        if isinstance(out, str):
            yield out
        else:
            name, args, cid = out
            yield {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=cid)}

    def fn(messages, info):
        out = script(messages)
        if isinstance(out, str):
            return ModelResponse(parts=[TextPart(out)])
        name, args, cid = out
        return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=cid)])

    return FunctionModel(fn, stream_function=stream)


def _approve(rid, ops):
    return {"id": "a1", "role": "assistant", "parts": [{
        "type": "tool-update_recipe", "toolCallId": "call_upd", "state": "approval-responded",
        "input": {"recipe_id": rid, "operations": ops, "summary": "Rename"},
        "approval": {"id": "call_upd", "approved": True},
    }]}


@pytest.mark.asyncio
async def test_valid_edit_waits_for_approval_then_applies(client, test_db, chat_env):  # noqa: F811
    rid = (await _save(test_db, JASPER))["recipe_id"]
    ops = [{"op": "replace", "path": "/recipe/name", "value": "Jasper (approved)"}]
    chat_env["model"] = _scripted({"rid": rid, "ops": ops})

    r = await _send(client, "r1", _user_msg("rename it"))
    assert "tool-approval-request" in [e["type"] for e in _events(r)]
    test_db.expire_all()
    assert (await get_recipe_document(test_db, rid))["document"]["recipe"]["name"] == JASPER["recipe"]["name"]

    r = await _send(client, "r1", _approve(rid, ops))
    assert r.status_code == 200, r.text
    test_db.expire_all()
    assert (await get_recipe_document(test_db, rid))["document"]["recipe"]["name"] == "Jasper (approved)"


@pytest.mark.asyncio
async def test_broken_edit_is_bounced_to_the_model_without_asking(client, test_db, chat_env):  # noqa: F811
    rid = (await _save(test_db, JASPER))["recipe_id"]
    ops = [{"op": "replace", "path": "/recipe/ingredients/hop_additions/9/amount/value", "value": 1}]
    chat_env["model"] = _scripted({"rid": rid, "ops": ops})

    r = await _send(client, "r2", _user_msg("break it"))
    types = [e["type"] for e in _events(r)]
    assert "tool-approval-request" not in types
    assert "Patch not applied" in r.text
