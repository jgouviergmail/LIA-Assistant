"""The override register in CI_CD.md names exactly the overrides package.json declares.

``pnpm.overrides`` pins transitive versions for a reason each — an advisory, an
alignment, a rendering split — and an override outlives its reason unless someone
can still read why it exists. ``docs/technical/CI_CD.md`` keeps that register. It
used to restate the versions as well, and drifted from the file it described: eight
overrides had no row and several pins were stale (found 2026-10-02). It now states no
version — ``package.json`` is their only source — so the claim left to hold is the
list of names: an override added without its reason, or a reason kept for an
override that is gone, fails here.
"""

from __future__ import annotations

import json
import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()

_REGISTER_HEADING = "**Current overrides**"
_REGISTER_END = "\n---"
_ROW = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)


def _declared() -> set[str]:
    manifest = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    return set(manifest["pnpm"]["overrides"])


def _registered() -> set[str]:
    document = (REPO_ROOT / "docs" / "technical" / "CI_CD.md").read_text(encoding="utf-8")
    start = document.index(_REGISTER_HEADING)
    end = document.index(_REGISTER_END, start)
    return set(_ROW.findall(document[start:end]))


def test_every_override_keeps_its_reason() -> None:
    unexplained = _declared() - _registered()

    assert not unexplained, (
        "pnpm override(s) with no row in the register of docs/technical/CI_CD.md "
        f"(say why each exists): {sorted(unexplained)}"
    )


def test_no_reason_outlives_its_override() -> None:
    stale = _registered() - _declared()

    assert not stale, (
        "row(s) of the override register for override(s) package.json no longer "
        f"declares (remove them): {sorted(stale)}"
    )
