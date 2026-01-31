# BeerJSON Multi-Format Recipe Import Frontend Design

**Date:** 2025-12-08
**Status:** Design
**Related Docs:**
- `docs/plans/2025-12-08-beerjson-multi-format-import-design.md` (backend design)

## Overview

Update the recipe import frontend to support multiple file formats (BeerXML, BeerJSON, Brewfather JSON) now that the backend fully supports multi-format import with auto-detection.

## Goals

1. **Multi-format support:** Accept both `.xml` and `.json` file uploads
2. **Clear communication:** Update UI copy to reflect multi-format capabilities
3. **Minimal changes:** Preserve existing UX patterns and component structure
4. **Backend delegation:** Rely on backend auto-detection and validation

## Non-Goals

- Format preview/detection UI (backend handles this)
- Format-specific upload flows (single unified flow)
- Client-side format validation (backend validates)

## Design Principles

1. **YAGNI:** Don't add UI complexity for what backend already handles
2. **Trust the backend:** Backend auto-detects format, validates schema, returns clear errors
3. **Preserve UX:** Keep existing simple drag-drop upload flow
4. **Progressive disclosure:** Show format details in help text, not as primary UI

## Current State

**Backend:** ✅ Complete (multi-format import with auto-detection)
- Accepts `.xml` (BeerXML, Brewfather XML) and `.json` (BeerJSON, Brewfather JSON)
- Auto-detects format from extension and content structure
- Validates against BeerJSON schema
- Returns normalized recipe data

**Frontend:** ❌ Legacy BeerXML-only
- Only accepts `.xml` files (line 15-18)
- Hardcoded "BeerXML" branding throughout
- Uses legacy `importBeerXML()` function name
- Shows error for non-XML files

## Approach: Minimal In-Place Update

**Rationale:** Backend handles all format detection and validation logic. Frontend just needs to:
1. Accept both file types
2. Communicate multi-format support
3. Display backend error messages

**Alternative approaches considered:**
- Format selector tabs: Rejected (redundant with backend auto-detection)
- Client-side format preview: Rejected (duplicates backend validation)

## Implementation

### File Changes

#### 1. Import Page Component

**File:** `frontend/src/routes/recipes/import/+page.svelte`

**Changes:**

| Line | Current | New | Reason |
|------|---------|-----|--------|
| 15-18 | Only accept `.xml` | Accept `.xml` or `.json` | Support multiple formats |
| 16 | Error: "Please upload a .xml BeerXML file" | "Please upload a .xml or .json recipe file" | Reflect multi-format support |
| 28 | `importBeerXML(file)` | `importRecipe(file)` | Rename API function |
| 97 | "Upload BeerXML files from..." | "Upload recipe files from..." | Remove format-specific branding |
| 117 | "Drop BeerXML file here" | "Drop recipe file here" | Generic file upload message |
| 122 | `accept=".xml"` | `accept=".xml,.json"` | HTML5 file picker accepts both |
| 130 | "Supported: .xml files (max 1MB)" | "Supported: BeerXML (.xml), BeerJSON (.json), Brewfather JSON (.json) - max 1MB" | List all supported formats |

**Detailed change snippets:**

```svelte
<!-- Change 1: File validation (lines 14-18) -->
async function handleFileUpload(file: File) {
    error = null;

    // Validate file extension
    const filename = file.name.toLowerCase();
    if (!filename.endsWith('.xml') && !filename.endsWith('.json')) {
        error = 'Please upload a .xml or .json recipe file';
        return;
    }

    if (file.size > MAX_FILE_SIZE) {
        error = 'File must be smaller than 1MB';
        return;
    }

    uploading = true;

    try {
        const recipes = await importRecipe(file); // Updated function name
        // ... rest unchanged
    }
}
```

```svelte
<!-- Change 2: Page description (lines 96-98) -->
<p class="page-description">
    Upload recipe files from Brewfather, BeerSmith, Brewer's Friend, or any brewing software
</p>
```

```svelte
<!-- Change 3: Drop zone text (line 117) -->
<p class="drop-text">Drop recipe file here</p>
```

```svelte
<!-- Change 4: File input accept attribute (line 122) -->
<input
    type="file"
    accept=".xml,.json"
    onchange={handleFileInput}
    class="file-input"
    disabled={uploading}
/>
```

```svelte
<!-- Change 5: Supported formats info (line 130) -->
<p class="info-text">
    Supported: BeerXML (.xml), BeerJSON (.json), Brewfather JSON (.json) - max 1MB
</p>
```

#### 2. API Function Rename

**File:** `frontend/src/lib/api.ts`

**Changes:**

```typescript
// Line 558: Rename function and add JSDoc
/**
 * Import recipe from BeerXML, BeerJSON, or Brewfather JSON.
 * Backend auto-detects format from file extension and content.
 *
 * @param file - Recipe file (.xml or .json)
 * @returns Array of imported recipes (typically single recipe)
 * @throws Error with backend validation message if import fails
 */
export async function importRecipe(file: File): Promise<RecipeResponse[]> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${BASE_URL}/recipes/import`, {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || 'Failed to import recipe');
    }

    return response.json();
}
```

### Error Handling

Frontend displays backend error messages as-is. Backend provides clear format-specific errors:

| Error Case | Backend Message | Frontend Display |
|------------|-----------------|------------------|
| Invalid XML structure | "Invalid BeerXML format: ..." | Show in error box |
| Invalid JSON structure | "Invalid JSON: ..." | Show in error box |
| Unknown JSON format | "Unknown JSON format (not Brewfather or BeerJSON)" | Show in error box |
| Schema validation failure | "Invalid recipe format: [field] is required" | Show in error box |
| File too large (backend) | "File too large (max 5MB)" | Show in error box |
| File too large (frontend) | "File must be smaller than 1MB" | Show in error box |

**Frontend validation:** File extension and size only (lines 14-23)
**Backend validation:** Format detection, schema validation, data integrity

### User Flow

1. **User navigates to `/recipes/import`**
   - Sees "Upload recipe files from..." description
   - Sees drop zone with "Drop recipe file here"

2. **User selects/drops file**
   - Frontend validates extension (`.xml` or `.json`)
   - Frontend validates size (< 1MB)
   - If invalid: Show error, stop
   - If valid: Upload to backend

3. **Backend processes file**
   - Auto-detects format from extension and content
   - Validates against appropriate schema
   - Converts to BeerJSON internal representation
   - Persists to database

4. **Success:**
   - Redirect to recipe detail page (single import)
   - Or redirect to recipe list (multiple imports)

5. **Failure:**
   - Display backend error message in error box
   - User can try different file

## Testing

### Manual Testing Checklist

- [ ] Upload Brewfather BeerXML (`.xml`) - should succeed
- [ ] Upload Brewfather JSON (`.json`) - should succeed
- [ ] Upload native BeerJSON (`.json`) - should succeed
- [ ] Upload invalid `.xml` - should show clear error
- [ ] Upload invalid `.json` - should show clear error
- [ ] Upload `.txt` file - should show extension error
- [ ] Upload 2MB file - should show size error
- [ ] Drag-drop `.xml` file - should work
- [ ] Drag-drop `.json` file - should work

### Test Files

Use existing test data:
- `docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml`
- `docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json`

## Success Criteria

1. **✅ Multi-format upload works:**
   - Accept both `.xml` and `.json` files
   - Backend auto-detection works seamlessly
   - No format-specific code paths in frontend

2. **✅ Clear communication:**
   - UI copy mentions all supported formats
   - Help text lists format options
   - No misleading "BeerXML only" messaging

3. **✅ Error handling:**
   - Backend errors display clearly
   - File extension errors show before upload
   - Size validation prevents oversized uploads

4. **✅ Backward compatibility:**
   - Existing BeerXML imports still work
   - No breaking changes to API contract
   - Recipe list/detail pages unaffected

## Migration Notes

**API function rename:**
- Old: `importBeerXML(file)`
- New: `importRecipe(file)`
- Only used in one location (`import/+page.svelte:28`)

**No database changes:** Frontend-only update

**No configuration changes:** No environment variables or settings

## Future Enhancements

- **Batch upload:** Upload multiple recipe files at once
- **Import preview:** Show recipe details before saving
- **Format conversion:** Export imported recipes to different formats
- **Import history:** Track which files have been imported

## References

- Backend design: `docs/plans/2025-12-08-beerjson-multi-format-import-design.md`
- BeerJSON spec: https://github.com/beerjson/beerjson
- Current import page: `frontend/src/routes/recipes/import/+page.svelte`
