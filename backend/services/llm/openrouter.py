"""Live OpenRouter model catalogue, so hardcoded default model ids can't go stale."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"
CACHE_TTL_SECONDS = 3600

_cache: tuple[float, list[dict]] | None = None


async def fetch_openrouter_models() -> list[dict]:
    """Tool-capable OpenRouter models in OpenRouter's order (newest first).

    The assistant needs function calling, so models without "tools" are dropped.
    Public endpoint, no API key needed. Cached for an hour. Raises on failure.
    """
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(MODELS_URL)
        resp.raise_for_status()
    models = [
        {"id": m["id"], "name": m.get("name") or m["id"], "description": ""}
        for m in resp.json().get("data", [])
        if "tools" in (m.get("supported_parameters") or [])
    ]
    _cache = (time.monotonic(), models)
    return models


async def resolve_openrouter_model(preferred: str) -> str:
    """Return `preferred` if OpenRouter still serves it, else the newest model
    in the same family (e.g. anthropic/claude-sonnet-4.5 -> newest
    anthropic/claude-sonnet-*). If the catalogue can't be fetched or nothing
    matches, return `preferred` unchanged so the real API error surfaces.
    """
    try:
        models = await fetch_openrouter_models()
    except Exception as e:
        logger.warning(f"OpenRouter model check skipped: {e}")
        return preferred
    ids = [m["id"] for m in models if ":" not in m["id"]]  # skip :free/:batch variants
    if preferred in ids:
        return preferred
    family = preferred.rsplit("-", 1)[0] + "-"
    replacement = next((i for i in ids if i.startswith(family)), preferred)
    if replacement != preferred:
        logger.warning(f"OpenRouter no longer serves {preferred}; using {replacement}")
    return replacement
