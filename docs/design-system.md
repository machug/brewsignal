# Tilt UI Design System

## Overview
This design system provides consistent guidelines for colors, typography, spacing, components, and interactions in the Tilt UI application. It builds on our existing CSS variables and Tailwind CSS setup to eliminate "vibe coding" and ensure maintainability.

## Colors

### Design Tokens
All colors use CSS custom properties defined in `app.css`. Never use hardcoded hex values—always reference these tokens.

```css
:root {
  /* Semantic Colors */
  --positive: #22c55e;
  --positive-muted: #dcfce7;
  --warning: #f59e0b;
  --warning-muted: #fef3c7;
  --error: #ef4444;
  --error-muted: #fecaca;
  --info: #3b82f6;
  --info-muted: #dbeafe;

  /* Recipe/Process Colors */
  --recipe-accent: #f59e0b;  /* Fermenting */
  --recipe-accent-muted: #fef3c7;
  --recipe-secondary: #8b5cf6;  /* Conditioning */
  --recipe-secondary-muted: #ede9fe;

  /* Status Colors */
  --status-fermenting: var(--recipe-accent);
  --status-conditioning: var(--recipe-secondary);
  --status-completed: var(--positive);
  --status-archived: var(--text-muted);

  /* Activity Levels */
  --activity-very-active: #22c55e;
  --activity-active: #84cc16;
  --activity-slowing: #eab308;
  --activity-complete: #6b7280;

  /* Chart Colors (updated Phase 4) */
  --chart-sg: var(--recipe-accent);
  --chart-sg-glow: rgba(245, 158, 11, 0.3);
  --chart-sg-fill: rgba(245, 158, 11, 0.1);
  --chart-temp: var(--tilt-blue);
  --chart-ambient: #22d3ee;
  --chart-chamber: var(--tilt-purple);
  --chart-trend: rgba(245, 158, 11, 0.5);
  --chart-anomaly: var(--negative);
  --chart-battery: var(--positive);
  --chart-grid: rgba(255, 255, 255, 0.04);
  --chart-axis: var(--gray-600);
  --chart-text: var(--text-muted);

  /* Tilt Device Colors */
  --tilt-red: #f87171;
  --tilt-green: #4ade80;
  --tilt-black: #71717a;
  --tilt-purple: #a78bfa;
  --tilt-orange: #fb923c;
  --tilt-blue: #60a5fa;
  --tilt-yellow: #facc15;
  --tilt-pink: #f472b6;

  /* Base Colors */
  --surface: #ffffff;
  --surface-secondary: #f8fafc;
  --text: #1e293b;
  --text-muted: #64748b;
  --text-inverse: #ffffff;
  --border: #e2e8f0;
  --border-muted: #f1f5f9;

  /* Dark Theme Overrides */
  .dark {
    --surface: #0f172a;
    --surface-secondary: #1e293b;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --text-inverse: #0f172a;
    --border: #334155;
    --border-muted: #1e293b;
  }
}
```

### Usage Guidelines
- **Status Indicators**: Use `--status-*` tokens for batch states
- **Activity Levels**: Use `--activity-*` for fermentation progress
- **Charts**: Use `--chart-*` for data visualization
- **Semantic Colors**: Use `--positive`, `--warning`, etc. for alerts and feedback

## Typography

### Font Stack
- **Primary**: Geist Sans (variable font)
- **Fallback**: -apple-system, BlinkMacSystemFont, sans-serif

### Scale
```css
--text-xs: 0.75rem;   /* 12px */
--text-sm: 0.875rem;  /* 14px */
--text-base: 1rem;    /* 16px */
--text-lg: 1.125rem;  /* 18px */
--text-xl: 1.25rem;   /* 20px */
--text-2xl: 1.5rem;   /* 24px */
--text-3xl: 1.875rem; /* 30px */
--text-4xl: 2.25rem;  /* 36px */
```

### Usage Classes
- `.text-xs`, `.text-sm`, etc. (Tailwind-like)
- `.font-medium`, `.font-semibold`, `.font-bold`

## Spacing

### Scale
```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
--space-20: 5rem;     /* 80px */
--space-24: 6rem;     /* 96px */
```

### Usage Classes
- `.p-*`, `.m-*` (padding/margin with space tokens)
- `.gap-*` for flex/grid spacing

## Components

### StatusBadge
Reusable component for status indicators.

```svelte
<!-- StatusBadge.svelte -->
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
  .status-fermenting {
    @apply bg-status-fermenting text-on-accent;
  }
  .status-conditioning {
    @apply bg-recipe-secondary-muted text-recipe-secondary;
  }
  .status-completed {
    @apply bg-positive-muted text-positive;
  }
  .status-archived {
    @apply bg-surface-secondary text-text-muted;
  }
</style>
```

### ProgressBar
Reusable progress indicator.

```svelte
<!-- ProgressBar.svelte -->
<script lang="ts">
  interface Props {
    value: number; // 0-100
    color?: string;
  }
  let { value, color = 'var(--recipe-accent)' }: Props = $props();
</script>

<div class="progress-bar">
  <div class="progress-fill" style="width: {value}%; background: {color};"></div>
</div>

<style>
  .progress-bar {
    @apply w-full h-2 bg-surface-secondary rounded-full overflow-hidden;
  }
  .progress-fill {
    @apply h-full rounded-full transition-all duration-300;
  }
</style>
```

### MetricDisplay
Consistent metric formatting.

```svelte
<!-- MetricDisplay.svelte -->
<script lang="ts">
  interface Props {
    label: string;
    value: string | number;
    unit?: string;
    trend?: 'up' | 'down' | 'neutral';
  }
  let { label, value, unit = '', trend }: Props = $props();
</script>

<div class="metric">
  <div class="metric-label">{label}</div>
  <div class="metric-value">
    {value}{unit}
    {#if trend}
      <span class="metric-trend metric-trend-{trend}">↗</span>
    {/if}
  </div>
</div>

<style>
  .metric {
    @apply text-center;
  }
  .metric-label {
    @apply text-sm text-text-muted mb-1;
  }
  .metric-value {
    @apply text-xl font-semibold text-text;
  }
  .metric-trend-up {
    @apply text-positive;
  }
  .metric-trend-down {
    @apply text-error;
  }
  .metric-trend-neutral {
    @apply text-text-muted;
  }
</style>
```

## Interaction States

### Buttons
- **Primary**: `.btn-primary` - `bg-recipe-accent text-on-accent`
- **Secondary**: `.btn-secondary` - `bg-surface-secondary text-text border`
- **Ghost**: `.btn-ghost` - `text-text-muted hover:bg-surface-secondary`

### Hover States
- Use opacity changes: `hover:opacity-80`
- Background changes: `hover:bg-surface-secondary`

### Focus States
- Always include: `focus:outline-none focus:ring-2 focus:ring-recipe-accent focus:ring-offset-2`

## Responsive Design

### Breakpoints
- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px

### Grid System
- Use CSS Grid with `gap-*` classes
- Mobile-first: default styles for small screens, add breakpoints for larger

### Touch Targets
- Minimum 44px height/width for touch interfaces

## Accessibility

### Color Contrast
- Text on backgrounds: 4.5:1 minimum
- Large text: 3:1 minimum
- Use design tokens which are pre-tested for contrast

### Keyboard Navigation
- All interactive elements focusable
- Logical tab order
- Escape to close modals
- Use `tabindex="-1"` for programmatically focused elements

### Screen Readers
- Use semantic HTML
- Add `aria-label` for icon-only buttons
- Add `aria-hidden="true"` for decorative icons
- `role` attributes where needed

### Modal Pattern (Phase 5)
```svelte
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="modal-overlay"
  onclick={() => (showModal = false)}
  onkeydown={(e) => e.key === 'Escape' && (showModal = false)}
  role="presentation"
>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    tabindex="-1"
  >
    <h2 id="modal-title">Modal Title</h2>
    <!-- content -->
  </div>
</div>
```

### Chart Accessibility
For charts using uPlot:
```svelte
<div
  class="chart-container"
  role="img"
  aria-label="Chart description"
>
  <span class="sr-only">
    Descriptive text for screen readers
  </span>
</div>
```

## Usage in Code

### DO Use
```svelte
<div class="bg-positive text-text-inverse p-4 rounded-lg">
  <StatusBadge status="completed">Done</StatusBadge>
</div>
```

### DON'T Use
```svelte
<div style="background: #22c55e; color: white; padding: 16px; border-radius: 8px;">
  <span style="background: #dcfce7; color: #22c55e;">Done</span>
</div>
```

## Maintenance
- Update this document when adding new tokens or components
- Run `npm run lint` and visual regression tests after changes
- Review color contrast with automated tools</content>
<parameter name="filePath">docs/design-system.md