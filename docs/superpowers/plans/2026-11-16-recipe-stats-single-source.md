# Recipe Stats: One Calculator, Computed on Read — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recipe OG/FG/ABV/IBU/SRM (plus BU:GU, calories, colour hex) come from one backend calculator, computed from the ingredients every time they are read; nothing stores or trusts a computed stat.

**Architecture:** `brewing.calculate_recipe_stats` becomes the only calculator and returns a `CalculatedStats` (or `None` with no fermentables) with human-readable `assumptions`. Recipe responses carry a `calculated` block built by an explicit mapper from eagerly loaded ingredients; the editor gets live numbers from `POST /api/recipes/calculate`. A batch reads its recipe's live numbers until it starts fermenting, then keeps a frozen `expected_*` snapshot, so alerts, the rest rule, ML and batch pages never move under a running fermentation. The stored `recipes.og/fg/abv/ibu/color_srm` columns are kept server-filled during the transition and dropped last.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (SQLite 3.46 on the Pi, Postgres/Supabase in cloud mode), Pydantic v2, pytest; SvelteKit 2 + Svelte 5 runes, vitest.

**Spec:** epic bead `tilt_ui-4x2f` and the Decisions below. Inputs: code survey 2026-11-16; Gemini 4 Carbon design review and plan review; Fable 5.2 review of the batch snapshot and the column drop.

## Global Constraints

- Temperatures Celsius. API output: SG to 3 dp, IBU and SRM to 1 dp, ABV to 2 dp.
- Manual migrations in `backend/database.py` `init_db()` (no Alembic). Every schema change also gets `supabase/migrations/<timestamp>_<name>.sql` in the style of the newest one. Cloud order: deploy code first, then run the SQL (Fable F11).
- Svelte 5 runes only. `svelte-check --threshold error` = 0 errors; vitest green.
- Backend: `.venv/bin/python -m pytest tests backend/tests -q` green except the known `tests/test_curve_fitting.py::TestFermentationCurveFitter::test_returns_predictions_at_intervals` (`tilt_ui-7tlf`).
- One branch per task (`refactor/tilt_ui-4x2f.N-<slug>`), codex review per commit, CHANGELOG entry per user-visible task, merge and deploy to the Pi after each task. Every task ships green on its own.
- Before any task that migrates data: `sqlite3 data/fermentation.db ".backup data/fermentation.db.bak-4x2f-N"` on the Pi.

## Decisions

- **D1 Compute on read.** No stored computed stats, no recompute-on-write, no version column (~35 recipes; selectinload + Python maths is a few ms).
- **D2 One calculator, in the backend.** Delete the copy in `backend/services/llm/tools/recipe.py:449` and the stat functions in `frontend/src/lib/brewing/calculations.ts` (`calculateOG`, `calculateFG`, `calculateABV`, `calculateIBU_Tinseth`, `calculateTotalIBU`, `calculateSRM`, `calculateCalories`, `calculateRecipeStats`, `calculateBUGU`). Non-stat helpers (strike water, carbonation, `describeBUGU`) stay.
- **D3 Calculator rules.** Existing maths kept unless listed. Each default adds one plain-English line to `assumptions`:
  | Input missing | Default | assumption text |
  |---|---|---|
  | `efficiency_percent` | 75 | `Assumed 75% brewhouse efficiency` |
  | attenuation | culture midpoint `(min+max)/2` → the one set → `recipe.yeast_attenuation` → 75 | `Assumed 75% yeast attenuation` (last case only) |
  | fermentable yield | `DEFAULT_POTENTIALS` by name → 36 PPG | `Estimated yield for <name>` |
  | fermentable colour | 3 SRM | `Estimated colour for <name>` |
  | hop alpha | 5 % | `Assumed 5% alpha for <name>` |
  | whirlpool temperature | boil-hot (factor 1.0) | `No whirlpool temperature for <name>: counted as boiling` |
  | `batch_size_liters` | 20 | `Assumed 20 L batch` |
  - Types in `brewing.NO_EFFICIENCY_TYPES` (sugars, extracts, honey) use full potential, as today.
  - Whirlpool IBU stays `min(0.05 + 0.005·t, 0.20) × hop_stand_temp_factor(timing)` (Malowicki).
  - Hop `timing.duration.unit` is normalised: `day`×1440, `hr`/`h`×60, `s`/`sec`÷60, else minutes.
  - Dry hop / `add_to_fermentation` / `add_to_package` = 0 IBU. Boil hop at 0 min = 0.
  - SRM uncapped; `color_hex` clamps at 40 SRM.
  - No fermentables → `None`, never 1.000 / 0.
- **D4 API shape.** `calculated: CalculatedStats | None` on `RecipeResponse` and `RecipeDetailResponse`, built only by `to_recipe_response(recipe)`. Declared values stay in `target_*`.
- **D5 Effective stats.** `effective_stats(recipe)` resolves **per field**: calculated value if not None, else `target_*`, else None. `source` = `"calculated"` if any field is calculated, `"declared"` if only targets, `"empty"` if none.
- **D6 Batch numbers** (revised after Fable F1–F6):
  - `planning` / `brewing`: read the recipe live via `effective_stats` (no snapshot, so recipe edits by any writer, including the assistant, show up).
  - On entering `fermenting` (`routers/batches.py:353`, `:469`): `snapshot_expected(batch, recipe)` writes `expected_og/fg/abv/ibu/srm`. From then on they never change, including on recipe edits.
  - Recipe reassignment (`routers/batches.py:430-431`) on a batch at or past `fermenting`: re-snapshot from the new recipe. Unlinking clears the snapshot.
  - Readers use `batch_expected_og(batch)` = `measured_og` → snapshot (fermenting+) or live (planning/brewing) → None, and `batch_expected_fg(batch)` likewise without `measured_og`. A None FG keeps today's `REST_BLOCKED` behaviour.
  - Backfill for every existing batch at or past `fermenting`, including soft-deleted ones: **legacy stored `recipe.og/fg/abv/ibu/color_srm` first** (what the batch has been running against), then `effective_stats`. This runs synchronously in `init_db` before serving (not `run_deferred_backfills`). In cloud mode the Supabase SQL does the same copy from the legacy columns.
- **D7 Importers** write file stats to `target_*` (and, until Task 5, the legacy columns are filled from the calculator, not the file).
- **D8 Exports** (revised after Fable F12–F15):
  - Foreign formats (Brewfather JSON, strict BeerJSON): stat fields = per-field `effective_stats`.
  - BrewSignal v2 (own format, also the assistant's document): stat fields = declared `target_*` only, omitted when unset. This is already the assistant's contract (`recipe_v2._export:233-240`). The importer reads them into `target_*` and recomputes the rest. No extra `targets` block.
- **D9 UI.**
  - Show `calculated`. Show the target beside it when `|Δog| > 0.002` or `|Δibu| > 2`.
  - Small "Declared" label when `source="declared"`; `—` when empty.
  - `assumptions` render as a native `title` tooltip on an "Estimated" label (no new component).
  - Delete the hard-coded fallbacks (1.050 / 1.010 / 5.0 / 30 / 8).
- **D10 Cloud sync** keeps sending the legacy fields (server-filled) until Task 5, then stops; Supabase drops the columns after the code deploy.

## Review Focus

1. **Running batch, recipe edited.** Editing recipe 32 through `PUT /api/recipes/32` to move FG a lot (for example 1.011 → 1.025) while batch 16 ferments must not move its rest trigger, dry-hop trigger or ML expected FG. The test re-queries in a fresh session and runs the real rest rule tick, `_dry_hop_alert` and `GET /api/batches/{id}/predictions` (Task 3, `test_recipe_edit_does_not_move_fermenting_batch`).
2. **Deploy does not move a running batch.** After the Task 3 migration, batch 16's rest and dry-hop triggers equal their pre-deploy values (Task 3, `test_backfill_uses_legacy_stats_for_running_batches`).
3. **Hop with duration in days or hours** (BeerJSON imports) is not counted as a long boil (Task 1, `test_duration_units_normalised`).
4. **Editor while the Pi is slow or offline.** If `/calculate` fails, the last good numbers stay with a "not updated" state, never fake numbers (Task 4, vitest `keeps last stats when calculate fails`).
5. **Data loss on column drop.** Every legacy stat with no calculated value and no target is copied to `target_*`, per field (Task 5, `test_drop_preserves_uncalculable_stats_per_field`).

---

### Task 1: One hardened backend calculator (`tilt_ui-4x2f.1`)

**Files:**
- Modify: `backend/services/brewing.py` (`calculate_recipe_stats:303`, `get_attenuation_from_cultures:272`, `_calculate_ibu:134`, `calculate_og_from_fermentables:60`)
- Modify: `backend/services/llm/tools/recipe.py` (delete the copy at `:449` and its private helpers)
- Test: `backend/tests/test_recipe_stats_calculator.py` (new); repoint `backend/tests/test_brewing_ibu.py:124,215,307,313`, `test_og_sugar_efficiency.py:67`, `tests/test_extract_hops_ibu.py:95` to `brewing`

**Interfaces:**
- Produces, in `backend/services/brewing.py`: `@dataclass(frozen=True) class CalculatedStats: og: float; fg: float; abv: float; ibu: float; srm: float; bu_gu: float; calories_per_330ml: int; color_hex: str; assumptions: tuple[str, ...]` with `to_dict() -> dict`.
- Produces: `calculate_recipe_stats(recipe) -> CalculatedStats | None`. It takes an ORM `Recipe`, or any object with `fermentables, hops, cultures, efficiency_percent, batch_size_liters, yeast_attenuation`. It is pure: no DB I/O and no lazy loads.
- Callers that read `stats["og"]` switch to attributes. Callers that wrote `recipe.og = …` keep writing (from `stats`, skipped when `None`) until Task 5.

- [ ] **Step 1: Write failing tests** in `test_recipe_stats_calculator.py` with in-memory ORM objects (no DB):
  - `test_recipe_32_golden`. Recipe 32 as of 2026-11-16:
    - Grains: Pale Ale 2.30 kg, 82.8 %, 3 SRM; Pilsen Malt 2.30 kg, 82.8 %, 1.6 SRM; Carapils 0.252 kg, 73.0 %, 1.5 SRM; Melanoidin 0.151 kg, 77.0 %, 28 SRM.
    - Hops: El Dorado 15 g, 15 %, boil 60 min; Cascade 20 g, 5.8 %, boil 10 min; Cascade 40 g, 5.8 %, whirlpool 20 min at 80 °C; Amarillo 30 g, 8.5 %, whirlpool 20 min at 80 °C; 3 dry hops.
    - Yeast US-05, 72–78 %. Batch 23 L, efficiency 73 %.
    - Expect `og == approx(1.050, abs=0.001)`, `ibu == approx(37, abs=1.5)`, `fg == approx(1.0125, abs=0.001)`, `assumptions == ()`.
  - `test_no_fermentables_returns_none`.
  - `test_attenuation_midpoint_then_recipe_then_default`:
    - 72–78 → 75.
    - Only max 80 → 80.
    - None, with `yeast_attenuation=70` → 70.
    - None at all → 75, and the assumption is listed.
  - `test_duration_units_normalised`: a boil hop at `{"value": 1, "unit": "hr"}` gives the same IBU as one at 60 min. A dry hop at `{"value": 4, "unit": "day"}` gives 0.
  - `test_missing_inputs_listed_in_assumptions`: no efficiency, "Mystery Grain" with no yield or colour, a hop with no alpha, and a whirlpool hop with no temperature → one assumption line for each.
  - `test_sugar_ignores_efficiency`: 0.5 kg dextrose adds the same points at 50 % and 90 % efficiency.
  - `test_srm_uncapped_hex_clamped`: an imperial stout grist gives `srm > 40`, and `color_hex == srm_to_hex(40)`.
  - `test_bu_gu_and_calories`: expected values are copied from 2 current vitest cases for `calculateBUGU` and `calculateCalories`.
- [ ] **Step 2:** `pytest backend/tests/test_recipe_stats_calculator.py -q` → FAIL (`CalculatedStats` not defined).
- [ ] **Step 3:** Implement per D3. Port `srm_to_hex`, BU:GU and calories from `calculations.ts` to Python. Delete the LLM copy and repoint its tests.
- [ ] **Step 4:** Full backend suite green. Change existing IBU/OG expectations only where D3 changes them on purpose, and list each one in the commit message.
- [ ] **Step 5:** Commit, codex review, merge, deploy.

### Task 2: `calculated` in the API, `POST /api/recipes/calculate`, server-filled legacy columns (`tilt_ui-4x2f.2`)

**Files:**
- Create: `backend/services/recipe_stats.py` with `recipe_with_ingredients_stmt()`, `batch_with_recipe_options()`, `EffectiveStats`, `effective_stats()`, `fill_legacy_columns()`
- Modify: `backend/models.py` (`RecipeResponse:1922`, `RecipeDetailResponse:2112`; new `CalculatedStatsResponse`, `RecipeDraftCalculateRequest`)
- Modify: `backend/routers/recipes.py`:
  - list (`:270`), detail, create/update/import/scale responses
  - create (`:508-548`) and update (`:729-765`) fill legacy columns via `fill_legacy_columns`, ignoring client stat values
  - new `POST /calculate`
- Modify: `backend/routers/batches.py` (every query that serialises `BatchResponse.recipe` uses `batch_with_recipe_options()`)
- Modify: `backend/services/llm/tools/recipe_v2.py:254-279` and `backend/services/llm/tools/recipe.py:1087-1093` (call `fill_legacy_columns`)
- Test: `backend/tests/test_recipe_calculated_api.py` (new)

**Interfaces:**
- Consumes: `calculate_recipe_stats`, `CalculatedStats` (Task 1).
- Produces: `recipe_with_ingredients_stmt() -> Select[tuple[Recipe]]` (selectinload fermentables, hops, cultures, style).
- Produces: `batch_with_recipe_options() -> list[LoaderOption]` (`selectinload(Batch.recipe)` plus the same nested loads).
- Produces: `@dataclass class EffectiveStats: og: float | None; fg: float | None; abv: float | None; ibu: float | None; srm: float | None; source: Literal["calculated", "declared", "empty"]`, and `effective_stats(recipe) -> EffectiveStats` (per field, per D5).
- Produces: `fill_legacy_columns(recipe) -> None`. It writes `recipe.og/fg/abv/ibu/color_srm` from `calculate_recipe_stats` and leaves them untouched when that returns None. Deleted in Task 5.
- Produces: `to_recipe_response(recipe)` and `to_recipe_detail_response(recipe)`. These are the only builders.
- Produces: `POST /api/recipes/calculate`.
  - Body is `RecipeDraftCalculateRequest {batch_size_liters, efficiency_percent, yeast_attenuation, fermentables: [{name, amount_kg, yield_percent?, potential_sg?, color_srm?, type?}], hops: [{name, amount_grams, alpha_acid_percent?, form?, is_extract?, timing}], cultures: [{attenuation_min_percent?, attenuation_max_percent?}]}`.
  - The field names match the editor payload built by `recipe_ingredients._build_*`.
  - Returns `CalculatedStatsResponse | null`.

- [ ] **Step 1: Failing tests:**
  - `test_list_and_detail_include_calculated`
  - `test_declared_only_recipe_has_null_calculated`
  - `test_effective_stats_per_field` (calculated `og`/`fg`, no hops plus `target_ibu=40` → `ibu=0`, which is calculated, not 40; no grains plus `target_og` only → `og` declared, the rest None)
  - `test_calculate_endpoint_matches_saved_recipe`
  - `test_calculate_endpoint_empty_returns_null`
  - `test_update_ignores_client_stats` (a PUT with `og=1.200` stores the calculated OG)
  - `test_importer_writes_targets`
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Suite green. After deploy, `curl` `/api/recipes/32` on the Pi shows `calculated.ibu ≈ 37`. Recipe 25 shows its real IBU, so verify `tilt_ui-lc6y` and close it.
- [ ] **Step 5:** Commit, review, merge, deploy.

### Task 3: Batch numbers and backend readers (`tilt_ui-4x2f.3`)

**Files:**
- Modify: `backend/models.py` (`Batch:550` gets `expected_og/fg/abv/ibu/srm: Optional[float]`; `BatchResponse` exposes them)
- Modify: `backend/database.py`: `_migrate_add_batch_expected_columns` plus a synchronous backfill in `init_db` before serving, per D6 (legacy recipe columns first, every status at or past `fermenting`, soft-deleted included)
- Create: `supabase/migrations/<ts>_batch_expected_stats.sql` (add columns, plus the same backfill from the legacy recipe columns)
- Modify: `backend/routers/batches.py`:
  - create `:314` (load via `recipe_with_ingredients_stmt`)
  - recipe reassignment `:430-431`
  - entering fermenting `:353`, `:469`
  - progress `:804-843`
- Modify: `backend/services/alert_service.py:156-158`, `:375`, `:408-417` (`_dry_hop_alert` uses `batch_expected_*`)
- Modify: `backend/temp_controller.py:771-792`, `:890`
- Modify: `backend/ml/pipeline_manager.py:203-209`
- Modify: `backend/services/llm/tools/fermentation.py:92`, `:138`, `:205-207`, `:236`
- Modify: `backend/services/llm/tools/recipe.py:60-64`, `:921-927`
- Modify: `backend/services/llm/tools/recipe_v2.py:285-309` (`_stats`/`_warnings` use `calculate_recipe_stats` directly)
- Modify exporters per D8: `backend/services/converters/recipe_to_brewfather.py:49-58`; `backend/services/converters/brewsignal_v2.py:285-294` (v2 stat fields = `target_*`); the strict BeerJSON export path at `routers/recipes.py:470-471` (effective stats)
- Test: `backend/tests/test_batch_expected.py` (new). Change seeds in `test_rest_rule.py`, `test_predict_batch.py`, `test_alert_context.py`, `test_dry_hop_alert.py` and `test_batches_api.py` from `Recipe(og=, fg=)` to `target_*`, or to a snapshot for fermenting batches.

**Interfaces:**
- Consumes: `effective_stats`, `recipe_with_ingredients_stmt`, `batch_with_recipe_options` (Task 2).
- Produces, in `backend/services/recipe_stats.py`:
  - `snapshot_expected(batch, recipe | None) -> None`
  - `batch_expected_og(batch) -> float | None`
  - `batch_expected_fg(batch) -> float | None`
  - The 2 readers need `batch.recipe` loaded with ingredients only for `planning`/`brewing` batches.
- Every batch-side read of `recipe.og`/`recipe.fg` goes through those helpers. The check: `grep -rnE "recipe\.(og|fg)\b|Recipe\.(og|fg)\b" backend --include=*.py` must show hits only in `recipe_stats.py`, `database.py` migrations, `fill_legacy_columns` and tests.

- [ ] **Step 1: Failing tests:**
  - `test_planning_batch_reads_recipe_live` (an assistant-style edit through `update_recipe_document` shows up)
  - `test_snapshot_on_entering_fermenting`
  - `test_recipe_edit_does_not_move_fermenting_batch` (Review Focus 1, as specified there)
  - `test_reassign_recipe_resnapshots_fermenting_batch`
  - `test_unlink_recipe_clears_snapshot`
  - `test_measured_og_wins`
  - `test_backfill_uses_legacy_stats_for_running_batches` (Review Focus 2: a stored `og/fg` that differs from the calculated value gives a snapshot equal to the stored value; completed and soft-deleted batches are filled too)
  - `test_declared_only_recipe_feeds_batch` (`target_fg` only → expected FG)
  - `test_brewfather_export_uses_effective_stats`
  - `test_v2_stat_fields_are_targets_and_roundtrip` (export → import keeps `target_*`; a recipe with no targets exports no stat fields and re-imports with no targets)
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Run the grep check.
- [ ] **Step 4:** Suite green. Back up the Pi DB, then deploy. Check batch 16: `expected_fg` equals the old stored recipe FG, the rest status and dry-hop state are unchanged, and `/api/batches/16/predictions` is unchanged.
- [ ] **Step 5:** Commit, review, merge, deploy. Cloud: deploy the code, then run the SQL.

### Task 4: Frontend reads the backend numbers; editor uses `/calculate`; TS calculator deleted (`tilt_ui-4x2f.4`)

**Files:**
- Modify: `frontend/src/lib/api.ts` (types `CalculatedStats`, `RecipeResponse.calculated`, batch `expected_*`; `calculateRecipeDraft(draft, signal)`)
- Create: `frontend/src/lib/recipeStats.ts` with `effectiveStats(recipe)`, `batchExpected(batch)` and `statDiffers(calc, target)`. These are display rules only, with no brewing maths.
- Modify recipe pages:
  - `routes/recipes/[id]/+page.svelte` (delete `liveStats` and the fallback constants at `:487-499`)
  - `RecipeStatsPanel.svelte`
  - `routes/recipes/+page.svelte:127-136`
  - `routes/recipes/[id]/edit/+page.svelte:63-65`, `:246-250`
  - `routes/recipes/new/+page.svelte:39-43`
- Modify the editor: `components/recipe/RecipeBuilder.svelte:369`, `:383-428`, `:548-552`, `:586-594`. `FermentableSelector.svelte:64-72` and `HopSelector.svelte:92-102` show section totals; they get them as props from RecipeBuilder's `/calculate` result instead of calculating.
- Modify batch and picker components: `RecipeSelector.svelte:101-102`, `BatchForm.svelte:96-103`, `:194-195`, `BatchRecipeTargetsCard.svelte:19-41`, `BatchFermentationCard.svelte:58`, `:140-188`, `MLPredictions.svelte:107-116`, `PhaseFermentation.svelte:111`, `BrewDayObservations.svelte:35-36`
- Delete: `frontend/src/lib/components/RecipeCard.svelte` and `RecipeForm.svelte` (unused), plus the D2 stat functions and their tests. Fix `styleWarnings.ts`/`brewability.ts` if they import them.
- Test: `frontend/src/lib/recipeStats.test.ts`, and a RecipeBuilder draft-calculation test

**Interfaces:**
- Consumes: `calculated`, `target_*`, `expected_*`, and `POST /api/recipes/calculate` (Tasks 2–3).
- Produces: `calculateRecipeDraft(draft: RecipeDraft, signal?: AbortSignal): Promise<CalculatedStats | null>`. RecipeBuilder debounces 200 ms and aborts the previous request.
- Create and update payloads stop sending stat fields. The server already ignores them after Task 2.

- [ ] **Step 1: Failing vitest:**
  - `effectiveStats` per field (calculated / declared / empty)
  - `statDiffers` thresholds (0.002 SG, 2 IBU)
  - `batchExpected` (`measured_og` → snapshot → recipe)
  - `keeps last stats when calculate fails` (Review Focus 4)
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `svelte-check` shows 0 errors, vitest is green, and `BUILD_TARGET=pi npm run build` works. Gemini 4 Carbon does a UI review of the recipe page and the editor stat strip, from Playwright screenshots of `https://brewsignal.tail01c63e.ts.net/recipes/32` and its edit page.
- [ ] **Step 5:** Commit, review, merge, deploy. Check that the recipe 32 page shows IBU ≈ 37 and that the batch 16 targets card is unchanged.

### Task 5: Drop the stored columns (`tilt_ui-4x2f.5`)

**Files:**
- Modify: `backend/models.py`. Remove `Recipe.og/fg/abv/ibu/color_srm` (`:463-467`) and remove them from `RecipeCreate:1800`, `RecipeUpdate:1827`, `RecipeResponse` and `RecipeDetailResponse`. Set `lazy="raise"` on `Recipe.fermentables/hops/cultures`.
- Modify: `backend/database.py`. Add `_migrate_drop_recipe_stat_columns`, registered **after** `migrate_add_recipe_target_stats` (`:662`; Fable F9). It skips when the columns are absent. It does 2 things:
  1. Copy per field: `target_x = COALESCE(target_x, x)` wherever `target_x` is NULL and the calculator returns None for that field (Fable F10 / Gemini #8). Do this in Python with `calculate_recipe_stats`, not SQL.
  2. `ALTER TABLE recipes DROP COLUMN` for each of the 5 columns. There are no index, CHECK or default dependencies: checked on the Pi on 2026-11-16, where the only recipes index is `ix_recipes_user_id`.
- Create: `supabase/migrations/<ts>_drop_recipe_stat_columns.sql` (copy where there are no fermentables, then drop). Run it after the code deploy.
- Modify: `backend/routers/recipes.py`. Delete `/recalculate` (`:795-831`) and `?recalculate` (`:687`, `:759-765`). Change the stat constraint validation (`:488-492`, `:768-772`) to validate `calculated`.
- Modify: `backend/routers/sync.py:270-274` (stop sending the 5 fields)
- Modify: `backend/services/recipe_stats.py` (delete `fill_legacy_columns` and its call sites)
- Delete: `backend/migrations/backfill_recipe_color_srm.py`, its call at `database.py:760-766`, and its test. Delete `backend/services/recipe_importer.py` (unused; Fable F8) and its tests.
- Modify: `frontend/src/lib/api.ts` (remove the legacy stat fields)
- Test: `backend/tests/test_drop_recipe_stat_columns.py` (new). Update the importer tests that assert `recipe.og == declared` so they assert `recipe.target_og == declared`:
  - `tests/test_full_import_e2e.py:67-71`
  - `tests/test_recipe_import_integration.py:178-182`
  - `backend/tests/test_brewsignal_v2_import.py:18-19`
  - `test_brewfather_converter.py:218-242`
  - `test_recipes_api.py:297-381`, `:409`, `:467`
  - `test_recipe_scale.py:183`
  - `test_recipe_ingredients_persist.py:85`

**Interfaces:**
- After this task, the only sources of stats are `calculate_recipe_stats` (through `to_recipe_response`/`effective_stats`) and `batch_expected_*`.

- [ ] **Step 1: Failing tests:**
  - `test_drop_preserves_uncalculable_stats_per_field` (Review Focus 5: a recipe with grains but no hops keeps a stored `ibu=40` in `target_ibu`; a recipe with no grains keeps all 5)
  - `test_drop_is_idempotent`
  - `test_drop_runs_after_target_migration_on_old_db` (an old schema with no `target_*` columns migrates cleanly)
  - `test_lazy_raise_catches_unloaded_ingredients`
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Fix every `lazy="raise"` failure by routing that query through `recipe_with_ingredients_stmt()` or `batch_with_recipe_options()`.
- [ ] **Step 4:** Full suites green. Back up the Pi, then deploy. `pragma table_info(recipes)` must show no `og/fg/abv/ibu/color_srm`. Smoke test: the recipe list, recipe 32, the batch 16 page, a Brewfather export of recipe 33, and the assistant's `list_recipes`.
- [ ] **Step 5:** Commit, review, merge, deploy (cloud: code first, then SQL). Close `tilt_ui-4x2f`. Update the `brewsignal-three-duplicate-stat-calculators` bd memory.

## Out of scope (separate beads)

- Pre-boil gravity (needs a reliable boil size and boil-off rate; `pre_boil_og` stays empty).
- Brewfather misc unit ×1000 bug, and recipe 33 whirlpool hops stored as boil (found 2026-11-16).
- Dry-hop disturbance window after "Mark dry hopped" (offered 2026-11-16, not yet decided).
