# FG Validator Field-Order Dependency

**Status:** pending
**Priority:** P1 (CRITICAL - Blocks Merge)
**Issue ID:** 001
**Tags:** data-integrity, validation, pydantic, security

## Problem Statement

The `fg_less_than_og` field validator in `BrewSignalRecipe` has a critical field-order dependency that can cause validation bypass. Pydantic validators run in field definition order, so if `fg` is validated before `og` is set in `info.data`, the validation is silently skipped.

**Why This Matters:**
- Invalid recipes with FG >= OG can be accepted into the system
- Data corruption risk: physically impossible recipes stored in database
- Silent validation failure: no error, no warning, invalid data accepted

## Findings

**Location:** `backend/services/brewsignal_format.py:132-138`

**Current Implementation:**
```python
@field_validator('fg')
@classmethod
def fg_less_than_og(cls, v, info):
    """Ensure FG < OG"""
    if 'og' in info.data and v >= info.data['og']:
        raise ValueError('FG must be less than OG')
    return v
```

**Data Corruption Scenario:**
```python
# JSON with FG before OG (field order can vary in JSON parsers)
data = {"name": "IPA", "fg": 1.055, "og": 1.050}  # INVALID: FG > OG

# If Pydantic schema has fg before og:
class BrewSignalRecipe(BaseModel):
    name: str
    fg: float  # Validated BEFORE og
    og: float  # Not yet in info.data during fg validation

recipe = BrewSignalRecipe(**data)
# fg validator sees: info.data = {"name": "IPA"}
# 'og' not in info.data → validation SKIPPED
# INVALID DATA ACCEPTED ❌
```

## Proposed Solutions

### Solution 1: Use `@model_validator(mode='after')` (RECOMMENDED)

**Pros:**
- Runs after ALL fields are populated
- No dependency on field definition order
- Guaranteed to have both og and fg values
- Standard Pydantic V2 pattern

**Cons:**
- None

**Effort:** Small (15 minutes)
**Risk:** Very Low

**Implementation:**
```python
from pydantic import model_validator

class BrewSignalRecipe(BaseModel):
    # ... fields ...

    @model_validator(mode='after')
    def validate_fg_less_than_og(self) -> 'BrewSignalRecipe':
        """Ensure FG < OG (runs after all fields are set)"""
        if self.fg >= self.og:
            raise ValueError(
                f'Final gravity ({self.fg}) must be less than '
                f'original gravity ({self.og})'
            )
        return self
```

### Solution 2: Ensure Field Definition Order

**Pros:**
- Minimal code change

**Cons:**
- Fragile: breaks if field order changes
- Not obvious to future developers
- Harder to maintain

**Effort:** Small
**Risk:** Medium (fragile)

**NOT RECOMMENDED**

## Recommended Action

**Implement Solution 1:** Refactor to use `@model_validator(mode='after')`

## Technical Details

**Affected Files:**
- `backend/services/brewsignal_format.py` (lines 132-138)

**Components:**
- Pydantic validation layer
- Recipe data integrity

**Database Changes:**
- None (validation only)

## Acceptance Criteria

- [ ] Replace `@field_validator('fg')` with `@model_validator(mode='after')`
- [ ] Validation runs AFTER both og and fg are set
- [ ] Test with field order variations: `{"fg": X, "og": Y}` and `{"og": Y, "fg": X}`
- [ ] Add test case: `test_fg_validation_field_order_independence()`
- [ ] Verify error message includes both gravity values
- [ ] All existing tests still pass

## Work Log

### 2025-12-10
- **Discovered:** Data integrity guardian review identified field-order dependency
- **Impact Assessment:** Critical - can cause silent validation bypass
- **Next Action:** Implement model validator refactoring

## Resources

- **PR:** brewsignal-format-backend branch (not yet created)
- **Review Finding:** Data Integrity Guardian report, CRITICAL-3
- **Pydantic Docs:** https://docs.pydantic.dev/latest/concepts/validators/#model-validators
- **Similar Pattern:** N/A (new validation pattern for this codebase)
