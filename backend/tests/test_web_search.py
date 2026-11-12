"""Assistant web search (Tavily) and API-key masking (tilt_ui-eevz.3)."""

import json

import httpx
import pytest

from backend.routers.config import get_config_value
from backend.services import web_search as ws


def _fake_tavily(monkeypatch, status=200, payload=None, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = request.read().decode()
        return httpx.Response(status, json=payload or {})

    real = httpx.AsyncClient
    monkeypatch.setattr(ws.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_no_key_says_how_to_set_it_up():
    out = await ws.web_search(None, "Pliny the Elder clone")
    assert "System page" in out["error"]


@pytest.mark.asyncio
async def test_results_are_returned_and_marked_untrusted(monkeypatch):
    seen = {}
    _fake_tavily(monkeypatch, payload={"results": [
        {"title": "Pliny clone", "url": "https://example.com/p", "content": "x" * 5000, "score": 0.9},
        {"title": "no url"},
    ]}, seen=seen)
    out = await ws.web_search("tvly-secret", "Pliny the Elder clone recipe", max_results=50)
    assert seen["auth"] == "Bearer tvly-secret"
    assert json.loads(seen["body"])["max_results"] == 10  # capped
    assert [r["url"] for r in out["results"]] == ["https://example.com/p"]
    assert len(out["results"][0]["content"]) == 1200
    assert "Untrusted" in out["note"]


@pytest.mark.asyncio
async def test_bad_key_is_explained(monkeypatch):
    _fake_tavily(monkeypatch, status=401)
    out = await ws.web_search("tvly-bad", "anything")
    assert "rejected" in out["error"]


@pytest.mark.asyncio
async def test_api_keys_are_masked_and_the_mask_does_not_overwrite(client, test_db):
    r = await client.patch("/api/config", json={"tavily_api_key": "tvly-abcdef1234", "ai_api_key": "sk-or-zzzz9876"})
    assert r.status_code == 200
    assert r.json()["tavily_api_key"] == "****1234"
    assert r.json()["ai_api_key"] == "****9876"

    # The System page sends the masked value back unchanged on save
    r = await client.patch("/api/config", json={"tavily_api_key": "****1234", "ai_api_key": "****9876"})
    assert r.status_code == 200
    assert await get_config_value(test_db, "tavily_api_key") == "tvly-abcdef1234"
    assert await get_config_value(test_db, "ai_api_key") == "sk-or-zzzz9876"

    # Clearing still works
    await client.patch("/api/config", json={"tavily_api_key": ""})
    assert await get_config_value(test_db, "tavily_api_key") == ""


@pytest.mark.asyncio
async def test_get_config_masks_and_short_or_padded_keys_are_safe(client, test_db):
    await client.patch("/api/config", json={"tavily_api_key": "  tvly-abcdef1234\n", "ai_api_key": "abc"})
    assert await get_config_value(test_db, "tavily_api_key") == "tvly-abcdef1234"  # stripped on save
    got = (await client.get("/api/config")).json()
    assert got["tavily_api_key"] == "****1234"
    assert got["ai_api_key"] == "****"  # short value: nothing revealed


@pytest.mark.asyncio
async def test_domains_given_as_urls_are_reduced_to_hosts(monkeypatch):
    seen = {}
    _fake_tavily(monkeypatch, payload={"results": []}, seen=seen)
    await ws.web_search("tvly-k", "clone", max_results="lots", include_domains=["https://www.homebrewtalk.com/forums", "", 5])
    body = json.loads(seen["body"])
    assert body["include_domains"] == ["www.homebrewtalk.com"] and body["max_results"] == 5
