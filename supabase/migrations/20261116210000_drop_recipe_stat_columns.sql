-- tilt_ui-4x2f.5: recipes no longer store og/fg/abv/ibu/color_srm (calculated on read).
-- NOT applied automatically to hosted. DESTRUCTIVE: run it AFTER the code deploy, never before:
-- the old code still selects these columns and would fail without them.
--
-- Approximation of the app's Python migration (which uses the calculator): the SQL cannot
-- run the calculator, so it only copies where the recipe has no fermentables (nothing to
-- calculate from) and, for IBU, no bittering hops (a dry-hop-only recipe keeps its declared IBU). target_* is never overwritten.
UPDATE "public"."recipes" r
SET target_og  = COALESCE(r.target_og, r.og),
    target_fg  = COALESCE(r.target_fg, r.fg),
    target_abv = COALESCE(r.target_abv, r.abv),
    target_srm = COALESCE(r.target_srm, r.color_srm),
    target_ibu = COALESCE(r.target_ibu, r.ibu)
WHERE NOT EXISTS (SELECT 1 FROM "public"."recipe_fermentables" f WHERE f.recipe_id = r.id AND f.amount_kg > 0);

UPDATE "public"."recipes" r
SET target_ibu = COALESCE(r.target_ibu, r.ibu)
WHERE NOT EXISTS (
    SELECT 1 FROM "public"."recipe_hops" h
    WHERE h.recipe_id = r.id AND h.amount_grams > 0
      -- bittering = boil, whirlpool, first wort or mash; a hop with no recorded use counts as bittering
      AND (h."timing" IS NULL
           OR lower(coalesce(h."timing"::jsonb->>'use', '')) IN
              ('', 'boil', 'add_to_boil', 'whirlpool', 'add_to_whirlpool', 'first_wort', 'mash', 'add_to_mash'))
);

ALTER TABLE "public"."recipes" DROP COLUMN IF EXISTS "og";
ALTER TABLE "public"."recipes" DROP COLUMN IF EXISTS "fg";
ALTER TABLE "public"."recipes" DROP COLUMN IF EXISTS "abv";
ALTER TABLE "public"."recipes" DROP COLUMN IF EXISTS "ibu";
ALTER TABLE "public"."recipes" DROP COLUMN IF EXISTS "color_srm";
