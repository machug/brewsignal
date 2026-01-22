"""LLM service using LiteLLM for unified API access."""

import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from backend.services.llm.config import DEFAULT_BASE_URLS, LLMConfig, LLMProvider

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


class LLMNotAvailableError(LLMServiceError):
    """Raised when LLM dependencies are not installed."""

    pass


class LLMService:
    """Service for interacting with LLMs via LiteLLM."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._litellm = None

    def _get_litellm(self):
        """Lazy import of litellm to handle missing dependency gracefully."""
        if self._litellm is None:
            try:
                import litellm

                # Suppress litellm's verbose logging
                litellm.suppress_debug_info = True
                self._litellm = litellm
            except ImportError:
                raise LLMNotAvailableError(
                    "LiteLLM is not installed. Install with: pip install 'brewsignal[ai]'"
                )
        return self._litellm

    def _get_api_key(self) -> Optional[str]:
        """Get the API key as a string."""
        if self.config.api_key:
            return self.config.api_key.get_secret_value()
        return None

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

        litellm = self._get_litellm()

        # Build kwargs
        kwargs = {
            "model": self.config.effective_model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        # Only pass explicit API key if configured in UI (not from env)
        # LiteLLM automatically reads env vars like ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
        api_key = self._get_api_key()
        if api_key:
            kwargs["api_key"] = api_key

        # Add base URL for local providers (Ollama and Hailo)
        provider_str = self.config._provider_str()
        if provider_str in ("local", "hailo"):
            default_url = DEFAULT_BASE_URLS.get(
                LLMProvider(provider_str), "http://localhost:11434"
            )
            kwargs["api_base"] = self.config.base_url or default_url

        try:
            logger.info(f"Sending chat request to {self.config.effective_model}")
            response = await litellm.acompletion(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
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

        litellm = self._get_litellm()

        # Build kwargs
        kwargs = {
            "model": self.config.effective_model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": True,
        }

        # Only pass explicit API key if configured in UI (not from env)
        api_key = self._get_api_key()
        if api_key:
            kwargs["api_key"] = api_key

        # Add base URL for local providers (Ollama and Hailo)
        provider_str = self.config._provider_str()
        if provider_str in ("local", "hailo"):
            default_url = DEFAULT_BASE_URLS.get(
                LLMProvider(provider_str), "http://localhost:11434"
            )
            kwargs["api_base"] = self.config.base_url or default_url

        try:
            logger.info(f"Starting streaming chat to {self.config.effective_model}")
            response = await litellm.acompletion(**kwargs)

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
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
        except LLMNotAvailableError as e:
            return {"success": False, "error": str(e)}
        except LLMServiceError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_status(self) -> dict:
        """Get the current LLM service status."""
        # Check if litellm is available
        litellm_available = True
        try:
            self._get_litellm()
        except LLMNotAvailableError:
            litellm_available = False

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
            "litellm_available": litellm_available,
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
