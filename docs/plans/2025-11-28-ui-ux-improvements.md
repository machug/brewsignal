# TiltUI UI/UX Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Strip back TiltUI's visual design to fundamentals - removing decorative elements that signal "AI-generated" and establishing a restrained, professional aesthetic. Then improve UX with better layout, alerts handling, and accessibility.

**Architecture:** Frontend-only changes using Svelte 5 with runes, Tailwind CSS, and CSS custom properties. The refined design prioritizes typography, spacing, and information hierarchy over decoration.

**Tech Stack:** Svelte 5, Tailwind CSS, CSS custom properties, Geist font family, localStorage for persistence

**Design Principles:**
1. One typeface, used well (Geist or system fallback)
2. Monochromatic grays + single blue accent used sparingly
3. No textures, glows, or decorative gradients
4. Depth through spacing, not shadows
5. Motion for function only (150ms state transitions)

---

## Development Environment

**Local dev machine:** Working directory is `/home/ladmin/Projects/tilt_ui`

**Raspberry Pi (test/preview box):**
- IP: `192.168.4.117`
- SSH: `sshpass -p 'tilt' ssh pi@192.168.4.117`
- App URL: `http://192.168.4.117:8080/`

**Deployment workflow after each task:**
1. Commit changes to `dev` branch and push
2. SSH to Pi: `sshpass -p 'tilt' ssh pi@192.168.4.117`
3. Pull changes: `cd /opt/tiltui && git pull`
4. Restart service: `sudo systemctl restart tiltui`
5. Verify at `http://192.168.4.117:8080/`

**One-liner for deployment:**
```bash
git push && sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Use Chrome DevTools MCP to visually verify changes after deployment.

---

## Task 0: Theme Foundation - Strip and Refine

**Problem:** Current design has amber glows, grain textures, trendy Outfit font, and overused accent colors that signal "AI-generated." Need to establish restrained, professional foundation.

**Files:**
- Modify: `frontend/src/app.css`

**Step 1: Replace the entire CSS custom properties section**

Replace the current `:root` block and remove decorative styles:

```css
/* uPlot chart styles - must be first */
@import 'uplot/dist/uPlot.min.css';
@import 'tailwindcss';

/* Single font family - Geist with system fallback */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap');

:root {
  /* Font stacks */
  --font-sans: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;

  /* True neutral grays - zinc scale, no warm/cool tint */
  --gray-950: #09090b;
  --gray-900: #18181b;
  --gray-850: #1f1f23;
  --gray-800: #27272a;
  --gray-700: #3f3f46;
  --gray-600: #52525b;
  --gray-500: #71717a;
  --gray-400: #a1a1aa;
  --gray-300: #d4d4d8;
  --gray-200: #e4e4e7;
  --gray-100: #f4f4f5;
  --gray-50: #fafafa;

  /* Semantic background tokens */
  --bg-base: var(--gray-950);
  --bg-surface: var(--gray-900);
  --bg-elevated: var(--gray-850);
  --bg-hover: var(--gray-800);

  /* Legacy aliases for compatibility during migration */
  --bg-deep: var(--bg-base);
  --bg-primary: var(--bg-surface);
  --bg-card: var(--bg-surface);

  /* Text hierarchy */
  --text-primary: var(--gray-50);
  --text-secondary: var(--gray-400);
  --text-muted: var(--gray-500);

  /* Borders - subtle, structural */
  --border-subtle: var(--gray-850);
  --border-default: var(--gray-700);

  /* Single accent: calm blue. Used sparingly for interactive states only. */
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --accent-muted: rgba(59, 130, 246, 0.15);

  /* Semantic colors - functional only */
  --positive: #22c55e;
  --warning: #eab308;
  --negative: #ef4444;

  /* Tilt colors - slightly muted for dark background */
  --tilt-red: #f87171;
  --tilt-green: #4ade80;
  --tilt-black: #71717a;
  --tilt-purple: #a78bfa;
  --tilt-orange: #fb923c;
  --tilt-blue: #60a5fa;
  --tilt-yellow: #facc15;
  --tilt-pink: #f472b6;

  /* Spacing scale - 4px base */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  /* Single transition timing */
  --transition: 150ms ease;
}
```

**Step 2: Update base styles**

```css
html {
  background-color: var(--bg-base);
  color: var(--text-primary);
}

body {
  margin: 0;
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  letter-spacing: -0.01em;
  -webkit-font-smoothing: antialiased;
}

/* Monospace for readings */
.font-mono {
  font-family: var(--font-mono);
  letter-spacing: -0.02em;
}
```

**Step 3: Remove decorative styles**

Delete these sections entirely:
- The `body::after` grain texture overlay
- The `.card-glow` class and hover effects
- The `.reading-glow` class
- The `@keyframes pulse-soft` animation (keep fade-in-up)

**Step 4: Simplify remaining utility classes**

```css
/* Simple fade-in for page load */
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.animate-fade-in {
  animation: fade-in 0.2s ease-out;
}

/* Custom scrollbar - minimal */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--gray-700);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--gray-600);
}

/* uPlot overrides - simplified */
.u-wrap {
  font-family: var(--font-mono);
}

.u-legend {
  display: none;
}

.u-cursor-x,
.u-cursor-y {
  border-color: var(--gray-600) !important;
}

.u-select {
  background: var(--accent-muted) !important;
}
```

**Step 5: Verify the build succeeds**

Run: `cd frontend && npm run build`
Expected: Build completes (may have style warnings we'll fix in later tasks)

**Step 6: Commit and deploy**

```bash
git add frontend/src/app.css
git commit -m "refactor(ui): establish restrained design foundation

- Replace Outfit with Geist font family
- Switch to neutral zinc gray scale
- Remove amber accent colors
- Remove grain texture overlay
- Remove glow effects
- Add single blue accent for interactive states
- Simplify animations to functional transitions"
git push
```

**Step 7: Deploy to Pi and verify**

```bash
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Use Chrome DevTools MCP to verify at http://192.168.4.117:8080/

---

## Task 1: Update TiltCard Component Styling

**Problem:** TiltCard still uses old color variables and glow classes. Update to new design system.

**Files:**
- Modify: `frontend/src/lib/components/TiltCard.svelte`

**Step 1: Remove glow class from container**

```svelte
<!-- Replace the root div (around line 98) -->
<div
    class="rounded-lg overflow-hidden animate-fade-in"
    style="background: var(--bg-surface); border: 1px solid var(--border-subtle);"
>
```

**Step 2: Simplify accent bar**

```svelte
<!-- Update accent bar (around line 104) -->
<div
    class="h-0.5"
    style="background: {accentColor};"
></div>
```

Remove the `box-shadow` glow from the accent bar.

**Step 3: Update reading display styles**

```svelte
<!-- Update gravity reading (around line 169) -->
<div
    class="rounded-md p-4 text-center"
    style="background: var(--bg-elevated);"
>
    <p class="text-3xl font-medium font-mono tracking-tight" style="color: var(--text-primary);">
        {formatSG(tilt.sg)}
    </p>
    <p class="text-[11px] text-[var(--text-muted)] uppercase tracking-wider mt-1 font-medium">
        Gravity
    </p>
</div>
```

Remove the `reading-glow` class from readings.

**Step 4: Simplify card hover in styles section**

```css
/* Remove .card-glow styles, replace with simple hover */
.card:hover {
    border-color: var(--border-default);
}
```

**Step 5: Update expand button to use accent**

```css
.expand-btn:hover {
    color: var(--accent);
    border-color: var(--accent-muted);
    background: var(--accent-muted);
}
```

**Step 6: Verify changes**

Run: `npm run build` in frontend directory
Open: http://192.168.4.117:8080/
Expected: Card has cleaner look - no glows, simpler borders, readable text

**Step 7: Commit and deploy**

```bash
git add frontend/src/lib/components/TiltCard.svelte
git commit -m "refactor(ui): simplify TiltCard to restrained design

- Remove glow effects from card and readings
- Thin accent bar without shadow
- Use neutral backgrounds
- Accent color only on interactive hover"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/

---

## Task 2: Update Layout Navigation

**Problem:** Navigation uses amber accent and inline styles. Update to new design system.

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`

**Step 1: Update logo accent color**

```svelte
<!-- Update logo span (around line 65) -->
<span class="text-lg font-semibold tracking-tight" style="color: var(--text-primary);">
    Tilt<span style="color: var(--accent);">UI</span>
</span>
```

**Step 2: Update logo icon background**

```svelte
<!-- Update logo icon (around line 59) -->
<div
    class="w-9 h-9 rounded-lg flex items-center justify-center"
    style="background: var(--accent);"
>
    <span class="text-lg">🍺</span>
</div>
```

Remove the gradient and box-shadow.

**Step 3: Add nav-link styles using new accent**

```css
/* In <style> section */
.nav-link {
    position: relative;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-secondary);
    background: transparent;
    border-radius: 0.375rem;
    transition: color var(--transition), background var(--transition);
}

.nav-link:hover {
    color: var(--text-primary);
}

.nav-link.active {
    color: var(--text-primary);
    background: var(--bg-elevated);
}

.nav-link.active::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 1.5rem;
    height: 2px;
    background: var(--accent);
    border-radius: 1px;
}
```

**Step 4: Simplify connection status indicator**

```svelte
<!-- Update connection status (around line 113) -->
<div
    class="flex items-center gap-2 px-3 py-1.5 rounded-full"
    style="background: var(--bg-elevated);"
>
    <span
        class="w-2 h-2 rounded-full"
        style="background: {tiltsState.connected ? 'var(--positive)' : 'var(--text-muted)'};"
    ></span>
    <span class="text-xs font-medium hidden sm:inline" style="color: var(--text-muted);">
        {tiltsState.connected ? 'Live' : 'Offline'}
    </span>
</div>
```

Remove the pulse animation class.

**Step 5: Simplify heater indicator**

```svelte
<!-- Update heater indicator (around line 94) -->
{#if showHeaterIndicator && tiltsState.heater.available}
    <div
        class="flex items-center gap-2 px-3 py-1.5 rounded-full"
        style="background: {tiltsState.heater.state === 'on' ? 'rgba(239, 68, 68, 0.1)' : 'var(--bg-elevated)'};"
    >
        <span class="text-sm" style="opacity: {tiltsState.heater.state === 'on' ? 1 : 0.4};">🔥</span>
        <span
            class="text-xs font-medium uppercase tracking-wide hidden sm:inline"
            style="color: {tiltsState.heater.state === 'on' ? 'var(--negative)' : 'var(--text-muted)'};"
        >
            {tiltsState.heater.state === 'on' ? 'Heating' : 'Off'}
        </span>
    </div>
{/if}
```

No pulse animation - static is fine.

**Step 6: Verify changes**

Run: `npm run build` in frontend directory
Expected: Navigation uses blue accent, cleaner indicators

**Step 7: Commit and deploy**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "refactor(ui): update navigation to restrained design

- Blue accent on logo and active nav
- Remove pulse animations from status indicators
- Simplify heater indicator styling"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/

---

## Task 3: Update Dashboard Page Styles

**Problem:** Dashboard page has amber-colored alert badges and styling. Update to new system.

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

**Step 1: Update alerts banner styling**

```css
/* Replace alerts-banner styles */
.alerts-banner {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--warning);
    border-radius: 0.375rem;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
}

.alerts-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-primary);
}

.alerts-title svg {
    width: 1.25rem;
    height: 1.25rem;
    color: var(--warning);
}

.alerts-count {
    background: var(--warning);
    color: var(--gray-950);
    font-size: 0.625rem;
    font-weight: 700;
    padding: 0.125rem 0.375rem;
    border-radius: 9999px;
    margin-left: 0.5rem;
}

.alert-item {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    padding-left: 0.5rem;
    border-left: 2px solid var(--gray-700);
}

.show-more-btn {
    font-size: 0.75rem;
    color: var(--accent);
    background: none;
    border: none;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    margin-top: 0.25rem;
}

.show-more-btn:hover {
    text-decoration: underline;
}
```

**Step 2: Update ambient card styling**

```css
.ambient-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.375rem;
    padding: 1rem 1.25rem;
    margin-top: 1.5rem;
}

.ambient-value .value {
    font-size: 1.5rem;
    font-weight: 500;
    font-family: var(--font-mono);
    color: var(--text-primary);
}
```

**Step 3: Update forecast card styling**

```css
.forecast-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.375rem;
    padding: 1rem 1.25rem;
    margin-top: 1.5rem;
}

.forecast-day {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    min-width: 4.5rem;
    background: var(--bg-elevated);
    border-radius: 0.375rem;
}

.temp-high {
    font-size: 0.875rem;
    font-weight: 500;
    font-family: var(--font-mono);
    color: var(--text-primary);
}

.temp-low {
    font-size: 0.75rem;
    font-family: var(--font-mono);
    color: var(--text-muted);
}
```

**Step 4: Change weather icons to use text-secondary instead of amber**

```css
.weather-icon {
    width: 1.75rem;
    height: 1.75rem;
    color: var(--text-secondary);
}
```

**Step 5: Add alert localStorage persistence and collapse (from original Task 2)**

Add the localStorage persistence logic for dismissed alerts:

```typescript
let alertsDismissed = $state(false);
let alertsCollapsed = $state(false);

onMount(() => {
    const dismissed = localStorage.getItem('tiltui_alerts_dismissed');
    const dismissedTime = localStorage.getItem('tiltui_alerts_dismissed_time');
    if (dismissed === 'true' && dismissedTime) {
        const elapsed = Date.now() - parseInt(dismissedTime, 10);
        if (elapsed < 6 * 60 * 60 * 1000) {
            alertsDismissed = true;
        }
    }
    // ... rest of onMount
});

function dismissAlerts() {
    alertsDismissed = true;
    localStorage.setItem('tiltui_alerts_dismissed', 'true');
    localStorage.setItem('tiltui_alerts_dismissed_time', Date.now().toString());
}
```

**Step 6: Verify changes**

Run: `npm run build` in frontend directory
Expected: Dashboard uses neutral colors, warning yellow for alerts only

**Step 7: Commit and deploy**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "refactor(ui): update dashboard to restrained design

- Neutral alert banner with yellow left border
- Remove amber from weather icons
- Simplify card backgrounds
- Add alerts dismiss persistence"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/

---

## Task 4: Update System Page Styles

**Problem:** System page has amber toggle accents and button styles.

**Files:**
- Modify: `frontend/src/routes/system/+page.svelte`

**Step 1: Update toggle/switch active states**

Find toggle buttons and update active state to use accent:

```css
/* Toggle active state */
.toggle-active {
    background: var(--accent);
}
```

**Step 2: Update primary buttons**

```css
/* Primary button */
.btn-primary {
    background: var(--accent);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 0.375rem;
    font-weight: 500;
    border: none;
    cursor: pointer;
    transition: background var(--transition);
}

.btn-primary:hover {
    background: var(--accent-hover);
}
```

**Step 3: Update unit toggle buttons (temperature °C/°F)**

```css
.unit-btn {
    min-width: 2.75rem;
    min-height: 2.75rem;
    padding: 0.5rem 0.75rem;
    font-weight: 500;
    border-radius: 0.375rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition);
}

.unit-btn:hover {
    border-color: var(--border-default);
    color: var(--text-primary);
}

.unit-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
}
```

**Step 4: Update section headings to be simpler**

```css
.section-heading {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 1rem;
}
```

**Step 5: Verify changes**

Run: `npm run build` in frontend directory
Expected: System page uses blue for active toggles and primary buttons

**Step 6: Commit and deploy**

```bash
git add frontend/src/routes/system/+page.svelte
git commit -m "refactor(ui): update system page to restrained design

- Blue accent for active toggles
- Simplified button styles
- Improved touch targets on unit toggles"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/system

---

## Task 5: Update Calibration and Logging Pages

**Problem:** These pages may still reference old color variables.

**Files:**
- Modify: `frontend/src/routes/calibration/+page.svelte`
- Modify: `frontend/src/routes/logging/+page.svelte`

**Step 1: Audit calibration page for old styles**

Search for any amber/amber-glow references and replace with new variables.

**Step 2: Update primary buttons on both pages**

Ensure save/add buttons use:
```css
background: var(--accent);
```

**Step 3: Update any toggle switches**

Ensure active state uses:
```css
background: var(--accent);
```

**Step 4: Verify changes**

Run: `npm run build` in frontend directory
Visit /calibration and /logging pages
Expected: Consistent blue accents, neutral backgrounds

**Step 5: Commit and deploy**

```bash
git add frontend/src/routes/calibration/+page.svelte frontend/src/routes/logging/+page.svelte
git commit -m "refactor(ui): update calibration and logging pages to restrained design"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/calibration and http://192.168.4.117:8080/logging

---

## Task 6: Update TiltChart Component

**Problem:** Chart may have amber-colored elements and loading state needs skeleton.

**Files:**
- Modify: `frontend/src/lib/components/TiltChart.svelte`

**Step 1: Update time range button active state**

```css
.time-btn.active {
    background: var(--bg-elevated);
    color: var(--text-primary);
    border-color: var(--border-default);
}
```

Remove any amber coloring.

**Step 2: Add simple loading skeleton**

```svelte
{#if loading}
    <div class="py-8 flex flex-col items-center gap-3">
        <div class="w-full h-48 bg-[var(--bg-elevated)] rounded animate-pulse"></div>
        <span class="text-sm text-[var(--text-muted)]">Loading chart...</span>
    </div>
{:else}
    <!-- chart content -->
{/if}
```

**Step 3: Update legend colors if custom**

Ensure chart series colors use tilt color variables, not amber.

**Step 4: Verify changes**

Run: `npm run build` in frontend directory
Expand chart on dashboard
Expected: Neutral time buttons, simple loading state

**Step 5: Commit and deploy**

```bash
git add frontend/src/lib/components/TiltChart.svelte
git commit -m "refactor(ui): update TiltChart to restrained design

- Neutral time range buttons
- Simple loading skeleton
- Remove amber from chart elements"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually by expanding a TiltCard at http://192.168.4.117:8080/

---

## Task 7: Improve Single-Tilt Dashboard Layout

**Problem:** When only one Tilt is active, the card uses ~35% viewport width, wasting space.

**Files:**
- Modify: `frontend/src/routes/+page.svelte`
- Modify: `frontend/src/lib/components/TiltCard.svelte`

**Step 1: Add wide prop to TiltCard**

```svelte
interface Props {
    tilt: TiltReading;
    expanded?: boolean;
    wide?: boolean;
    onToggleExpand?: () => void;
}

let { tilt, expanded = false, wide = false, onToggleExpand }: Props = $props();
```

**Step 2: Add wide class to container**

```svelte
<div
    class="rounded-lg overflow-hidden animate-fade-in"
    class:expanded
    class:wide
    style="background: var(--bg-surface); border: 1px solid var(--border-subtle);"
>
```

**Step 3: Add wide mode styles**

```css
.wide {
    max-width: 28rem;
}

@media (min-width: 768px) {
    .wide {
        max-width: 36rem;
    }
}

.wide .reading-value {
    font-size: 2.5rem;
}
```

**Step 4: Update +page.svelte grid**

```svelte
<div class="tilt-grid" class:single-tilt={tiltsList.length === 1}>
    {#each tiltsList as tilt (tilt.id)}
        <TiltCard
            {tilt}
            expanded={expandedTiltId === tilt.id}
            wide={tiltsList.length === 1}
            onToggleExpand={() => toggleExpand(tilt.id)}
        />
    {/each}
</div>
```

```css
.tilt-grid.single-tilt {
    display: flex;
    justify-content: center;
}
```

**Step 5: Verify changes**

Run: `npm run build` in frontend directory
Expected: Single tilt card is centered and larger

**Step 6: Commit and deploy**

```bash
git add frontend/src/routes/+page.svelte frontend/src/lib/components/TiltCard.svelte
git commit -m "feat(ui): center and enlarge single-tilt dashboard layout"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify visually at http://192.168.4.117:8080/

---

## Task 8: Add Mobile Menu Animation

**Problem:** Mobile menu appears/disappears abruptly.

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`

**Step 1: Import slide transition**

```svelte
import { slide } from 'svelte/transition';
```

**Step 2: Add transition to mobile menu**

```svelte
{#if mobileMenuOpen}
    <div
        class="md:hidden"
        style="background: var(--bg-surface); border-top: 1px solid var(--border-subtle);"
        transition:slide={{ duration: 150 }}
    >
        <!-- menu content -->
    </div>
{/if}
```

**Step 3: Verify changes**

Test on mobile viewport, toggle menu
Expected: Menu slides in/out smoothly

**Step 4: Commit and deploy**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "feat(ui): add slide animation to mobile menu"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Test on mobile viewport at http://192.168.4.117:8080/

---

## Task 9: Add Signal Strength Tooltip

**Problem:** RSSI number alone doesn't communicate signal quality.

**Files:**
- Modify: `frontend/src/lib/components/TiltCard.svelte`

**Step 1: Update getSignalStrength to include label**

```typescript
function getSignalStrength(rssi: number): { bars: number; color: string; label: string } {
    if (rssi >= -50) return { bars: 4, color: 'var(--positive)', label: 'Excellent' };
    if (rssi >= -60) return { bars: 3, color: 'var(--positive)', label: 'Good' };
    if (rssi >= -70) return { bars: 2, color: 'var(--warning)', label: 'Fair' };
    return { bars: 1, color: 'var(--negative)', label: 'Weak' };
}
```

**Step 2: Add title attribute**

```svelte
<div class="flex flex-col items-end gap-1" title="{signal.label} signal ({tilt.rssi} dBm)">
```

**Step 3: Commit and deploy**

```bash
git add frontend/src/lib/components/TiltCard.svelte
git commit -m "feat(ui): add signal strength description tooltip"
git push
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

Verify tooltip by hovering over signal bars at http://192.168.4.117:8080/

---

## Task 10: Final Build, Test, and Deploy

**Files:**
- All modified files

**Step 1: Run full build**

```bash
cd frontend && npm run build
```

**Step 2: Copy to backend static**

```bash
cp -r build/* ../backend/static/
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final build with restrained UI design

Complete visual refresh:
- Geist font family
- Neutral zinc gray palette
- Single blue accent for interactive states
- Removed all amber/gold styling
- Removed textures and glow effects
- Simplified animations to functional transitions"
git push
```

**Step 4: Deploy to Pi**

```bash
sshpass -p 'tilt' ssh pi@192.168.4.117 'cd /opt/tiltui && git pull && sudo systemctl restart tiltui'
```

**Step 5: Visual audit all pages**

Use Chrome DevTools MCP to verify at http://192.168.4.117:8080/:

- Dashboard: Neutral colors, blue accents only on interactive
- Logging: Consistent button styles
- Calibration: Clean form styling
- System: Blue toggles and buttons

**Step 6: Test mobile responsiveness**

Chrome DevTools at 375px width - toggle mobile menu, verify slide animation

---

## Summary

| Task | Description | Focus |
|------|-------------|-------|
| 0 | Theme foundation | app.css - colors, fonts, remove decorations |
| 1 | TiltCard update | Remove glows, simplify card styling |
| 2 | Layout navigation | Blue accent, remove pulse animations |
| 3 | Dashboard page | Neutral alerts, simplified cards |
| 4 | System page | Blue toggles and buttons |
| 5 | Calibration/Logging | Consistent styling |
| 6 | TiltChart | Neutral buttons, loading skeleton |
| 7 | Single-tilt layout | Centered, larger card |
| 8 | Mobile menu | Slide animation |
| 9 | Signal tooltip | Descriptive hover text |
| 10 | Final build | Test and deploy |

**Design changes:**
- Outfit → Geist (or system fonts)
- Amber palette → Single blue accent
- Grain texture → Solid backgrounds
- Glows/shadows → Border-only depth
- Decorative animations → Functional transitions only
