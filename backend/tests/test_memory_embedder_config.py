"""Tests for memory service embedder + provider-env wiring (tilt_ui-ejz).

OpenRouter exposes /api/v1/embeddings — the previous code's failure was a
missing provider prefix on the embedding model id ("text-embedding-3-small"
vs the required "openai/text-embedding-3-small"). Separately, mem0's
LiteLLM wrapper drops api_key when calling litellm.completion(), so the
chat / memory-extraction call also needed the OPENROUTER_API_KEY env var
set. This module pins both behaviours.
"""

import os

import pytest

from backend.services.llm.config import LLMConfig, LLMProvider
from backend.services.memory import (
    _APP_SEEDED_PROVIDER_ENV,
    _PROVIDER_ENV_VARS,
    _get_embedder_config,
    _seed_provider_env,
    get_memory_config,
)


@pytest.fixture(autouse=True)
def _reset_seeded_tracking():
    """Each test starts with a clean app-seeded set so module state doesn't
    leak between tests."""
    _APP_SEEDED_PROVIDER_ENV.clear()
    yield
    _APP_SEEDED_PROVIDER_ENV.clear()


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
        assert "openai_base_url" not in result["config"]
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


class TestProviderEnvSeed:
    """_seed_provider_env exports the chat key into the env var LiteLLM
    expects, because mem0's LiteLLM wrapper drops the api_key from config."""

    def test_seeds_openrouter_api_key_when_unset(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-real")
        _seed_provider_env(cfg)
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-real"

    def test_does_not_overwrite_existing_env_var(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "operator-managed")
        cfg = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-different")
        _seed_provider_env(cfg)
        assert os.environ["OPENROUTER_API_KEY"] == "operator-managed"

    def test_seeds_anthropic_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = _cfg(LLMProvider.ANTHROPIC, api_key="sk-ant-real")
        _seed_provider_env(cfg)
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-real"

    def test_rotates_app_seeded_value_on_config_change(self, monkeypatch):
        """If we seeded the env var earlier, rotating the key in AI
        Assistant settings must update the env var on the next call.
        Otherwise memory keeps trying to auth with a revoked key."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg1 = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-old")
        _seed_provider_env(cfg1)
        assert os.environ["OPENROUTER_API_KEY"] == "sk-or-old"

        cfg2 = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-rotated")
        _seed_provider_env(cfg2)
        assert os.environ["OPENROUTER_API_KEY"] == "sk-or-rotated"

    def test_operator_set_var_not_overwritten_even_on_subsequent_calls(
        self, monkeypatch
    ):
        monkeypatch.setenv("OPENROUTER_API_KEY", "operator-managed")
        cfg1 = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-from-ui-1")
        _seed_provider_env(cfg1)
        cfg2 = _cfg(LLMProvider.OPENROUTER, api_key="sk-or-from-ui-2")
        _seed_provider_env(cfg2)
        assert os.environ["OPENROUTER_API_KEY"] == "operator-managed"

    def test_known_providers_covered(self):
        # Guards against silent drift if a new LLMProvider value is added.
        for provider in ("openrouter", "openai", "anthropic"):
            assert provider in _PROVIDER_ENV_VARS, (
                f"_PROVIDER_ENV_VARS missing entry for '{provider}' — "
                "memory's LiteLLM chat call would 401 for this provider."
            )
