"""Every door that prices a model call is handed the Claude cache writes (ADR-306).

A token Claude writes to its prompt cache costs 1.25x the input price. The
written tokens stay inside the prompt count -- they are prompt tokens -- so a
price computed from the three historical counts alone bills them at 1x, in
silence: nothing fails, the ledger is simply short. The surcharge therefore
travels as a fourth count, and the only thing that can drop it is a call site
that forgets to pass it on. The doors default it to zero so a test can build a
call in one line, which is exactly why a call in ``src/`` must say it out loud
-- including the doors that price something with no prompt cache (characters,
an embedding), where the explicit zero is the decision.

AST, not grep: a keyword written in a comment or a string must not satisfy the
guard, and a door reached through an alias (``estimate_cost_from_cache``) must
not escape it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

#: Every door that turns counts into euros, with the keyword carrying the writes.
DOORS: dict[str, str] = {
    "get_cached_cost_usd_eur": "cache_write_tokens",
    "get_cached_cost": "cache_write_tokens",
    "estimate_cost_from_cache": "cache_write_tokens",
    "record_node_tokens": "cache_write_tokens",
    "track_proactive_tokens": "tokens_cache_write",
    "record_instance_llm_spend": "tokens_cache_write",
}


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _offenders() -> list[str]:
    found: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node)
            keyword = DOORS.get(name or "")
            if keyword is None:
                continue
            if any(kw.arg == keyword for kw in node.keywords):
                continue
            found.append(f"{path.relative_to(_SRC.parent).as_posix()}:{node.lineno} {name}")
    return found


def test_every_price_is_handed_the_cache_writes() -> None:
    offenders = _offenders()
    assert offenders == [], (
        "A call that prices a model's usage without its cache writes bills them "
        "at the plain input price (ADR-306). Pass the write count explicitly -- "
        "0 where the priced thing has no prompt cache:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_sees_the_doors() -> None:
    """A guard that matched nothing would pass for the wrong reason."""
    seen: set[str] = set()
    for path in _SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and (name := _called_name(node)) in DOORS:
                seen.add(name)
    # ``get_cached_cost`` is only reached through its metrics alias.
    assert seen >= set(DOORS) - {"get_cached_cost"}
