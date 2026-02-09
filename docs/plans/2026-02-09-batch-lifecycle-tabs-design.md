# Batch Lifecycle Tabs — Design Document

**Date:** 2026-02-09
**Status:** Draft

## Problem

The batch detail page (`/batches/[id]`) is a 1200+ line monolithic component with conditional rendering per status. All phases share the same layout, leading to:

1. **Wrong context in wrong phase** — ML predictions show "will appear once fermentation is underway" during conditioning. Fermentation ETA shows during conditioning. Rate-of-change stats are meaningless post-fermentation.
2. **No recipe-driven guidance** — Recipes already define fermentation steps (primary/secondary/conditioning with durations and temperatures) but the UI doesn't use them to guide the user through phases.
3. **Tasting journal buried** — The guided tasting system (designed in `2026-02-02-guided-tasting-design.md`) should be a primary feature during conditioning, not hidden.
4. **No transition prompts** — The user must manually change status. The app has ML predictions and sensor data that could suggest when to advance.

## Design

### URL & Navigation

**URL stays the same:** `/batches/[id]`

**Page layout:**
```
┌──────────────────────────────────────────────────┐
│ Batch Header (name, recipe link, started date)   │
│                                                  │
│ ● Recipe → ● Brew Day → ● Ferm → ○ Cond → ○ Done│  ← lifecycle stepper
├──────────────────────────────────────────────────┤
│ [Recipe] [Brew Day] [Fermentation] [Conditioning]│  ← phase tabs
├──────────────────────────────────────────────────┤
│                                                  │
│  Phase-specific content (one component per tab)  │
│                                                  │
├──────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────┐ │
│ │ ⚡ Gravity stable 48h — Ready to condition?  │ │  ← transition prompt
│ │                          [Not Yet] [Advance] │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Lifecycle Stepper

A horizontal progress indicator above the tabs:

- **Completed phases:** Filled circle + checkmark, clickable to view that tab
- **Current phase:** Highlighted/pulsing, active tab
- **Future phases:** Greyed out circles, tabs visible but show "Not started yet" placeholder
- Phases: Recipe → Brew Day → Fermentation → Conditioning → Complete
- Maps to statuses: `planning` → `brewing` → `fermenting` → `conditioning` → `completed`

**Default tab on load:** The tab matching the batch's current status.

### Phase Tab Components

Extract the existing conditional rendering into focused components:

#### `PhaseRecipe.svelte`
- Recipe targets card (OG, FG, IBU, ABV, SRM, color)
- Ingredient summary (fermentables, hops, cultures, misc)
- Fermentation schedule from recipe steps (primary X days at Y°C → conditioning Z days at W°C)
- Mash schedule summary
- Water profile if defined
- **Action:** "Start Brew Day" button → transitions to `brewing`

#### `PhaseBrewDay.svelte`
- BrewDayTimer (hop additions, mash steps from recipe)
- BrewDayChecklist (recipe-driven process steps)
- BrewDayObservations (notes, pre-boil gravity, volumes)
- Pre-pitch chilling progress (if device paired + target temp set)
- OG recording
- **Action:** "Yeast Pitched — Start Fermentation" button → transitions to `fermenting`

#### `PhaseFermentation.svelte`
- **Left column:**
  - BatchFermentationCard (live gravity + temp hero, progress bar OG→FG)
  - Recipe target comparison (where we are vs recipe expectations)
  - Fermentation chart (full historical chart with SG, temps, trend lines)
  - FermentationStats bar (rate, duration, at SG, OG, attenuation, ABV, ETA)
- **Right column:**
  - MLPredictions (active mode — predicted FG, model selection, confidence, anomalies, stuck warnings)
  - BatchAlertsCard
  - Temperature control card (if HA configured)
  - Notes
- **Recipe-driven:** Shows expected duration from recipe fermentation step (`type=primary`), e.g., "Day 8 of 14 (recipe target)"
- **Transition prompt:** When ML predicts FG reached + gravity stable for configurable period → banner: "Fermentation appears complete — ready to condition?"

#### `PhaseConditioning.svelte`
- **Left column:**
  - **Conditioning Progress Card**
    - Reads from recipe `fermentation_steps` where `type = 'conditioning'`
    - "Day 3 of 14 at 5.0°C" — recipe-defined duration and temp
    - Sub-phase timeline: Diacetyl Rest → Cold Crash → Packaging Ready
    - Diacetyl rest: derived from yeast type (lager strains) or recipe step
    - Cold crash: recipe conditioning temp, suggested 24–72h if not specified
    - If no conditioning step in recipe, prompt user to add one or use style defaults
  - **Final Fermentation Summary** (collapsed card)
    - OG, FG, ABV, Attenuation — locked-in final numbers
    - Compact, read-only — fermentation is done
  - **Tasting Journal** (prominent, primary activity)
    - LLM-assisted guided tasting (per `2026-02-02-guided-tasting-design.md`)
    - "Start Guided Tasting" button or manual BJCP form
    - Timeline of tasting entries showing beer evolution over conditioning
    - This is a first-class citizen here, not a collapsible afterthought
- **Right column:**
  - Temperature control card (critical for cold crash management)
  - Conditioning checklist / guidance (recipe-aware suggestions)
  - Notes
- **Stats bar changes:**
  - Drop: ETA, Rate (meaningless post-fermentation)
  - Keep: Duration, OG, FG, ABV, Attenuation
  - Add: Conditioning day count, days remaining to recipe target ready date
- **Transition prompt:** When conditioning duration target reached → "Conditioning target reached — ready to package?"

#### `PhaseComplete.svelte`
- Batch summary card (final OG, FG, ABV, Attenuation, total duration)
- Phase timeline showing all transitions with dates
- ML post-mortem (prediction accuracy: predicted vs actual FG)
- Packaging info (keg/bottle, carbonation, date)
- Reflections & learnings section
- Full tasting journal history (read-only, showing evolution)
- Full fermentation chart (historical, read-only)

### Shared Elements

These remain visible across all tabs (in the batch header area or always-accessible):

- Batch name, recipe link, status badge, started date
- Lifecycle stepper (always shows where you are)
- Edit/Pause/Delete actions

The fermentation chart could optionally appear as a collapsible on non-fermentation tabs for quick reference.

### Transition Prompts

**Prompt by default, auto-advance as future opt-in.**

Transition conditions detected by the system:

| Transition | Condition |
|---|---|
| Brewing → Fermenting | User clicks "Yeast Pitched" (manual, no auto-detect) |
| Fermenting → Conditioning | ML predicts FG reached AND gravity stable for N hours (configurable, default 48h) |
| Conditioning → Completed | Recipe conditioning duration elapsed OR user decides |

**Prompt UI:** A banner at the bottom of the phase content (not a modal — non-blocking). Includes:
- What was detected ("Gravity stable for 48h at 1.004")
- Suggested action ("Ready to start conditioning?")
- Two buttons: "Not Yet" (dismiss, re-prompts later) and "Advance to Conditioning"

**Future (opt-in):** Auto-advance setting per batch or globally. When enabled, the system advances automatically and logs the transition with reason.

### Recipe-Driven Phase Awareness

The recipe's `fermentation_steps` table drives the lifecycle:

```
fermentation_steps:
  - step_number: 1, type: "primary",      temp_c: 20.0, time_days: 14
  - step_number: 2, type: "secondary",    temp_c: 18.0, time_days: 7
  - step_number: 3, type: "conditioning",  temp_c: 5.0,  time_days: 14
```

Each phase tab reads its targets from the matching step:
- PhaseFermentation reads `type=primary` (and `type=secondary` if present)
- PhaseConditioning reads `type=conditioning`
- Duration countdowns, temperature targets, and progress all derive from recipe data

**Fallback for missing data:** If a recipe has no fermentation steps defined, show sensible defaults based on style (ale vs lager) and prompt user to define them in the recipe.

### MLPredictions Adaptation

The MLPredictions component needs phase-aware behavior:

| Phase | ML Behavior |
|---|---|
| Planning/Brewing | Hidden or shows "ML activates during fermentation" |
| Fermenting | Full active mode (current behavior) — predictions, anomalies, model selection |
| Conditioning | Hidden or shows compact summary: "Final prediction accuracy: ±2 points" |
| Completed | Post-mortem mode (current behavior) — accuracy comparison |

### FermentationStats Bar Adaptation

| Phase | Stats Shown |
|---|---|
| Fermenting | Rate, Duration, At SG, OG, Attenuation, ABV, ETA (current behavior) |
| Conditioning | Duration (conditioning), OG, FG, ABV, Attenuation, Days Remaining |
| Completed | Total Duration, OG, FG, ABV, Attenuation |

## Implementation Strategy

### Phase 1: Extract Tab Components (refactor, no new features)
1. Create `PhaseRecipe.svelte`, `PhaseBrewDay.svelte`, `PhaseFermentation.svelte`, `PhaseConditioning.svelte`, `PhaseComplete.svelte`
2. Move existing conditional blocks from `+page.svelte` into respective components
3. Add tab navigation UI to `+page.svelte`
4. Add lifecycle stepper component
5. Default to current-status tab on load
6. **Outcome:** Same functionality, cleaner architecture, ~200-400 lines per component instead of 1200+

### Phase 2: Conditioning Differentiation
1. Build conditioning progress card reading recipe fermentation steps
2. Adapt FermentationStats bar for conditioning (drop ETA/Rate, add conditioning day count)
3. Make tasting journal prominent in conditioning tab
4. Adapt MLPredictions to hide/summarize during conditioning
5. Add cold crash / diacetyl rest sub-phase guidance

### Phase 3: Recipe-Driven Guidance
1. Show recipe-defined durations as targets in each phase ("Day 8 of 14")
2. Add fermentation step awareness to temperature control suggestions
3. Fallback defaults when recipe steps are missing

### Phase 4: Transition Prompts
1. Detect fermentation completion (stable gravity + ML prediction match)
2. Detect conditioning duration reached
3. Show non-blocking transition prompt banners
4. Log transitions with detected reason

### Future: Auto-Advance (opt-in)
- Per-batch or global setting
- Auto-transitions with logged reasons
- Notification when auto-advanced

## Files Affected

### New Files
- `frontend/src/lib/components/batch/PhaseRecipe.svelte`
- `frontend/src/lib/components/batch/PhaseBrewDay.svelte`
- `frontend/src/lib/components/batch/PhaseFermentation.svelte`
- `frontend/src/lib/components/batch/PhaseConditioning.svelte`
- `frontend/src/lib/components/batch/PhaseComplete.svelte`
- `frontend/src/lib/components/batch/LifecycleStepper.svelte`
- `frontend/src/lib/components/batch/TransitionPrompt.svelte`
- `frontend/src/lib/components/batch/ConditioningProgress.svelte`

### Modified Files
- `frontend/src/routes/batches/[id]/+page.svelte` — gut conditional blocks, add tab/stepper navigation
- `frontend/src/lib/components/batch/MLPredictions.svelte` — phase-aware rendering
- `frontend/src/lib/components/FermentationStats.svelte` — phase-aware stats
- Backend: Possibly add transition detection endpoint or WebSocket event

### No Schema Changes Required
- Recipe `fermentation_steps` already exists with `type`, `temp_c`, `time_days`
- Batch status flow already supports all phases
- No new database tables needed
