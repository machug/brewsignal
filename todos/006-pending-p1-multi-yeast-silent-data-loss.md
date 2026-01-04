# Multi-Yeast Silent Data Loss Warning

**Status:** pending
**Priority:** P1 (CRITICAL - Blocks Merge)
**Issue ID:** 006
**Tags:** data-integrity, user-experience, logging, data-loss

## Problem Statement

When converting recipes with multiple yeast cultures from BeerJSON to BrewSignal, only the first culture is used and additional cultures are silently dropped without any warning or logging. This can cause users to brew incorrect recipes, leading to ruined batches.

**Why This Matters:**
- Silent data loss: User unaware of missing ingredients
- Ruined batches: Missing Brett, Lacto, or co-pitched strains
- Poor user experience: No indication data was dropped
- Data integrity: Conversion should never silently lose data

## Findings

**Location:** `backend/services/brewsignal_format.py:238-261`

**Current Implementation:**
```python
def _convert_yeast(self, cultures: List[dict]) -> Optional[dict]:
    """Convert BeerJSON cultures array to single BrewSignal yeast.

    BrewSignal v1.0 supports single yeast only.
    Takes first culture from array.  # ❌ NO WARNING
    """
    if not cultures:
        return None

    culture = cultures[0]  # SILENTLY DROPS cultures[1:]
    # ... conversion logic
```

**Data Loss Scenario:**
```python
beerjson = {
    "ingredients": {
        "culture_additions": [
            {"name": "US-05", "type": "ale"},
            {"name": "Brett B", "type": "brett"},      # ❌ LOST
            {"name": "Lacto", "type": "bacteria"}      # ❌ LOST
        ]
    }
}

# User imports recipe
result = converter.convert(beerjson)
# result only has US-05
# ❌ User doesn't know Brett and Lacto were dropped
# ❌ Brews beer without critical mixed-fermentation cultures
# ❌ RUINED BATCH
```

## Proposed Solutions

### Solution 1: Add Warning Log (RECOMMENDED for v1.0)

**Pros:**
- Informs user about data loss
- Maintains v1.0 single-yeast constraint
- Simple implementation
- Logged warnings can be monitored

**Cons:**
- Data still lost (but acknowledged)
- User must check logs

**Effort:** Small (15 minutes)
**Risk:** Very Low

**Implementation:**
```python
import logging

logger = logging.getLogger(__name__)

def _convert_yeast(self, cultures: List[dict]) -> Optional[dict]:
    """Convert BeerJSON cultures array to single BrewSignal yeast.

    BrewSignal v1.0 supports single yeast only.
    Takes first culture from array and WARNS if multiple cultures exist.

    Raises:
        Warning (via logging): If multiple cultures detected
    """
    if not cultures:
        return None

    if len(cultures) > 1:
        # ✅ CRITICAL: Warn user about data loss
        dropped_cultures = [c.get("name", "Unknown") for c in cultures[1:]]
        logger.warning(
            f"Multiple yeast cultures detected in BeerJSON. "
            f"BrewSignal v1.0 supports only one yeast. "
            f"Using first culture: '{cultures[0].get('name')}'. "
            f"DROPPED cultures: {dropped_cultures}"
        )

    culture = cultures[0]
    # ... rest of conversion
```

### Solution 2: Raise Error (Strict Mode)

**Pros:**
- Forces user to handle multi-yeast explicitly
- No silent data loss
- User must choose which yeast to use

**Cons:**
- Breaking: Prevents import of multi-yeast recipes
- Poor UX: User can't import valid BeerJSON

**Effort:** Small
**Risk:** Medium (breaks valid use case)

**NOT RECOMMENDED for v1.0**

### Solution 3: Store Dropped Cultures in Extensions

**Pros:**
- Preserves ALL data
- Future v2.0 can restore dropped cultures
- Best long-term solution

**Cons:**
- More complex
- Requires extension structure

**Effort:** Medium (30 minutes)
**Risk:** Low

**Implementation:**
```python
def _convert_yeast(self, cultures: List[dict]) -> Optional[dict]:
    if not cultures:
        return None

    if len(cultures) > 1:
        dropped_cultures = [c.get("name") for c in cultures[1:]]
        logger.warning(
            f"Multiple yeasts detected. Using first: {cultures[0].get('name')}. "
            f"Dropped: {dropped_cultures}. "
            f"Storing in brewsignal_extensions._dropped_cultures"
        )

    result = {
        "name": cultures[0].get("name"),
        # ... other fields ...
    }

    # Preserve dropped cultures for future use
    if len(cultures) > 1:
        result["_dropped_cultures"] = cultures[1:]

    return result
```

## Recommended Action

**Implement Solution 1 for v1.0:** Add warning log.

**Future (v2.0):** Consider Solution 3 to preserve data.

## Technical Details

**Affected Files:**
- `backend/services/brewsignal_format.py:238-261`

**Logging Configuration:**
Ensure backend has logging configured to display WARNING level:
```python
# backend/main.py or logging config
logging.basicConfig(level=logging.WARNING)
```

**User Notification:**
Consider adding warning to API response:
```json
{
  "recipe": { ... },
  "warnings": [
    "Multiple yeast cultures detected. Only first culture imported."
  ]
}
```

## Acceptance Criteria

- [ ] Add `import logging` and create logger
- [ ] Log WARNING when `len(cultures) > 1`
- [ ] Warning message includes:
  - "Multiple yeast cultures detected"
  - Name of first (kept) culture
  - Names of dropped cultures
- [ ] Test case: `test_multi_yeast_logs_warning()`
- [ ] Test case: `test_single_yeast_no_warning()`
- [ ] Verify warning appears in server logs
- [ ] All existing tests still pass

## Work Log

### 2025-12-10
- **Discovered:** Data Integrity Guardian review, CRITICAL-4
- **User Impact:** High - can cause ruined batches
- **Current Behavior:** Silent data loss
- **Next Action:** Add warning log

## Resources

- **PR:** brewsignal-format-backend branch
- **Review Finding:** Data Integrity Guardian report, CRITICAL-4
- **Python Logging Docs:** https://docs.python.org/3/library/logging.html
- **Future Enhancement:** Store dropped cultures in brewsignal_extensions
