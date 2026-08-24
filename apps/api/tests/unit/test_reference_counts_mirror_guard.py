"""The installer's reference thresholds ARE the seed SQL's. Pin them together.

``verify_installation._REFERENCE_COUNTS`` calls itself "the same order and
thresholds as verify_reference_seeds.sql". Nothing enforced that, and it had
drifted on four of six rows — most damagingly by becoming STRICTER than the
SQL: ADR-244 removed three ``llm_config_overrides`` rows and lowered the SQL
floor to 39, the Python copy stayed at 41, and every leg of the disposable
installer smoke then declared a correct fresh install broken (measured
2026-08-24, four legs out of four).

Two copies of one number need a test, or the comment claiming they agree is the
only thing holding them together — and a comment cannot fail a build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SEED_SQL = (
    Path(__file__).resolve().parents[4]
    / "infrastructure"
    / "database"
    / "seeds"
    / "verify_reference_seeds.sql"
)

#: `SELECT COUNT(*) INTO c FROM <table>;` followed by `IF c <> N` / `IF c < N`.
_BLOCK = re.compile(
    r"SELECT\s+COUNT\(\*\)\s+INTO\s+c\s+FROM\s+(?P<table>\w+)\s*;.*?IF\s+c\s+(?P<op><>|<)\s*(?P<n>\d+)",
    re.IGNORECASE | re.DOTALL,
)


def _thresholds_from_sql() -> list[tuple[str, int, bool]]:
    """Every postcondition the seed transaction enforces, in file order."""
    sql = _SEED_SQL.read_text(encoding="utf-8")
    found = [
        (m.group("table"), int(m.group("n")), m.group("op") == "<>") for m in _BLOCK.finditer(sql)
    ]
    assert found, "no COUNT postcondition parsed — the SQL shape changed"
    return found


def test_the_seed_sql_still_declares_postconditions() -> None:
    """Guard the guard: a parse returning nothing must not read as agreement."""
    assert len(_thresholds_from_sql()) >= 6


def test_reference_counts_mirror_the_seed_sql() -> None:
    """Same tables, same order, same numbers, same exact-vs-floor semantics."""
    from scripts.data.verify_installation import _REFERENCE_COUNTS

    assert list(_REFERENCE_COUNTS) == _thresholds_from_sql(), (
        "verify_installation._REFERENCE_COUNTS drifted from "
        "verify_reference_seeds.sql — the SQL is the authority"
    )


def test_the_sql_query_selects_exactly_those_tables_in_order() -> None:
    """A threshold nobody counts is not a check; a count nobody reads is noise."""
    from scripts.data.verify_installation import _REFERENCE_COUNTS, _REFERENCE_COUNTS_SQL

    selected = re.findall(r"FROM (\w+)\) AS (\w+)", str(_REFERENCE_COUNTS_SQL))
    assert [table for table, _alias in selected] == [name for name, _n, _e in _REFERENCE_COUNTS]
    assert [alias for _table, alias in selected] == [name for name, _n, _e in _REFERENCE_COUNTS]
