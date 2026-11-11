"""Tests for memory service embedder + provider-env wiring (tilt_ui-ejz).

OpenRouter exposes /api/v1/embeddings — the previous code's failure was a
missing provider prefix on the embedding model id ("text-embedding-3-small"
vs the required "openai/text-embedding-3-small"). mem0's chat side
now uses its OpenAI-compatible provider (no LiteLLM). This module pins both.
"""

from backend.services.llm.config import LLMConfig, LLMProvider
from backend.services.memory import _get_embedder_config, get_memory_config


def _cfg(provider: LLMProvider, api_key: str = "sk-test") -> LLMConfig:
    return LLMConfig(
        enabled=True,
        provider=provider,
        api_key=api_key,
        model="anthropic/claude-sonnet-4",
    )


class TestEmbedderConfig:
    def test_openai_key_in_env_uses_openai_embeddings(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        cfg = _cfg(LLMProvider.OPENROUTER)
        result = _get_embedder_config(cfg)
        assert result is not None
        assert result["provider"] == "openai"
        assert result["config"]["openai_base_url"] == "https://api.openai.com/v1"
        assert result["config"]["api_key"] == "sk-openai-test"

    def test_openrouter_uses_prefixed_embedding_model(self, monkeypatch):
        """OpenRouter requires the provider prefix on the model id; the
        bare 'text-embedding-3-small' is what caused the 401."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-test")
        result = _get_embedder_config(cfg)
        assert result is not None
        assert result["config"]["model"] == "openai/text-embedding-3-small"
        assert result["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
        assert result["config"]["api_key"] == "sk-or-test"

    def test_anthropic_without_openai_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.ANTHROPIC)
        assert _get_embedder_config(cfg) is None

    def test_get_memory_config_returns_full_config_for_openrouter(
        self, monkeypatch
    ):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-test")
        result = get_memory_config(cfg)
        assert result is not None
        assert "embedder" in result
        assert result["embedder"]["config"]["model"] == "openai/text-embedding-3-small"

    def test_get_memory_config_none_when_no_embedder(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.ANTHROPIC)
        assert get_memory_config(cfg) is None
