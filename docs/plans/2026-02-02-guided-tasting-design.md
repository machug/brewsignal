# Guided Tasting Interview - Design Document

## Overview

AI-guided tasting interview that walks users through a BJCP-style beer evaluation. When AI is disabled, a manual BJCP scoresheet form is provided instead. Both produce identical structured data.

## User Experience

### Entry Point
- Batch detail page (conditioning/completed status)
- `ai_enabled = true`: "Start Guided Tasting" button → opens embedded chat panel
- `ai_enabled = false`: "Add Tasting" button → opens manual BJCP form

### Guided Flow (AI Enabled)
1. User clicks "Start Guided Tasting" → chat panel slides open on right
2. AI greets, confirms batch, asks quick context (serving temp, glassware)
3. AI walks through 5 categories with proactive style guidance:
   - Aroma (12pts) → Appearance (3pts) → Flavor (20pts) → Mouthfeel (5pts) → Overall (10pts)
4. For each category:
   - AI describes style expectations first
   - Asks specific subcategory questions
   - Gently prompts if answers incomplete
   - Shows score before moving on
5. At end: AI shows summary, total (out of 50), style conformance, suggestions
6. User confirms → tasting saved → panel closes

### Panel Behavior
- Collapsible panel on right side of batch detail
- Batch info stays visible on left
- Can minimize mid-tasting and resume (session state preserved)
- Progress indicator shows current category

## Data Model

Replace existing simple 1-5 scores with BJCP-accurate structure:

```python
class TastingNote(Base):
    """BJCP-style tasting evaluation for a batch."""
    __tablename__ = "tasting_notes"

    id: int (primary key)
    batch_id: int (foreign key)
    user_id: str (multi-tenant)
    tasted_at: datetime

    # Context
    days_since_packaging: int (nullable)
    serving_temp_c: float (nullable)
    glassware: str (nullable)

    # Aroma (12 pts max)
    aroma_malt: int  # 0-3
    aroma_hops: int  # 0-3
    aroma_fermentation: int  # 0-3
    aroma_other: int  # 0-3
    aroma_notes: text

    # Appearance (3 pts max)
    appearance_color: int  # 0-1
    appearance_clarity: int  # 0-1
    appearance_head: int  # 0-1
    appearance_notes: text

    # Flavor (20 pts max)
    flavor_malt: int  # 0-5
    flavor_hops: int  # 0-5
    flavor_bitterness: int  # 0-3
    flavor_fermentation: int  # 0-3
    flavor_balance: int  # 0-2
    flavor_finish: int  # 0-2
    flavor_notes: text

    # Mouthfeel (5 pts max)
    mouthfeel_body: int  # 0-2
    mouthfeel_carbonation: int  # 0-2
    mouthfeel_warmth: int  # 0-1
    mouthfeel_notes: text

    # Overall (10 pts max)
    overall_score: int  # 0-10
    overall_notes: text

    # Computed
    total_score: int  # 0-50 (calculated)
    to_style: bool
    style_deviation_notes: text

    # AI fields
    ai_suggestions: text
    interview_transcript: json  # Full conversation for reference

    # Timestamps
    created_at: datetime
    updated_at: datetime
```

### BJCP Score Ranges

| Category | Max Points | Subcategories |
|----------|------------|---------------|
| Aroma | 12 | Malt (3), Hops (3), Fermentation (3), Other (3) |
| Appearance | 3 | Color (1), Clarity (1), Head (1) |
| Flavor | 20 | Malt (5), Hops (5), Bitterness (3), Fermentation (3), Balance (2), Finish (2) |
| Mouthfeel | 5 | Body (2), Carbonation (2), Warmth (1) |
| Overall | 10 | Single score |
| **Total** | **50** | |

### Score Interpretation
- 45-50: Outstanding
- 38-44: Excellent
- 30-37: Very Good
- 21-29: Good
- 14-20: Fair
- 0-13: Problematic

## Architecture

### Backend Changes

1. **Update TastingNote model** (`backend/models.py`)
   - Replace simple scores with BJCP subcategory fields
   - Add computed total_score property
   - Update Pydantic schemas

2. **Migration** (`backend/database.py`)
   - Drop old simple score columns
   - Add BJCP columns
   - No backwards compatibility needed

3. **Update AG-UI tools** (`backend/services/llm/tools/tasting.py`)
   - `start_tasting_session`: Return style guidelines for interview
   - `save_tasting_note`: Accept BJCP structure
   - Add `update_tasting_progress`: Save partial progress mid-interview

4. **Tasting router** (`backend/routers/batches.py`)
   - Update endpoints for BJCP structure

### Frontend Components

1. **`TastingPanel.svelte`** (new)
   - Embedded chat panel for guided tasting
   - Connects to AG-UI streaming endpoint
   - Manages interview state (current category, collected scores)
   - Progress indicator
   - Minimize/resume capability

2. **`BJCPScoreForm.svelte`** (new)
   - Manual form with all BJCP subcategory inputs
   - Grouped sections (Aroma, Appearance, Flavor, Mouthfeel, Overall)
   - Score inputs with point ranges displayed
   - Used when AI is disabled

3. **`TastingNoteCard.svelte`** (update)
   - Display BJCP scores with category breakdowns
   - Friendly summary view (default)
   - "View Scoresheet" → expandable full BJCP format

4. **`TastingNotesList.svelte`** (update)
   - Conditional rendering based on `ai_enabled`
   - "Start Guided Tasting" vs "Add Tasting" button

### Batch Detail Integration

```svelte
{#if configState.config.ai_enabled}
  <button onclick={() => showTastingPanel = true}>
    Start Guided Tasting
  </button>
  {#if showTastingPanel}
    <TastingPanel {batch} onClose={() => showTastingPanel = false} />
  {/if}
{:else}
  <button onclick={() => showBJCPForm = true}>
    Add Tasting
  </button>
  {#if showBJCPForm}
    <BJCPScoreForm {batch} onClose={() => showBJCPForm = false} />
  {/if}
{/if}
```

## AI Conversation Flow

### System Prompt
AI receives via `start_tasting_session`:
- Batch info (name, recipe, measured OG/FG/ABV)
- Style guidelines (BJCP description for the style)
- Previous tastings for this batch (for comparison)
- Days since packaging

### Interview Structure

**Phase 1: Context (~30 seconds)**
```
AI: "Ready to taste [Batch Name]? Quick setup:
     What temperature is it served at?
     What glass are you using?"
```

**Phases 2-6: Categories**
For each category:
1. AI states style expectation
2. Asks subcategory questions
3. Validates completeness (gentle prompts if vague)
4. Confirms scores before moving on

**Example - Aroma:**
```
AI: "For your Irish Stout, aroma should feature roasted grain,
     coffee/chocolate notes, with low hop presence.

     Take a few sniffs... What malt/grain aromas do you detect?"

User: "Strong coffee and chocolate, some roast"

AI: "Nice - that's classic. Any hop aroma?"

User: "Very faint, maybe earthy"

AI: "And fermentation character - any esters or off-flavors?"

User: "Clean, no issues"

AI: "Great. For Aroma I'm scoring:
     Malt 3/3, Hops 2/3, Fermentation 3/3, Other 2/3 = 10/12

     Moving to Appearance..."
```

**Phase 7: Summary**
```
AI: "All done! Here's your tasting:

     Total: 42/50 (Excellent)
     ✓ To style - classic Irish Stout character

     Highlights: Strong roast character, clean fermentation
     Suggestion: Could use slightly more head retention

     Save this tasting note?"
```

## Mem0 Integration

When tasting is saved, store key insights in mem0:
- Notable flavor observations
- Style deviations
- Improvement suggestions

This feeds future recipe recommendations.

## Out of Scope (Future)

- PDF export of BJCP scoresheet
- Multi-person tasting sessions
- Photo attachments
- Comparison view across multiple tastings
