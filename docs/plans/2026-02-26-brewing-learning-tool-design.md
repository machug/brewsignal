# Brewing Learning Tool — Design

## Problem

The BrewSignal assistant makes generic assumptions (boil-off rates, efficiency, ingredient behavior) that don't match the user's specific equipment and experience. When corrected, it forgets by next conversation. The assistant needs to proactively identify and save brewing learnings so it improves over time — a form of soft fine-tuning through structured memory.

## Solution

A `save_brewing_learning` tool the LLM calls mid-conversation when it detects a teaching moment. Dual-write to Mem0 (semantic recall) and a `brewing_learnings` table (UI browsing/editing). System prompt guidance tells the LLM when to save.

## Architecture

### Storage — Dual Write

1. **Mem0 (existing)** — semantic vector store, already searched at conversation start and via `search_brewing_memories`. No changes needed.
2. **`brewing_learnings` table (new)** — structured storage for the UI.

### Database Model

```python
class BrewingLearning(Base):
    __tablename__ = "brewing_learnings"

    id: int (PK, autoincrement)
    user_id: str (indexed)
    category: str  # equipment | technique | recipe | ingredient | correction
    learning: str (Text)  # The insight, concise and factual
    source_context: str (nullable)  # What triggered it (batch name, topic)
    mem0_memory_id: str (nullable)  # Cross-reference to Mem0 for sync
    created_at: datetime (UTC)
    updated_at: datetime (UTC)
```

### Categories (Fixed Enum)

| Category | Examples |
|----------|----------|
| `equipment` | Boil-off rates, dead space, mash tun efficiency |
| `technique` | Preferred mash temps, sparge method, water adjustments |
| `recipe` | Recipe feedback, style preferences, what worked/didn't |
| `ingredient` | Yeast performance, hop character, grain behavior |
| `correction` | When the assistant was wrong about something |

### Tool Definition

```json
{
  "name": "save_brewing_learning",
  "description": "Save a brewing learning or insight to long-term memory. Call this PROACTIVELY when you identify a teaching moment — user corrections, equipment-specific knowledge, recipe feedback, or ingredient observations. Do not ask permission; save the learning and briefly mention it.",
  "parameters": {
    "type": "object",
    "properties": {
      "learning": {
        "type": "string",
        "description": "The insight, written as a concise factual statement. E.g. 'Grainfather Gen 1 boil-off rate is ~3.5 L/hr, lower than the typical 4-5 L/hr assumption'"
      },
      "category": {
        "type": "string",
        "enum": ["equipment", "technique", "recipe", "ingredient", "correction"],
        "description": "Category of this learning"
      },
      "source_context": {
        "type": "string",
        "description": "Brief context about what triggered this learning. E.g. 'Pale Ale brew day discussion' or 'Batch #12 post-brew review'"
      }
    },
    "required": ["learning", "category"]
  }
}
```

### System Prompt Additions

Add to `assistant.prompty` under a new `## Proactive Learning` section:

```
## Proactive Learning
You have access to `save_brewing_learning` to save insights to long-term memory. Use it PROACTIVELY — don't ask permission, just save and briefly mention it.

### When to Save
- **User corrects you** — you assumed wrong boil-off rate, efficiency, etc.
- **Actual vs predicted differs** — measured OG was lower than expected, fermentation took longer
- **Equipment-specific knowledge** — capacity limits, dead space, heating power
- **Recipe feedback** — what tasted good, what to change, ingredient observations
- **Technique preferences** — preferred mash temp, sparge method, water chemistry approach
- **Ingredient learnings** — yeast attenuation in their system, hop character notes

### How to Save
- Write learnings as concise factual statements, not conversation summaries
- Include specific numbers when available (3.5 L/hr, not "lower than expected")
- Choose the most specific category
- Include source_context so the learning is traceable

### Examples
- User: "The boil-off was way less than you predicted, it's a Gen 1 Grainfather"
  → save_brewing_learning("Grainfather Gen 1 boil-off rate is ~3.5 L/hr, lower than typical 4-5 L/hr", "equipment", "Pale Ale brew day")

- User: "The US-05 attenuated way more than 75%, I got 82%"
  → save_brewing_learning("US-05 typically attenuates to ~82% in this system, higher than the listed 75%", "ingredient", "IPA batch fermentation review")

- User: "That recipe was too bitter, the 60min addition was too much"
  → save_brewing_learning("User prefers lower bitterness; reduce 60-minute hop additions by ~20% from calculated values", "recipe", "Pale Ale recipe feedback")
```

### API Endpoints

```
GET  /api/learnings              — List all learnings (filterable by category)
PUT  /api/learnings/{id}         — Update a learning
DELETE /api/learnings/{id}       — Delete a learning (also removes from Mem0)
```

No POST endpoint — learnings are created exclusively via the LLM tool to encourage proactive AI-driven capture.

### Frontend — Brewing Knowledge Page

Route: `/knowledge`

Simple list view:
- Category filter tabs (All | Equipment | Technique | Recipe | Ingredient | Correction)
- Each learning shows: text, category badge, source context, date
- Edit button (inline edit or modal)
- Delete button with confirmation
- Empty state: "Your assistant hasn't saved any learnings yet. As you brew and chat, it will proactively capture insights about your equipment, techniques, and preferences."

### Data Flow

```
User corrects assistant in chat
  → LLM detects teaching moment
  → LLM calls save_brewing_learning(learning, category, context)
  → Backend:
    1. Insert into brewing_learnings table
    2. Write to Mem0 via add_memory() with category metadata
    3. Return success + learning ID
  → LLM mentions: "Noted — I've saved that your Grainfather boil-off is ~3.5 L/hr"

Next conversation:
  → Mem0 search finds the learning in system prompt context
  → LLM uses correct boil-off rate without being told
```

### What's Out of Scope

- No changes to existing Mem0 search or background extraction
- No deduplication logic (trust Mem0's built-in dedup + user can delete from UI)
- No knowledge graph or relationships between learnings
- No import/export
