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


async def resolve_style_id(
    db: AsyncSession, style_name: Optional[str]
) -> Optional[str]:
    """Look up a BJCP style by name (exact then case-insensitive then fuzzy).

    Returns Style.id when found, None otherwise.
    """
    if not style_name or not isinstance(style_name, str):
        return None
    name = style_name.strip()
    if not name:
        return None

    # .limit(1) + order keeps lookup deterministic when the styles table has
    # duplicate names across BJCP guide versions or imported rows.
    result = await db.execute(
        select(Style)
        .where(func.lower(Style.name) == name.lower())
        .order_by(Style.guide.desc(), Style.id)
        .limit(1)
    )
    style = result.scalar_one_or_none()
    if not style:
        result = await db.execute(
            select(Style)
            .where(Style.name.ilike(f"%{name}%"))
            .order_by(Style.guide.desc(), Style.id)
            .limit(1)
        )
        style = result.scalar_one_or_none()
    return style.id if style else None
