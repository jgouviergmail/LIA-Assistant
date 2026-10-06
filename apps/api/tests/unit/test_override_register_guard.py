"""The registers in CI_CD.md name exactly what package.json declares.

``pnpm.overrides`` pins transitive versions for a reason each — an advisory, an
alignment, a rendering split — and an override outlives its reason unless someone
can still read why it exists. ``docs/technical/CI_CD.md`` keeps that register. It
used to restate the versions as well, and drifted from the file it described: eight
overrides had no row and several pins were stale (found 2026-10-02). It now states no
version — ``package.json`` is their only source — so the claim left to hold is the
list of names: an override added without its reason, or a reason kept for an
override that is gone, fails here.

An advisory with no published fix cannot be overridden away: it is accepted by its
GHSA in ``pnpm.auditConfig.ignoreGhsas`` (release v2.4.0, ``braces``). That list
silences a gate, so it answers to the same rule — every accepted advisory has its
row (why it is harmless here, when it goes), and no row survives its acceptance.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()

_REGISTER_HEADING = "**Current overrides**"
_ADVISORY_HEADING = "**Accepted advisories**"
# A register runs from its bold heading to the next rule, section or register.
_SECTION_ENDS = ("\n---", "\n### ", "\n**")
_ROW = re.compile(r"^\|[ \t]+`([^`]+)`[ \t]+\|", re.MULTILINE)
_ADVISORY_ROW = re.compile(r"^\| `(GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})`", re.MULTILINE)


def _pnpm_settings() -> dict[str, Any]:
    manifest = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    settings: dict[str, Any] = manifest["pnpm"]
    return settings


def _register(heading: str) -> str:
    document = (REPO_ROOT / "docs" / "technical" / "CI_CD.md").read_text(encoding="utf-8")
    start = document.index(heading)
    ends = [document.find(mark, start + len(heading)) for mark in _SECTION_ENDS]
    return document[start : min(end for end in ends if end != -1)]


def _declared() -> set[str]:
    return set(_pnpm_settings()["overrides"])


def _registered() -> set[str]:
    return set(_ROW.findall(_register(_REGISTER_HEADING)))


def _accepted() -> set[str]:
    audit_config: dict[str, Any] = _pnpm_settings().get("auditConfig", {})
    return set(audit_config.get("ignoreGhsas", []))


def _accepted_registered() -> set[str]:
    return set(_ADVISORY_ROW.findall(_register(_ADVISORY_HEADING)))


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


def test_every_accepted_advisory_keeps_its_reason() -> None:
    unexplained = _accepted() - _accepted_registered()

    assert not unexplained, (
        "advisory(ies) accepted in pnpm.auditConfig.ignoreGhsas with no row in the "
        "accepted-advisories register of docs/technical/CI_CD.md (say why it is "
        f"harmless here and when it goes): {sorted(unexplained)}"
    )


def test_no_accepted_advisory_outlives_its_acceptance() -> None:
    stale = _accepted_registered() - _accepted()

    assert not stale, (
        "row(s) of the accepted-advisories register for advisory(ies) package.json "
        f"no longer accepts (remove them): {sorted(stale)}"
    )
