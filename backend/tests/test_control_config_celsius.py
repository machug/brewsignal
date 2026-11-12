"""Global control config stored in Fahrenheit is migrated to Celsius once (tilt_ui-xrq5.6)."""

import json

from sqlalchemy import create_engine, text

from backend.database import _migrate_global_control_config_to_celsius


def _run(rows, runs=2):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)"))
        for k, v in rows.items():
            conn.execute(text("INSERT INTO config VALUES (:k, :v)"), {"k": k, "v": json.dumps(v)})
        for _ in range(runs):  # second run must be a no-op
            _migrate_global_control_config_to_celsius(conn)
        out = {k: json.loads(v) for k, v in conn.execute(text("SELECT key, value FROM config"))}
    out.pop("control_config_celsius_v1")
    return out


def test_pi_values_are_converted_once():
    assert _run({"temp_target": 66.2, "temp_hysteresis": 1.08}) == {"temp_target": 19.0, "temp_hysteresis": 0.6}


def test_cold_crash_target_below_50f_is_converted():
    """Codex P2: a 40 F target must not be mistaken for 40 C."""
    assert _run({"temp_target": 40.0}) == {"temp_target": 4.4}


def test_fresh_install_sets_marker_and_later_celsius_saves_are_kept():
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)"))
        _migrate_global_control_config_to_celsius(conn)  # fresh: nothing to convert
        conn.execute(text("INSERT INTO config VALUES ('temp_target', '20.0')"))  # new UI saves C
        _migrate_global_control_config_to_celsius(conn)
        assert conn.execute(text("SELECT value FROM config WHERE key='temp_target'")).scalar() == "20.0"
