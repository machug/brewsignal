"""LLM service on Pydantic AI (direct model requests; model built by services/llm/model.py)."""

import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from pydantic_ai.direct import model_request, model_request_stream
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    SystemPromptPart,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters

from backend.services.llm.config import DEFAULT_BASE_URLS, LLMConfig, LLMProvider
from backend.services.llm.model import build_model, model_settings

logger = logging.getLogger(__name__)


def load_dotenv_if_available():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        # Look for .env in project root (parent of backend/)
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded environment from {env_path}")
            return True
    except ImportError:
        pass
    return False


# Try to load .env on module import
load_dotenv_if_available()

# Global service instance
_llm_service: Optional["LLMService"] = None


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""

    pass


class LLMNotConfiguredError(LLMServiceError):
    """Raised when LLM is not configured or disabled."""

    pass


class LLMService:
    """Service for interacting with LLMs via Pydantic AI."""

    def __init__(self, config: LLMConfig):
        self.config = config

    def _request_args(self, messages: list[dict], temperature: Optional[float], max_tokens: Optional[int]):
        """(model, pydantic-ai messages, settings) for one request; per-call overrides beat config."""
        config = self.config.model_copy(
            update={
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or self.config.max_tokens,
            }
        )
        history: list[ModelMessage] = []
        parts: list = []
        for m in messages:
            role, content = m.get("role", "user"), m.get("content", "")
            if role == "assistant":
                if parts:
                    history.append(ModelRequest(parts=parts))
                    parts = []
                history.append(ModelResponse(parts=[TextPart(content=content)]))
            else:
                parts.append(SystemPromptPart(content=content) if role == "system" else UserPromptPart(content=content))
        if parts:
            history.append(ModelRequest(parts=parts))
        return build_model(config), history, model_settings(config)

    def _strip_ollama_prefix(self, model: str) -> str:
        """Remove ollama/ prefix for direct Ollama-compatible APIs."""
        if model.startswith("ollama/"):
            return model[len("ollama/"):]
        return model

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        """Convert chat messages into a simple prompt for generate endpoints."""
        lines = []
        for msg in messages:
            role = msg.get("role", "user").strip().lower()
            content = msg.get("content", "")
            if role == "system":
                lines.append(f"System: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            else:
                lines.append(f"User: {content}")
        lines.append("Assistant:")
        return "\n".join(lines)

    async def _hailo_generate_fallback(
        self,
        messages: list[dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> str:
        """Fallback to /api/generate for hailo-ollama when chat fails."""
        import httpx

        base_url = self.config.base_url or DEFAULT_BASE_URLS.get(
            LLMProvider.HAILO, "http://localhost:8000"
        )
        model = self._strip_ollama_prefix(self.config.effective_model)
        payload = {
            "model": model,
            "prompt": self._messages_to_prompt(messages),
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "response" in data:
                return data["response"]
            # Fallback if server returns chat-style payload
            if "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", "")
            raise LLMServiceError("Unexpected hailo-ollama response format")

    async def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Override config temperature
            max_tokens: Override config max_tokens

        Returns:
            The assistant's response text

        Raises:
            LLMNotConfiguredError: If LLM is not configured
            LLMServiceError: If the API call fails
        """
        if not self.config.is_configured():
            raise LLMNotConfiguredError("LLM is not configured or disabled")

        try:
            logger.info(f"Sending chat request to {self.config.effective_model}")
            model, history, settings = self._request_args(messages, temperature, max_tokens)
            response = await model_request(
                model, history, model_settings=settings, model_request_parameters=ModelRequestParameters()
            )
            return response.text
        except Exception as e:
            provider_str = self.config._provider_str()
            if provider_str == "hailo":
                try:
                    logger.warning("Hailo chat failed, falling back to /api/generate")
                    return await self._hailo_generate_fallback(
                        messages=messages,
                        temperature=temperature or self.config.temperature,
                        max_tokens=max_tokens or self.config.max_tokens,
                    )
                except Exception as fallback_error:
                    logger.error(
                        "Hailo fallback error: %s; original error: %s",
                        fallback_error,
                        e,
                    )
                    raise LLMServiceError(
                        f"LLM API error: {str(e)}; hailo fallback failed: {fallback_error}"
                    ) from fallback_error
            logger.error(f"LLM API error: {e}")
            raise LLMServiceError(f"LLM API error: {str(e)}") from e

    async def stream_chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Override config temperature
            max_tokens: Override config max_tokens

        Yields:
            Text chunks as they arrive from the LLM

        Raises:
            LLMNotConfiguredError: If LLM is not configured
            LLMServiceError: If the API call fails
        """
        if not self.config.is_configured():
            raise LLMNotConfiguredError("LLM is not configured or disabled")

        try:
            logger.info(f"Starting streaming chat to {self.config.effective_model}")
            model, history, settings = self._request_args(messages, temperature, max_tokens)
            async with model_request_stream(
                model, history, model_settings=settings, model_request_parameters=ModelRequestParameters()
            ) as stream:
                async for event in stream:
                    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart) and event.part.content:
                        yield event.part.content
                    elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                        yield event.delta.content_delta

        except Exception as e:
            provider_str = self.config._provider_str()
            if provider_str == "hailo":
                try:
                    logger.warning("Hailo streaming failed, falling back to /api/generate")
                    text = await self._hailo_generate_fallback(
                        messages=messages,
                        temperature=temperature or self.config.temperature,
                        max_tokens=max_tokens or self.config.max_tokens,
                    )
                    if text:
                        yield text
                    return
                except Exception as fallback_error:
                    logger.error(
                        "Hailo streaming fallback error: %s; original error: %s",
                        fallback_error,
                        e,
                    )
                    raise LLMServiceError(
                        f"LLM streaming error: {str(e)}; hailo fallback failed: {fallback_error}"
                    ) from fallback_error
            logger.error(f"LLM streaming error: {e}")
            raise LLMServiceError(f"LLM streaming error: {str(e)}") from e

    async def test_connection(self) -> dict:
        """
        Test the LLM connection.

        Returns:
            Dict with 'success', 'model', and optional 'error' keys
        """
        if not self.config.enabled:
            return {"success": False, "error": "LLM is disabled"}

        if self.config.requires_api_key and not self.config.api_key:
            return {"success": False, "error": "API key is required but not set"}

        try:
            # Simple test message
            response = await self.chat(
                messages=[{"role": "user", "content": "Say 'Hello from BrewSignal!'"}],
                max_tokens=50,
            )
            return {
                "success": True,
                "model": self.config.effective_model,
                "response": response,
            }
        except LLMServiceError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_status(self) -> dict:
        """Get the current LLM service status."""
        # Handle provider as either enum or string
        provider = self.config.provider
        if hasattr(provider, "value"):
            provider_str = provider.value
        else:
            provider_str = str(provider) if provider else None

        return {
            "enabled": self.config.enabled,
            "configured": self.config.is_configured(),
            "provider": provider_str,
            "model": self.config.effective_model if self.config.enabled else None,
            "requires_api_key": self.config.requires_api_key,
            "has_api_key": self.config.has_any_api_key,
            "has_env_api_key": self.config.has_env_api_key,
            "litellm_available": True,  # kept for API shape; LiteLLM is no longer used
        }


def get_llm_service() -> Optional[LLMService]:
    """Get the global LLM service instance."""
    return _llm_service


def init_llm_service(config: LLMConfig) -> LLMService:
    """Initialize the global LLM service."""
    global _llm_service
    _llm_service = LLMService(config)
    logger.info(f"LLM service initialized: provider={config.provider}, enabled={config.enabled}")
    return _llm_service
