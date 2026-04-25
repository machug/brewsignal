-- tilt_ui-ak6: split imported brewer-declared targets from calculated stats.
-- Mirror columns of the existing og/fg/abv/ibu/color_srm fields on recipes.
-- Importers populate both at import time; the recalculator only touches the
-- canonical og/fg/abv/ibu/color_srm columns, leaving target_* as the
-- source-of-truth surface for the UI.

ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_og" real;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_fg" real;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_abv" real;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_ibu" real;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_srm" real;

-- Backfill: existing recipes carry their imported brewer-declared values
-- only in the canonical og/fg/abv/ibu/color_srm columns. The first
-- ?recalculate=true after migration would otherwise erase the only copy.
-- Seed target_* from the canonical column where target_* is still NULL.
UPDATE "public"."recipes" SET
    "target_og" = COALESCE("target_og", "og"),
    "target_fg" = COALESCE("target_fg", "fg"),
    "target_abv" = COALESCE("target_abv", "abv"),
    "target_ibu" = COALESCE("target_ibu", "ibu"),
    "target_srm" = COALESCE("target_srm", "color_srm");
