-- tilt_ui-8d49: one set of equipment per controlled batch.
-- tilt_ui-f50x: persisted per-entity switch state for the temperature controller.
--
-- NOT applied automatically to hosted. The controller itself runs on the Pi
-- (SQLite); this keeps the hosted schema in step with the models.
--
-- The legacy idx_fermenting_*_unique indexes only cover status = 'fermenting',
-- but the controller also drives 'conditioning' batches. The new indexes cover
-- both, ignore soft-deleted batches, and are per user (hosted is multi-tenant).
-- If live rows already collide, that index is skipped with a WARNING instead
-- of failing the whole migration; the legacy indexes are left in place.

DO $$
DECLARE
    spec RECORD;
    conflicts integer;
BEGIN
    FOR spec IN
        SELECT * FROM (VALUES
            ('idx_active_heater_unique', 'heater_entity_id'),
            ('idx_active_cooler_unique', 'cooler_entity_id'),
            ('idx_active_device_unique', 'device_id')
        ) AS t(idx, col)
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM (SELECT 1 FROM public.batches '
            'WHERE status IN (''fermenting'', ''conditioning'') AND deleted_at IS NULL AND %I IS NOT NULL '
            'GROUP BY user_id, %I HAVING count(*) > 1) c',
            spec.col, spec.col
        ) INTO conflicts;

        IF conflicts > 0 THEN
            RAISE WARNING 'Not creating %: % group(s) of active batches share %', spec.idx, conflicts, spec.col;
        ELSE
            EXECUTE format(
                'CREATE UNIQUE INDEX IF NOT EXISTS %I ON public.batches (user_id, %I) '
                'WHERE status IN (''fermenting'', ''conditioning'') AND deleted_at IS NULL AND %I IS NOT NULL',
                spec.idx, spec.col, spec.col
            );
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS "public"."control_entity_state" (
    "entity_id"      character varying(100) PRIMARY KEY,
    "last_switch_at" timestamp with time zone,
    "on_since"       timestamp with time zone,
    "locked_until"   timestamp with time zone
);

-- Controller-internal table: no policies, so only the service role (direct
-- Postgres connection) can touch it; anon/authenticated get nothing.
ALTER TABLE "public"."control_entity_state" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "public"."control_entity_state" FROM anon, authenticated;
