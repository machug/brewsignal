-- Backfill zero-min boil hops as whirlpool/flameout additions.
-- Mirrors backend/migrations/backfill_zero_min_boil_to_whirlpool.py for
-- the cloud schema. Pre-2.13.0 imports of Brewfather Whirlpool hops
-- landed as use=add_to_boil with duration.value=0; the new stand-time
-- IBU model needs add_to_whirlpool to credit them. Heuristic: only
-- retag rows with EXPLICIT duration of 0 — missing duration is
-- ambiguous (legacy First Wort additions imply the recipe boil time).

-- 1. recipe_hops.timing
UPDATE "public"."recipe_hops"
SET "timing" = jsonb_set("timing"::jsonb, '{use}', '"add_to_whirlpool"')
WHERE "timing" IS NOT NULL
  AND lower(coalesce("timing"->>'use', '')) IN ('add_to_boil', 'boil')
  AND "timing" ? 'duration'
  AND (
    -- duration as object: {value: 0, unit: ...}
    (jsonb_typeof("timing"->'duration') = 'object'
     AND "timing"->'duration' ? 'value'
     AND ("timing"->'duration'->>'value')::numeric = 0)
    OR
    -- duration as scalar: 0
    (jsonb_typeof("timing"->'duration') = 'number'
     AND ("timing"->>'duration')::numeric = 0)
  );

-- 2. recipes.format_extensions.hops[*].use
-- Postgres jsonb path mutation requires walking the array. Build a new
-- hops array with the offending entries' use rewritten, then write it
-- back. A subquery+jsonb_agg approach is simplest and readable.
UPDATE "public"."recipes" r
SET "format_extensions" = jsonb_set(
    "format_extensions"::jsonb,
    '{hops}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN lower(coalesce(hop->>'use', '')) IN ('add_to_boil', 'boil')
                     AND hop ? 'boil_time_minutes'
                     AND (hop->>'boil_time_minutes')::numeric = 0
                THEN jsonb_set(hop, '{use}', '"add_to_whirlpool"')
                ELSE hop
            END
            ORDER BY ord
        )
        FROM jsonb_array_elements(r."format_extensions"::jsonb->'hops')
            WITH ORDINALITY AS arr(hop, ord)
    )
)
WHERE "format_extensions" IS NOT NULL
  AND jsonb_typeof("format_extensions"::jsonb->'hops') = 'array'
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(r."format_extensions"::jsonb->'hops') AS hop
      WHERE lower(coalesce(hop->>'use', '')) IN ('add_to_boil', 'boil')
        AND hop ? 'boil_time_minutes'
        AND (hop->>'boil_time_minutes')::numeric = 0
  );
