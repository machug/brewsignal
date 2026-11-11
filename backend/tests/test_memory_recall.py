"""Assistant memory recall: backfill, keyword fallback, extraction gating, embedder (tilt_ui-scbr). mem0 is mocked."""
import pytest

from backend.models import BrewingLearning
from backend.services import memory as mem
from backend.services import chat_support
from backend.services.llm.config import LLMConfig, LLMProvider

UID = "user-1"


def _cfg(provider=LLMProvider.OPENROUTER, **kw):
    return LLMConfig(enabled=True, provider=provider, api_key="sk-test", model="anthropic/claude-sonnet-5.5", **kw)


class FakeMemory:
    def __init__(self):
        self.added = []

    def add(self, messages, user_id=None, metadata=None, infer=True):
        self.added.append((messages, user_id, metadata, infer))
        return {"results": [{"id": f"m{len(self.added)}", "memory": messages[0]["content"]}]}


async def _rows(db):
    for u, cat, text, mid in [
        (UID, "equipment", "Fermzilla conical holds pressure for transfers", None),
        (UID, "technique", "Dry hop IPA on day 4 at 18C", "already"),
        ("other", "equipment", "Fermzilla belongs to someone else", None),
    ]:
        db.add(BrewingLearning(user_id=u, category=cat, learning=text, mem0_memory_id=mid))
    await db.commit()


class TestEmbedderConfig:
    def test_dims_match_collection(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = mem.get_memory_config(_cfg())
        assert cfg["vector_store"]["config"]["embedding_model_dims"] == mem.EMBEDDING_DIMS == 1536

    def test_extraction_uses_fast_model_not_chat_model(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = mem.get_memory_config(_cfg())
        assert cfg["llm"]["config"]["model"] == "anthropic/claude-haiku-4.5"

    def test_openai_env_key_is_pinned_to_openai_host(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://elsewhere.example/v1")
        for provider in (LLMProvider.GROQ, LLMProvider.OPENROUTER):
            c = mem._get_embedder_config(_cfg(provider))["config"]
            assert c["api_key"] == "sk-openai" and c["openai_base_url"] == "https://api.openai.com/v1"

    def test_openrouter_key_only_goes_to_openrouter(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        c = mem._get_embedder_config(_cfg(LLMProvider.OPENROUTER))["config"]
        assert c["api_key"] == "sk-test" and c["openai_base_url"] == "https://openrouter.ai/api/v1"
        assert mem._get_embedder_config(_cfg(LLMProvider.GROQ)) is None

    def test_memory_dir_override(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("BREWSIGNAL_MEMORY_DIR", str(tmp_path))
        assert mem.get_memory_config(_cfg())["vector_store"]["config"]["path"] == str(tmp_path / "qdrant")


class TestBackfill:
    async def test_adds_rows_without_id_and_is_idempotent(self, test_db, monkeypatch):
        fake = FakeMemory()
        monkeypatch.setattr(mem, "get_memory", lambda cfg=None: fake)
        await _rows(test_db)

        assert await mem.backfill_learnings(test_db, _cfg()) == 2
        assert all(infer is False for *_, infer in fake.added)  # verbatim, no LLM
        assert {u for _, u, _, _ in fake.added} == {UID, "other"}  # owner scoped per row
        rows = (await test_db.execute(BrewingLearning.__table__.select())).all()
        assert all(r.mem0_memory_id for r in rows)
        assert next(r for r in rows if r.learning.startswith("Dry hop")).mem0_memory_id == "already"

        fake.added.clear()
        assert await mem.backfill_learnings(test_db, _cfg()) == 0
        assert fake.added == []

    async def test_failed_add_is_retried_next_time(self, test_db, monkeypatch):
        fake = FakeMemory()
        fake.add = lambda *a, **k: {"results": []}
        monkeypatch.setattr(mem, "get_memory", lambda cfg=None: fake)
        await _rows(test_db)
        assert await mem.backfill_learnings(test_db, _cfg()) == 0
        monkeypatch.setattr(mem, "get_memory", lambda cfg=None: FakeMemory())
        assert await mem.backfill_learnings(test_db, _cfg()) == 2

    async def test_skips_cleanly_without_memory(self, test_db, monkeypatch):
        monkeypatch.setattr(mem, "get_memory", lambda cfg=None: None)
        await _rows(test_db)
        assert await mem.backfill_learnings(test_db, _cfg()) == 0


class TestKeywordFallback:
    async def test_owner_scoped_keyword_hits(self, test_db):
        await _rows(test_db)
        hits = await mem.keyword_search_learnings(test_db, "what about my fermzilla pressure", UID)
        assert [h["memory"] for h in hits] == ["Fermzilla conical holds pressure for transfers"]

    async def test_no_words_no_hits(self, test_db):
        await _rows(test_db)
        assert await mem.keyword_search_learnings(test_db, "??", UID) == []

    async def test_tool_falls_back_when_mem0_errors(self, test_db, monkeypatch):
        from backend.routers import assistant
        from backend.services.llm import tools

        async def cfg(db):
            return _cfg()

        async def broken(*a, **k):
            return None  # mem0 unavailable / errored

        monkeypatch.setattr(assistant, "get_llm_config", cfg)
        monkeypatch.setattr(mem, "search_memories_strict", broken)
        await _rows(test_db)
        out = await tools.search_brewing_memories(test_db, "fermzilla", user_id=UID)
        assert out["count"] == 1 and "Fermzilla conical" in out["memories"][0]["content"]


class TestExtractionGating:
    @pytest.fixture
    def calls(self, monkeypatch):
        calls = []

        async def fake_add(messages, **kw):
            calls.append(messages)
            return {"results": []}

        monkeypatch.setattr(chat_support, "add_memory", fake_add)
        chat_support._extracted.clear()
        return calls

    TURN = [
        {"role": "user", "content": "earlier question about my brew kettle size"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "I ferment pale ales at 18C in a Fermzilla"},
        {"role": "assistant", "content": "Good temperature for clean ale yeast."},
    ]

    async def test_only_latest_turn_sent_and_never_twice(self, calls):
        await chat_support._extract_memories_background(self.TURN, UID, _cfg())
        await chat_support._extract_memories_background(self.TURN, UID, _cfg())
        assert len(calls) == 1
        assert [m["content"] for m in calls[0]] == [self.TURN[2]["content"], self.TURN[3]["content"]]

    async def test_trivial_turn_skipped(self, calls):
        short = [{"role": "user", "content": "thanks!"}, {"role": "assistant", "content": "You are welcome, happy brewing."}]
        await chat_support._extract_memories_background(short, UID, _cfg())
        assert calls == []

    def test_switch_defaults_on(self):
        assert LLMConfig().memory_auto_extract is True
        assert LLMConfig(memory_auto_extract=False).memory_auto_extract is False


async def test_auto_extract_setting_persists_via_config_api(client):
    assert (await client.get("/api/config")).json()["ai_memory_auto_extract"] is True
    r = await client.patch("/api/config", json={"ai_memory_auto_extract": False})
    assert r.status_code == 200 and r.json()["ai_memory_auto_extract"] is False
    assert (await client.get("/api/config")).json()["ai_memory_auto_extract"] is False


async def test_ai_lite_setting_persists_via_config_api(client):
    assert (await client.get("/api/config")).json()["ai_lite_enabled"] is False
    r = await client.patch("/api/config", json={"ai_lite_enabled": True})
    assert r.status_code == 200 and r.json()["ai_lite_enabled"] is True
    assert (await client.get("/api/config")).json()["ai_lite_enabled"] is True

