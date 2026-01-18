"""AI Brewing Assistant API endpoints."""

import json
import logging
from pathlib import Path
from typing import Optional

import prompty
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Config, Style
from backend.services.llm import LLMConfig, LLMProvider, LLMService

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "services" / "llm" / "prompts"

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
            {"id": "smollm2:360m", "name": "SmolLM2 360M", "description": "Best for RPi - very fast"},
            {"id": "smollm2:135m", "name": "SmolLM2 135M", "description": "Fastest, minimal resources"},
            {"id": "smollm2:1.7b", "name": "SmolLM2 1.7B", "description": "Better quality, still fast"},
            {"id": "gemma2:2b", "name": "Gemma 2 2B", "description": "Good quality, needs more RAM"},
            {"id": "phi3:mini", "name": "Phi-3 Mini (3.8B)", "description": "High quality, slow on Pi"},
            {"id": "llama3:8b", "name": "Llama 3 8B", "description": "Best quality, needs fast CPU"},
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


# =============================================================================
# Recipe Review Endpoint
# =============================================================================


class RecipeFermentableInput(BaseModel):
    """Fermentable in a recipe for review."""
    name: str
    amount_kg: float
    color_srm: Optional[float] = None
    type: Optional[str] = None


class RecipeHopInput(BaseModel):
    """Hop in a recipe for review."""
    name: str
    amount_grams: float
    boil_time_minutes: int
    alpha_acid_percent: Optional[float] = None
    use: Optional[str] = None  # boil, whirlpool, dry_hop


class RecipeYeastInput(BaseModel):
    """Yeast info for recipe review."""
    name: str
    producer: Optional[str] = None
    attenuation: Optional[float] = None


class RecipeReviewRequest(BaseModel):
    """Request body for recipe review."""
    name: str
    style: str  # The declared style (e.g., "American IPA")
    og: float
    fg: float
    abv: float
    ibu: float
    color_srm: float
    fermentables: list[RecipeFermentableInput]
    hops: list[RecipeHopInput]
    yeast: Optional[RecipeYeastInput] = None


class RecipeReviewResponse(BaseModel):
    """Response from recipe review."""
    review: str
    style_found: bool
    style_name: Optional[str] = None
    model: str


async def _get_style_guidelines(db: AsyncSession, style_name: str) -> tuple[bool, str, str]:
    """Look up BJCP style guidelines by name.

    Returns: (found, style_name, guidelines_text)
    """
    if not style_name:
        return False, "", ""

    # Try exact match first
    result = await db.execute(
        select(Style).where(func.lower(Style.name) == style_name.lower())
    )
    style = result.scalar_one_or_none()

    # Try fuzzy match if exact match fails
    if not style:
        result = await db.execute(
            select(Style).where(Style.name.ilike(f"%{style_name}%")).limit(1)
        )
        style = result.scalar_one_or_none()

    if not style:
        return False, "", ""

    # Build guidelines text
    guidelines = []
    guidelines.append(f"**{style.name}** (BJCP {style.category_number}{style.style_letter})")

    if style.description:
        guidelines.append(f"\n**Description:** {style.description}")

    # Vital statistics
    stats = []
    if style.og_min and style.og_max:
        stats.append(f"OG: {style.og_min:.3f}-{style.og_max:.3f}")
    if style.fg_min and style.fg_max:
        stats.append(f"FG: {style.fg_min:.3f}-{style.fg_max:.3f}")
    if style.abv_min and style.abv_max:
        stats.append(f"ABV: {style.abv_min:.1f}-{style.abv_max:.1f}%")
    if style.ibu_min and style.ibu_max:
        stats.append(f"IBU: {int(style.ibu_min)}-{int(style.ibu_max)}")
    if style.srm_min and style.srm_max:
        stats.append(f"SRM: {style.srm_min:.0f}-{style.srm_max:.0f}")

    if stats:
        guidelines.append(f"\n**Vital Statistics:** {', '.join(stats)}")

    if style.comments:
        guidelines.append(f"\n**Comments:** {style.comments}")

    return True, style.name, "\n".join(guidelines)


def _format_fermentables(fermentables: list[RecipeFermentableInput]) -> str:
    """Format fermentables list for prompt."""
    if not fermentables:
        return "No fermentables specified"

    lines = []
    total_kg = sum(f.amount_kg for f in fermentables)

    for f in sorted(fermentables, key=lambda x: x.amount_kg, reverse=True):
        pct = (f.amount_kg / total_kg * 100) if total_kg > 0 else 0
        color_str = f" ({f.color_srm:.0f} SRM)" if f.color_srm else ""
        lines.append(f"- {f.name}: {f.amount_kg:.2f} kg ({pct:.0f}%){color_str}")

    return "\n".join(lines)


def _format_hops(hops: list[RecipeHopInput]) -> str:
    """Format hops list for prompt."""
    if not hops:
        return "No hops specified"

    lines = []
    for h in sorted(hops, key=lambda x: x.boil_time_minutes, reverse=True):
        use = h.use or "boil"
        aa_str = f" ({h.alpha_acid_percent:.1f}% AA)" if h.alpha_acid_percent else ""

        if use == "dry_hop":
            timing = "dry hop"
        elif use == "whirlpool":
            timing = "whirlpool"
        elif h.boil_time_minutes == 0:
            timing = "flameout"
        else:
            timing = f"{h.boil_time_minutes} min"

        lines.append(f"- {h.name}: {h.amount_grams:.0f}g @ {timing}{aa_str}")

    return "\n".join(lines)


def _format_yeast(yeast: Optional[RecipeYeastInput]) -> str:
    """Format yeast info for prompt."""
    if not yeast:
        return "No yeast specified"

    parts = [yeast.name]
    if yeast.producer:
        parts.append(f"by {yeast.producer}")
    if yeast.attenuation:
        parts.append(f"({yeast.attenuation:.0f}% attenuation)")

    return " ".join(parts)


@router.post("/review-recipe", response_model=RecipeReviewResponse)
async def review_recipe(
    request: RecipeReviewRequest,
    service: LLMService = Depends(get_llm_service),
    db: AsyncSession = Depends(get_db),
) -> RecipeReviewResponse:
    """
    Review a recipe against its declared BJCP style guidelines.

    Returns an AI-generated review analyzing how well the recipe
    fits the declared style, with suggestions for improvement.
    """
    if not service.config.is_configured():
        raise HTTPException(
            status_code=400,
            detail="AI assistant is not configured. Enable it in Settings.",
        )

    try:
        # Look up style guidelines
        style_found, style_name, style_guidelines = await _get_style_guidelines(
            db, request.style
        )

        # Format recipe data for prompt
        fermentables_summary = _format_fermentables(request.fermentables)
        hops_summary = _format_hops(request.hops)
        yeast_info = _format_yeast(request.yeast)

        # Load and prepare the review prompt using Prompty
        prompt_path = PROMPTS_DIR / "recipe-review.prompty"
        p = prompty.load(str(prompt_path))

        rendered = prompty.prepare(p, inputs={
            "recipe_name": request.name or "Untitled Recipe",
            "style_name": style_name if style_found else request.style,
            "og": request.og,
            "fg": request.fg,
            "abv": request.abv,
            "ibu": request.ibu,
            "color_srm": request.color_srm,
            "fermentables_summary": fermentables_summary,
            "hops_summary": hops_summary,
            "yeast_info": yeast_info,
            "style_guidelines": style_guidelines if style_found else "",
        })

        # Call LLM
        response = await service.chat(
            messages=rendered,
            temperature=0.5,  # Lower temperature for more consistent reviews
        )

        return RecipeReviewResponse(
            review=response,
            style_found=style_found,
            style_name=style_name if style_found else None,
            model=service.config.effective_model,
        )

    except Exception as e:
        logger.error(f"Recipe review error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
