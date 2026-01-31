# UI/UX Refactor Plan for Tilt UI

## Overview
This plan addresses the "vibe coded" UI/UX issues in the tilt_ui project by transforming inconsistent, inline-style-heavy components into a maintainable design system. It leverages existing CSS variables and Tailwind CSS for consistency, reusability, and accessibility improvements.

## Phase 1: Color Token Standardization
**Objectives**: Replace all hardcoded colors with design tokens to ensure consistency and themeability. This fixes inconsistent status colors (e.g., fermenting uses `#f59e0b` in some places, `--warning` in others).

**Tasks**:
1. **Audit and Map Colors**: Identify all hardcoded colors using grep. (Already done via exploration: 71+ instances.)
2. **Update `FermentationCard.svelte`**:
   - File: `/home/ladmin/Projects/tilt_ui/src/routes/(app)/batches/[id]/FermentationCard.svelte`
   - Lines 182, 187, 229, 255, 256, 258, 306, 319, 395: Inline styles like `style="background: {accentColor};"` where `accentColor` is hardcoded.
   - Old Snippet (Line 182-187):
     ```
     <div class="progress-bar" style="background: {accentColor};">
       <div class="progress-fill" style="width: {progress}%; background: linear-gradient(90deg, {accentColor}, {lighterAccent});"></div>
     </div>
     ```
   - Corrected Snippet:
     ```
     <div class="progress-bar bg-accent">
       <div class="progress-fill" style={`width: ${progress}%; background: linear-gradient(90deg, var(--recipe-accent), var(--recipe-accent-muted));`}></div>
     </div>
     ```
     - Rationale: Uses `--recipe-accent` token instead of prop-based colors. Assumes `accentColor` is derived from batch data; replace with tokens.

3. **Update `BatchCard.svelte`**:
   - File: `/home/ladmin/Projects/tilt_ui/src/routes/(app)/batches/BatchCard.svelte`
   - Lines 45-60: Hardcoded status colors like `style="background: {statusInfo.color};"` (e.g., `statusInfo.color = '#f59e0b'` for fermenting).
   - Old Snippet (Line 45-50):
     ```
     <div class="status-indicator" style="background: {statusInfo.color};">
       {statusInfo.label}
     </div>
     ```
   - Corrected Snippet:
     ```
     <div class="status-indicator bg-status-fermenting">
       {statusInfo.label}
     </div>
     ```
     - Add to `app.css`: `--status-fermenting: var(--recipe-accent);` and CSS class `.bg-status-fermenting { background: var(--status-fermenting); }`.

4. **Update `BatchAlertsCard.svelte`**:
   - File: `/home/ladmin/Projects/tilt_ui/src/routes/(app)/batches/BatchAlertsCard.svelte`
   - Lines 120-140: Hardcoded severity colors (e.g., `style="color: #ef4444;"` for errors).
   - Old Snippet (Line 120):
     ```
     <span style="color: #ef4444;">Critical</span>
     ```
   - Corrected Snippet:
     ```
     <span class="text-error">Critical</span>
     ```
     - Add to `app.css`: `--text-error: #ef4444;` and class `.text-error { color: var(--text-error); }`.

5. **Update `MLPredictions.svelte`**:
   - File: `/home/ladmin/Projects/tilt_ui/src/routes/(app)/batches/[id]/MLPredictions.svelte`
   - Lines 150-170: Inline styles for progress like `style="background: linear-gradient(to right, #22c55e, #84cc16);"`.
   - Old Snippet (Line 155):
     ```
     <div style="background: linear-gradient(to right, #22c55e, #84cc16); width: {confidence}%;"></div>
     ```
   - Corrected Snippet:
     ```
     <div class="confidence-bar" style={`width: ${confidence}%;`}></div>
     ```
     - Add CSS: `.confidence-bar { background: linear-gradient(to right, var(--activity-very-active), var(--activity-active)); }`.

**Rationale**: Ensures theme changes (e.g., dark mode) propagate everywhere. Improves consistency for users seeing uniform status indicators.
**Estimated Effort**: 1-2 days. Run `npm run typecheck` and visual tests post-changes.
**Dependencies**: None.

## Phase 2: Shared Component Creation
**Objectives**: Build reusable components to eliminate duplication (e.g., status badges in 5+ files).

**Tasks**:
1. **Create `StatusBadge.svelte`**:
   - New File: `/home/ladmin/Projects/tilt_ui/src/lib/components/StatusBadge.svelte`
   - Snippet:
     ```
     <script lang="ts">
       interface Props {
         status: 'fermenting' | 'conditioning' | 'completed' | 'archived';
         children: any;
       }
       let { status, children }: Props = $props();
     </script>

     <span class="status-badge status-{status}">
       {@render children()}
     </span>

     <style>
       .status-badge {
         @apply px-2 py-1 rounded-full text-xs font-medium;
       }
       .status-fermenting { @apply bg-status-fermenting text-on-accent; }
       .status-completed { @apply bg-positive-muted text-positive; }
       /* Add others */
     </style>
     ```

2. **Refactor `FermentationCard.svelte`**:
   - Replace lines 45-60 (status pill) with: `<StatusBadge status={batch.status}>{batch.status}</StatusBadge>`
   - Old Snippet (Line 45): `<div class="status" style="background: {statusColor};">{status}</div>`
   - Corrected: Import and use `StatusBadge`.

3. **Refactor `BatchCard.svelte`**:
   - Replace lines 45-50 with `<StatusBadge status={batch.status}>{statusInfo.label}</StatusBadge>`
   - Similar to above.

**Rationale**: Reduces code duplication, ensures consistent styling, and improves maintainability. Users get uniform badges across the app.
**Estimated Effort**: 2-3 days. Test component imports.
**Dependencies**: Phase 1 (tokens defined).

## Phase 3: Inline Style Elimination
**Objectives**: Move all `style=` attributes to CSS classes for better performance and maintainability.

**Tasks**:
1. **Update `+layout.svelte`**:
   - File: `/home/ladmin/Projects/tilt_ui/src/routes/+layout.svelte`
   - Lines 85, 89, 97, 101, 102, 132: Multiple inline styles (e.g., `style="backdrop-filter: blur(8px);"`).
   - Old Snippet (Line 85): `<nav style="backdrop-filter: blur(8px); background: rgba(0,0,0,0.5);">`
   - Corrected: `<nav class="nav-blur">` and add CSS: `.nav-blur { backdrop-filter: blur(8px); background: rgba(0,0,0,0.5); }`.

2. **Update `FermentationCard.svelte`**:
   - Move all 15+ inline styles (e.g., Line 395: `style="color: {textColor};"`) to component `<style>` or classes.

3. **Update `FermentationChart.svelte`**:
   - Lines 63-83: Remove color palette definition; use tokens. Replace 20+ inline styles with CSS variables.

**Rationale**: Inline styles are hard to override and hurt performance. CSS classes enable global theming.
**Estimated Effort**: 3-4 days. Use browser dev tools to verify styles.
**Dependencies**: Phases 1-2.

## Phase 4: Chart Improvements
**Objectives**: Standardize chart theming and add accessibility.

**Tasks**:
1. **Refactor `FermentationChart.svelte`**:
   - Lines 63-83: Remove hardcoded colors; use `--chart-*` tokens.
   - Add ARIA: `<svg role="img" aria-labelledby="chart-title">` and `<title id="chart-title">Fermentation Progress Chart</title>`.
   - Old Snippet (Line 70): `fill="#f59e0b"` → Corrected: `fill="var(--chart-fermenting)"`.

**Rationale**: Charts become theme-aware and screen-reader friendly.
**Estimated Effort**: 2 days.
**Dependencies**: Phase 1.

## Phase 5: Accessibility Enhancements
**Objectives**: Improve keyboard navigation and screen reader support.

**Tasks**:
1. **Update Charts and Interactions**: Add `tabindex` and ARIA to interactive elements in `FermentationChart.svelte` and `BatchCard.svelte`.
2. **Test with Tools**: Use axe-core or Lighthouse for validation.

**Rationale**: Ensures WCAG compliance for all users.
**Estimated Effort**: 1-2 days.
**Dependencies**: All previous phases.

## Phase 6: Documentation and Testing
**Objectives**: Document the design system and validate changes.

**Tasks**:
1. **Create Design System Doc**: New file `/home/ladmin/Projects/tilt_ui/docs/design-system.md` with token usage examples.
2. **Run Tests**: `npm run lint`, `npm run typecheck`, and manual UI tests.

**Rationale**: Prevents future "vibe coding."
**Estimated Effort**: 1 day.
**Dependencies**: All phases.

## Overall Strategy
- Leverage your existing design tokens (e.g., `--positive`, `--warning`) from `app.css` to eliminate hardcoded colors.
- Create reusable components to reduce duplication.
- Move from inline styles to CSS classes/modules for better maintainability and theming.
- Ensure responsive and accessible improvements without changing core logic.
- Total estimated effort: 4-6 weeks for one developer, with testing after each phase.

## Next Steps
1. Start with Phase 1: Color Token Standardization
2. Create shared components in Phase 2
3. Iterate through remaining phases
4. Run `npm run lint` and `npm run typecheck` after each phase</content>
<parameter name="filePath">docs/plans/ui-ux-refactor-plan.md