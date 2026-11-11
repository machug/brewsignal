"""Memory page API: list and delete what the assistant remembers about the signed-in user (tilt_ui-or48).

Items are the user's saved learnings (brewing_learnings) plus mem0 memories that are not copies
of a learning (auto-extracted from chats and reflections, source 'chat'). Ids are
'learning:<n>' or 'mem:<mem0 id>'. Everything is scoped to the authenticated user_id.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import AuthUser, require_auth
from backend.database import get_db
from backend.models import BrewingLearning
from backend.routers.assistant import get_llm_config
from backend.services import memory as mem

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryItem(BaseModel):
    id: str
    text: str
    source: str  # 'learning' | 'chat'
    created_at: str | None = None


@router.get("", response_model=list[MemoryItem])
async def list_memory(db: AsyncSession = Depends(get_db), user: AuthUser = Depends(require_auth)):
    rows = (await db.execute(
        select(BrewingLearning).where(BrewingLearning.user_id == user.user_id)
    )).scalars().all()
    items = [
        MemoryItem(id=f"learning:{r.id}", text=r.learning, source="learning",
                   created_at=r.created_at.isoformat() if r.created_at else None)
        for r in rows
    ]
    linked = {r.mem0_memory_id for r in rows if r.mem0_memory_id}
    for m in await mem.get_all_memories(user.user_id, await get_llm_config(db)):
        if m.get("id") in linked or (m.get("metadata") or {}).get("learning_id") is not None:
            continue  # a copy of a learning
        items.append(MemoryItem(id=f"mem:{m['id']}", text=m.get("memory", ""), source="chat",
                                created_at=m.get("created_at")))
    items.sort(key=lambda i: i.created_at or "", reverse=True)
    return items


@router.delete("/{item_id}", status_code=204)
async def delete_memory_item(item_id: str, db: AsyncSession = Depends(get_db), user: AuthUser = Depends(require_auth)):
    kind, _, ref = item_id.partition(":")
    config = await get_llm_config(db)
    learning = None
    if kind == "learning" and ref.isdigit():
        learning = (await db.execute(select(BrewingLearning).where(
            BrewingLearning.id == int(ref), BrewingLearning.user_id == user.user_id))).scalar_one_or_none()
        if not learning:
            raise HTTPException(404, "Memory not found")
        if learning.mem0_memory_id:
            await mem.delete_memory(learning.mem0_memory_id, user.user_id, config)
    elif kind == "mem" and ref:
        if not await mem.delete_memory(ref, user.user_id, config):
            raise HTTPException(404, "Memory not found")  # also: someone else's id
        learning = (await db.execute(select(BrewingLearning).where(
            BrewingLearning.mem0_memory_id == ref, BrewingLearning.user_id == user.user_id))).scalar_one_or_none()
    else:
        raise HTTPException(404, "Memory not found")
    if learning:
        await db.delete(learning)
        await db.commit()


@router.delete("", status_code=204)
async def delete_all_memory(db: AsyncSession = Depends(get_db), user: AuthUser = Depends(require_auth)):
    await mem.delete_all_memories(user.user_id, await get_llm_config(db))
    await db.execute(delete(BrewingLearning).where(BrewingLearning.user_id == user.user_id))
    await db.commit()
