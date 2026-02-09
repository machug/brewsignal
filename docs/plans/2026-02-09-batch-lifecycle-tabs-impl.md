# Batch Lifecycle Tabs — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the monolithic 2583-line batch detail page into tabbed phase components with a lifecycle stepper.

**Architecture:** Extract existing conditional rendering blocks from `+page.svelte` into dedicated phase components. Add tab navigation and a lifecycle stepper. No new features — pure refactor that preserves all existing functionality while establishing the architecture for future phase-specific enhancements.

**Tech Stack:** SvelteKit 5, Svelte 5 runes ($state, $derived, $props), TypeScript

**Worktree:** `/home/ladmin/Projects/brewsignal/brewsignal-web/.worktrees/lifecycle-tabs/`

---

## Task Overview

Tasks 1-6 are independent (new component files) and can be parallelized.
Task 7 depends on all of 1-6 (wires everything together in the page).

---

### Task 1: Create LifecycleStepper Component

**Files:**
- Create: `frontend/src/lib/components/batch/LifecycleStepper.svelte`

**What it does:** Horizontal progress stepper showing the batch lifecycle phases. Completed phases get checkmarks, current phase is highlighted, future phases are greyed out.

**Step 1: Create the component**

```svelte
<script lang="ts">
	import type { BatchStatus } from '$lib/api';
	import { statusConfig } from '$lib/components/status';

	interface Props {
		currentStatus: BatchStatus;
	}

	let { currentStatus }: Props = $props();

	const phases: { status: BatchStatus; label: string }[] = [
		{ status: 'planning', label: 'Recipe' },
		{ status: 'brewing', label: 'Brew Day' },
		{ status: 'fermenting', label: 'Fermentation' },
		{ status: 'conditioning', label: 'Conditioning' },
		{ status: 'completed', label: 'Complete' },
	];

	const statusOrder: Record<string, number> = {
		planning: 0,
		brewing: 1,
		fermenting: 2,
		conditioning: 3,
		completed: 4,
		archived: 4,
	};

	let currentIndex = $derived(statusOrder[currentStatus] ?? 0);

	function getPhaseState(phaseIndex: number): 'completed' | 'current' | 'future' {
		if (phaseIndex < currentIndex) return 'completed';
		if (phaseIndex === currentIndex) return 'current';
		return 'future';
	}
</script>

<div class="lifecycle-stepper">
	{#each phases as phase, i}
		{@const state = getPhaseState(i)}
		{#if i > 0}
			<div class="connector" class:completed={i <= currentIndex}></div>
		{/if}
		<div class="step" class:completed={state === 'completed'} class:current={state === 'current'} class:future={state === 'future'}>
			<div class="step-dot">
				{#if state === 'completed'}
					<svg class="check-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
				{/if}
			</div>
			<span class="step-label">{phase.label}</span>
		</div>
	{/each}
</div>
```

Styles: horizontal flex layout, dots connected by lines, completed=green with checkmark, current=accent color with pulse, future=muted. Use CSS variables from the existing theme (`var(--positive)`, `var(--accent)`, `var(--text-muted)`, `var(--border-subtle)`).

**Step 2: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/LifecycleStepper.svelte
git commit -m "feat: add LifecycleStepper component for batch lifecycle navigation"
```

---

### Task 2: Create PhaseRecipe Component

**Files:**
- Create: `frontend/src/lib/components/batch/PhaseRecipe.svelte`

**What it does:** Extract lines 575-606 of `+page.svelte` (planning phase). Shows "Ready to Brew?" action card and recipe targets.

**Step 1: Create the component**

Extract the planning phase block. Props needed:
- `batch: BatchResponse` — for recipe access
- `statusUpdating: boolean` — for button disabled state
- `onStartBrewDay: () => void` — callback for the button

```svelte
<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';

	interface Props {
		batch: BatchResponse;
		statusUpdating: boolean;
		onStartBrewDay: () => void;
	}

	let { batch, statusUpdating, onStartBrewDay }: Props = $props();
</script>
```

Template: Copy the `{#if batch.status === 'planning'}` block (lines 575-606) into this component's template, removing the outer `{#if}` since the parent controls which phase is shown. Replace `handleStartBrewDay` with `onStartBrewDay`.

Styles: Copy `.phase-action-card`, `.phase-icon`, `.phase-title`, `.phase-description`, `.start-brewday-btn`, `.btn-spinner`, `.btn-icon` from `+page.svelte` styles.

**Step 2: Verify build**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/PhaseRecipe.svelte
git commit -m "feat: extract PhaseRecipe component from batch detail page"
```

---

### Task 3: Create PhaseBrewDay Component

**Files:**
- Create: `frontend/src/lib/components/batch/PhaseBrewDay.svelte`

**What it does:** Extract lines 608-736 of `+page.svelte` (brewing phase). Shows brew day tools, chilling progress, pitch button.

**Step 1: Create the component**

Props needed:
- `batch: BatchResponse`
- `liveReading: TiltReading | null`
- `statusUpdating: boolean`
- `onStartFermentation: () => void`
- `onEdit: () => void` — for device card edit button

The component needs several derived values that are currently in the page script. Move these INTO the component:
- `isPrePitchChilling` (line 70-72)
- `pitchTempReached` (lines 75-78)
- `chillingProgress` (lines 81-93)

```svelte
<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BrewDayTimer from './BrewDayTimer.svelte';
	import BrewDayChecklist from './BrewDayChecklist.svelte';
	import BrewDayObservations from './BrewDayObservations.svelte';
	import BatchDeviceCard from './BatchDeviceCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';

	interface Props {
		batch: BatchResponse;
		liveReading: TiltReading | null;
		statusUpdating: boolean;
		onStartFermentation: () => void;
		onEdit: () => void;
		onBatchUpdate: (updated: BatchResponse) => void;
	}

	let { batch, liveReading, statusUpdating, onStartFermentation, onEdit, onBatchUpdate }: Props = $props();

	let tempUnit = $derived(getTempUnit());

	// Move derived values from page
	let isPrePitchChilling = $derived(
		(batch.status === 'planning' || batch.status === 'brewing') && batch.temp_target != null
	);

	let pitchTempReached = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch.temp_target) return false;
		return liveReading.temp <= batch.temp_target;
	});

	let chillingProgress = $derived.by(() => {
		if (!isPrePitchChilling || !liveReading?.temp || !batch.temp_target) return null;
		const estimatedStartTemp = batch.temp_target + 30;
		const currentTemp = liveReading.temp;
		const targetTemp = batch.temp_target;
		if (currentTemp <= targetTemp) return 100;
		if (currentTemp >= estimatedStartTemp) return 0;
		const progress = ((estimatedStartTemp - currentTemp) / (estimatedStartTemp - targetTemp)) * 100;
		return Math.min(100, Math.max(0, progress));
	});

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}
</script>
```

Template: Copy lines 608-736 (the `{:else if batch.status === 'brewing'}` block), removing outer condition. Replace direct function calls with prop callbacks. Replace `batch = updated` with `onBatchUpdate(updated)`.

Styles: Copy all brewing-phase related styles (`.brewing-phase`, `.phase-action-card.brewing`, `.phase-action-card.chilling`, `.phase-action-card.ready-to-pitch`, `.chilling-temp-display`, `.chilling-progress`, `.brewday-tools-grid`, `.start-fermentation-btn`, etc.)

**Step 2: Verify build**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/PhaseBrewDay.svelte
git commit -m "feat: extract PhaseBrewDay component from batch detail page"
```

---

### Task 4: Create PhaseFermentation Component

**Files:**
- Create: `frontend/src/lib/components/batch/PhaseFermentation.svelte`

**What it does:** Extract the fermenting-specific parts from lines 922-1170. This is the current `{:else}` block which handles both fermenting AND conditioning — we split it so this one only handles fermenting.

**Step 1: Create the component**

Props needed:
- `batch: BatchResponse`
- `progress: BatchProgressResponse | null`
- `liveReading: TiltReading | null`
- `controlStatus: BatchControlStatus | null`
- `controlEvents: ControlEvent[]`
- `hasTempControl: boolean`
- `heaterLoading: boolean`
- `tempControlCollapsed: boolean`
- `onOverride: (deviceType: 'heater' | 'cooler', state: 'on' | 'off' | null) => void`
- `onClearOverrides: () => void`
- `onTempControlToggle: () => void`

```svelte
<script lang="ts">
	import type { BatchResponse, BatchProgressResponse, BatchControlStatus, ControlEvent } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BatchFermentationCard from './BatchFermentationCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';
	import BatchAlertsCard from './BatchAlertsCard.svelte';
	import MLPredictions from './MLPredictions.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';
	import FermentationChart from '../FermentationChart.svelte';

	// ... props and derived values
</script>
```

Template: Copy the content-grid (lines 924-1132) — the two-column layout with:
- Left: BatchFermentationCard, BatchRecipeTargetsCard
- Right: BatchAlertsCard, MLPredictions, Temperature Control Card, Notes
- Below: FermentationChart

Do NOT include the conditioning tasting journal block (lines 1134-1169).

Styles: Copy `.content-grid`, `.stats-section`, `.info-section`, `.info-card`, `.temp-control-card`, all temperature control styles, `.chart-section`.

**Step 2: Verify build**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/PhaseFermentation.svelte
git commit -m "feat: extract PhaseFermentation component from batch detail page"
```

---

### Task 5: Create PhaseConditioning Component

**Files:**
- Create: `frontend/src/lib/components/batch/PhaseConditioning.svelte`

**What it does:** For Phase 1 (refactor only), this starts as a copy of PhaseFermentation but includes the tasting journal section from lines 1134-1169 prominently (not collapsed at bottom).

**Step 1: Create the component**

Same props as PhaseFermentation, plus:
- `tastingNotes: TastingNote[]`
- `tastingLoading: boolean`

Template: Same two-column layout as fermentation, but:
- Left column: BatchFermentationCard, BatchRecipeTargetsCard, then **Tasting Journal section** (moved up from bottom, not collapsible)
- Right column: MLPredictions, Temperature Control Card, Notes
- Below: FermentationChart

The tasting journal here should NOT be in a collapsible section — it's a primary element during conditioning. Copy the TastingNotesList rendering from lines 1134-1169 but without the collapsible wrapper.

**Step 2: Verify build**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/PhaseConditioning.svelte
git commit -m "feat: extract PhaseConditioning component from batch detail page"
```

---

### Task 6: Create PhaseComplete Component

**Files:**
- Create: `frontend/src/lib/components/batch/PhaseComplete.svelte`

**What it does:** Extract lines 738-920 of `+page.svelte` (completed phase). Shows batch summary, timeline, packaging, reflections, tasting journal.

**Step 1: Create the component**

Props needed:
- `batch: BatchResponse`
- `reflections: BatchReflection[]`
- `tastingNotes: TastingNote[]`
- `reflectionsLoading: boolean`
- `tastingLoading: boolean`
- `onBatchUpdate: (updated: BatchResponse) => void`
- `onTastingNotesReload: () => void`

Also needs these helper functions (copy from page script):
- `formatSG` (line 378-381)
- `formatDate` (lines 406-414)

```svelte
<script lang="ts">
	import type { BatchResponse } from '$lib/api';
	import type { BatchReflection } from '$lib/types/reflection';
	import type { TastingNote } from '$lib/types/tasting';
	import { formatGravity } from '$lib/stores/config.svelte';
	import PackagingInfo from './PackagingInfo.svelte';
	import TastingNotes from './TastingNotes.svelte';
	import TastingNotesList from './TastingNotesList.svelte';
	import ReflectionCard from './ReflectionCard.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';

	// ... props
	// ... local state for expand/collapse
	let reflectionsExpanded = $state(true);
	let tastingExpanded = $state(true);
</script>
```

Template: Copy lines 738-920, the entire `{:else if batch.status === 'completed'}` block. Remove outer condition.

Styles: Copy `.completed-phase`, `.batch-summary-card`, `.summary-title`, `.summary-stats`, `.summary-stat`, `.stat-label`, `.stat-value`, `.timeline-card`, `.timeline-*`, `.postmortem-section`, `.section-header`, `.section-*`, `.reflections-grid`, `.add-first-btn`.

**Step 2: Verify build**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/batch/PhaseComplete.svelte
git commit -m "feat: extract PhaseComplete component from batch detail page"
```

---

### Task 7: Refactor +page.svelte with Tab Navigation

**Depends on:** Tasks 1-6

**Files:**
- Modify: `frontend/src/routes/batches/[id]/+page.svelte`

**What it does:** Replace the conditional phase blocks with tab navigation + the new phase components. This is the integration task.

**Step 1: Add imports and tab state**

At top of script, add:
```typescript
import LifecycleStepper from '$lib/components/batch/LifecycleStepper.svelte';
import PhaseRecipe from '$lib/components/batch/PhaseRecipe.svelte';
import PhaseBrewDay from '$lib/components/batch/PhaseBrewDay.svelte';
import PhaseFermentation from '$lib/components/batch/PhaseFermentation.svelte';
import PhaseConditioning from '$lib/components/batch/PhaseConditioning.svelte';
import PhaseComplete from '$lib/components/batch/PhaseComplete.svelte';
```

Add tab state:
```typescript
type PhaseTab = 'planning' | 'brewing' | 'fermenting' | 'conditioning' | 'completed';

const tabConfig: { status: PhaseTab; label: string }[] = [
	{ status: 'planning', label: 'Recipe' },
	{ status: 'brewing', label: 'Brew Day' },
	{ status: 'fermenting', label: 'Fermentation' },
	{ status: 'conditioning', label: 'Conditioning' },
	{ status: 'completed', label: 'Complete' },
];

// Active tab defaults to current batch status
let activeTab = $state<PhaseTab>('planning');

// When batch loads or status changes, default to current phase tab
$effect(() => {
	if (batch?.status) {
		const status = batch.status === 'archived' ? 'completed' : batch.status;
		activeTab = status as PhaseTab;
	}
});
```

**Step 2: Replace template**

Replace the entire phase-specific content block (lines 574-1170) with:

```svelte
<!-- Lifecycle Stepper -->
<LifecycleStepper currentStatus={batch.status} />

<!-- Phase Tabs -->
<div class="phase-tabs">
	{#each tabConfig as tab}
		{@const statusOrder = { planning: 0, brewing: 1, fermenting: 2, conditioning: 3, completed: 4 }}
		{@const currentOrder = statusOrder[batch.status === 'archived' ? 'completed' : batch.status] ?? 0}
		{@const tabOrder = statusOrder[tab.status]}
		<button
			type="button"
			class="phase-tab"
			class:active={activeTab === tab.status}
			class:future={tabOrder > currentOrder}
			onclick={() => activeTab = tab.status}
		>
			{tab.label}
		</button>
	{/each}
</div>

<!-- Phase Content -->
<div class="phase-content">
	{#if activeTab === 'planning'}
		<PhaseRecipe {batch} {statusUpdating} onStartBrewDay={handleStartBrewDay} />
	{:else if activeTab === 'brewing'}
		<PhaseBrewDay
			{batch}
			{liveReading}
			{statusUpdating}
			onStartFermentation={handleStartFermentation}
			onEdit={() => (isEditing = true)}
			onBatchUpdate={(updated) => batch = updated}
		/>
	{:else if activeTab === 'fermenting'}
		<PhaseFermentation
			{batch}
			{progress}
			{liveReading}
			{controlStatus}
			{controlEvents}
			{hasTempControl}
			{heaterLoading}
			{tempControlCollapsed}
			onOverride={handleOverride}
			onClearOverrides={handleClearAllOverrides}
			onTempControlToggle={() => tempControlCollapsed = !tempControlCollapsed}
		/>
	{:else if activeTab === 'conditioning'}
		<PhaseConditioning
			{batch}
			{progress}
			{liveReading}
			{controlStatus}
			{controlEvents}
			{hasTempControl}
			{heaterLoading}
			{tempControlCollapsed}
			{tastingNotes}
			{tastingLoading}
			onOverride={handleOverride}
			onClearOverrides={handleClearAllOverrides}
			onTempControlToggle={() => tempControlCollapsed = !tempControlCollapsed}
		/>
	{:else if activeTab === 'completed'}
		<PhaseComplete
			{batch}
			{reflections}
			{tastingNotes}
			{reflectionsLoading}
			{tastingLoading}
			onBatchUpdate={(updated) => batch = updated}
			onTastingNotesReload={loadTastingNotes}
		/>
	{/if}
</div>
```

**Step 3: Remove extracted code**

Remove from `+page.svelte`:
- The old conditional blocks (lines 574-1170)
- The derived values moved to PhaseBrewDay (`isPrePitchChilling`, `pitchTempReached`, `chillingProgress`)
- Styles that were moved to phase components
- Old component imports that are no longer directly used (BrewDayTimer, BrewDayChecklist, etc.)

Keep in `+page.svelte`:
- All state declarations (batch, progress, controlStatus, etc.)
- All async functions (loadBatch, handleStatusChange, handleOverride, etc.)
- WebSocket logic
- Batch header, loading/error states, delete modal
- Readings paused banner (shared across fermenting/conditioning)

**Step 4: Add tab styles**

```css
.phase-tabs {
	display: flex;
	gap: 0;
	border-bottom: 1px solid var(--border-subtle);
	margin-bottom: 1.5rem;
	overflow-x: auto;
}

.phase-tab {
	padding: 0.75rem 1rem;
	font-size: 0.8125rem;
	font-weight: 500;
	color: var(--text-muted);
	background: none;
	border: none;
	border-bottom: 2px solid transparent;
	cursor: pointer;
	transition: all 0.15s ease;
	white-space: nowrap;
}

.phase-tab:hover:not(.future) {
	color: var(--text-secondary);
}

.phase-tab.active {
	color: var(--accent);
	border-bottom-color: var(--accent);
}

.phase-tab.future {
	opacity: 0.4;
	cursor: default;
}
```

**Step 5: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors, all types resolved

**Step 6: Visual verification**

Run: `cd frontend && npm run dev`
Manually verify:
- Planning batch shows Recipe tab active
- Fermenting batch shows Fermentation tab active
- Can click between tabs
- All existing functionality preserved

**Step 7: Commit**

```bash
git add frontend/src/routes/batches/[id]/+page.svelte
git commit -m "feat: refactor batch detail page with lifecycle tabs and phase components"
```

---

### Task 8: Load data for all phase tabs

**Depends on:** Task 7

**Files:**
- Modify: `frontend/src/routes/batches/[id]/+page.svelte`

**What it does:** Currently `loadBatch()` only loads progress for fermenting/conditioning/completed and reflections/tasting for completed/conditioning. Since users can now click back to view any phase, we should load progress and related data more eagerly.

**Step 1: Update loadBatch**

Change the conditional loading in `loadBatch()` (lines 118-149) to always load progress if the batch has ever been in fermentation (i.e., status is fermenting, conditioning, or completed). Also load reflections/tasting for all post-fermentation batches.

This is a minor change — just ensure the existing conditionals still cover the tab switching scenario. The current logic should already work since it checks the batch status, not which tab is active.

**Step 2: Verify and commit**

```bash
git commit -m "fix: ensure batch data loads for all accessible phase tabs"
```

---

## Parallelization Guide

```
Tasks 1-6: ALL PARALLEL (independent new files)
   ├── Task 1: LifecycleStepper
   ├── Task 2: PhaseRecipe
   ├── Task 3: PhaseBrewDay
   ├── Task 4: PhaseFermentation
   ├── Task 5: PhaseConditioning
   └── Task 6: PhaseComplete
         │
         ▼
Task 7: Refactor +page.svelte (depends on 1-6)
         │
         ▼
Task 8: Data loading adjustments (depends on 7)
```

## Important Notes

- **Working in worktree:** All paths are relative to `/home/ladmin/Projects/brewsignal/brewsignal-web/.worktrees/lifecycle-tabs/`
- **No backend changes:** This is purely frontend refactoring
- **Preserve all styles:** Each phase component must carry its own styles (copied from `+page.svelte`). Don't lose any existing styling.
- **Svelte 5 runes:** Use `$state`, `$derived`, `$props`, `$effect` — NOT legacy `let x = ...` reactive declarations
- **Type imports:** Use `import type { ... }` for type-only imports
- **Build check:** `cd frontend && npm run check` is the verification command (svelte-check)
