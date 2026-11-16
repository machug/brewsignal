-- tilt_ui-4x2f.3: batches keep the recipe's expected stats from when they started fermenting.
-- NOT applied automatically to hosted. Run after the code deploy.
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_og" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_fg" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_abv" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_ibu" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "expected_srm" double precision;

-- Backfill every batch at or past fermenting (soft-deleted included) from the legacy
-- stored recipe numbers, only where nothing is set yet.
UPDATE "public"."batches" b
SET expected_og = r.og, expected_fg = r.fg, expected_abv = r.abv,
    expected_ibu = r.ibu, expected_srm = r.color_srm
FROM "public"."recipes" r
WHERE r.id = b.recipe_id
  AND b.status NOT IN ('planning', 'brewing')
  AND b.expected_og IS NULL AND b.expected_fg IS NULL AND b.expected_abv IS NULL
  AND b.expected_ibu IS NULL AND b.expected_srm IS NULL;
