"""Systemic guard: every user-keyed Redis key built from a literal f-string
belongs to a family declared in ``infrastructure/cache/key_families.py``
(ADR-260).

The boot guard only sees the ``REDIS_KEY_*_PREFIX`` constants; three families
were built from literal f-strings and escaped it (``heartbeat:birthdays``,
``meetings:start``, ``relations:context:v2``, measured 2026-09-03). This scan
reads every ``src/**/*.py`` file for an f-string whose literal head is followed
by a user-id placeholder and requires the head to be a declared family. A
head that starts with a placeholder (``f"{PREFIX}:{user_id}"``) is out of the
regex's reach by construction — that residual is what the reset's
``reset_undeclared_family_total`` counter is for.

Allow-list: empty. Add an entry only with a written reason; never weaken the
regex.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.infrastructure.cache.key_families import family_of

pytestmark = pytest.mark.unit

SRC_DIR = Path(__file__).parents[2] / "src"

# f"<head>:{user_id}" / {uid} / {user.id} / {self.user.id} / {user_id_str} / {str(user_id)}
_USER_KEYED_FSTRING = re.compile(
    r"f[\"']([a-z][a-z0-9_]*(?::[a-z0-9_.]+)*):\{"
    r"(?:user_id|uid|user\.id|self\.user\.id|user_id_str|str\(user_id\)|current_user\.id)\b"
)

ALLOWED_FILES: set[str] = set()


def _iter_heads() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        rel = path.relative_to(SRC_DIR).as_posix()
        if rel in ALLOWED_FILES:
            continue
        for match in _USER_KEYED_FSTRING.finditer(path.read_text(encoding="utf-8")):
            found.append((rel, match.group(1)))
    return found


class TestGuardScan:
    def test_scan_sees_a_known_literal_family(self) -> None:
        heads = {head for _, head in _iter_heads()}
        assert "gmail_history_anchor" in heads, (
            "The scan no longer detects the literal f-string key in "
            "domains/heartbeat/gmail_delta.py — the guard is broken."
        )


class TestEveryLiteralUserKeyHasADeclaredFamily:
    def test_all_heads_are_declared(self) -> None:
        undeclared = sorted(
            {f"{rel}: {head}" for rel, head in _iter_heads() if family_of(head + ":x") is None}
        )
        assert not undeclared, (
            "User-keyed Redis keys whose family is not declared in "
            "infrastructure/cache/key_families.py (a reset would neither purge nor "
            f"protect them knowingly): {undeclared}"
        )
