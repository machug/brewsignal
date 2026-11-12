"""LiteLLM is gone (tilt_ui-i5nw): LLMService, review_recipe and mem0 config work without it importable."""

import sys
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.models import Recipe, RecipeFermentable
from backend.services.llm.config import LLMConfig, LLMProvider
from backend.services.llm.service import LLMService
from backend.services.llm.tools.recipe import review_recipe
from backend.services.memory import get_memory_config

OPENROUTER = LLMConfig(
    enabled=True, provider=LLMProvider.OPENROUTER, api_key="sk-or-test", model="anthropic/claude-sonnet-4", max_tokens=400
)


@pytest.fixture(autouse=True)
def no_litellm(monkeypatch):
    monkeypatch.setitem(sys.modules, "litellm", None)  # import litellm -> ImportError


def _fake_model(seen: list):
    def respond(messages, info: AgentInfo):
        seen.append((messages, info.model_settings))
        return ModelResponse(parts=[TextPart("Fine brew.")])

    return FunctionModel(respond)


@pytest.mark.asyncio
async def test_service_chat_status_and_test_connection():
    seen: list = []
    svc = LLMService(OPENROUTER)
    with patch("backend.services.llm.service.build_model", lambda c: _fake_model(seen)):
        text = await svc.chat(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}], temperature=0.5, max_tokens=123
        )
        result = await svc.test_connection()
    assert text == "Fine brew."
    messages, settings = seen[0]
    assert [type(p).__name__ for p in messages[0].parts] == ["SystemPromptPart", "UserPromptPart"]
    assert settings["max_tokens"] == 123 and settings["temperature"] == 0.5
    assert settings["openrouter_reasoning"] == {"max_tokens": 61}
    assert result["success"] is True and result["response"] == "Fine brew."
    assert svc.get_status()["configured"] is True


@pytest.mark.asyncio
async def test_review_recipe_without_litellm(test_db):
    recipe = Recipe(name="Plain", type="all-grain", batch_size_liters=20, og=1.050, fg=1.012, user_id="u")
    recipe.fermentables.append(RecipeFermentable(name="Pale Malt", amount_kg=4.0))
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    seen: list = []

    async def cfg(db):
        return OPENROUTER

    with patch("backend.routers.assistant.get_llm_config", cfg), patch(
        "backend.services.llm.service.build_model", lambda c: _fake_model(seen)
    ):
        result = await review_recipe(db=test_db, recipe_id=recipe.id, user_id="u")
    assert result["review"] == "Fine brew."
    assert seen[0][1]["temperature"] == 0.5


def test_memory_config_without_litellm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = get_memory_config(OPENROUTER)
    assert cfg["llm"]["provider"] == "openai"
    assert cfg["llm"]["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["llm"]["config"]["api_key"] == "sk-or-test"
    assert cfg["llm"]["config"]["model"] == "anthropic/claude-haiku-4.5"  # fast model, bare id, no litellm prefix
    assert cfg["embedder"]["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"


def test_memory_config_ollama_llm_uses_v1_endpoint(monkeypatch):
    from backend.services.memory import _get_llm_provider_config

    cfg = LLMConfig(enabled=True, provider=LLMProvider.LOCAL, base_url="http://box:11434", model="qwen2:1.5b")
    out = _get_llm_provider_config(cfg)["config"]
    assert out["openai_base_url"] == "http://box:11434/v1" and out["model"] == "qwen2:1.5b"


def test_memory_config_anthropic_disabled():
    cfg = LLMConfig(enabled=True, provider=LLMProvider.ANTHROPIC, api_key="k")
    assert get_memory_config(cfg) is None


def test_reasoning_budget_is_bounded_so_the_reply_keeps_room():
    """tilt_ui-s1k4: a recipe save was cut off because thinking took half the budget."""
    from backend.services.llm.model import model_settings

    cfg = LLMConfig(enabled=True, provider=LLMProvider.OPENROUTER, api_key="k", model="m", max_tokens=16000)
    assert model_settings(cfg)["openrouter_reasoning"] == {"max_tokens": 4000}
    assert LLMConfig(max_tokens=50000).max_tokens == 32000


def test_config_api_accepts_the_larger_budget():
    from backend.models import ConfigUpdate

    assert ConfigUpdate(ai_max_tokens=16000).ai_max_tokens == 16000
    with pytest.raises(ValueError):
        ConfigUpdate(ai_max_tokens=40000)


def test_openrouter_prompt_caching_is_on():
    """tilt_ui-mpad: no cache_read_tokens on a 127k-token thread, ~US$0.27 per step."""
    from backend.services.llm.model import model_settings

    cfg = LLMConfig(enabled=True, provider=LLMProvider.OPENROUTER, api_key="k", model="anthropic/claude-sonnet-5.5")
    s = model_settings(cfg)
    assert s["openrouter_cache_instructions"] and s["openrouter_cache_tool_definitions"] and s["openrouter_cache_messages"]
