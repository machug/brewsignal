"""Pydantic AI models for the configured LLM provider (shared by chat, LLMService and memory)."""

import os
from typing import Optional

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from backend.services.llm.config import DEFAULT_BASE_URLS, DEFAULT_MODELS, ENV_VAR_NAMES, LLMConfig, LLMProvider

# Providers reachable with the openai SDK (already installed with the openrouter extra)
OPENAI_COMPATIBLE_URLS: dict[str, Optional[str]] = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "huggingface": "https://router.huggingface.co/v1",
}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class UnsupportedProvider(Exception):
    pass


def _ollama_v1(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def _ollama_model(name: str, base_url: str) -> Model:
    return OpenAIChatModel(name, provider=OllamaProvider(base_url=_ollama_v1(base_url)))


def model_name(config: LLMConfig) -> str:
    """Bare model id (no routing prefix) for the configured provider."""
    return config.model or DEFAULT_MODELS[LLMProvider(config._provider_str())]


def api_key_for(config: LLMConfig) -> Optional[str]:
    if config.api_key:
        return config.api_key.get_secret_value()
    return os.environ.get(ENV_VAR_NAMES.get(config._provider_str(), ""))


def openai_base_url(config: LLMConfig) -> Optional[str]:
    """OpenAI-compatible base URL for the provider, or None when it is plain OpenAI.

    Raises UnsupportedProvider for providers with no OpenAI-compatible endpoint.
    """
    provider = config._provider_str()
    if provider == "openrouter":
        return OPENROUTER_BASE_URL
    if provider in ("local", "hailo"):
        return _ollama_v1(config.base_url or DEFAULT_BASE_URLS[LLMProvider(provider)])
    if provider in OPENAI_COMPATIBLE_URLS:
        return OPENAI_COMPATIBLE_URLS[provider]
    raise UnsupportedProvider(provider)


def build_model(config: LLMConfig, model_name: Optional[str] = None) -> Model:
    """Pydantic AI model for the configured provider."""
    provider = config._provider_str()
    name = model_name or config.model or DEFAULT_MODELS[LLMProvider(provider)]
    key = api_key_for(config)
    if provider == "openrouter":
        return OpenRouterModel(name, provider=OpenRouterProvider(api_key=key))
    if provider in ("local", "hailo"):
        return _ollama_model(name, config.base_url or DEFAULT_BASE_URLS[LLMProvider(provider)])
    if provider in OPENAI_COMPATIBLE_URLS:
        return OpenAIChatModel(name, provider=OpenAIProvider(base_url=OPENAI_COMPATIBLE_URLS[provider], api_key=key))
    raise UnsupportedProvider(provider)


def model_settings(config: LLMConfig) -> ModelSettings:
    if config._provider_str() == "openrouter":
        # Reasoning models can spend the whole max_tokens budget thinking after
        # tool results and emit no text: cap reasoning at half (tilt_ui-atvb)
        return OpenRouterModelSettings(
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            openrouter_reasoning={"max_tokens": config.max_tokens // 2},
        )
    return ModelSettings(max_tokens=config.max_tokens, temperature=config.temperature)
