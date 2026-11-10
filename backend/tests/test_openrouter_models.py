"""OpenRouter: live model list, static fallback, and stale-default resolution."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers import assistant
from backend.services.llm import openrouter


def _live(models):
    resp = AsyncMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"data": models}
    return patch("httpx.AsyncClient.get", AsyncMock(return_value=resp))


@pytest.fixture(autouse=True)
def clear_cache():
    openrouter._cache = None
    yield
    openrouter._cache = None


def tools(id_, name=None):
    return {"id": id_, "name": name or id_, "supported_parameters": ["tools"]}


@pytest.mark.asyncio
async def test_live_list_filters_to_tool_models_and_sorts():
    live = [
        tools("b/tools", "B Tools"),
        {"id": "a/notools", "name": "A", "supported_parameters": ["temperature"]},
        tools("a/tools", "A Tools"),
    ]
    with _live(live):
        out = await assistant.get_models("openrouter")
    assert [m["id"] for m in out.models] == ["a/tools", "b/tools"]


@pytest.mark.asyncio
async def test_falls_back_to_static_list_on_error():
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=RuntimeError("down"))):
        out = await assistant.get_models("openrouter")
    assert len(out.models) > 0


@pytest.mark.asyncio
async def test_resolve_keeps_model_that_is_still_served():
    with _live([tools("anthropic/claude-sonnet-5"), tools("anthropic/claude-sonnet-4.5")]):
        assert await openrouter.resolve_openrouter_model("anthropic/claude-sonnet-4.5") == "anthropic/claude-sonnet-4.5"


@pytest.mark.asyncio
async def test_resolve_swaps_dropped_model_for_newest_in_family():
    live = [
        tools("anthropic/claude-haiku-5.5"),
        tools("anthropic/claude-sonnet-5.5:batch"),
        tools("anthropic/claude-sonnet-5.5"),
        tools("anthropic/claude-sonnet-5"),
    ]
    with _live(live):
        assert await openrouter.resolve_openrouter_model("anthropic/claude-sonnet-4") == "anthropic/claude-sonnet-5.5"


@pytest.mark.asyncio
async def test_resolve_returns_preferred_when_fetch_fails():
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=RuntimeError("down"))):
        assert await openrouter.resolve_openrouter_model("x/y-1") == "x/y-1"
