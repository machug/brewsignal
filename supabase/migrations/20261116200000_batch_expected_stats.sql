-- tilt_ui-4x2f.3: batches keep the recipe's expected stats from when they started fermenting.
-- NOT applied automatically to hosted. This migration is ADDITIVE: run it BEFORE the code
-- deploy, because the new code selects and syncs the expected_* columns.
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_og" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_fg" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_abv" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_ibu" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_srm" double precision;

-- Backfill every batch at or past fermenting (soft-deleted included), per field: the legacy
-- stored recipe number first, then the declared target. Only where nothing is set yet.
UPDATE "public"."batches" b
SET expected_og = COALESCE(r.og, r.target_og),
    expected_fg = COALESCE(r.fg, r.target_fg),
    expected_abv = COALESCE(r.abv, r.target_abv),
    expected_ibu = COALESCE(r.ibu, r.target_ibu),
    expected_srm = COALESCE(r.color_srm, r.target_srm)
FROM "public"."recipes" r
WHERE r.id = b.recipe_id
  AND b.status NOT IN ('planning', 'brewing')
  AND b.expected_og IS NULL AND b.expected_fg IS NULL AND b.expected_abv IS NULL
  AND b.expected_ibu IS NULL AND b.expected_srm IS NULL;
