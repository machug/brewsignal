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


# Recipe generation models
class RecipeChatRequest(BaseModel):
    """Request for recipe chat conversation."""

    message: str
    conversation_id: Optional[str] = None
    batch_size: Optional[float] = None  # liters
    efficiency: Optional[float] = None  # percent


class RecipeChatResponse(BaseModel):
    """Response from recipe chat."""

    response: str
    has_recipe: bool = False
    recipe: Optional[dict] = None
    conversation_id: str


class RecipeGenerateRequest(BaseModel):
    """Request for one-shot recipe generation."""

    prompt: str
    style: Optional[str] = None
    batch_size: float = 19.0
    efficiency: float = 72.0


class RecipeGenerateResponse(BaseModel):
    """Response from recipe generation."""

    response: str
    has_recipe: bool = False
    recipe: Optional[dict] = None


# In-memory conversation storage (for simplicity)
# In production, you might want to use Redis or database
_recipe_conversations: dict[str, list[dict]] = {}


@router.post("/recipe/chat", response_model=RecipeChatResponse)
async def recipe_chat(
    request: RecipeChatRequest,
    service: LLMService = Depends(get_llm_service),
) -> RecipeChatResponse:
    """Chat with the recipe assistant for conversational recipe building."""
    from backend.services.llm.recipe_agent import RecipeAgent, extract_recipe_json
    import uuid

    if not service.config.is_configured():
        raise HTTPException(
            status_code=400,
            detail="AI assistant is not configured. Enable it in Settings.",
        )

    # Get or create conversation
    conv_id = request.conversation_id or str(uuid.uuid4())

    # Create agent with conversation history
    agent = RecipeAgent(service)
    if conv_id in _recipe_conversations:
        agent.conversation_history = _recipe_conversations[conv_id].copy()

    try:
        result = await agent.chat(
            user_message=request.message,
            batch_size=request.batch_size,
            efficiency=request.efficiency,
        )

        # Store updated conversation
        _recipe_conversations[conv_id] = agent.conversation_history

        return RecipeChatResponse(
            response=result["response"],
            has_recipe=result["has_recipe"],
            recipe=result.get("recipe"),
            conversation_id=conv_id,
        )
    except Exception as e:
        logger.error(f"Recipe chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recipe/generate", response_model=RecipeGenerateResponse)
async def generate_recipe(
    request: RecipeGenerateRequest,
    service: LLMService = Depends(get_llm_service),
) -> RecipeGenerateResponse:
    """Generate a recipe from a single prompt (one-shot generation)."""
    from backend.services.llm.recipe_agent import generate_recipe_from_prompt

    if not service.config.is_configured():
        raise HTTPException(
            status_code=400,
            detail="AI assistant is not configured. Enable it in Settings.",
        )

    try:
        result = await generate_recipe_from_prompt(
            service=service,
            prompt=request.prompt,
            style=request.style,
            batch_size=request.batch_size,
            efficiency=request.efficiency,
        )

        return RecipeGenerateResponse(
            response=result["response"],
            has_recipe=result["has_recipe"],
            recipe=result.get("recipe"),
        )
    except Exception as e:
        logger.error(f"Recipe generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/recipe/conversation/{conversation_id}")
async def clear_conversation(conversation_id: str) -> dict:
    """Clear a recipe conversation history."""
    if conversation_id in _recipe_conversations:
        del _recipe_conversations[conversation_id]
        return {"status": "cleared"}
    return {"status": "not_found"}


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
        "openrouter": [
            {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "description": "Anthropic via OpenRouter"},
            {"id": "anthropic/claude-haiku-4", "name": "Claude Haiku 4", "description": "Fast Anthropic via OpenRouter"},
            {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "OpenAI via OpenRouter"},
            {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "description": "Google via OpenRouter"},
            {"id": "deepseek/deepseek-chat-v3", "name": "DeepSeek V3", "description": "DeepSeek via OpenRouter"},
            {"id": "meta-llama/llama-4-maverick", "name": "Llama 4 Maverick", "description": "Meta via OpenRouter"},
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
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": "400+ models via unified API (Claude, GPT, Gemini, Llama)",
            "requires_api_key": True,
            "setup_url": "https://openrouter.ai/keys",
        },
    ]
