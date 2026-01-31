# Batch Detail Page: Live Data Enhancement

**Date:** 2025-12-03
**Issue:** [#48 - Batch detail page missing live measurement data](https://github.com/user/repo/issues/48)
**Status:** Design Approved

## Overview

Enhance the batch detail page to display comprehensive live measurement data, real-time fermentation calculations, and diagnostic information. The design uses a modular card-based architecture to support future features like AI brewing assistants.

## Problem Statement

The batch detail page currently shows limited live data compared to the dashboard:

**Missing:**
- Raw (uncalibrated) measurements
- Signal strength (RSSI/dBm)
- Real-time ABV and attenuation calculations during active fermentation
- Current gravity shown as "FG" while fermenting

**Impact:**
- Users can't monitor fermentation progress in real-time
- No troubleshooting data for calibration or connectivity issues
- No visibility into how close fermentation is to target

## Design Goals

1. **Information Completeness:** Show all diagnostic data available from live readings
2. **Real-Time Insights:** Calculate and display ABV, attenuation, and progress during active fermentation
3. **Future-Proof Architecture:** Enable easy addition of AI features and insights
4. **Consistency:** Match dashboard patterns while providing more detail
5. **Mobile-First:** Ensure usability on all screen sizes

## Architectural Approach

### Modular Card-Based System

Break the batch detail page into discrete, self-contained card components:

```
<BatchDetailPage>
  ├── <BatchLiveReadingsCard>        // Current + raw SG/temp, signal strength
  ├── <BatchFermentationCard>        // Real-time ABV, attenuation, progress
  ├── <BatchRecipeTargetsCard>       // Expected vs actual
  ├── <BatchTimelineCard>            // Dates and milestones
  ├── <BatchDeviceCard>              // Enhanced with signal diagnostics
  ├── <BatchHeaterControlCard>       // Temperature control (existing)
  └── <BatchNotesCard>               // Notes + future AI suggestions
```

**Benefits:**
- Each card is independently maintainable
- Easy to add new cards (e.g., `<AIInsightsCard>`) without refactoring
- Cards can be reordered, hidden, or expanded based on context
- Clear data dependencies and separation of concerns

## Component Design

### 1. BatchCard (Base Component)

**Purpose:** Consistent wrapper for all information cards

**Props:**
```typescript
interface BatchCardProps {
  title: string;
  icon?: string;           // Optional emoji or icon
  highlight?: boolean;     // Accent border for live data
  collapsible?: boolean;   // Add expand/collapse functionality
  expanded?: boolean;      // Controlled expansion state
}
```

**Styling:**
```css
.batch-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 0.75rem;
  padding: 1.25rem;
}

.batch-card.highlight {
  border-color: rgba(245, 158, 11, 0.3); /* Amber for live data */
}
```

---

### 2. BatchLiveReadingsCard

**Purpose:** Display current readings with full diagnostic information

**Data Requirements:**
- `liveReading` (from WebSocket)
- `progress` (fallback for current readings)

**Layout:**
```
┌─────────────────────────────────────┐
│ LIVE READINGS              🟢 LIVE  │
├─────────────────────────────────────┤
│                                     │
│   1.042 SG          20.5°C         │
│   (Calibrated)      (Calibrated)    │
│                                     │
│   Raw: 1.045 SG · 21.2°C           │
│                                     │
│   📶 Good Signal                    │
│   -58 dBm • Updated 12s ago        │
│                                     │
└─────────────────────────────────────┘
```

**Features:**
- Large calibrated readings (current implementation)
- Small raw values shown below when calibration is active
- Signal strength: visual bars + quality label + dBm value
- Last update timestamp
- Only renders if `liveReading` exists

**Visual Indicators:**
- Live badge with pulsing dot (existing pattern from TiltCard)
- Signal quality colors:
  - Excellent (≥-50 dBm): Green
  - Good (≥-60 dBm): Green
  - Fair (≥-70 dBm): Amber
  - Weak (<-70 dBm): Red

---

### 3. BatchFermentationCard

**Purpose:** Real-time fermentation metrics with visual progress

**Data Requirements:**
- `batch.measured_og`
- `liveReading.sg` or `progress.measured.current_sg`
- `batch.recipe.fg_target` (if available)
- `progress` (for progress bar)

**Active Fermentation Layout:**
```
┌─────────────────────────────────────┐
│ FERMENTATION PROGRESS               │
├─────────────────────────────────────┤
│                                     │
│  Current SG                         │
│  1.015  (fermenting)                │
│                                     │
│  ────────────────────────────────  │
│  OG      FG (Target)    FG (Est)   │
│  1.052   1.012          1.015      │
│                                     │
│  ABV              Attenuation       │
│  4.9% (live)      71% (live)       │
│                                     │
│  Progress: 82% ████████░░ 0.003 SG │
│                                     │
└─────────────────────────────────────┘
```

**Completed Batch Layout:**
```
┌─────────────────────────────────────┐
│ FERMENTATION MEASUREMENTS           │
├─────────────────────────────────────┤
│  OG        FG        ABV      Atten │
│  1.052     1.012     5.3%     77%   │
└─────────────────────────────────────┘
```

**Calculations:**

```typescript
// Real-time ABV calculation
const abv = (batch.measured_og - currentSg) * 131.25;

// Real-time attenuation calculation
const attenuation = ((batch.measured_og - currentSg) / (batch.measured_og - 1.0)) * 100;

// Clamp values
const displayAbv = Math.max(0, abv);
const displayAttenuation = Math.max(0, Math.min(100, attenuation));
```

**Visual Indicators:**
- "(live)" badge next to calculated values during active fermentation
- "(fermenting)" next to current SG to distinguish from final FG
- Progress bar (reuse existing pattern)
- Color coding:
  - Live/in-progress values: Amber
  - Final values: Default text color
  - Target values: Muted color

**Logic:**
- Show real-time calculations only when:
  - Batch status is 'fermenting' or 'conditioning'
  - `measured_og` is set
  - Current SG reading is available
- Fall back to static measurements when batch is completed
- Show "--" with hint if OG is not set

---

### 4. BatchDeviceCard (Enhanced)

**Purpose:** Device connection status with signal diagnostics

**Current Implementation:**
- Shows device ID and connection status
- "Updated just now" or "Not receiving data"

**Enhanced Features:**
- Signal strength indicator (bars + dBm)
- Signal quality label (Excellent/Good/Fair/Weak)
- Last seen timestamp with relative time
- Colored status dot (green for connected, gray for offline)

**Layout:**
```
┌─────────────────────────────────────┐
│ TRACKING DEVICE                     │
├─────────────────────────────────────┤
│                                     │
│  🟢 RED Tilt - Connected            │
│                                     │
│  Signal: Good (-58 dBm)             │
│  📶📶📶📶                            │
│                                     │
│  Updated 23s ago                    │
│                                     │
└─────────────────────────────────────┘
```

**Future Enhancement:**
- Collapsible section showing signal history chart
- Average signal strength over time

---

### 5. Other Card Components

**BatchRecipeTargetsCard:**
- Extract existing "Recipe Targets" section
- No changes to logic, just componentized

**BatchTimelineCard:**
- Extract existing "Timeline" section
- No changes to logic, just componentized

**BatchNotesCard:**
- Extract existing "Notes" section
- Future: Add section for AI-generated suggestions/insights

**BatchHeaterControlCard:**
- Already exists as inline component
- Extract to separate file for consistency

---

## Page Layout

### Desktop (2-column grid at >900px)

```
┌──────────────────────┬─────────────┐
│ LiveReadingsCard     │ TimelineCard│
│ (if device linked)   │             │
├──────────────────────┼─────────────┤
│ FermentationCard     │ DeviceCard  │
│                      │             │
├──────────────────────┼─────────────┤
│ RecipeTargetsCard    │ HeaterCard  │
│ (if recipe linked)   │ (if heater) │
│                      ├─────────────┤
│                      │ NotesCard   │
└──────────────────────┴─────────────┘
```

### Mobile (<900px)

All cards stack vertically in priority order:
1. LiveReadingsCard (if available)
2. FermentationCard
3. RecipeTargetsCard (if available)
4. TimelineCard
5. DeviceCard
6. HeaterCard (if available)
7. NotesCard (if available)

### Future AI Integration

```
┌──────────────────────┬─────────────┐
│ LiveReadingsCard     │ TimelineCard│
├──────────────────────┼─────────────┤
│ AI InsightsCard ✨   │ DeviceCard  │
│ (NEW)                │             │
├──────────────────────┼─────────────┤
│ FermentationCard     │ HeaterCard  │
└──────────────────────┴─────────────┘
```

AI card would display:
- Fermentation health assessment
- Predictions (completion date, final gravity)
- Recommendations (dry hop timing, cold crash, etc.)
- Anomaly alerts

---

## Data Flow

### Existing Data Sources

```typescript
// 1. Batch data (from API)
batch: BatchResponse

// 2. Live reading (from WebSocket via tiltsState)
liveReading = $derived.by(() => {
  // Find tilt matching batch.device_id by color
  // Returns: { sg, temp, sg_raw, temp_raw, rssi, color, last_seen }
});

// 3. Progress data (from API)
progress: BatchProgressResponse

// 4. Control status (from API, if heater configured)
controlStatus: BatchControlStatus
```

### New Derived Values

```typescript
// Calculate real-time metrics
let currentMetrics = $derived.by(() => {
  if (!batch?.measured_og) return null;

  // Prefer live reading, fall back to progress
  const currentSg = liveReading?.sg ?? progress?.measured?.current_sg;
  if (!currentSg) return null;

  // ABV calculation: (OG - Current SG) × 131.25
  const abv = (batch.measured_og - currentSg) * 131.25;

  // Attenuation calculation: ((OG - Current SG) / (OG - 1.000)) × 100
  const attenuation = ((batch.measured_og - currentSg) / (batch.measured_og - 1.0)) * 100;

  return {
    currentSg,
    abv: Math.max(0, abv),
    attenuation: Math.max(0, Math.min(100, attenuation)),
    isFermenting: batch.status === 'fermenting' || batch.status === 'conditioning'
  };
});
```

---

## Error Handling & Fallbacks

### Missing Data Scenarios

| Scenario | Behavior |
|----------|----------|
| No live reading | Use `progress.measured.current_sg` and `progress.temperature.current` |
| No device linked | Hide LiveReadingsCard |
| No OG set | Show "--" in FermentationCard with hint: "Set OG to see calculations" |
| Batch completed | FermentationCard shows static final values (no "live" badges) |
| No recipe | Hide RecipeTargetsCard |
| WebSocket disconnected | Continue showing last known values with stale timestamp |

### Graceful Degradation

- Each card independently validates its required data
- Cards that can't render don't mount (vs showing empty state)
- Page remains functional even if some data is unavailable
- No hard dependencies between cards

---

## File Structure

```
frontend/src/lib/components/batch/
├── BatchCard.svelte                 (base wrapper component)
├── BatchLiveReadingsCard.svelte     (new)
├── BatchFermentationCard.svelte     (new)
├── BatchDeviceCard.svelte           (extracted + enhanced)
├── BatchTimelineCard.svelte         (extracted, no changes)
├── BatchRecipeTargetsCard.svelte    (extracted, no changes)
├── BatchNotesCard.svelte            (extracted, no changes)
└── BatchHeaterControlCard.svelte    (extracted, no changes)
```

### Migration Strategy

**Phase 1:** Extract existing sections
1. Create BatchCard base component
2. Extract Timeline, RecipeTargets, Notes, HeaterControl into separate components
3. Verify existing functionality works unchanged

**Phase 2:** Add new features
4. Create BatchLiveReadingsCard with raw values and signal strength
5. Create BatchFermentationCard with real-time calculations
6. Enhance BatchDeviceCard with signal diagnostics

**Phase 3:** Polish
7. Add loading skeletons
8. Test responsive behavior
9. Accessibility improvements

---

## Visual Design

### Color Palette

| Element | Color | Usage |
|---------|-------|-------|
| Live data accent | `#f59e0b` (amber) | Border, badges, indicators for real-time data |
| Positive/Complete | `var(--positive)` | Signal strength (good), completed status |
| Warning | `var(--warning)` | Signal strength (fair), alerts |
| Negative | `var(--negative)` | Signal strength (weak), errors |
| Muted | `var(--text-muted)` | Raw values, secondary info |

### Typography

| Element | Style |
|---------|-------|
| Card titles | `0.75rem`, `500` weight, uppercase, muted color |
| Primary readings | `2.5rem`, monospace, primary color |
| Raw values | `0.6875rem`, monospace, muted color |
| Labels | `0.6875rem`, `500` weight, uppercase, muted color |

### Spacing

- Card padding: `1.25rem`
- Card gap: `1rem`
- Internal spacing: multiples of `0.25rem`

---

## Accessibility

### Screen Reader Support

- Cards have semantic structure (heading + content)
- Signal strength indicators include text labels
- Live badges announced as "Live" or "Fermenting"
- Timestamps use relative time ("23 seconds ago")

### Keyboard Navigation

- Collapsible cards toggle with Enter/Space
- Tab order flows naturally top-to-bottom, left-to-right
- Focus indicators visible on all interactive elements

### Responsive Design

- Cards reflow from 2-column to 1-column at 900px breakpoint
- Touch targets minimum 44×44px on mobile
- Font sizes scale appropriately for readability
- No horizontal scrolling required

---

## Implementation Notes

### IMPORTANT: Use frontend-design Skill

When implementing the UI components, **use the `frontend-design:frontend-design` skill** to ensure:
- High-quality, polished visual design
- Consistent styling with existing BrewSignal aesthetic
- Proper use of design system (colors, spacing, typography)
- Distinctive, non-generic appearance

The frontend-design skill will help create production-grade components that avoid common AI-generated aesthetics.

### Testing Scenarios

1. **Active fermentation with live data:**
   - All cards visible
   - Real-time calculations displayed
   - Live badges present

2. **Active fermentation without device:**
   - LiveReadingsCard hidden
   - FermentationCard uses progress API data
   - DeviceCard shows "no device assigned"

3. **Completed batch:**
   - FermentationCard shows static final values
   - No "live" badges
   - LiveReadingsCard hidden (device unlinked)

4. **Planning batch (no OG):**
   - FermentationCard shows "--" with hint
   - Other cards function normally

5. **No recipe:**
   - RecipeTargetsCard hidden
   - Other cards unaffected

6. **Mobile view:**
   - All cards stack vertically
   - Touch targets appropriately sized
   - No information hidden

### Performance Considerations

- Cards lazy-mount based on data availability
- WebSocket updates trigger reactive updates only in affected cards
- No unnecessary re-renders when expanding/collapsing cards
- Chart components (future) only mount when expanded

---

## Future Enhancements

### Short-term (Next 2-3 Issues)

1. **Signal history chart** in expandable DeviceCard
2. **Fermentation velocity** calculation and display
3. **Temperature stability** indicator

### Medium-term (AI Assistant Integration)

1. **AIInsightsCard** component
   - Fermentation health score
   - Completion date prediction
   - Anomaly detection
   - Action recommendations

2. **Batch comparison** view
   - Compare current batch to previous batches of same recipe
   - Show typical ranges and outliers

3. **Notification triggers**
   - Fermentation stalled
   - Temperature out of range for extended period
   - Ready for next step (dry hop, cold crash, bottle)

### Long-term

1. **Customizable card layout**
   - User preference for card order
   - Show/hide individual cards
   - Saved layouts per user

2. **Export/sharing**
   - Generate batch report PDF
   - Share batch link with read-only access

---

## Success Metrics

After implementation, the batch detail page should:

1. ✅ Display all data currently shown on dashboard
2. ✅ Show real-time ABV and attenuation during active fermentation
3. ✅ Provide diagnostic information (raw values, signal strength)
4. ✅ Support future AI features without architectural changes
5. ✅ Maintain performance on mobile devices
6. ✅ Be accessible to screen reader users

---

## Related Issues

- #48 - Batch detail page missing live measurement data (this design)
- #37 - Add loading skeletons for asynchronous UI elements
- #44 - Add fermentation finish notifications and visual indicators
- #45 - Implement yeast strain database with attenuation and temp ranges

---

## Approval

**Approved by:** User
**Date:** 2025-12-03

Ready to proceed to implementation planning phase.

---

## Implementation Status

**Completed:** 2025-12-03

### Components Created

- ✅ `BatchCard.svelte` - Base wrapper component
- ✅ `BatchLiveReadingsCard.svelte` - Live data with signal strength
- ✅ `BatchFermentationCard.svelte` - Real-time calculations
- ✅ `BatchTimelineCard.svelte` - Extracted timeline section
- ✅ `BatchDeviceCard.svelte` - Enhanced device status
- ✅ `BatchRecipeTargetsCard.svelte` - Extracted targets section
- ✅ `BatchNotesCard.svelte` - Extracted notes section

### Integration

- ✅ All cards integrated into batch detail page
- ✅ Responsive layout (2-column → 1-column at 900px)
- ✅ Real-time ABV and attenuation calculations
- ✅ Signal strength diagnostics
- ✅ Raw value display when calibrated
- ✅ Accessibility improvements

### Testing

- ✅ Active fermentation with live device
- ✅ Active fermentation without device
- ✅ Completed batch display
- ✅ Batch without OG set
- ✅ Responsive behavior verified
- ✅ Heater control compatibility

### Future Enhancements Ready

The modular architecture is ready for:
- AI insights card
- Signal history chart
- Fermentation velocity display
- Batch comparison features
