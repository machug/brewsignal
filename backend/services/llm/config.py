"""Configuration for LLM service."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, SecretStr, field_validator


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    LOCAL = "local"  # Ollama
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    HUGGINGFACE = "huggingface"


# Default models per provider
DEFAULT_MODELS = {
    LLMProvider.LOCAL: "phi3:mini",
    LLMProvider.OPENAI: "gpt-4o-mini",
    LLMProvider.ANTHROPIC: "claude-3-5-haiku-latest",
    LLMProvider.GOOGLE: "gemini-1.5-flash",
    LLMProvider.GROQ: "llama-3.1-8b-instant",
    LLMProvider.DEEPSEEK: "deepseek-chat",
    LLMProvider.HUGGINGFACE: "meta-llama/Llama-3.1-8B-Instruct",
}

# Model prefixes for LiteLLM
MODEL_PREFIXES = {
    LLMProvider.LOCAL: "ollama/",
    LLMProvider.OPENAI: "",  # No prefix needed
    LLMProvider.ANTHROPIC: "",  # No prefix needed
    LLMProvider.GOOGLE: "gemini/",
    LLMProvider.GROQ: "groq/",
    LLMProvider.DEEPSEEK: "deepseek/",
    LLMProvider.HUGGINGFACE: "huggingface/",
}


class LLMConfig(BaseModel):
    """Configuration for LLM service."""

    enabled: bool = False
    provider: LLMProvider = LLMProvider.LOCAL
    model: Optional[str] = None  # If None, uses default for provider
    api_key: Optional[SecretStr] = None
    base_url: Optional[str] = None  # For Ollama: http://localhost:11434
    temperature: float = 0.7
    max_tokens: int = 2000

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Temperature must be between 0 and 2."""
        if not 0 <= v <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Max tokens must be positive."""
        if v <= 0:
            raise ValueError("Max tokens must be positive")
        return min(v, 8000)  # Cap at 8000

    @property
    def effective_model(self) -> str:
        """Get the model name with appropriate prefix for LiteLLM."""
        base_model = self.model or DEFAULT_MODELS.get(self.provider, "phi3:mini")
        prefix = MODEL_PREFIXES.get(self.provider, "")

        # Don't double-prefix
        if base_model.startswith(prefix):
            return base_model
        return f"{prefix}{base_model}"

    @property
    def requires_api_key(self) -> bool:
        """Check if this provider requires an API key."""
        return self.provider != LLMProvider.LOCAL

    def is_configured(self) -> bool:
        """Check if the LLM is properly configured."""
        if not self.enabled:
            return False
        if self.requires_api_key and not self.api_key:
            return False
        return True

    class Config:
        use_enum_values = True
