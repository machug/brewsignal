"""Per-user memory isolation + Memory page API (tilt_ui-or48). Real mem0 on a tmp qdrant, fake embeddings."""
import hashlib

import pytest
import pytest_asyncio

from backend.auth import AuthUser, require_auth
from backend.main import app
from backend.models import BrewingLearning
from backend.routers import memory as memory_router
from backend.services import memory as mem
from backend.services.llm.config import LLMConfig, LLMProvider

A, B = "user-a", "user-b"
CFG = LLMConfig(enabled=True, provider=LLMProvider.OPENROUTER, api_key="sk-test", model="anthropic/claude-sonnet-5.5")


def _vec(text):
    h = hashlib.sha256(text.encode()).digest()
    return [(h[i % 32] - 128) / 128 for i in range(mem.EMBEDDING_DIMS)]


@pytest.fixture
def real_mem0(monkeypatch, tmp_path):
    from mem0 import Memory
    from mem0.embeddings.openai import OpenAIEmbedding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BREWSIGNAL_MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(OpenAIEmbedding, "embed", lambda self, text, memory_action=None: _vec(text))
    m = Memory.from_config(mem.get_memory_config(CFG))
    monkeypatch.setattr(mem, "get_memory", lambda cfg=None: m)
    return m


async def _add(text, user, **meta):
    r = await mem.add_memory([{"role": "user", "content": text}], user_id=user, llm_config=CFG, infer=False, metadata=meta or None)
    return r["results"][0]["id"]


async def test_user_cannot_see_or_delete_another_users_memories(real_mem0):
    a_id = await _add("Fermzilla holds 2 bar", A)
    b_id = await _add("I only brew lagers", B)

    # fake embeddings only match identical text, so query B's exact text as both users
    assert [x["memory"] for x in await mem.search_memories("I only brew lagers", B, CFG)] == ["I only brew lagers"]
    assert all(x["memory"] != "I only brew lagers" for x in await mem.search_memories("I only brew lagers", A, CFG))
    assert [x["memory"] for x in await mem.search_memories("Fermzilla holds 2 bar", A, CFG)] == ["Fermzilla holds 2 bar"]
    assert [x["id"] for x in await mem.get_all_memories(A, CFG)] == [a_id]

    assert await mem.delete_memory(b_id, A, CFG) is False  # A tries B's id
    assert [x["id"] for x in await mem.get_all_memories(B, CFG)] == [b_id]

    assert await mem.delete_all_memories(A, CFG)
    assert await mem.get_all_memories(A, CFG) == []
    assert [x["id"] for x in await mem.get_all_memories(B, CFG)] == [b_id]


def test_cloud_config_uses_pgvector_and_no_disk(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BREWSIGNAL_MEMORY_DIR", raising=False)
    monkeypatch.setattr(mem.settings, "deployment_mode", "cloud", raising=False)
    monkeypatch.setattr(mem, "_pg_pool", lambda: "POOL")
    cfg = mem.get_memory_config(CFG)
    assert cfg["vector_store"]["provider"] == "pgvector"
    assert cfg["vector_store"]["config"]["connection_pool"] == "POOL"
    assert cfg["vector_store"]["config"]["embedding_model_dims"] == 1536
    assert cfg["history_db_path"] == ":memory:"


@pytest_asyncio.fixture
async def as_user(client):
    def switch(uid):
        app.dependency_overrides[require_auth] = lambda: AuthUser(user_id=uid)
    yield switch
    app.dependency_overrides.pop(require_auth, None)


class TestMemoryApi:
    async def test_list_and_delete_scoped_to_owner(self, client, test_db, real_mem0, as_user):
        mid = await _add("[technique] Dry hop day 4", A, learning_id=1)  # a learning's mem0 copy
        test_db.add(BrewingLearning(user_id=A, category="technique", learning="Dry hop day 4", mem0_memory_id=mid))
        test_db.add(BrewingLearning(user_id=B, category="technique", learning="B secret", mem0_memory_id=None))
        await test_db.commit()
        chat_id = await _add("Prefers 20L batches", A)
        b_chat = await _add("B chat fact", B)

        as_user(A)
        items = (await client.get("/api/memory")).json()
        assert {(i["source"], i["text"]) for i in items} == {("learning", "Dry hop day 4"), ("chat", "Prefers 20L batches")}
        assert all(i["id"] and "B " not in i["text"] for i in items)

        learning_id = next(i["id"] for i in items if i["source"] == "learning")
        b_learning = (await test_db.execute(BrewingLearning.__table__.select().where(BrewingLearning.user_id == B))).first().id
        assert (await client.delete(f"/api/memory/learning:{b_learning}")).status_code == 404
        assert (await client.delete(f"/api/memory/mem:{b_chat}")).status_code == 404
        assert len(await mem.get_all_memories(B, CFG)) == 1

        assert (await client.delete(f"/api/memory/{learning_id}")).status_code == 204
        assert (await client.delete(f"/api/memory/mem:{chat_id}")).status_code == 204
        assert (await client.get("/api/memory")).json() == []
        assert await mem.get_all_memories(A, CFG) == []  # learning's mem0 copy went too
        as_user(B)
        assert len((await client.get("/api/memory")).json()) == 2

    async def test_delete_all_only_own(self, client, test_db, real_mem0, as_user):
        test_db.add(BrewingLearning(user_id=A, category="technique", learning="a1"))
        test_db.add(BrewingLearning(user_id=B, category="technique", learning="b1"))
        await test_db.commit()
        await _add("a chat", A)
        await _add("b chat", B)
        as_user(A)
        assert (await client.delete("/api/memory")).status_code == 204
        assert (await client.get("/api/memory")).json() == []
        as_user(B)
        assert {i["text"] for i in (await client.get("/api/memory")).json()} == {"b1", "b chat"}
