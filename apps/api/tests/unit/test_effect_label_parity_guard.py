"""The two sides of one wording must not drift (ADR-263).

An effect label is resolved TWICE, on purpose: by the frontend for the live
card and the action journal (where a client can follow the reader's current
language), and by the backend for the export (where there is no client at
all). Two renderers, one vocabulary — so a key added on one side and forgotten
on the other produces a line that reads correctly in one surface and blank in
the other, which is exactly the kind of half-truth this register exists to
remove.

The guard is a plain set comparison over the two tables. It runs in the backend
suite because that is the side that owns the source of truth (the label
BUILDERS live there); the frontend's own parity across its six locales is
already enforced by the pre-commit hook.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_TABLE = REPO_ROOT / "apps/api/src/core/i18n_effects.py"
LOCALES = REPO_ROOT / "apps/web/locales"

#: Frontend locale directory -> backend canonical language code.
LANGUAGE_PAIRS: dict[str, str] = {
    "en": "en",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "it": "it",
    "zh": "zh-CN",
}


def _backend_labels() -> dict[str, dict[str, str]]:
    """The backend table, read from the source (no import, no settings)."""
    tree = ast.parse(BACKEND_TABLE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "EFFECT_LABELS":
            table: dict[str, dict[str, str]] = ast.literal_eval(node.value)  # type: ignore[arg-type]
            return table
    raise AssertionError("EFFECT_LABELS not found in the backend table")


def _frontend_labels(locale: str) -> dict[str, Any]:
    """The `effects.labels` subtree of one frontend locale."""
    data = json.loads((LOCALES / locale / "translation.json").read_text(encoding="utf-8"))
    return data.get("effects", {}).get("labels", {})


def _flatten(tree: dict[str, Any], prefix: str = "effects.labels") -> set[str]:
    """Dotted keys of a nested i18n subtree."""
    keys: set[str] = set()
    for name, value in tree.items():
        path = f"{prefix}.{name}"
        if isinstance(value, dict):
            keys |= _flatten(value, path)
        else:
            keys.add(path)
    return keys


class TestTheTwoSidesCarryTheSameKeys:
    def test_the_backend_table_is_not_empty(self) -> None:
        """Anti-vacuity: an empty table would make every comparison pass."""
        assert len(_backend_labels()["en"]) >= 40

    @pytest.mark.parametrize("locale", sorted(LANGUAGE_PAIRS))
    def test_every_backend_key_exists_in_the_locale(self, locale: str) -> None:
        backend = set(_backend_labels()[LANGUAGE_PAIRS[locale]])
        frontend = _flatten(_frontend_labels(locale))

        missing = sorted(backend - frontend)
        assert not missing, (
            f"{len(missing)} effect label(s) exist in core/i18n_effects.py but not in "
            f"apps/web/locales/{locale}: {missing}. The card and the journal would "
            "render nothing where the export renders a sentence."
        )

    @pytest.mark.parametrize("locale", sorted(LANGUAGE_PAIRS))
    def test_the_locale_carries_no_orphan_effect_label(self, locale: str) -> None:
        backend = set(_backend_labels()[LANGUAGE_PAIRS[locale]])
        frontend = _flatten(_frontend_labels(locale))

        orphans = sorted(frontend - backend)
        assert not orphans, (
            f"{orphans} exist in apps/web/locales/{locale} but not in the backend "
            "table — a wording nothing can produce."
        )


class TestThePlaceholdersMatch:
    """A key can exist on both sides and still interpolate differently."""

    @pytest.mark.parametrize("locale", sorted(LANGUAGE_PAIRS))
    def test_each_wording_expects_the_same_values(self, locale: str) -> None:
        import re

        backend = _backend_labels()[LANGUAGE_PAIRS[locale]]
        frontend_tree = _frontend_labels(locale)

        def resolve(dotted: str) -> str | None:
            node: Any = frontend_tree
            for part in dotted.removeprefix("effects.labels.").split("."):
                if not isinstance(node, dict) or part not in node:
                    return None
                node = node[part]
            return node if isinstance(node, str) else None

        mismatches: list[str] = []
        for key, wording in backend.items():
            other = resolve(key)
            if other is None:
                continue  # covered by the parity test above
            # Backend uses ``{name}``; the frontend uses i18next's ``{{name}}``.
            expected = set(re.findall(r"\{(\w+)\}", wording))
            actual = set(re.findall(r"\{\{(\w+)\}\}", other))
            if expected != actual:
                mismatches.append(f"{key}: backend {sorted(expected)} vs front {sorted(actual)}")

        assert not mismatches, (
            "the two renderers expect different values — one side would print an "
            f"empty hole: {mismatches}"
        )
