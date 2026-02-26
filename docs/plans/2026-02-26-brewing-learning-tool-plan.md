# Brewing Learning Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `save_brewing_learning` LLM tool so the assistant proactively saves brewing insights, with a UI to browse/edit accumulated knowledge.

**Architecture:** Dual-write — new `brewing_learnings` SQLite table for structured storage + existing Mem0 for semantic recall. New tool in AG-UI tool registry. New `/knowledge` frontend route. System prompt updated to instruct proactive saving.

**Tech Stack:** FastAPI (backend router), SQLAlchemy (model), Svelte 5 with runes (frontend), existing Mem0 memory service, existing AG-UI tool framework.

**Design doc:** `docs/plans/2026-02-26-brewing-learning-tool-design.md`

---

### Task 1: Database Model — BrewingLearning

**Files:**
- Modify: `backend/models.py` (add model + Pydantic schemas after BatchReflection block ~line 1155)
- Modify: `backend/database.py` (Base.metadata.create_all handles new tables automatically, no migration needed for new tables)

**Step 1: Add the SQLAlchemy model to models.py**

Add after the `BatchReflection` class (around line 1155):

```python
class BrewingLearning(Base):
    """Proactive brewing insights saved by the AI assistant."""
    __tablename__ = "brewing_learnings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # equipment|technique|recipe|ingredient|correction
    learning: Mapped[str] = mapped_column(Text, nullable=False)
    source_context: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    mem0_memory_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

**Step 2: Add Pydantic response/update schemas**

Add after the model (still in models.py):

```python
LEARNING_CATEGORIES = ["equipment", "technique", "recipe", "ingredient", "correction"]


class BrewingLearningResponse(BaseModel):
    """Response schema for a brewing learning."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    learning: str
    source_context: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)


class BrewingLearningUpdate(BaseModel):
    """Update schema for a brewing learning."""
    learning: Optional[str] = None
    category: Optional[str] = None
    source_context: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in LEARNING_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(LEARNING_CATEGORIES)}")
        return v
```

**Step 3: Verify the server starts**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -c "from backend.models import BrewingLearning, BrewingLearningResponse, BrewingLearningUpdate; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/models.py
git commit -m "feat: add BrewingLearning model and schemas"
```

---

### Task 2: Backend Tool — save_brewing_learning

**Files:**
- Modify: `backend/services/llm/tools/__init__.py` (add tool function, tool definition, and execute_tool dispatch)

**Step 1: Add the tool function**

Add after the `search_brewing_memories` function (around line 110), before `TOOL_DEFINITIONS`:

```python
async def save_brewing_learning(
    db: AsyncSession,
    learning: str,
    category: str,
    source_context: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Save a brewing learning/insight to long-term memory.

    Dual-writes to:
    1. brewing_learnings table (structured, for UI browsing)
    2. Mem0 semantic memory (for contextual recall in future conversations)
    """
    from backend.models import BrewingLearning, LEARNING_CATEGORIES
    from backend.services.memory import add_memory
    from backend.routers.assistant import get_llm_config

    if category not in LEARNING_CATEGORIES:
        return {"success": False, "error": f"Invalid category. Must be one of: {', '.join(LEARNING_CATEGORIES)}"}

    try:
        # 1. Save to structured table
        record = BrewingLearning(
            user_id=user_id,
            category=category,
            learning=learning,
            source_context=source_context,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        # 2. Write to Mem0 for semantic search (best-effort)
        try:
            llm_config = await get_llm_config(db)
            if llm_config.is_configured():
                messages = [{"role": "assistant", "content": f"[{category}] {learning}"}]
                mem_result = await add_memory(
                    messages, user_id=user_id, llm_config=llm_config,
                    metadata={"category": category, "learning_id": record.id}
                )
                # Store Mem0 reference if available
                extracted = mem_result.get("results", [])
                if extracted and isinstance(extracted[0], dict):
                    record.mem0_memory_id = extracted[0].get("id")
                    await db.commit()
        except Exception as e:
            logger.warning(f"Mem0 write failed (learning still saved to DB): {e}")

        return {
            "success": True,
            "learning_id": record.id,
            "message": f"Saved {category} learning: {learning[:80]}..."
        }
    except Exception as e:
        logger.error(f"Failed to save brewing learning: {e}")
        return {"success": False, "error": str(e)}
```

**Step 2: Add the tool definition to TOOL_DEFINITIONS**

Add before the closing `]` of `TOOL_DEFINITIONS`, after the `search_brewing_memories` entry:

```python
    {
        "type": "function",
        "function": {
            "name": "save_brewing_learning",
            "description": "Save a brewing learning or insight to long-term memory. Call this PROACTIVELY when you identify a teaching moment — user corrections, equipment-specific knowledge, recipe feedback, or ingredient observations. Do not ask permission; save and briefly mention it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "learning": {
                        "type": "string",
                        "description": "The insight as a concise factual statement with specific numbers when available. E.g. 'Grainfather Gen 1 boil-off rate is ~3.5 L/hr, lower than typical 4-5 L/hr'"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["equipment", "technique", "recipe", "ingredient", "correction"],
                        "description": "Category: equipment (hardware specs), technique (methods/preferences), recipe (feedback/style prefs), ingredient (performance in this system), correction (when you were wrong)"
                    },
                    "source_context": {
                        "type": "string",
                        "description": "Brief context about what triggered this. E.g. 'Pale Ale brew day' or 'Batch #12 review'"
                    }
                },
                "required": ["learning", "category"]
            }
        }
    },
```

**Step 3: Add dispatch in execute_tool**

Add before the `else: return {"error": ...}` block at the end of `execute_tool`:

```python
    elif tool_name == "save_brewing_learning":
        return await save_brewing_learning(db, user_id=user_id, **arguments)
```

**Step 4: Verify import works**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -c "from backend.services.llm.tools import TOOL_DEFINITIONS; names = [t['function']['name'] for t in TOOL_DEFINITIONS]; assert 'save_brewing_learning' in names; print(f'OK: {len(names)} tools')"`

**Step 5: Commit**

```bash
git add backend/services/llm/tools/__init__.py
git commit -m "feat: add save_brewing_learning tool for proactive memory"
```

---

### Task 3: Backend API — Learnings Router

**Files:**
- Create: `backend/routers/learnings.py`
- Modify: `backend/main.py` (register the router)

**Step 1: Create the learnings router**

Create `backend/routers/learnings.py`:

```python
"""API endpoints for browsing and managing brewing learnings."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.auth import AuthUser, require_auth
from backend.models import (
    BrewingLearning, BrewingLearningResponse, BrewingLearningUpdate,
    LEARNING_CATEGORIES,
)

router = APIRouter(prefix="/api/learnings", tags=["learnings"])


@router.get("", response_model=list[BrewingLearningResponse])
async def list_learnings(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """List all brewing learnings, optionally filtered by category."""
    query = select(BrewingLearning).where(BrewingLearning.user_id == user.id)
    if category:
        if category not in LEARNING_CATEGORIES:
            raise HTTPException(400, f"Invalid category. Must be one of: {', '.join(LEARNING_CATEGORIES)}")
        query = query.where(BrewingLearning.category == category)
    query = query.order_by(BrewingLearning.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.put("/{learning_id}", response_model=BrewingLearningResponse)
async def update_learning(
    learning_id: int,
    update: BrewingLearningUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Update a brewing learning."""
    result = await db.execute(
        select(BrewingLearning).where(
            BrewingLearning.id == learning_id,
            BrewingLearning.user_id == user.id,
        )
    )
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(404, "Learning not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(learning, field, value)

    await db.commit()
    await db.refresh(learning)
    return learning


@router.delete("/{learning_id}", status_code=204)
async def delete_learning(
    learning_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Delete a brewing learning."""
    result = await db.execute(
        select(BrewingLearning).where(
            BrewingLearning.id == learning_id,
            BrewingLearning.user_id == user.id,
        )
    )
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(404, "Learning not found")

    # Optionally delete from Mem0 too
    if learning.mem0_memory_id:
        try:
            from backend.services.memory import delete_memory
            await delete_memory(learning.mem0_memory_id)
        except Exception:
            pass  # Best-effort Mem0 cleanup

    await db.delete(learning)
    await db.commit()
```

**Step 2: Register the router in main.py**

Find the router includes section in `backend/main.py` and add:

```python
from backend.routers.learnings import router as learnings_router
app.include_router(learnings_router)
```

Follow the existing pattern — look for `include_router` calls and add alongside them.

**Step 3: Verify server starts with new router**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -c "from backend.routers.learnings import router; print(f'OK: {len(router.routes)} routes')"`
Expected: `OK: 3 routes`

**Step 4: Commit**

```bash
git add backend/routers/learnings.py backend/main.py
git commit -m "feat: add learnings API router (list, update, delete)"
```

---

### Task 4: System Prompt — Proactive Learning Instructions

**Files:**
- Modify: `backend/services/llm/prompts/assistant.prompty`

**Step 1: Add the Proactive Learning section**

Insert before `## Conversation Style` (around line 143), and add `save_brewing_learning` to the tool list at the top. Two edits:

**Edit 1 — Tool list (under `### Long-Term Memory & Conversation History`):**

Add after `search_threads` entry:

```
- **save_brewing_learning**: PROACTIVELY save brewing insights when you detect a teaching moment (corrections, equipment knowledge, recipe feedback, ingredient observations)
```

**Edit 2 — New section before `## Conversation Style`:**

```
## Proactive Learning
You have `save_brewing_learning` to save insights to long-term memory. Use it PROACTIVELY — don't ask permission, just save and briefly mention what you noted.

### When to Save
- **User corrects you** — wrong boil-off rate, efficiency, volumes, etc.
- **Actual vs predicted differs** — measured OG lower than expected, fermentation time different
- **Equipment-specific knowledge** — capacity limits, dead space, heating power, boil vigor
- **Recipe feedback** — what tasted good, what to change next time
- **Technique preferences** — preferred mash temp, sparge method, water chemistry
- **Ingredient learnings** — yeast attenuation in their system, hop character notes

### How to Save
- Write concise factual statements, not conversation summaries
- Include specific numbers (3.5 L/hr, not "lower than expected")
- Choose the most specific category: equipment, technique, recipe, ingredient, or correction
- Include source_context so the learning is traceable

### Examples
- User says boil-off was less than predicted on Gen 1 Grainfather
  → save_brewing_learning("Grainfather Gen 1 boil-off rate is ~3.5 L/hr, lower than typical 4-5 L/hr", "equipment", "Pale Ale brew day")

- User reports US-05 attenuated to 82% instead of listed 75%
  → save_brewing_learning("US-05 attenuates to ~82% in this system, higher than listed 75%", "ingredient", "IPA fermentation review")

- User says a recipe was too bitter
  → save_brewing_learning("User prefers lower bitterness; reduce 60-minute hop additions by ~20%", "recipe", "Pale Ale feedback")
```

**Step 2: Commit**

```bash
git add backend/services/llm/prompts/assistant.prompty
git commit -m "feat: add proactive learning instructions to system prompt"
```

---

### Task 5: Frontend API Client — Learnings

**Files:**
- Modify: `frontend/src/lib/api.ts` (add types and API functions)

**Step 1: Add TypeScript types**

Add near the other response types:

```typescript
export interface BrewingLearningResponse {
	id: number;
	category: 'equipment' | 'technique' | 'recipe' | 'ingredient' | 'correction';
	learning: string;
	source_context?: string;
	created_at: string;
	updated_at: string;
}

export interface BrewingLearningUpdate {
	learning?: string;
	category?: 'equipment' | 'technique' | 'recipe' | 'ingredient' | 'correction';
	source_context?: string;
}
```

**Step 2: Add API functions**

Add near the other API functions:

```typescript
export async function getLearnings(category?: string): Promise<BrewingLearningResponse[]> {
	const params = category ? `?category=${category}` : '';
	const response = await authFetch(`${BASE_URL}/learnings${params}`);
	if (!response.ok) throw new Error(`Failed to fetch learnings: ${response.statusText}`);
	return response.json();
}

export async function updateLearning(id: number, update: BrewingLearningUpdate): Promise<BrewingLearningResponse> {
	const response = await authFetch(`${BASE_URL}/learnings/${id}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(update),
	});
	if (!response.ok) throw new Error(`Failed to update learning: ${response.statusText}`);
	return response.json();
}

export async function deleteLearning(id: number): Promise<void> {
	const response = await authFetch(`${BASE_URL}/learnings/${id}`, { method: 'DELETE' });
	if (!response.ok) throw new Error(`Failed to delete learning: ${response.statusText}`);
}
```

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add learnings API client types and functions"
```

---

### Task 6: Frontend — Knowledge Page

**Files:**
- Create: `frontend/src/routes/knowledge/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte` (add nav link)

**Step 1: Create the Knowledge page**

Create `frontend/src/routes/knowledge/+page.svelte`. Build a simple page with:

- Page title "Brewing Knowledge"
- Subtitle "Insights your assistant has learned from your brewing experience"
- Category filter tabs: All | Equipment | Technique | Recipe | Ingredient | Correction
- Each learning rendered as a card with:
  - Category badge (colored by category)
  - Learning text
  - Source context (muted text)
  - Date (formatted)
  - Edit button (inline textarea that appears on click, save on blur)
  - Delete button with confirmation
- Empty state message when no learnings exist

Use existing CSS variable patterns from the codebase (`--bg-surface`, `--border-subtle`, `--text-primary`, `--text-muted`, `--accent`, etc.). Follow Svelte 5 runes (`$state`, `$derived`, `$effect`). Use `onMount` for initial data fetch.

Category badge colors:
- equipment: `#d97706` (amber)
- technique: `#2563eb` (blue)
- recipe: `#16a34a` (green)
- ingredient: `#9333ea` (purple)
- correction: `#dc2626` (red)

**Step 2: Add nav link in +layout.svelte**

Modify the `navLinks` derived value (around line 157-162). Add the knowledge link when AI is enabled, right after the assistant link:

```javascript
...(configState.config.ai_enabled ? [
    { href: '/assistant', label: 'Assistant' },
    { href: '/knowledge', label: 'Knowledge' }
] : []),
```

**Step 3: Verify it builds**

Run: `cd frontend && npx svelte-check --threshold error 2>&1 | tail -5`
Expected: Only pre-existing errors in system/+page.svelte (3 Shelly config errors)

**Step 4: Commit**

```bash
git add frontend/src/routes/knowledge/+page.svelte frontend/src/routes/+layout.svelte
git commit -m "feat: add Brewing Knowledge page with category filters and edit/delete"
```

---

### Task 7: Build, Deploy, and Verify

**Step 1: Build for Pi**

Run: `cd frontend && BUILD_TARGET=pi npm run build`

**Step 2: Push and deploy**

```bash
git push
sshpass -p 'tilt' ssh pi@192.168.4.218 "cd /opt/brewsignal && git pull && cd frontend && BUILD_TARGET=pi npm run build && sudo systemctl restart brewsignal"
```

**Step 3: Verify**

1. Check the Pi logs for startup: `sshpass -p 'tilt' ssh pi@192.168.4.218 "sudo journalctl -u brewsignal --no-pager -n 20"`
2. Verify `/knowledge` page loads in browser at `http://192.168.4.218:8080/knowledge`
3. Verify the API responds: `curl http://192.168.4.218:8080/api/learnings`
4. Test the assistant — tell it something like "my boil-off rate is actually about 3.5 litres per hour on the Grainfather" and see if it proactively calls `save_brewing_learning`

**Step 4: Final commit if any adjustments needed**

```bash
git add -A && git commit -m "fix: deployment adjustments for brewing knowledge"
```
