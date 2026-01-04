# Percentage Scale Ambiguity in Validation

**Status:** pending
**Priority:** P1 (CRITICAL - Blocks Merge)
**Issue ID:** 004
**Tags:** data-integrity, conversion, validation, data-corruption

## Problem Statement

The `_unwrap_percent()` method uses ambiguous conditional logic `if value <= 1` that can cause data corruption. When BeerJSON percentage is exactly 1.0 (representing 100%), the logic is ambiguous about whether to multiply by 100 or leave as-is.

**Why This Matters:**
- Data corruption risk for 100% values
- Silent acceptance of wrong-scale percentages
- Violates principle of explicit validation
- Could corrupt brewing efficiency, attenuation data

## Findings

**Location:** `backend/services/brewsignal_format.py:333-343`

**Current Implementation:**
```python
def _unwrap_percent(self, unit_obj: Optional[dict]) -> Optional[float]:
    if not unit_obj:
        return None
    value = unit_obj["value"]
    # Convert from 0-1 to 0-100 scale
    return value * 100 if value <= 1 else value  # ❌ AMBIGUOUS
```

**Data Corruption Scenarios:**

**Scenario 1: 100% Efficiency**
```python
# BeerJSON with 100% efficiency (rare but valid)
beerjson = {"efficiency": {"brewhouse": {"value": 1.0, "unit": "%"}}}

# Current logic: value <= 1 → multiply by 100
result = converter._unwrap_percent(beerjson["efficiency"]["brewhouse"])
# Result: 100.0 ✅ CORRECT (by accident)

# But what if BeerJSON spec changes or we misunderstand?
```

**Scenario 2: Malformed Input Silently Accepted**
```python
# User accidentally sends 0-100 scale in BeerJSON (wrong!)
malformed = {"value": 75.0, "unit": "%"}  # Should be 0.75

# Current logic: value > 1 → return as-is
result = converter._unwrap_percent(malformed)
# Result: 75.0 ✅ Looks correct but accepted WRONG INPUT

# Should have been rejected with clear error
```

**Scenario 3: Edge Case at Boundary**
```python
# Exactly 1.0 is ambiguous
{"value": 1.0, "unit": "%"}
# Is this 1% (needs *100 → 100) or 100% (already 100)?
# Current logic assumes 100% (value <= 1 → *100 → 100.0)
```

## Proposed Solutions

### Solution 1: Always Convert, Add Validation (RECOMMENDED)

**Pros:**
- Explicit: Always assumes BeerJSON uses 0-1 scale (per spec)
- Fail-fast: Rejects out-of-range values with clear error
- Self-documenting: Code states assumptions
- Defensive: Logs warning for unexpected values

**Cons:**
- Slightly more code

**Effort:** Medium (30 minutes)
**Risk:** Very Low

**Implementation:**
```python
import logging

logger = logging.getLogger(__name__)

def _unwrap_percent(self, unit_obj: Optional[dict]) -> Optional[float]:
    """Extract percentage value from unit object.

    BeerJSON stores percentages as 0-1 (e.g., 0.069 for 6.9%).
    BrewSignal uses 0-100 scale.

    We assume BeerJSON ALWAYS uses 0-1 scale per spec.
    Values > 1.5 trigger warning about unexpected format.

    Raises:
        ValueError: If value is negative or impossibly high
    """
    if not unit_obj:
        return None

    value = unit_obj["value"]

    # Validate range BEFORE conversion
    if value < 0:
        raise ValueError(
            f"Negative percentage not allowed: {value}"
        )

    # BeerJSON spec requires 0-1 scale
    # Allow slight tolerance (1.5) for rounding errors
    if value > 1.5:
        logger.warning(
            f"Unexpected percentage value > 1.5: {value}. "
            f"BeerJSON spec requires 0-1 scale. "
            f"Converting anyway, but this may indicate malformed input."
        )

    # ALWAYS convert from 0-1 to 0-100
    return value * 100
```

### Solution 2: Strict Validation (More Restrictive)

**Pros:**
- Even more explicit
- Catches spec violations immediately

**Cons:**
- May reject valid edge cases (e.g., 100.1% efficiency in theory)
- Less tolerant of rounding errors

**Effort:** Small
**Risk:** Medium (might be too strict)

**Implementation:**
```python
if not (0 <= value <= 1.0):
    raise ValueError(
        f"BeerJSON percentage {value} out of spec range [0, 1]. "
        f"Expected 0-1 scale (e.g., 0.069 for 6.9%)."
    )
return value * 100
```

## Recommended Action

**Implement Solution 1:** Always convert with validation and warning.

**Why:** Balance between strictness and tolerance. Catches real errors while allowing slight spec deviations.

## Technical Details

**Affected Files:**
- `backend/services/brewsignal_format.py:333-343` (_unwrap_percent)
- Potentially `backend/services/brewsignal_format.py:548-557` (_wrap_percent - reverse converter)

**Reciprocal Issue:**
The reverse converter `_wrap_percent()` has the SAME problem - needs validation that input is 0-100 scale.

**Database Impact:**
- None (conversion only)

**API Impact:**
- May reject previously accepted (but wrong) inputs
- Better error messages for malformed data

## Acceptance Criteria

- [ ] Remove conditional `if value <= 1 else value`
- [ ] Always multiply by 100 (assume BeerJSON 0-1 scale)
- [ ] Add validation: reject negative percentages
- [ ] Add warning log for value > 1.5
- [ ] Update docstring to explain assumptions
- [ ] Test case: `test_percent_conversion_edge_cases()`
  - Test 0.0, 0.5, 1.0, 1.5 explicitly
- [ ] Test case: `test_reject_negative_percentage()`
- [ ] Test case: `test_warn_on_out_of_range_percentage()`
- [ ] All existing tests still pass

## Work Log

### 2025-12-10
- **Discovered:** Data Integrity Guardian review, CRITICAL-1
- **Root Cause:** Ambiguous conditional tries to handle both scales
- **Impact:** Data corruption risk for edge cases
- **Next Action:** Implement explicit validation with logging

## Resources

- **PR:** brewsignal-format-backend branch
- **Review Finding:** Data Integrity Guardian report, CRITICAL-1
- **BeerJSON Spec:** https://github.com/beerjson/beerjson (percentage format)
- **Related Issue:** 005-pending-p1-reciprocal-percentage-validation (reverse converter)
