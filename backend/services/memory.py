"""
Mem0 Memory Service for BrewSignal Assistant.

Provides semantic long-term memory for the AI assistant, allowing it to
remember user preferences, brewing habits, and past learnings across sessions.

Deployment modes:
- LOCAL: Embedded Qdrant + SQLite (zero external dependencies)
- CLOUD: Same for now, can be extended to use hosted Qdrant or pgvector

LLM Configuration:
- Uses the same LLM config as the assistant (from database)
- Supports OpenRouter, Anthropic, OpenAI, Groq, etc. via LiteLLM
- Memory features disabled if no LLM is configured
"""

import logging
import os
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.services.llm.config import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

# Lazy-loaded memory instance
_memory_instance = None
_memory_config_hash = None


def _get_llm_provider_config(llm_config: LLMConfig) -> Optional[dict]:
    """Convert LLMConfig to Mem0's LLM provider config.

    Mem0 supports: openai, anthropic, groq, ollama, litellm
    We'll use litellm for maximum compatibility with our existing setup.
    """
    if not llm_config.is_configured():
        return None

    provider = llm_config._provider_str()
    api_key = None
    if llm_config.api_key:
        api_key = llm_config.api_key.get_secret_value()

    # Use LiteLLM backend for all providers (same as assistant)
    # This gives us OpenRouter, Anthropic, OpenAI, etc. support
    return {
        "provider": "litellm",
        "config": {
            "model": llm_config.effective_model,
            "api_key": api_key,
            "temperature": 0.1,  # Low temp for factual memory extraction
            "max_tokens": 500,   # Memories should be concise
        }
    }


def _get_embedder_config(llm_config: LLMConfig) -> Optional[dict]:
    """Get embedder config. Uses OpenAI embeddings if available, else tries alternatives."""
    # Check for OpenAI API key (best embeddings)
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": openai_key,
            }
        }

    # For OpenRouter, use their embeddings endpoint (OpenAI-compatible)
    provider = llm_config._provider_str()
    if provider == "openrouter" and llm_config.api_key:
        return {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",  # OpenRouter routes to OpenAI
                "api_key": llm_config.api_key.get_secret_value(),
                "openai_base_url": "https://openrouter.ai/api/v1",
            }
        }

    # For Anthropic or other providers without embeddings, try to use OpenAI if available
    if provider == "anthropic":
        logger.warning(
            "Anthropic doesn't provide embeddings. Set OPENAI_API_KEY for memory search. "
            "Memory features disabled without embeddings."
        )
        return None

    # No embedder available - memory features won't work
    logger.warning(
        f"No embedding API available for provider '{provider}'. "
        "Set OPENAI_API_KEY or use OpenRouter for memory features."
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

    # Determine data directory
    if settings.is_local:
        data_dir = Path(__file__).parent.parent.parent / "data" / "memory"
    else:
        data_dir = Path("/tmp/brewsignal-memory")
    data_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": str(data_dir / "qdrant"),
                "on_disk": True,
            }
        },
        "history_db_path": str(data_dir / "history.db"),
        "llm": llm_provider,
    }

    # Add embedder if available
    embedder = _get_embedder_config(llm_config)
    if embedder:
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
        new_hash = f"{llm_config._provider_str()}:{llm_config.model}:{llm_config.enabled}"
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

        _memory_instance = Memory.from_config(config)
        _memory_config_hash = new_hash
        logger.info(f"Mem0 memory initialized (provider={llm_config._provider_str()})")
        return _memory_instance
    except Exception as e:
        logger.warning(f"Failed to initialize Mem0: {e}. Memory features disabled.")
        return None


async def search_memories(
    query: str,
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
    limit: int = 5,
) -> list[dict]:
    """Search for relevant memories for a user.

    Args:
        query: The search query (typically the user's message)
        user_id: The user's ID for isolation
        llm_config: LLM configuration (optional, uses cached if available)
        limit: Maximum number of memories to return

    Returns:
        List of memory dicts with 'memory' and 'score' keys
    """
    memory = get_memory(llm_config)
    if not memory:
        return []

    try:
        results = memory.search(query, user_id=user_id, limit=limit)
        # Handle both dict and list return types from mem0
        if isinstance(results, dict):
            return results.get("results", [])
        return results or []
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return []


async def add_memory(
    messages: list[dict],
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Extract and store memories from a conversation.

    Args:
        messages: List of message dicts with 'role' and 'content'
        user_id: The user's ID for isolation
        llm_config: LLM configuration (optional, uses cached if available)
        metadata: Optional metadata to attach to memories

    Returns:
        Dict with 'results' containing extracted memories
    """
    memory = get_memory(llm_config)
    if not memory:
        return {"results": []}

    try:
        result = memory.add(messages, user_id=user_id, metadata=metadata)
        return result or {"results": []}
    except Exception as e:
        logger.warning(f"Memory add failed: {e}")
        return {"results": []}


async def get_all_memories(
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> list[dict]:
    """Get all memories for a user.

    Args:
        user_id: The user's ID
        llm_config: LLM configuration (optional, uses cached if available)

    Returns:
        List of all memory dicts for this user
    """
    memory = get_memory(llm_config)
    if not memory:
        return []

    try:
        results = memory.get_all(user_id=user_id)
        # Handle both dict and list return types
        if isinstance(results, dict):
            return results.get("results", [])
        return results or []
    except Exception as e:
        logger.warning(f"Get all memories failed: {e}")
        return []


async def delete_memory(
    memory_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> bool:
    """Delete a specific memory.

    Args:
        memory_id: The ID of the memory to delete
        llm_config: LLM configuration (optional, uses cached if available)

    Returns:
        True if deleted successfully
    """
    memory = get_memory(llm_config)
    if not memory:
        return False

    try:
        memory.delete(memory_id)
        return True
    except Exception as e:
        logger.warning(f"Memory delete failed: {e}")
        return False


async def delete_all_memories(
    user_id: str,
    llm_config: Optional[LLMConfig] = None,
) -> bool:
    """Delete all memories for a user.

    Args:
        user_id: The user's ID
        llm_config: LLM configuration (optional, uses cached if available)

    Returns:
        True if deleted successfully
    """
    memory = get_memory(llm_config)
    if not memory:
        return False

    try:
        memory.delete_all(user_id=user_id)
        return True
    except Exception as e:
        logger.warning(f"Delete all memories failed: {e}")
        return False


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
