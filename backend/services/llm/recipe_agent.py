"""Recipe generation agent using LLM."""

import json
import logging
from typing import Optional

from backend.services.llm.service import LLMService, LLMServiceError

logger = logging.getLogger(__name__)

# System prompt for recipe generation
RECIPE_SYSTEM_PROMPT = """You are BrewSignal's AI Brewing Assistant, an expert homebrewer who helps create beer recipes.

## Your Expertise
- Deep knowledge of BJCP beer styles and their characteristics
- Understanding of brewing ingredients: malts, hops, yeast, adjuncts
- Ability to calculate OG, FG, ABV, IBU, and SRM from ingredients
- Knowledge of fermentation temperatures and schedules
- Understanding of water chemistry basics

## Response Format
When asked to create or discuss a recipe, provide:
1. A brief description of the beer style and what makes it special
2. Target specifications (OG, FG, ABV, IBU, SRM)
3. Suggested ingredients with amounts for a standard batch
4. Brewing notes (mash temp, boil time, fermentation temp)

## When Generating a Final Recipe
When the user is ready to create the recipe, output a JSON block with this exact format:
```json
{
  "name": "Recipe Name",
  "style": "BJCP Style Name",
  "type": "all-grain",
  "og": 1.050,
  "fg": 1.010,
  "abv": 5.2,
  "ibu": 35,
  "color_srm": 8,
  "batch_size_liters": 19,
  "boil_time_minutes": 60,
  "efficiency_percent": 72,
  "yeast_name": "Yeast Strain Name",
  "yeast_lab": "Manufacturer",
  "yeast_attenuation": 75,
  "yeast_temp_min": 18,
  "yeast_temp_max": 22,
  "notes": "Detailed brewing instructions including:\\n- Grain bill with amounts\\n- Hop schedule\\n- Mash schedule\\n- Fermentation notes"
}
```

## Conversation Style
- Be friendly and enthusiastic about brewing
- Ask clarifying questions if the request is vague
- Offer alternatives when appropriate
- Explain the "why" behind suggestions
- Keep responses concise but informative

## Important Rules
- Always use metric units (liters, kg, grams, Celsius)
- Default batch size is 19 liters (5 gallons) unless specified
- Default efficiency is 72% unless specified
- Calculate ABV from OG and FG: ABV = (OG - FG) × 131.25
- Only output JSON when the user confirms they want to save/create the recipe
"""


def extract_recipe_json(text: str) -> Optional[dict]:
    """Extract recipe JSON from assistant response."""
    # Look for JSON block in markdown code fence
    import re

    # Try to find JSON in code block
    json_match = re.search(r'```(?:json)?\s*\n({[\s\S]*?})\s*\n```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'({[\s\S]*?"name"[\s\S]*?"notes"[\s\S]*?})', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


class RecipeAgent:
    """Agent for conversational recipe generation."""

    def __init__(self, service: LLMService):
        self.service = service
        self.conversation_history: list[dict] = []

    def reset(self):
        """Reset conversation history."""
        self.conversation_history = []

    async def chat(
        self,
        user_message: str,
        batch_size: Optional[float] = None,
        efficiency: Optional[float] = None,
    ) -> dict:
        """
        Send a message and get a response.

        Args:
            user_message: The user's message
            batch_size: Optional batch size in liters
            efficiency: Optional brewhouse efficiency percent

        Returns:
            Dict with 'response' text and optional 'recipe' if JSON was extracted
        """
        # Build system prompt with user preferences
        system_prompt = RECIPE_SYSTEM_PROMPT
        if batch_size:
            system_prompt += f"\n\nUser's batch size: {batch_size} liters"
        if efficiency:
            system_prompt += f"\nUser's brewhouse efficiency: {efficiency}%"

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.service.chat(messages)

            # Add to history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": response})

            # Try to extract recipe JSON
            recipe = extract_recipe_json(response)

            return {
                "response": response,
                "recipe": recipe,
                "has_recipe": recipe is not None,
            }
        except LLMServiceError as e:
            logger.error(f"Recipe agent error: {e}")
            raise


async def generate_recipe_from_prompt(
    service: LLMService,
    prompt: str,
    style: Optional[str] = None,
    batch_size: float = 19.0,
    efficiency: float = 72.0,
) -> dict:
    """
    Generate a complete recipe from a single prompt.

    This is a one-shot generation that returns a recipe directly.
    """
    system_prompt = RECIPE_SYSTEM_PROMPT + f"""

User's batch size: {batch_size} liters
User's brewhouse efficiency: {efficiency}%

IMPORTANT: The user wants to create a recipe now. Generate and output the recipe JSON immediately.
"""

    user_prompt = prompt
    if style:
        user_prompt = f"Create a {style} recipe. {prompt}"

    user_prompt += "\n\nPlease generate the complete recipe with JSON output."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await service.chat(messages, max_tokens=2000)
        recipe = extract_recipe_json(response)

        return {
            "response": response,
            "recipe": recipe,
            "has_recipe": recipe is not None,
        }
    except LLMServiceError as e:
        logger.error(f"Recipe generation error: {e}")
        raise
