"""OpenRouter model list: live fetch filtered to tool-capable models, static fallback."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers import assistant


@pytest.mark.asyncio
async def test_openrouter_live_list_filters_to_tool_models():
    live = [
        {"id": "b/tools", "name": "B Tools", "supported_parameters": ["tools", "temperature"]},
        {"id": "a/notools", "name": "A", "supported_parameters": ["temperature"]},
        {"id": "a/tools", "name": "A Tools", "supported_parameters": ["tools"]},
    ]
    resp = AsyncMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"data": live}
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=resp)):
        out = await assistant.get_models("openrouter")
    assert [m.id if hasattr(m, "id") else m["id"] for m in out.models] == ["a/tools", "b/tools"]


@pytest.mark.asyncio
async def test_openrouter_falls_back_to_static_on_error():
    with patch("httpx.AsyncClient.get", AsyncMock(side_effect=RuntimeError("down"))):
        out = await assistant.get_models("openrouter")
    assert len(out.models) > 0
