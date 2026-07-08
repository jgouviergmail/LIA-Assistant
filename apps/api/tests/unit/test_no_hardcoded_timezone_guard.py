"""Systemic guards for the datetime/timezone doctrine, enforced statically on src/.

Two independent AST scans over every ``src/**/*.py`` file:

1. **No hardcoded ``"Europe/Paris"`` default** (``TestNoHardcodedParisTimezone``).
   The user's display timezone must come from their preferences or, as a last
   resort, from the single central default ``DEFAULT_USER_DISPLAY_TIMEZONE``
   (``src/core/constants.py``). A hardcoded ``"Europe/Paris"`` literal as a
   parameter default, ``.get(..., "Europe/Paris")`` fallback, ``default=`` column
   value, or ``Field(default=...)`` silently pins every un-migrated code path to
   Paris and defeats the central knob (C3, project rule "never a hardcoded
   'Europe/Paris' literal"). The scan flags any string literal (``ast.Constant``)
   whose value is **exactly** ``"Europe/Paris"``. Exact-equality is deliberate:
   it naturally excludes docstrings, comments, and longer illustrative strings
   (``"e.g. 'Europe/Paris'"``) which are legitimate documentation.

2. **No naive datetime construction** (``TestNoNaiveDatetimeCalls``).
   ``datetime.now()`` without a tz argument, ``datetime.utcnow()``, and
   ``date.today()`` / ``datetime.today()`` all produce values pinned to the
   *server's* clock/timezone frame: naive datetimes poison aware comparisons,
   and the server's date is NOT the user's date (at 01:00 in Paris,
   ``date.today()`` on a UTC server still returns yesterday). Use
   ``datetime.now(UTC)`` for technical timestamps (cache keys, TTLs,
   comparisons) and ``now_in_timezone()`` / ``get_current_datetime_context()``
   from ``core/time_utils.py`` for anything shown or spoken to the user.
   The scan flags the forbidden **call expressions**; examples inside
   docstrings are string constants, not calls, and are intentionally out of
   scope (same design choice as scan #1).

Both scans have their own allow-list. If a new legitimate usage appears, add
the file with a justification — do not weaken the scan. Each scan also has a
self-check test so it cannot rot silently.

Context: 2026-07 latent-debt remediation (C3); naive-datetime scan added after
the 2026-07 audit found the CLAUDE.md "enforced in CI" claim did not yet cover
naive ``datetime.now()``.
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

LITERAL = "Europe/Paris"

# Files where an exact "Europe/Paris" literal is legitimate DATA, not an
# application default that should resolve the user's timezone:
#   - core/constants.py: THE central definition (DEFAULT_USER_DISPLAY_TIMEZONE).
#   - core/validators.py: one valid selectable zone in the COMMON_TIMEZONES
#     picker list (a valid option, not "the default").
#   - domains/agents/semantic/core_types.py: an illustrative value in a Pydantic
#     ``examples=[...]`` list.
ALLOWED_FILES: set[str] = {
    "core/constants.py",
    "core/validators.py",
    "domains/agents/semantic/core_types.py",
}


def _iter_paris_literals(tree: ast.AST):
    """Yield the line number of every exact ``"Europe/Paris"`` string constant."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == LITERAL:
                yield node.lineno


class TestTimezoneGuardScan:
    """Sanity check on the scan itself (guards against scan rot)."""

    def test_scan_detects_the_central_definition(self):
        """The scan must detect the exact literal where it legitimately lives."""
        constants_file = SRC_DIR / "core" / "constants.py"
        linenos = list(_iter_paris_literals(ast.parse(constants_file.read_text(encoding="utf-8"))))
        assert linenos, (
            "The AST scan no longer detects the exact 'Europe/Paris' literal in "
            "core/constants.py — the guard is broken, fix it before trusting it."
        )


class TestNoHardcodedParisTimezone:
    """CI guard: any hardcoded 'Europe/Paris' default fails the build."""

    def test_no_hardcoded_paris_default(self):
        """Scan all production code for hardcoded 'Europe/Paris' literals."""
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in ALLOWED_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno in _iter_paris_literals(tree):
                violations.append(f"src/{rel_path}:{lineno}")

        if violations:
            pytest.fail(
                "Hardcoded 'Europe/Paris' timezone default(s) detected — resolve the "
                "user's timezone or reference DEFAULT_USER_DISPLAY_TIMEZONE instead:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )


# =============================================================================
# Scan #2 — naive datetime construction (datetime.now() / utcnow() / today())
# =============================================================================

# Files where the forbidden call names may legitimately appear:
#   - core/time_utils.py: THE datetime doctrine module — documents the
#     anti-patterns and hosts the canonical aware wrappers (now_utc,
#     now_in_timezone). Allow-listed explicitly so the doctrine file can never
#     trip its own guard, even if a future wrapper needs an unusual form.
NAIVE_DATETIME_ALLOWED_FILES: set[str] = {
    "core/time_utils.py",
}

# Receivers whose ``.today()`` is the stdlib naive-date constructor. Matched on
# the terminal attribute/name so aliased forms (``dt.datetime.today()``) are
# caught too.
_TODAY_RECEIVERS = frozenset({"date", "datetime"})


def _receiver_name(node: ast.expr) -> str | None:
    """Return the terminal name of a call receiver.

    ``datetime.now()`` → ``"datetime"`` (ast.Name), ``dt.datetime.now()`` →
    ``"datetime"`` (ast.Attribute). Anything else (subscripts, calls) → None.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_tz_naive_now_call(call: ast.Call) -> bool:
    """True when a ``.now()`` call carries no usable tz argument.

    Flags ``now()``, ``now(None)`` and ``now(tz=None)``; any other argument
    shape (``now(UTC)``, ``now(tz=tz)``, ``now(ZoneInfo(...))``) is aware or at
    least explicit, and is left to code review.
    """
    if not call.args and not call.keywords:
        return True
    if len(call.args) == 1 and not call.keywords:
        arg = call.args[0]
        return isinstance(arg, ast.Constant) and arg.value is None
    if not call.args and len(call.keywords) == 1 and call.keywords[0].arg == "tz":
        value = call.keywords[0].value
        return isinstance(value, ast.Constant) and value.value is None
    return False


def _iter_naive_datetime_calls(tree: ast.AST):
    """Yield ``(lineno, description)`` for every forbidden naive datetime call.

    Detection rules (all on ``ast.Call`` nodes, so docstring examples are
    naturally excluded):
      - ``*.utcnow()`` — forbidden regardless of receiver (no legitimate use).
      - ``datetime.now()`` without tz — receiver must be the ``datetime`` class
        (``ast.Name`` or terminal ``ast.Attribute``), which excludes
        SQLAlchemy's server-side ``func.now()``.
      - ``date.today()`` / ``datetime.today()`` — always naive/server-local.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        receiver = _receiver_name(node.func.value)
        if attr == "utcnow":
            yield node.lineno, f"{receiver or '<expr>'}.utcnow() — use datetime.now(UTC)"
        elif attr == "now" and receiver == "datetime" and _is_tz_naive_now_call(node):
            yield (
                node.lineno,
                "datetime.now() without tz — use datetime.now(UTC) or now_in_timezone()",
            )
        elif attr == "today" and receiver in _TODAY_RECEIVERS:
            yield (
                node.lineno,
                f"{receiver}.today() — compute the date from an aware datetime "
                "(datetime.now(UTC).date() or now_in_timezone(tz).date())",
            )


class TestNaiveDatetimeGuardScan:
    """Sanity checks on the naive-datetime scan itself (guards against scan rot)."""

    def test_scan_detects_synthetic_violations(self):
        """Every forbidden call family must be detected in a synthetic snippet."""
        snippet = (
            "from datetime import date, datetime\n"
            "import datetime as dt\n"
            "a = datetime.now()\n"
            "b = datetime.utcnow()\n"
            "c = date.today()\n"
            "d = dt.datetime.now()\n"
            "e = datetime.now(tz=None)\n"
            "f = datetime.now(None)\n"
            "g = datetime.today()\n"
        )
        found = list(_iter_naive_datetime_calls(ast.parse(snippet)))
        assert len(found) == 7, (
            "The naive-datetime AST scan no longer detects the synthetic "
            f"violations (found {len(found)}/7) — the guard is broken, fix it "
            "before trusting it."
        )

    def test_scan_ignores_legitimate_calls(self):
        """Aware calls and SQLAlchemy server-side now() must not be flagged."""
        snippet = (
            "from datetime import UTC, datetime\n"
            "from zoneinfo import ZoneInfo\n"
            "from sqlalchemy import func\n"
            "a = datetime.now(UTC)\n"
            "b = datetime.now(tz=UTC)\n"
            "c = datetime.now(ZoneInfo('America/New_York'))\n"
            "d = func.now()\n"
        )
        assert list(_iter_naive_datetime_calls(ast.parse(snippet))) == []


class TestNoNaiveDatetimeCalls:
    """CI guard: naive datetime.now()/utcnow()/today() in src/ fails the build."""

    def test_no_naive_datetime_calls(self):
        """Scan all production code for naive datetime construction."""
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in NAIVE_DATETIME_ALLOWED_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno, description in _iter_naive_datetime_calls(tree):
                violations.append(f"src/{rel_path}:{lineno} — {description}")

        if violations:
            pytest.fail(
                "Naive datetime construction detected — all datetimes must be "
                "timezone-aware (datetime doctrine, core/time_utils.py):\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
