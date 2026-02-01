# Batch Post-Mortem System Design

## Overview

A comprehensive post-mortem system for batches that captures structured reflections at each brewing phase, AI-generated insights, and BJCP-style tasting notes. All data feeds back into the AI assistant to improve future recipe and process recommendations.

## Batch Lifecycle

**Updated status flow:**

```
Planning → Brewing → Fermenting → Conditioning → Completed
```

| Status | Description |
|--------|-------------|
| Planning | Recipe selected, ingredients gathered, batch scheduled |
| Brewing | Active brew day (mash, boil, chill, pitch) |
| Fermenting | Yeast working, monitoring gravity drop |
| Conditioning | Packaged and carbonating/maturing |
| Completed | Ready to drink, accepting tasting notes |

**Reflection points:**

| Transition | Reflection Phase |
|------------|-----------------|
| Brewing → Fermenting | `brew_day` |
| Fermenting → Conditioning | `fermentation` (+ packaging details) |
| Conditioning → Completed | `conditioning` |
| Ongoing while Completed | Tasting sessions (multiple) |

## Data Models

### BatchReflection

Captures structured learning at each phase transition.

```python
class BatchReflection(Base):
    __tablename__ = "batch_reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    phase: Mapped[str] = mapped_column(String(20))  # brew_day, fermentation, packaging, conditioning
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Structured metrics (phase-specific JSON)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON)

    # Freeform reflection
    what_went_well: Mapped[Optional[str]] = mapped_column(Text)
    what_went_wrong: Mapped[Optional[str]] = mapped_column(Text)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)
    next_time_changes: Mapped[Optional[str]] = mapped_column(Text)

    # AI-generated
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_generated_at: Mapped[Optional[datetime]]
    ai_model_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="reflections")
```

**Metrics JSON structure per phase:**

```python
# brew_day
{
    "efficiency_actual": 72.5,
    "efficiency_expected": 75.0,
    "mash_ph_actual": 5.4,
    "mash_ph_target": 5.4,
    "pre_boil_volume_actual": 28.5,
    "pre_boil_volume_expected": 29.0,
    "time_deviation_minutes": 15
}

# fermentation
{
    "fg_actual": 1.010,
    "fg_expected": 1.012,
    "attenuation_actual": 78.5,
    "attenuation_expected": 76.0,
    "days_to_terminal": 12,
    "temp_excursions": 2,
    "max_temp_c": 21.5,
    "min_temp_c": 18.0
}

# packaging
{
    "volume_packaged_liters": 19.5,
    "packaging_type": "keg",  # keg, bottles, cans
    "carbonation_method": "forced",  # forced, bottle_conditioned, keg_conditioned
    "carbonation_volumes_target": 2.4,
    "oxidation_concern": "low"  # none, low, medium, high
}

# conditioning
{
    "days_conditioned": 14,
    "carbonation_achieved": "good",  # under, good, over
    "clarity": "clear",  # hazy, slightly_hazy, clear, brilliant
    "serving_temp_c": 4.0
}
```

### BatchTastingNote

BJCP-style tasting evaluations, multiple per batch.

```python
class BatchTastingNote(Base):
    __tablename__ = "batch_tasting_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    tasted_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Context
    days_since_packaging: Mapped[Optional[int]]
    serving_temp_c: Mapped[Optional[float]]
    glassware: Mapped[Optional[str]] = mapped_column(String(50))

    # BJCP-style scores (1-5 scale)
    appearance_score: Mapped[Optional[int]]
    appearance_notes: Mapped[Optional[str]] = mapped_column(Text)

    aroma_score: Mapped[Optional[int]]
    aroma_notes: Mapped[Optional[str]] = mapped_column(Text)

    flavor_score: Mapped[Optional[int]]
    flavor_notes: Mapped[Optional[str]] = mapped_column(Text)

    mouthfeel_score: Mapped[Optional[int]]
    mouthfeel_notes: Mapped[Optional[str]] = mapped_column(Text)

    overall_score: Mapped[Optional[int]]
    overall_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Computed (5-25 range)
    total_score: Mapped[Optional[int]]

    # Style assessment
    to_style: Mapped[Optional[bool]]
    style_deviation_notes: Mapped[Optional[str]] = mapped_column(Text)

    # AI-assisted
    ai_suggestions: Mapped[Optional[str]] = mapped_column(Text)
    interview_transcript: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="tasting_notes")
```

### Batch Model Updates

Add relationships:

```python
class Batch(Base):
    # ... existing fields ...

    # New relationships
    reflections: Mapped[list["BatchReflection"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    tasting_notes: Mapped[list["BatchTastingNote"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
```

## AI Integration

### AG-UI Tools

New tools for the brewing assistant:

```python
# Reflection management
async def create_batch_reflection(
    db: AsyncSession,
    batch_id: int,
    phase: str,
    metrics: Optional[dict] = None,
    what_went_well: Optional[str] = None,
    what_went_wrong: Optional[str] = None,
    lessons_learned: Optional[str] = None,
    next_time_changes: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict

async def get_batch_reflections(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict

async def regenerate_reflection_insights(
    db: AsyncSession,
    reflection_id: int,
    user_id: Optional[str] = None,
) -> dict

# Tasting management
async def start_tasting_session(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict  # Returns batch context for interview

async def save_tasting_note(
    db: AsyncSession,
    batch_id: int,
    tasted_at: datetime,
    appearance_score: int,
    appearance_notes: str,
    aroma_score: int,
    aroma_notes: str,
    flavor_score: int,
    flavor_notes: str,
    mouthfeel_score: int,
    mouthfeel_notes: str,
    overall_score: int,
    overall_notes: str,
    to_style: Optional[bool] = None,
    style_deviation_notes: Optional[str] = None,
    serving_temp_c: Optional[float] = None,
    glassware: Optional[str] = None,
    ai_suggestions: Optional[str] = None,
    interview_transcript: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> dict

async def get_batch_tasting_notes(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict

# Learning/context tools
async def search_past_reflections(
    db: AsyncSession,
    style: Optional[str] = None,
    phase: Optional[str] = None,
    issue_keywords: Optional[str] = None,
    limit: int = 10,
    user_id: Optional[str] = None,
) -> dict

async def search_past_tastings(
    db: AsyncSession,
    style: Optional[str] = None,
    min_score: Optional[int] = None,
    keywords: Optional[str] = None,
    limit: int = 10,
    user_id: Optional[str] = None,
) -> dict
```

### AI Insight Generation

When a phase transition occurs:

1. System creates a `BatchReflection` record
2. Gathers context:
   - **brew_day**: Recipe targets, actual measurements from batch fields, timer logs
   - **fermentation**: Full reading curve from `readings` table, temp profile, duration
   - **conditioning**: Days elapsed, packaging details, any user notes
3. Calls LLM with structured prompt
4. Saves `ai_summary` and suggested `lessons_learned`

User can edit AI suggestions and regenerate anytime.

### Tasting Interview Flow

1. User triggers via chat ("I want to taste my Hefeweizen") or button
2. AI receives batch context (recipe, style, age, previous tastings)
3. AI guides through each BJCP category with style-specific prompts:
   - "Pour your beer. Describe the color - is it the pale gold you'd expect from a Helles?"
   - "Take a sniff. What malt character comes through first?"
4. After each category, AI asks for 1-5 score
5. At end, AI summarizes and offers improvement suggestions
6. Saves complete `BatchTastingNote` with `interview_transcript`

## Frontend UI

### Batch Detail Page

**Timeline/milestone view:**
- Visual progress through phases
- Each phase shows completion status and reflection indicator
- Phases: Planning → Brewing → Fermenting → Conditioning → Completed

**Reflection cards (one per phase):**
- Expandable sections showing:
  - Structured metrics in a clean grid
  - AI-generated summary
  - User notes (what went well/wrong, lessons, changes)
- "Edit" button for user notes
- "Regenerate insights" button for AI summary

**Tasting notes section:**
- List of dated entries showing: date, total score (X/25), excerpt
- Click to expand full BJCP breakdown
- "Add tasting" button

### Tasting Wizard

**Quick mode:** Via chat conversation

**Full mode:** Step-by-step modal wizard
1. Context (serving temp, glassware, batch age)
2. Appearance (color, clarity, head - with helper descriptions)
3. Aroma (malt, hops, fermentation character)
4. Flavor (malt, hops, bitterness, balance, finish)
5. Mouthfeel (body, carbonation, warmth)
6. Overall + style assessment
7. Review & save

AI suggestions appear inline based on beer style.

## Implementation Order

### Phase 1: Foundation
1. Add "brewing" status to batch validation
2. Create `BatchReflection` model + migration
3. Create `BatchTastingNote` model + migration
4. Add relationships to Batch model
5. Basic CRUD API endpoints for both

### Phase 2: Reflection System
1. Reflection CRUD router endpoints
2. AG-UI tools for reflections
3. Reflection cards UI component
4. Phase transition hooks to create reflections

### Phase 3: AI Insights
1. Insight generation prompts per phase
2. Auto-generation on phase transition
3. Regenerate functionality
4. Display in reflection cards

### Phase 4: Tasting Notes
1. Tasting notes CRUD router endpoints
2. AG-UI tools for tastings
3. Tasting notes list UI component
4. Tasting wizard modal

### Phase 5: Tasting Interview
1. Interview conversation flow in AG-UI
2. Style-specific prompts
3. Transcript saving
4. Chat integration

### Phase 6: Learning Integration
1. Search tools for past reflections/tastings
2. Context injection for recipe creation
3. "Similar batches" suggestions

## API Endpoints

```
# Reflections
POST   /api/batches/{batch_id}/reflections
GET    /api/batches/{batch_id}/reflections
GET    /api/batches/{batch_id}/reflections/{phase}
PUT    /api/batches/{batch_id}/reflections/{id}
POST   /api/batches/{batch_id}/reflections/{id}/regenerate

# Tasting Notes
POST   /api/batches/{batch_id}/tasting-notes
GET    /api/batches/{batch_id}/tasting-notes
GET    /api/batches/{batch_id}/tasting-notes/{id}
PUT    /api/batches/{batch_id}/tasting-notes/{id}
DELETE /api/batches/{batch_id}/tasting-notes/{id}
```

## Future Considerations

- **Context-aware AI sidebar** (tracked in `tilt_ui-avm`): Global sidebar that detects page context for seamless assistance
- **Comparative analysis**: Compare tastings across batches of same recipe
- **Trend tracking**: Graph tasting scores over time for a recipe
- **Export**: Generate shareable tasting reports
