"""
Mem0 Memory Service for BrewSignal Assistant.

Provides semantic long-term memory for the AI assistant, allowing it to
remember user preferences, brewing habits, and past learnings across sessions.

Deployment modes:
- LOCAL: Embedded Qdrant + SQLite (zero external dependencies)
- CLOUD: pgvector on the app Postgres (Supabase), rows keyed by payload user_id; no disk

LLM Configuration:
- Uses the same LLM config as the assistant (from database)
- Uses mem0's OpenAI-compatible provider against the configured provider's
  base URL (OpenRouter, OpenAI, Groq, DeepSeek, Google, HF, Ollama/Hailo /v1)
- Memory features disabled if no LLM is configured
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.services.llm.config import LLMConfig
from backend.services.llm.model import FAST_MODELS, UnsupportedProvider, api_key_for, openai_base_url

os.environ.setdefault("MEM0_TELEMETRY", "False")  # no phone-home from a home appliance

logger = logging.getLogger(__name__)

EMBEDDING_DIMS = 1536  # openai/text-embedding-3-small; must match the qdrant collection
# mem0 and its local qdrant are synchronous and single-process: run them in a thread, one at a time
_mem_lock = asyncio.Lock()

# Lazy-loaded memory instance
_memory_instance = None
_memory_config_hash = None


PG_COLLECTION = "mem0"  # pgvector table; mem0 also uses "mem0_entities". user_id lives in payload->>'user_id'


def _pg_pool():
    """psycopg pool on the app database for mem0's pgvector store (hosted only)."""
    from psycopg_pool import ConnectionPool

    url = settings.get_database_url().replace("+asyncpg", "")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    # prepare_threshold=None: Supabase poolers (pgbouncer transaction mode) break server-side prepared statements
    pool = ConnectionPool(url, min_size=1, max_size=3, open=False, kwargs={"prepare_threshold": None})
    pool.open(wait=False)
    return pool


def _get_llm_provider_config(llm_config: LLMConfig) -> Optional[dict]:
    """Convert LLMConfig to Mem0's LLM provider config (its OpenAI-compatible provider).

    Returns None for providers without an OpenAI-compatible endpoint (Anthropic).
    """
    if not llm_config.is_configured():
        return None

    try:
        base_url = openai_base_url(llm_config)
    except UnsupportedProvider:
        logger.warning(
            "Memory needs an OpenAI-compatible provider; '%s' is not one. Memory disabled.",
            llm_config._provider_str(),
        )
        return None

    config = {
        # cheap/fast model: fact extraction does not need the main chat model
        # (self-hosted local/hailo have no per-token cost: keep the user's own small model)
        "model": (
            llm_config.model
            if llm_config._provider_str() in ("local", "hailo") and llm_config.model
            else FAST_MODELS.get(llm_config._provider_str()) or llm_config.model
        ),
        # Ollama-compatible servers ignore the key but the OpenAI client needs one
        "api_key": api_key_for(llm_config) or "ollama",
        "temperature": 0.1,  # Low temp for factual memory extraction
        "max_tokens": 500,  # Memories should be concise
    }
    if base_url:
        config["openai_base_url"] = base_url
    return {"provider": "openai", "config": config}


def _get_embedder_config(llm_config: LLMConfig) -> Optional[dict]:
    """Get embedder config. Uses OpenAI embeddings if available, else tries alternatives."""
    # OpenAI key (best embeddings), whatever the chat provider. The base URL is pinned to
    # OpenAI so the key only goes to its own host (not OPENAI_BASE_URL, not the chat host).
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": openai_key,
                "openai_base_url": "https://api.openai.com/v1",
            }
        }

    # OpenRouter exposes /api/v1/embeddings and includes
    # openai/text-embedding-3-small in its catalogue. The previous code
    # passed the bare "text-embedding-3-small" model id; OpenRouter requires
    # the provider-prefixed form ("openai/text-embedding-3-small"), which
    # is why the call fell through to a web-auth path ("No cookie auth
    # credentials found, code:401"). mem0's openai embedder respects the
    # api_key and openai_base_url config fields, so embeddings work directly
    # — the chat (LLM) side uses mem0's OpenAI provider with the same key and base URL.
    provider = llm_config._provider_str()
    if provider == "openrouter" and llm_config.api_key:
        return {
            "provider": "openai",
            "config": {
                "model": "openai/text-embedding-3-small",
                "api_key": llm_config.api_key.get_secret_value(),
                "openai_base_url": "https://openrouter.ai/api/v1",
            }
        }

    if provider == "anthropic":
        logger.warning(
            "Anthropic doesn't provide embeddings. Set OPENAI_API_KEY for "
            "memory features. Memory disabled."
        )
        return None

    logger.warning(
        "No embedding API available for provider '%s'. Set OPENAI_API_KEY "
        "or switch chat provider to OpenRouter for memory features. "
        "Memory disabled.",
        provider,
    )
    return None


def get_memory_config(llm_config: LLMConfig) -> Optional[dict]:
    """Get Mem0 configuration using the provided LLM config.

    Returns None if LLM is not configured.
    """
    llm_provider = _get_llm_provider_config(llm_config)
    if not llm_provider:
        logger.info("LLM not configured. Memory features disabled.")
        return None

    # Embedder is required — without it mem0 falls back to a default OpenAI
    # config that 401s when no OPENAI_API_KEY is set. Better to disable
    # memory cleanly than to let mem0 generate noisy auth errors on every
    # turn. Resolved before any DB pool is opened.
    embedder = _get_embedder_config(llm_config)
    if not embedder:
        return None

    if settings.is_cloud and not os.environ.get("BREWSIGNAL_MEMORY_DIR"):
        # Hosted: vectors live in the Supabase Postgres (durable, per-user rows). No disk.
        # mem0's history log is SQLite-only: keep it in RAM (loses only the per-memory edit audit trail).
        config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "collection_name": PG_COLLECTION,
                    "embedding_model_dims": EMBEDDING_DIMS,
                    "hnsw": True,
                    "connection_pool": _pg_pool(),
                },
            },
            "history_db_path": ":memory:",
            "llm": llm_provider,
        }
    else:
        if os.environ.get("BREWSIGNAL_MEMORY_DIR"):
            data_dir = Path(os.environ["BREWSIGNAL_MEMORY_DIR"])
        else:
            data_dir = Path(__file__).parent.parent.parent / "data" / "memory"
        data_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": str(data_dir / "qdrant"),
                    "embedding_model_dims": EMBEDDING_DIMS,
                    "on_disk": True,
                }
            },
            "history_db_path": str(data_dir / "history.db"),
            "llm": llm_provider,
        }

    config["embedder"] = embedder

    return config


def get_memory(llm_config: Optional[LLMConfig] = None):
    """Get or create the Mem0 memory instance.

    Args:
        llm_config: LLM configuration from database. Required on first call.

    Returns:
        Memory instance or None if not configured.
    """
    global _memory_instance, _memory_config_hash

    # Calculate config hash to detect changes
    if llm_config:
        # not the main model: changing it must not rebuild mem0 (local qdrant allows one client)
        new_hash = f"{llm_config._provider_str()}:{llm_config.enabled}"
    else:
        new_hash = None

    # Return cached instance if config hasn't changed
    if _memory_instance is not None and new_hash == _memory_config_hash:
        return _memory_instance

    # Need llm_config to initialize
    if llm_config is None:
        if _memory_instance is not None:
            return _memory_instance
        logger.debug("Memory not initialized and no LLM config provided")
        return None

    try:
        from mem0 import Memory

        config = get_memory_config(llm_config)
        if config is None:
            return None

        try:
            _memory_instance = Memory.from_config(config)
        except Exception:
            pool = config["vector_store"]["config"].get("connection_pool")
            if pool is not None:
                pool.close()  # do not leak a pool when init fails
            raise
        _memory_config_hash = new_hash
        logger.info(
            "Assistant memory enabled: embedder=%s, extraction model=%s",
            config["embedder"]["config"]["model"],
            config["llm"]["config"]["model"],
        )
        return _memory_instance
    except Exception as e:
        logger.warning(f"Assistant memory disabled: failed to initialize Mem0: {e}")
        return None


def _results(res) -> list[dict]:
    return res.get("results", []) if isinstance(res, dict) else (res or [])


async def search_memories_strict(
    query: str,
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
    limit: int = 5,
) -> Optional[list[dict]]:
    """Semantic search. Returns None when mem0 is unavailable or errors (so callers can
    fall back); an empty list means mem0 ran and found nothing."""
    memory = get_memory(llm_config)
    if not memory:
        return None
    try:
        async with _mem_lock:
            res = await asyncio.to_thread(memory.search, query, filters={"user_id": user_id}, top_k=limit)
        return _results(res)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return None


async def search_memories(
    query: str,
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
    limit: int = 5,
) -> list[dict]:
    """Search for relevant memories for a user. Empty list when mem0 is unavailable."""
    return await search_memories_strict(query, user_id, llm_config, limit) or []


_WORD = re.compile(r"[a-z0-9]{3,}")


async def keyword_search_learnings(db: AsyncSession, query: str, user_id: Optional[str], limit: int = 5) -> list[dict]:
    """Fallback recall: rank this owner's brewing_learnings by shared words with the query."""
    from backend.models import BrewingLearning

    words = set(_WORD.findall(query.lower()))
    if not words:
        return []
    rows = (await db.execute(select(BrewingLearning).where(BrewingLearning.user_id == user_id))).scalars().all()
    scored = []
    for r in rows:
        hits = len(words & set(_WORD.findall(r.learning.lower())))
        if hits:
            scored.append((hits, r.created_at, r))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [{"memory": r.learning, "score": hits / len(words), "source": "keyword"} for hits, _, r in scored[:limit]]


async def add_memory(
    messages: list[dict],
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
    metadata: Optional[dict] = None,
    infer: bool = True,
) -> dict:
    """Store memories from messages. infer=True runs LLM fact extraction; infer=False stores verbatim.

    Returns a dict with 'results' (each with 'id'); empty on failure.
    """
    memory = get_memory(llm_config)
    if not memory:
        return {"results": []}

    try:
        async with _mem_lock:
            result = await asyncio.to_thread(
                memory.add, messages, user_id=user_id, metadata=metadata, infer=infer
            )
        return result or {"results": []}
    except Exception as e:
        logger.warning(f"Memory add failed: {e}")
        return {"results": []}


async def get_all_memories(
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> list[dict]:
    """Get all memories for a user."""
    memory = get_memory(llm_config)
    if not memory:
        return []

    try:
        async with _mem_lock:
            res = await asyncio.to_thread(memory.get_all, filters={"user_id": user_id}, top_k=1000)
        return _results(res)
    except Exception as e:
        logger.warning(f"Get all memories failed: {e}")
        return []


async def backfill_learnings(db: AsyncSession, llm_config: LLMConfig) -> int:
    """Add brewing_learnings rows that have no mem0_memory_id into mem0 and store the ids.

    Idempotent: rows with an id are skipped, a failed row stays unset and is retried next
    start. Verbatim (infer=False): one embedding call per row, no LLM. Returns rows added.
    """
    from backend.models import BrewingLearning

    if get_memory(llm_config) is None:
        return 0
    rows = (await db.execute(
        select(BrewingLearning).where(BrewingLearning.mem0_memory_id.is_(None)).order_by(BrewingLearning.id)
    )).scalars().all()
    added = 0
    for row in rows:
        res = await add_memory(
            [{"role": "user", "content": f"[{row.category}] {row.learning}"}],
            user_id=row.user_id or "local",
            llm_config=llm_config,
            metadata={"category": row.category, "learning_id": row.id},
            infer=False,
        )
        items = res.get("results") or []
        if items and isinstance(items[0], dict) and items[0].get("id"):
            row.mem0_memory_id = items[0]["id"]
            await db.commit()
            added += 1
    return added


async def backfill_learnings_background() -> None:
    """Startup task: backfill with its own session; never raises, skips if memory is off."""
    from backend.database import async_session_factory
    from backend.routers.assistant import get_llm_config

    try:
        async with async_session_factory() as db:
            llm_config = await get_llm_config(db)
            if not llm_config.is_configured():
                logger.info("Assistant memory off: LLM not configured")
                return
            if await asyncio.to_thread(get_memory, llm_config) is None:  # init off the loop; logs on/off once
                return
            n = await backfill_learnings(db, llm_config)
            if n:
                logger.info("Backfilled %d brewing learnings into assistant memory", n)
    except Exception as e:
        logger.warning("Memory backfill failed: %s", e)


class MemoryUnavailable(Exception):
    """The vector store could not be reached or errored; the delete may not have happened."""


def _store_or_raise(llm_config: Optional[LLMConfig]):
    """The mem0 instance, None when memory is off by configuration, MemoryUnavailable when it
    should be on but failed to start."""
    memory = get_memory(llm_config)
    if memory is None and _memory_instance is None and llm_config is not None and llm_config.is_configured():
        raise MemoryUnavailable("memory store is not available")
    return memory


async def delete_memory(
    memory_id: str,
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> bool:
    """Delete one memory, only if it belongs to user_id (mem0 itself deletes by bare id).

    Returns True if deleted; False if absent, not the user's, or memory is off.
    Raises MemoryUnavailable if the vector store failed (caller must not report success).
    """
    memory = _store_or_raise(llm_config)
    if not memory:
        return False
    try:
        async with _mem_lock:
            found = await asyncio.to_thread(memory.get, memory_id)
            if not found or found.get("user_id") != user_id:
                return False
            await asyncio.to_thread(memory.delete, memory_id)
        return True
    except Exception as e:
        logger.warning(f"Memory delete failed: {e}")
        raise MemoryUnavailable(str(e)) from e


async def delete_all_memories(
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> bool:
    """Delete all of a user's memories. Raises MemoryUnavailable if the store failed;
    returns False only when memory is off (nothing to delete)."""
    memory = _store_or_raise(llm_config)
    if not memory:
        return False
    try:
        async with _mem_lock:
            await asyncio.to_thread(memory.delete_all, user_id=user_id)
        return True
    except Exception as e:
        logger.warning(f"Delete all memories failed: {e}")
        raise MemoryUnavailable(str(e)) from e


def format_memories_for_context(memories: list[dict]) -> str:
    """Format memories for injection into system prompt.

    Args:
        memories: List of memory dicts from search

    Returns:
        Formatted string for context injection
    """
    if not memories:
        return ""

    lines = ["## Remembered about this user:"]
    for mem in memories:
        # Handle both 'memory' key and direct string
        content = mem.get("memory") if isinstance(mem, dict) else str(mem)
        if content:
            lines.append(f"- {content}")

    return "\n".join(lines)
