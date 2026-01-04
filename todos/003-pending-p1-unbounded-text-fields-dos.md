# Unbounded Text Fields DoS Risk

**Status:** pending
**Priority:** P1 (CRITICAL - Blocks Merge)
**Issue ID:** 003
**Tags:** security, dos, resource-exhaustion, validation

## Problem Statement

The `notes` field in `BrewSignalRecipe` has no maximum length constraint, allowing attackers to submit extremely large payloads that consume server memory and cause Denial of Service.

**Why This Matters:**
- DoS attack vector: 100+ MB text can crash server
- Memory exhaustion on recipe import
- Database storage overflow
- CVSS Score: 7.5 (High)
- CWE-400: Uncontrolled Resource Consumption

## Findings

**Location:** `backend/services/brewsignal_format.py:108`

**Current Implementation:**
```python
notes: Optional[str] = None  # NO MAX LENGTH ❌
```

**Attack Scenario:**
```python
# Attacker sends massive notes payload
attack_recipe = {
    "name": "DoS Recipe",
    "og": 1.050,
    "fg": 1.010,
    "notes": "A" * 100_000_000  # 100 MB of text
}

# Server attempts to validate
recipe = BrewSignalRecipe(**attack_recipe)
# Memory spike: 100+ MB allocated
# Multiple concurrent requests → OOM crash
```

**Measured Impact (from security review):**
- 100 MB notes field: Accepted ✅
- 1 GB notes field: Accepted (eventually) ✅
- Server memory usage spikes during validation
- PostgreSQL/SQLite TEXT field unbounded by default

## Proposed Solutions

### Solution 1: Add `max_length` Constraint (RECOMMENDED)

**Pros:**
- Simple one-line fix
- Pydantic handles validation automatically
- Clear error message to user
- Industry standard (10,000 chars = ~2-3 pages)

**Cons:**
- Need to choose appropriate limit

**Effort:** Small (5 minutes)
**Risk:** Very Low

**Implementation:**
```python
notes: Optional[str] = Field(None, max_length=10_000)
```

**Rationale for 10,000 character limit:**
- 10K chars ≈ 2-3 pages of text
- Sufficient for detailed brewing notes
- ~10 KB memory per recipe (acceptable)
- 1000 recipes = ~10 MB total (reasonable)

### Solution 2: Add Database-Level Constraint

**Pros:**
- Defense in depth
- Protects against direct database inserts

**Cons:**
- Requires database migration
- Different limits for SQLite vs PostgreSQL

**Effort:** Medium
**Risk:** Medium (migration required)

**Implementation:**
```sql
ALTER TABLE recipes
ADD CONSTRAINT notes_length_limit
CHECK (LENGTH(notes) <= 10000);
```

### Solution 3: Implement Pagination for Large Notes

**Pros:**
- Supports unlimited notes

**Cons:**
- Massive over-engineering for v1.0
- Not needed for brewing recipes

**NOT RECOMMENDED** (YAGNI violation)

## Recommended Action

**Implement Solution 1:** Add `max_length=10_000` to notes field.

**Optional:** Add Solution 2 as database-level defense in depth (future migration).

## Technical Details

**Affected Files:**
- `backend/services/brewsignal_format.py:108`
- Potentially `backend/models.py` (database model)

**Other Unbounded Fields to Review:**
- `author`: Should have `max_length=200`
- `type`: Should have `max_length=100`
- `brewsignal_extensions`: dict - implement depth/size limits

**Memory Impact:**
- Before fix: 100 MB per malicious recipe
- After fix: 10 KB per recipe (1000x reduction)

## Acceptance Criteria

- [ ] Add `max_length=10_000` to `notes` field
- [ ] Add `max_length=200` to `author` field
- [ ] Add `max_length=100` to `type` field
- [ ] Test case: `test_notes_exceeds_max_length()`
- [ ] Test case: `test_notes_at_max_length_accepted()`
- [ ] Error message clearly states limit
- [ ] All existing tests still pass
- [ ] Security test suite updated

## Work Log

### 2025-12-10
- **Discovered:** Security Sentinel review identified unbounded text fields
- **CVSS Score:** 7.5 (High severity - DoS risk)
- **Attack Vector:** HTTP POST with 100+ MB notes payload
- **Impact:** Server memory exhaustion, potential crash
- **Next Action:** Add max_length constraints

## Resources

- **PR:** brewsignal-format-backend branch
- **Review Finding:** Security Sentinel report, CRITICAL-2
- **Security POC:** `VULNERABILITY_POC.md` in worktree demonstrates attack
- **OWASP:** A04:2021 – Insecure Design (missing resource limits)
- **CWE-400:** https://cwe.mitre.org/data/definitions/400.html
