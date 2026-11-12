"""Global control config stored in Fahrenheit is migrated to Celsius (tilt_ui-xrq5.6)."""

import json

from sqlalchemy import create_engine, text

from backend.database import _migrate_global_control_config_to_celsius


def _run(target, hysteresis):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)"))
        conn.execute(text("INSERT INTO config VALUES ('temp_target', :t), ('temp_hysteresis', :h)"),
                     {"t": json.dumps(target), "h": json.dumps(hysteresis)})
        _migrate_global_control_config_to_celsius(conn)
        _migrate_global_control_config_to_celsius(conn)  # idempotent
        return {k: json.loads(v) for k, v in conn.execute(text("SELECT key, value FROM config"))}


def test_fahrenheit_values_on_the_pi_are_converted():
    assert _run(66.2, 1.08) == {"temp_target": 19.0, "temp_hysteresis": 0.6}


def test_celsius_values_are_left_alone():
    assert _run(20.0, 0.5) == {"temp_target": 20.0, "temp_hysteresis": 0.5}
