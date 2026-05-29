"""Resolve free-text BJCP style names to Style.id FK values.

Shared by the LLM save_recipe/update_recipe tools (which pass style names
emitted by the model) and the REST POST/PUT /recipes endpoints (which pass
style names typed into the edit form's autocomplete). Keeping this in
services/ avoids the REST layer importing private helpers from
services/llm/tools/.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Style


# Colloquial brewer shorthand -> canonical BJCP 2021 style name. Brewers and
# imported recipes routinely use names that are not BJCP-canonical ("West
# Coast IPA", "NEIPA", "XPA"); exact + substring matching misses all of them
# and the style_id lands NULL (tilt_ui-ru9). Each alias maps to a canonical
# name that is then resolved through the normal name lookup, so the result
# stays correct across guide versions. Keys are matched lowercased and exact.
_STYLE_ALIASES = {
    # American IPA (21A) — West Coast is the archetypal 21A in BJCP 2021.
    "west coast ipa": "American IPA",
    "west coast": "American IPA",
    "wcipa": "American IPA",
    "wc ipa": "American IPA",
    # Hazy IPA (21C)
    "neipa": "Hazy IPA",
    "ne ipa": "Hazy IPA",
    "new england ipa": "Hazy IPA",
    "juicy ipa": "Hazy IPA",
    "hazy": "Hazy IPA",
    # American Pale Ale (18B) — XPA / "extra pale ale" sit closest to APA.
    "xpa": "American Pale Ale",
    "extra pale ale": "American Pale Ale",
    "apa": "American Pale Ale",
    # Double IPA (22A)
    "dipa": "Double IPA",
    "imperial ipa": "Double IPA",
    "double ipa": "Double IPA",
    # Irish Stout (15B)
    "dry stout": "Irish Stout",
    "irish dry stout": "Irish Stout",
}


async def _exact(db: AsyncSession, name: str) -> Optional[Style]:
    """Case-insensitive exact name match. .limit(1) + deterministic ordering
    keeps the result stable across duplicate names / guide versions."""
    result = await db.execute(
        select(Style)
        .where(func.lower(Style.name) == name.lower())
        .order_by(Style.guide.desc(), Style.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _substring(db: AsyncSession, name: str) -> Optional[Style]:
    """Loose substring name match — last resort."""
    result = await db.execute(
        select(Style)
        .where(Style.name.ilike(f"%{name}%"))
        .order_by(Style.guide.desc(), Style.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_style_id(
    db: AsyncSession, style_name: Optional[str]
) -> Optional[str]:
    """Resolve a free-text style name to Style.id.

    Order, strongest signal first:
      1. exact (case-insensitive) name match
      2. curated alias map (exact key) -> canonical name, matched exactly
      3. loose substring name match

    The alias step runs *before* the substring fallback so a known shorthand
    ("APA", "Hazy") resolves to its intended canonical style instead of being
    preempted by some other row whose name merely contains the alias text
    (the styles table explicitly allows duplicate/imported rows). Returns
    Style.id when found, None otherwise.
    """
    if not style_name or not isinstance(style_name, str):
        return None
    name = style_name.strip()
    if not name:
        return None

    style = await _exact(db, name)
    if style:
        return style.id

    # Only an exact alias-key hit counts — substring matching the alias keys
    # would be too loose (e.g. a bare "ipa").
    canonical = _STYLE_ALIASES.get(name.lower())
    if canonical:
        style = await _exact(db, canonical)
        if style:
            return style.id

    style = await _substring(db, name)
    return style.id if style else None
