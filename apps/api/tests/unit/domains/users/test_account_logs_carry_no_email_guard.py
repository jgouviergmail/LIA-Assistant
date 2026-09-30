"""The account domain logs an account by its id, never by its e-mail (ADR-317).

The PII filter pseudonymises an ``email`` field into ``email_hash_<sha256[:16]>``:
an unsalted hash anyone holding the address can recompute. Every event of this
domain already carries ``user_id``, so the hash identifies nothing more — it only
ties the lines of an account to its address, including the lines written when that
account is erased. The authentication flows keep theirs: a failed sign-in for an
unknown address has no id to log.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

USERS_DOMAIN = Path(__file__).resolve().parents[4] / "src" / "domains" / "users"

#: Levels the filter treats as "above DEBUG".
_ABOVE_DEBUG = frozenset({"info", "warning", "warn", "error", "exception", "critical"})


def _email_keywords(tree: ast.AST) -> list[tuple[int, str]]:
    """``(line, keyword)`` of every e-mail-named keyword in a log call above DEBUG."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _ABOVE_DEBUG:
            continue
        found.extend(
            (node.lineno, keyword.arg)
            for keyword in node.keywords
            if keyword.arg is not None and "email" in keyword.arg.lower()
        )
    return found


@pytest.mark.unit
def test_no_account_event_logs_an_email() -> None:
    offenders = [
        f"{path.name}:{line} {name}="
        for path in sorted(USERS_DOMAIN.rglob("*.py"))
        for line, name in _email_keywords(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == [], (
        "Log the account by user_id; an e-mail above DEBUG is a recomputable hash "
        f"of the address: {offenders}"
    )


@pytest.mark.unit
def test_the_scan_sees_a_keyword_email() -> None:
    tree = ast.parse("logger.warning('x', user_id=u, email=user.email)")

    assert _email_keywords(tree) == [(1, "email")]


@pytest.mark.unit
def test_the_scan_leaves_debug_alone() -> None:
    tree = ast.parse("logger.debug('x', email=user.email)")

    assert _email_keywords(tree) == []
