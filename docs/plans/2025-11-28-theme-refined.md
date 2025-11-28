# TiltUI Theme Refinement: Restraint Over Decoration

**Problem:** The current design tries too hard with amber glows, grain textures, and trendy fonts. The themed alternatives (copper, chalkboard) overcorrected into tackiness.

**Approach:** Strip back to fundamentals. Let typography, spacing, and information hierarchy do the work. No themes, no personality - just quiet competence.

---

## Principles

1. **One typeface, used well** - No display/body split. One family, weight hierarchy only.
2. **Monochromatic base** - Grays that don't lean warm or cool. True neutral.
3. **Single accent, used sparingly** - For interactive states and critical data only. Not decoration.
4. **No textures** - No grain, no patterns, no gradients on backgrounds.
5. **Depth through spacing** - Not shadows and glows. Whitespace creates hierarchy.
6. **Motion for function** - State transitions, not "delight."

---

## Color System

```css
:root {
  /* True neutral grays - no warm/cool tint */
  --gray-950: #0a0a0b;
  --gray-900: #121214;
  --gray-850: #18181b;
  --gray-800: #1f1f23;
  --gray-700: #2e2e33;
  --gray-600: #3f3f46;
  --gray-500: #52525b;
  --gray-400: #71717a;
  --gray-300: #a1a1aa;
  --gray-200: #d4d4d8;
  --gray-100: #e4e4e7;
  --gray-50: #fafafa;

  /* Backgrounds */
  --bg-base: var(--gray-900);
  --bg-surface: var(--gray-850);
  --bg-elevated: var(--gray-800);
  --bg-hover: var(--gray-700);

  /* Text */
  --text-primary: var(--gray-50);
  --text-secondary: var(--gray-400);
  --text-muted: var(--gray-500);

  /* Borders - barely visible, just structure */
  --border-subtle: var(--gray-800);
  --border-default: var(--gray-700);

  /* Single accent: a calm teal-blue. Not exciting. Trustworthy. */
  --accent: #3b82f6;
  --accent-muted: rgba(59, 130, 246, 0.15);

  /* Semantic - functional only */
  --positive: #22c55e;
  --warning: #eab308;
  --negative: #ef4444;

  /* Tilt colors - muted, not saturated */
  --tilt-red: #f87171;
  --tilt-green: #4ade80;
  --tilt-black: #71717a;
  --tilt-purple: #a78bfa;
  --tilt-orange: #fb923c;
  --tilt-blue: #60a5fa;
  --tilt-yellow: #facc15;
  --tilt-pink: #f472b6;
}
```

**What changed:**
- Removed amber entirely
- True neutral grays (Zinc scale)
- Single blue accent - boring but functional
- No glow variants, no "strong" variants

---

## Typography

```css
/* One font. That's it. */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap');

/* Fallback if Geist unavailable - system fonts are fine */
:root {
  --font-sans: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'Geist Mono', ui-monospace, 'SF Mono', Menlo, monospace;
}

body {
  font-family: var(--font-sans);
  font-weight: 400;
  font-size: 14px;
  line-height: 1.5;
  letter-spacing: -0.01em;
  -webkit-font-smoothing: antialiased;
}

/* Weight hierarchy - only three weights */
/* 400: body text */
/* 500: labels, emphasis */
/* 600: headings, important values */

/* Size scale - tight, functional */
/* 11px: micro labels */
/* 12px: secondary text, metadata */
/* 14px: body (base) */
/* 16px: subheadings */
/* 20px: page titles */
/* 32px: large data display */

.reading-value {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  /* No glow. No special color. Just big and readable. */
}

.label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-muted);
}
```

**What changed:**
- Geist (or system fallback) instead of Outfit
- No reading-glow class
- Readings are just large mono text, no color treatment
- Tighter size scale

---

## Components

### Cards

```css
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  /* No shadow. No glow. Border is enough. */
}

.card:hover {
  border-color: var(--border-default);
  /* No transform. No shadow animation. Just border change. */
}
```

**What changed:**
- Removed card-glow class entirely
- No hover lift/shadow
- Simple border darkening on hover

### Accent Usage

```css
/* Accent ONLY for: */

/* 1. Interactive elements */
.button-primary {
  background: var(--accent);
  color: white;
}

/* 2. Active/selected states */
.nav-link.active {
  color: var(--text-primary);
  background: var(--bg-elevated);
}
.nav-link.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--accent);
}

/* 3. Focus rings */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 4. Links */
a:hover {
  color: var(--accent);
}

/* NOT for: */
/* - Decorative borders */
/* - Background tints */
/* - Data values (use text-primary) */
/* - Icons (use text-secondary) */
```

### Data Display

```css
/* Gravity/temp readings - no decoration */
.reading-container {
  padding: 16px;
  background: var(--bg-elevated);
  border-radius: 6px;
}

.reading-value {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 500;
  color: var(--text-primary);
  /* That's it. No glow, no accent color. */
}

.reading-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-top: 4px;
}
```

### Tilt Color Indicator

```css
/* Small, functional, not decorative */
.tilt-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tilt-color);
  /* No glow. No shadow. Just a dot. */
}

/* Accent bar on card - thinner, no glow */
.card-accent {
  height: 2px;
  background: var(--tilt-color);
  border-radius: 2px 2px 0 0;
  /* No box-shadow glow */
}
```

### Status Indicators

```css
/* Connection status - minimal */
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--positive);
}

.status-dot.offline {
  background: var(--text-muted);
}

/* No pulse animation. Static is fine. */
/* If you must animate, subtle opacity only: */
.status-dot.live {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

## What To Remove

From `app.css`:
- [ ] Grain texture overlay (`body::after` with noise SVG)
- [ ] `.reading-glow` class
- [ ] `.card-glow` class and hover shadow effects
- [ ] `--amber-*` variables (all of them)
- [ ] `--amber-glow` and `--amber-glow-strong`
- [ ] Outfit font import

From components:
- [ ] Animated signal bars (just static colored bars)
- [ ] Heater pulse animation (static indicator is fine)
- [ ] Any `text-shadow` or `box-shadow` with color

---

## Spacing System

Consistent 4px base:

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
}
```

Apply consistently:
- Card padding: `--space-4` (16px)
- Card gap in grid: `--space-4` (16px)
- Section spacing: `--space-8` (32px)
- Reading container padding: `--space-4` (16px)
- Label to value gap: `--space-1` (4px)

---

## Motion

```css
/* One transition timing for everything */
:root {
  --transition: 150ms ease;
}

/* Apply to interactive state changes only */
.button,
.card,
.nav-link,
input,
select {
  transition:
    background var(--transition),
    border-color var(--transition),
    color var(--transition);
}

/* No transforms (scale, translate) on hover */
/* No elaborate keyframe animations */
/* Page transitions: simple fade, 150ms */
```

---

## Before/After Mental Model

| Element | Before | After |
|---------|--------|-------|
| Gravity reading | Amber color + glow | White mono text, larger |
| Card hover | Lift + amber shadow | Border color change |
| Background | Grain texture overlay | Solid color |
| Signal bars | Animated fill | Static bars |
| Nav active | Amber underline | Blue underline |
| Heater status | Pulsing red glow | Static red dot |
| Typography | Outfit (trendy) | Geist/system (invisible) |
| Accent usage | Everywhere | Interactive states only |

---

## Summary

This isn't a "theme." It's the absence of theme.

Good UI disappears. The data is the interface. Every decorative element we remove is cognitive load we eliminate.

The current TiltUI is 80% there. We're removing the 20% that tries too hard:
- Glows
- Textures
- Trendy fonts
- Accent color overuse
- Decorative animations

What remains: readable text, clear hierarchy, functional color, and breathing room.
