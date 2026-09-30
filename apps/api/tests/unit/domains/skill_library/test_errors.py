"""Every refusal the skill library's API sends is told in the reader's words (ADR-327).

The API names a refusal with a stable ``detail.code`` and the web translates it
(``lib/skill-library/errors.ts``). A code added here without its sentence would
reach the reader as a generic « could not » in six languages at once, with
every gate green — so each code the router can send is pinned to the sentence
keys the web reads for it, in every locale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.domains.skill_library.errors import (
    AUDIT_BLOCKED,
    QUERY_INVALID,
    RATE_LIMITED,
    RENAMED,
    STATUSES,
    TOO_LARGE,
)

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"
_PREFIX = "settings.skills.library.errors"

#: The codes whose sentence quotes a fact: their variants, as the web reads them.
_VARIANTS: dict[str, tuple[str, ...]] = {
    QUERY_INVALID: ("", "_plain"),
    RATE_LIMITED: ("", "_plain"),
    AUDIT_BLOCKED: ("", "_plain"),
    RENAMED: ("", "_plain"),
    TOO_LARGE: ("", "_files", "_kb"),
}


def _keys(code: str) -> list[str]:
    return [f"{_PREFIX}.{code}{suffix}" for suffix in _VARIANTS.get(code, ("",))]


def _resolve(tree: dict[str, Any], dotted: str) -> object:
    node: object = tree
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


@pytest.mark.parametrize("locale", LOCALES)
def test_every_refusal_has_its_sentence(locale: str) -> None:
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    tree = json.loads(raw)
    missing = [
        key
        for code in sorted(STATUSES)
        for key in _keys(code)
        if not str(_resolve(tree, key) or "").strip()
    ]
    assert not missing, f"{locale}: refusals the API sends and nobody can read: {missing}"


def test_the_web_reads_every_code_the_api_sends() -> None:
    module = (_WEB / "src" / "lib" / "skill-library" / "errors.ts").read_text(encoding="utf-8")
    unread = [code for code in STATUSES if f"'{code}'" not in module]
    assert not unread, f"codes the web does not map: {unread}"
