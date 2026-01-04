# Type Coercion Security Bypass

**Status:** pending
**Priority:** P1 (CRITICAL - Blocks Merge)
**Issue ID:** 002
**Tags:** security, validation, pydantic, type-safety

## Problem Statement

Pydantic automatically coerces strings to floats, bypassing type safety. An attacker can send string values where floats are expected, and Pydantic will silently convert them, potentially causing calculation errors or bypassing validation.

**Why This Matters:**
- Type confusion attacks possible
- String "1.050" accepted where float 1.050 expected
- Bypasses numeric range validation in edge cases
- CVSS Score: 7.5 (High)
- CWE-704: Incorrect Type Conversion

## Findings

**Location:** `backend/services/brewsignal_format.py:103-106`

**Current Implementation:**
```python
og: float = Field(ge=1.0, le=1.2)
fg: float = Field(ge=1.0, le=1.2)
abv: Optional[float] = Field(None, ge=0, le=20)
# No type validation - Pydantic auto-converts strings
```

**Attack Scenario:**
```python
# Attacker sends string instead of float
malicious_recipe = {
    "name": "Test",
    "og": "1.050",  # String, not float!
    "fg": "1.010"   # String, not float!
}

# Pydantic silently converts
recipe = BrewSignalRecipe(**malicious_recipe)
# recipe.og == 1.050 (float, converted from string)
# ✅ ACCEPTED without error

# Edge case that could bypass validation:
edge_case = {
    "og": "1.3",  # Out of range BUT as string
}
# In some Pydantic versions, string conversion happens before validation
```

**Security Impact:**
- Medium severity: Type confusion, not RCE
- Could cause calculation errors in brewing software
- Potential for DoS if conversion fails unexpectedly

## Proposed Solutions

### Solution 1: Add `@field_validator(mode='before')` (RECOMMENDED)

**Pros:**
- Explicit type checking before Pydantic conversion
- Clear error messages for type mismatches
- Industry standard security practice
- Minimal performance impact

**Cons:**
- Adds validation code for each numeric field

**Effort:** Medium (1-2 hours for all fields)
**Risk:** Very Low

**Implementation:**
```python
from pydantic import field_validator

class BrewSignalRecipe(BaseModel):
    og: float = Field(ge=1.0, le=1.2)
    fg: float = Field(ge=1.0, le=1.2)
    abv: Optional[float] = Field(None, ge=0, le=20)

    @field_validator('og', 'fg', mode='before')
    @classmethod
    def reject_non_numeric(cls, v):
        """Reject non-numeric values before type coercion."""
        if v is None:
            return v
        if not isinstance(v, (int, float)):
            raise ValueError(
                f'Must be numeric (int or float), got {type(v).__name__}: {v!r}'
            )
        return v

    @field_validator('abv', mode='before')
    @classmethod
    def reject_non_numeric_optional(cls, v):
        """Reject non-numeric values for optional fields."""
        if v is None:
            return None
        if not isinstance(v, (int, float)):
            raise ValueError(
                f'Must be numeric (int or float), got {type(v).__name__}: {v!r}'
            )
        return v
```

### Solution 2: Use Pydantic Strict Mode

**Pros:**
- Single configuration change
- Affects all fields globally

**Cons:**
- May break existing API clients
- Less control over individual fields

**Effort:** Small (5 minutes)
**Risk:** Medium (breaking change)

**Implementation:**
```python
class BrewSignalRecipe(BaseModel):
    model_config = {
        "strict": True,  # Disable all type coercion
        "extra": "forbid"
    }
```

### Solution 3: Use StrictFloat Type

**Pros:**
- Type-safe at field level
- Clear intent in schema

**Cons:**
- Requires Pydantic imports change
- May affect JSON schema generation

**Effort:** Medium
**Risk:** Low

**Implementation:**
```python
from pydantic import StrictFloat

class BrewSignalRecipe(BaseModel):
    og: StrictFloat = Field(ge=1.0, le=1.2)
    fg: StrictFloat = Field(ge=1.0, le=1.2)
```

## Recommended Action

**Implement Solution 1:** Add `@field_validator(mode='before')` for explicit type checking.

Why: Most control, clearest errors, minimal API breakage.

## Technical Details

**Affected Files:**
- `backend/services/brewsignal_format.py` (all numeric fields)
- Pydantic models: BrewSignalRecipe, BrewSignalFermentable, BrewSignalHop, BrewSignalYeast, BrewSignalMisc

**OWASP Top 10:**
- Not directly mapped, but related to A04:2021 – Insecure Design

**CWE Classification:**
- CWE-704: Incorrect Type Conversion or Cast

## Acceptance Criteria

- [ ] Add `@field_validator(mode='before')` for all numeric fields
- [ ] String values for numeric fields raise `ValueError`
- [ ] Error message clearly states expected type
- [ ] Test case: `test_reject_string_for_numeric_fields()`
- [ ] Test case: `test_accept_valid_int_for_float_fields()` (int → float is valid)
- [ ] All existing tests still pass
- [ ] Security test suite updated

## Work Log

### 2025-12-10
- **Discovered:** Security Sentinel review identified type coercion bypass
- **CVSS Score:** 7.5 (High severity)
- **Impact:** Medium - type confusion, not RCE
- **Next Action:** Implement field validators for type checking

## Resources

- **PR:** brewsignal-format-backend branch
- **Review Finding:** Security Sentinel report, CRITICAL-1
- **Security Documentation:** Created `SECURITY_AUDIT_REPORT.md` in worktree
- **Pydantic Security:** https://docs.pydantic.dev/latest/concepts/validators/
- **CWE-704:** https://cwe.mitre.org/data/definitions/704.html
