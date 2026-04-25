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
