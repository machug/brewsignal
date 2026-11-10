"""Agent loop: reasoning budget cap for OpenRouter, and a visible note when a
reply hits max_tokens (tilt_ui-atvb: Sonnet 5.5 spent the whole budget on
reasoning after tool calls and the chat showed nothing)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import backend.routers.ag_ui as ag
from backend.services.llm import LLMConfig, LLMProvider, LLMService


def _chunk(content=None, finish=None):
    delta = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


def _stream(chunks):
    async def gen():
        for c in chunks:
            yield c
    return gen()


async def _run(chunks, provider=LLMProvider.OPENROUTER):
    service = LLMService(LLMConfig(enabled=True, provider=provider, model="m", max_tokens=2000))
    fake = SimpleNamespace(acompletion=AsyncMock(return_value=_stream(chunks)))
    service._litellm = fake
    with patch.object(ag, "_save_message", AsyncMock()), \
         patch.object(ag, "count_context_tokens", lambda *a: 0):
        events = [ag._parse_sse_event(e) async for e in ag._run_agent_loop(
            service, None, [{"role": "user", "content": "hi"}], "t", "r")]
    text = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    return fake.acompletion.call_args.kwargs, events, text


@pytest.mark.asyncio
async def test_reasoning_only_reply_still_shows_a_message():
    # Model emitted only reasoning (empty content) then stopped at max_tokens.
    kwargs, events, text = await _run([_chunk(""), _chunk(""), _chunk(None, "length")])
    types = [e["type"] for e in events]
    assert types[0] == "TEXT_MESSAGE_START" and types[-1] == "TEXT_MESSAGE_END"
    assert "Max Tokens" in text
    assert kwargs["extra_body"] == {"reasoning": {"max_tokens": 1000}}


@pytest.mark.asyncio
async def test_cut_off_reply_gets_note_appended():
    _, _, text = await _run([_chunk("Partial answer"), _chunk(None, "length")])
    assert text.startswith("Partial answer") and "cut off" in text


@pytest.mark.asyncio
async def test_normal_reply_unchanged_and_no_reasoning_cap_off_openrouter():
    kwargs, _, text = await _run([_chunk("Done."), _chunk(None, "stop")], provider=LLMProvider.OPENAI)
    assert text == "Done."
    assert "extra_body" not in kwargs
