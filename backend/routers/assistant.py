"""AI Brewing Assistant API endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Config
from backend.services.llm import LLMConfig, LLMProvider, LLMService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str  # "user", "assistant", or "system"
    content: str


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    content: str
    model: str


class StatusResponse(BaseModel):
    """LLM service status."""

    enabled: bool
    configured: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    requires_api_key: bool
    has_api_key: bool
    has_env_api_key: bool = False
    litellm_available: bool


class TestResponse(BaseModel):
    """Response from test connection endpoint."""

    success: bool
    model: Optional[str] = None
    response: Optional[str] = None
    error: Optional[str] = None


class ModelsResponse(BaseModel):
    """Available models for a provider."""

    provider: str
    models: list[dict]


async def get_llm_config(db: AsyncSession) -> LLMConfig:
    """Load LLM configuration from database."""
    result = await db.execute(select(Config))
    config_rows = {row.key: row.value for row in result.scalars().all()}

    def get_value(key: str, default=None):
        val = config_rows.get(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    provider_str = get_value("ai_provider", "local")
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        provider = LLMProvider.LOCAL

    return LLMConfig(
        enabled=get_value("ai_enabled", False),
        provider=provider,
        model=get_value("ai_model") or None,
        api_key=get_value("ai_api_key") or None,
        base_url=get_value("ai_base_url") or None,
        temperature=get_value("ai_temperature", 0.7),
        max_tokens=get_value("ai_max_tokens", 2000),
    )


async def get_llm_service(db: AsyncSession = Depends(get_db)) -> LLMService:
    """Dependency to get configured LLM service."""
    config = await get_llm_config(db)
    return LLMService(config)


@router.get("/status", response_model=StatusResponse)
async def get_status(service: LLMService = Depends(get_llm_service)) -> StatusResponse:
    """Get the current AI assistant status."""
    status = service.get_status()
    return StatusResponse(**status)


@router.post("/test", response_model=TestResponse)
async def test_connection(service: LLMService = Depends(get_llm_service)) -> TestResponse:
    """Test the LLM connection."""
    result = await service.test_connection()
    return TestResponse(**result)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: LLMService = Depends(get_llm_service),
) -> ChatResponse:
    """Send a chat message to the AI assistant."""
    if not service.config.is_configured():
        raise HTTPException(
            status_code=400,
            detail="AI assistant is not configured. Enable it in Settings.",
        )

    try:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        response = await service.chat(
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return ChatResponse(content=response, model=service.config.effective_model)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{provider}", response_model=ModelsResponse)
async def get_models(provider: str) -> ModelsResponse:
    """Get available models for a provider."""
    # Define popular models per provider
    models_by_provider = {
        "local": [
            {"id": "phi3:mini", "name": "Phi-3 Mini (3.8B)", "description": "Fast, good for RPi"},
            {"id": "llama3:8b", "name": "Llama 3 8B", "description": "Good quality, balanced"},
            {"id": "mistral:7b", "name": "Mistral 7B", "description": "Strong reasoning"},
            {"id": "gemma2:2b", "name": "Gemma 2 2B", "description": "Very fast, compact"},
        ],
        "openai": [
            {"id": "gpt-4o", "name": "GPT-4o", "description": "Most capable, multimodal"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast and affordable"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "Previous flagship"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "description": "Budget option"},
        ],
        "anthropic": [
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "description": "Best balance, smart agents & coding"},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "description": "Fastest, near-frontier intelligence"},
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "description": "Most capable, premium"},
            {"id": "claude-sonnet-4-0", "name": "Claude Sonnet 4", "description": "Previous gen, still excellent"},
        ],
        "google": [
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "description": "Most capable"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "description": "Fast and efficient"},
            {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash", "description": "Latest experimental"},
        ],
        "groq": [
            {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "description": "Most capable"},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B", "description": "Very fast"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "description": "Good reasoning"},
        ],
        "deepseek": [
            {"id": "deepseek-chat", "name": "DeepSeek Chat", "description": "General purpose"},
            {"id": "deepseek-coder", "name": "DeepSeek Coder", "description": "Code focused"},
        ],
        "huggingface": [
            {"id": "meta-llama/Llama-3.1-8B-Instruct", "name": "Llama 3.1 8B", "description": "Popular open model"},
            {"id": "mistralai/Mistral-7B-Instruct-v0.3", "name": "Mistral 7B", "description": "Strong reasoning"},
        ],
    }

    if provider not in models_by_provider:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    return ModelsResponse(provider=provider, models=models_by_provider[provider])


@router.get("/providers")
async def get_providers() -> list[dict]:
    """Get available LLM providers."""
    return [
        {
            "id": "local",
            "name": "Local (Ollama)",
            "description": "Run models locally on your device. Free and private.",
            "requires_api_key": False,
            "setup_url": "https://ollama.ai/download",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "description": "GPT-4 and GPT-3.5 models",
            "requires_api_key": True,
            "setup_url": "https://platform.openai.com/api-keys",
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "description": "Claude 3.5 Sonnet, Haiku, and Opus",
            "requires_api_key": True,
            "setup_url": "https://console.anthropic.com/settings/keys",
        },
        {
            "id": "google",
            "name": "Google AI",
            "description": "Gemini 1.5 Pro and Flash",
            "requires_api_key": True,
            "setup_url": "https://aistudio.google.com/app/apikey",
        },
        {
            "id": "groq",
            "name": "Groq",
            "description": "Ultra-fast inference for open models",
            "requires_api_key": True,
            "setup_url": "https://console.groq.com/keys",
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "description": "Cost-effective Chinese AI models",
            "requires_api_key": True,
            "setup_url": "https://platform.deepseek.com/api_keys",
        },
    ]
