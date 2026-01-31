# Tilt Calibration Page Redesign

**Date:** 2025-12-07
**Status:** Design Complete
**Target:** `/calibration` page migration to modern JSON-based API

---

## Problem Statement

The current calibration page (`frontend/src/routes/calibration/+page.svelte`) is broken after the universal device migration. It uses deprecated table-based `CalibrationPoint` endpoints that don't align with the modern JSON-based calibration system.

Additionally, the page attempts to support all device types (Tilt, iSpindel, GravityMon), but:
- **Tilt devices** require app-side calibration (BrewSignal applies corrections to raw BLE data)
- **iSpindel/GravityMon devices** are pre-calibrated at the device level (send final gravity values via HTTP)

Mixing these paradigms in one UI creates confusion and technical debt.

---

## Design Decision

**Scope the calibration page exclusively to Tilt devices.**

### Rationale

1. **Real-world usage:** Tilt users expect app-side multi-point calibration (industry standard per Tilt's own app)
2. **Device architecture:** iSpindel/GravityMon calibrate via polynomial formulas stored on-device (web UI or spreadsheet tools)
3. **API readiness:** Backend already supports modern JSON-based calibration (`PUT /api/devices/{id}/calibration`)
4. **Simplicity:** Single-purpose page is easier to maintain and understand

---

## Architecture

### Data Flow (Before vs After)

**Current (Broken):**
```
Frontend → GET /api/devices/{id}/calibration_points (deprecated table-based)
        → POST /api/devices/{id}/calibration_points
        → DELETE /api/devices/{id}/calibration_points/{type}
```

**New (Modern):**
```
Frontend → GET /api/devices/{id}/calibration (JSON-based)
        ← { calibration_type: "linear", calibration_data: { points: [...] } }

        → PUT /api/devices/{id}/calibration
        → { calibration_type: "linear", calibration_data: { points: [[raw, actual]] } }
```

### Component Structure

```
┌─────────────────────────────────────────────┐
│  Calibration Page (/calibration)           │
│  Title: "Calibrate Your Tilt Hydrometer"   │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  Device Selector                            │
│  Filter: device_type === "tilt" && paired   │
│  Empty state: Link to /devices pairing page│
└─────────────────────────────────────────────┘
              ↓
┌──────────────────────┬──────────────────────┐
│  SG Calibration      │  Temp Calibration    │
│  ─────────────────   │  ──────────────────  │
│  • Points table      │  • Points table      │
│  • Add point form    │  • Add point form    │
│  • Clear all button  │  • Clear all button  │
└──────────────────────┴──────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  Info Section                               │
│  • How calibration works (linear interp)   │
│  • Tilt-specific tips (water = 1.000, etc) │
│  • Link to iSpindel/GravityMon docs        │
└─────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Device Filtering

**Filter criteria:**
- `device_type === "tilt"`
- `paired === true`

**Empty states:**
- No devices at all → "No Tilt devices found. Pair a Tilt on the Devices page."
- Has iSpindel/GravityMon only → "iSpindel and GravityMon calibrate on the device itself. See [docs link]."

### 2. State Management

**Replace point-by-point state with unified calibration object:**

```typescript
interface CalibrationState {
  calibration_type: "linear" | "none";
  calibration_data: {
    points: [number, number][];      // SG points: [raw, actual]
    temp_points?: [number, number][]; // Temp points (optional)
  };
}
```

### 3. Temperature Unit Handling

**Critical:** Backend stores all temperatures in Celsius, but Tilt broadcasts in Fahrenheit.

**Conversion flow:**
1. User enters temp calibration point in their preferred unit (C or F)
2. If preference is F, convert BOTH raw and actual to Celsius
3. Send Celsius values to backend
4. On display, convert stored Celsius back to user's preference

**Example:**
```typescript
// User preference: Fahrenheit
// User enters: Raw 68°F → Actual 67°F

// Convert to Celsius for storage:
const rawC = (68 - 32) * 5/9;   // 20°C
const actualC = (67 - 32) * 5/9; // 19.4°C

// Send to backend:
PUT /api/devices/{id}/calibration
{ calibration_type: "linear", calibration_data: { temp_points: [[20, 19.4]] } }

// Display to user (convert back):
// 20°C → 68°F, 19.4°C → 67°F
```

### 4. Validation

**Client-side:**
- Gravity range: 0.990 - 1.200
- Temperature range: -10°C to 50°C (14°F to 122°F)
- Minimum 2 points for linear calibration
- Warning if raw === actual (no correction)

**Backend validation:**
- Already implemented in `CalibrationRequest` model (backend/routers/devices.py:164-228)
- Returns 422 with error details if invalid

### 5. API Endpoints Used

**Primary:**
- `GET /api/devices?device_type=tilt&paired_only=true` - List Tilt devices
- `GET /api/devices/{id}/calibration` - Get current calibration
- `PUT /api/devices/{id}/calibration` - Update calibration

**Migration support (if implementing Option A):**
- `GET /api/devices/{id}/calibration_points` - Fetch legacy points
- `DELETE /api/devices/{id}/calibration_points/{type}` - Clean up after migration

### 6. Migration Strategy

**Option A: One-time auto-migration (recommended)**

On page load for each device:
1. Check if `calibration_type === "none"` BUT has `CalibrationPoint` records
2. Fetch legacy points via `GET /api/devices/{id}/calibration_points`
3. Convert to new format:
   ```javascript
   const sgPoints = legacyPoints
     .filter(p => p.type === 'sg')
     .map(p => [p.raw_value, p.actual_value]);

   const tempPoints = legacyPoints
     .filter(p => p.type === 'temp')
     .map(p => [p.raw_value, p.actual_value]);
   ```
4. Save via `PUT /api/devices/{id}/calibration` with `calibration_type: "linear"`
5. Delete legacy points (optional cleanup)
6. Show toast notification: "Migrated calibration points to new format"

**Option B: Ignore legacy data**
- Simpler implementation (no migration code)
- Users re-enter calibration points
- Legacy `CalibrationPoint` records remain orphaned in database

**Recommendation:** Option A for better user experience.

---

## UI/UX Changes

### Page Header
**Before:**
```
Calibration
Fine-tune SG and temperature readings with calibration points
```

**After:**
```
Tilt Calibration
Calibrate your Tilt hydrometer's gravity and temperature readings
```

### Info Section Updates

**Add Tilt-specific guidance:**
- "For best results, use distilled water (1.000 SG) and a known sugar solution (e.g., 1.061 SG)"
- "Temperature calibration is rarely needed for Tilts (accurate 38°F-98°F range)"
- "Calibration is applied in software to raw Tilt readings"

**Add device type notice:**
- "**Using iSpindel or GravityMon?** These devices calibrate on-board via polynomial formulas. Configure calibration through the device's web interface. [Learn more →]"

### Empty State
```
┌──────────────────────────────────┐
│           📊                     │
│    No Tilt Devices Found         │
│                                  │
│  Pair a Tilt hydrometer on the   │
│  Devices page to calibrate it.   │
│                                  │
│     [Go to Devices →]            │
└──────────────────────────────────┘
```

---

## Technical Considerations

### Backward Compatibility
- Legacy `CalibrationPoint` table-based endpoints remain functional (used by migration)
- No breaking changes to backend API
- Frontend is only component that changes

### Performance
- Single `GET /calibration` call per device (vs N calls for N points)
- JSON payload is smaller than relational rows
- Fewer database queries

### Error Recovery
- If migration fails, fallback to empty state (user can re-add points)
- Toast notification on migration errors
- Backend validation errors shown inline

---

## Testing Checklist

**Functional:**
- [ ] Tilt devices appear in selector
- [ ] Non-Tilt devices filtered out
- [ ] Add SG calibration point → saved to backend
- [ ] Add temp calibration point → saved to backend (Celsius storage)
- [ ] Clear all SG points → backend updated
- [ ] Clear all temp points → backend updated
- [ ] Temperature conversion (F ↔ C) works correctly
- [ ] Empty state shown when no Tilt devices

**Migration (Option A):**
- [ ] Legacy points auto-migrate on page load
- [ ] Migration toast notification shown
- [ ] Migrated points display correctly
- [ ] Legacy points cleaned up post-migration

**Validation:**
- [ ] Cannot add invalid gravity (< 0.990 or > 1.200)
- [ ] Cannot add invalid temperature (< -10°C or > 50°C)
- [ ] Backend validation errors displayed

**Edge Cases:**
- [ ] Device with no calibration (calibration_type === "none")
- [ ] Device with existing linear calibration
- [ ] User switches between C/F preferences (values convert correctly)
- [ ] Unpaired Tilt devices don't appear

---

## Open Questions

1. **Migration approach:** Implement Option A (auto-migrate) or Option B (clean slate)?
   - **Decision:** Option A for better UX

2. **Legacy endpoint removal:** Should we deprecate `calibration_points` endpoints entirely?
   - **Recommendation:** Keep for now (low maintenance cost, enables rollback)

3. **Polynomial support for Tilt:** Should we support manual polynomial entry for advanced users?
   - **Decision:** No, out of scope. Linear interpolation covers Tilt use cases.

---

## Success Criteria

- [ ] Calibration page loads without errors
- [ ] Only Tilt devices appear in selector
- [ ] Users can add/remove calibration points
- [ ] Temperature units convert correctly (F ↔ C)
- [ ] Backend receives correct JSON format
- [ ] Legacy data migrated (if Option A chosen)
- [ ] Info section guides users to device-specific calibration for non-Tilts

---

## Future Enhancements

1. **Visual calibration graph:** Plot raw vs actual values with interpolation line
2. **Test mode:** "What would 1.050 raw read as?" preview feature (uses existing `POST /calibration/test` endpoint)
3. **Import/export:** Share calibration profiles between devices
4. **Calibration presets:** "Water + Sugar" wizard that guides through standard calibration
5. **Device-specific calibration tabs:** Move calibration UI into device detail pages (Approach 3 from exploration)

---

## References

- [Tilt Multi-Point Calibration Guide](https://tilthydrometer.com/blogs/news/multi-point-calibration-with-the-tilt-2-app)
- [iSpindel Calibration Documentation](https://www.ispindel.de/docs/Calibration_en.html)
- Backend API: `backend/routers/devices.py` (lines 558-694)
- Current (broken) frontend: `frontend/src/routes/calibration/+page.svelte`
