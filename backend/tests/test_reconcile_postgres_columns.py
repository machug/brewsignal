"""Tests for the Postgres column-reconciliation planner (tilt_ui-xf8).

_reconcile_postgres_columns() adds ORM columns missing from the live Supabase
schema. The decision of which columns to add — and what DB DEFAULT to give them
— lives in the pure _plan_column_additions() / _column_default_sql() helpers,
tested here. The DDL execution path is cloud-only (Postgres) and verified live
on deploy.

Policy under test: every missing column is added as a nullable Postgres column
(the DDL emits no NOT NULL constraint, so it's safe on populated tables and the
ORM still enforces required-ness on writes). Columns whose model declares a
scalar or server default carry that as a SQL DEFAULT so existing rows backfill
instead of going NULL (Codex P1). Existing columns are left alone.
"""
from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, text
from sqlalchemy.dialects import postgresql

from backend.database import _column_default_sql, _plan_column_additions

_DIALECT = postgresql.dialect()


def _table():
    md = MetaData()
    return Table(
        "widgets",
        md,
        Column("id", Integer, primary_key=True),
        Column("nickname", String(50)),                       # nullable, no default
        Column("created_by", String(36), nullable=False),     # NOT NULL, no default
        Column("is_extract", Boolean, nullable=False,         # scalar bool default
               default=False),
        Column("status", String(10), nullable=False,          # server default
               server_default=text("'new'")),
    )


def test_adds_every_missing_column():
    table = _table()
    to_add = _plan_column_additions(table, {"id"}, _DIALECT)
    assert {name for name, _, _ in to_add} == {"nickname", "created_by", "is_extract", "status"}


def test_renders_defaults_for_defaulted_columns():
    table = _table()
    defaults = {name: dsql for name, _, dsql in _plan_column_additions(table, {"id"}, _DIALECT)}
    # scalar bool default -> SQL literal; existing rows backfill to false, not NULL
    assert defaults["is_extract"] == "false"
    # server default text carried through
    assert defaults["status"] == "'new'"
    # no default declared -> no DEFAULT clause
    assert defaults["nickname"] is None
    assert defaults["created_by"] is None


def test_existing_columns_are_left_alone():
    table = _table()
    full = {"id", "nickname", "created_by", "is_extract", "status"}
    assert _plan_column_additions(table, full, _DIALECT) == []


def test_compiled_types_are_postgres_dialect():
    table = _table()
    types = {name: coltype for name, coltype, _ in _plan_column_additions(table, {"id"}, _DIALECT)}
    assert types["nickname"] == "VARCHAR(50)"


def test_string_default_is_quoted_and_escaped():
    md = MetaData()
    t = Table("t", md, Column("id", Integer, primary_key=True),
              Column("label", String(20), default="o'brien"))
    assert _column_default_sql(t.c.label) == "'o''brien'"
