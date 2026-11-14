"""The one previous version a replaced skill keeps (lot 14): the rule and the disk."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.constants import SKILLS_PREVIOUS_VERSIONS_DIR
from src.domains.skills.models import SkillProvenance
from src.domains.skills.previous_version import (
    keeps_previous,
    previous_slot,
    previous_versions,
    restorable_at,
    settle_slot,
)

pytestmark = pytest.mark.unit

AUTHORED = SkillProvenance.AUTHORED


@pytest.mark.parametrize(
    ("existing", "incoming", "kept"),
    [
        # The person's own words replaced by their own words: an upload or a chat edit.
        ("authored", AUTHORED, True),
        ("authored", None, True),
        # Nothing replaced: a first import keeps nothing.
        (None, AUTHORED, False),
        # A third party's bytes are never restored as the person's own (ADR-327).
        ("url", AUTHORED, False),
        ("url", None, False),
        ("peer", AUTHORED, False),
        # The person's words replaced by a fetched skill: the fetched one rules now.
        ("authored", SkillProvenance.URL, False),
        # A managed skill changes through its channel only.
        ("library", SkillProvenance.LIBRARY, False),
        ("plugin", SkillProvenance.PLUGIN, False),
    ],
)
def test_only_the_persons_own_skill_replaced_by_their_own_keeps_its_previous_version(
    existing: str | None, incoming: SkillProvenance | None, kept: bool
) -> None:
    assert keeps_previous(existing, incoming) is kept


def _package(directory: Path, body: str) -> Path:
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(body, encoding="utf-8")
    return directory


def test_a_kept_version_takes_the_slot_and_replaces_an_older_one(tmp_path: Path) -> None:
    slot = previous_slot(str(tmp_path), uuid4(), "notes")
    _package(slot, "v0")
    backup = _package(tmp_path / "staging" / "__previous__", "v1")
    before = time.time()

    settle_slot(backup, slot, keep=True)

    assert (slot / "SKILL.md").read_text(encoding="utf-8") == "v1"
    assert not backup.exists()
    # The slot's time is WHEN the version was replaced, never its files' age.
    assert os.stat(slot).st_mtime >= before - 1


def test_a_replacement_that_keeps_nothing_leaves_no_stale_previous_version(
    tmp_path: Path,
) -> None:
    slot = previous_slot(str(tmp_path), uuid4(), "notes")
    _package(slot, "v0")
    backup = _package(tmp_path / "staging" / "__previous__", "v1")

    settle_slot(backup, slot, keep=False)

    assert not slot.exists()


def test_a_first_import_has_no_previous_version_to_keep(tmp_path: Path) -> None:
    slot = previous_slot(str(tmp_path), uuid4(), "notes")

    settle_slot(tmp_path / "staging" / "__previous__", slot, keep=True)

    assert not slot.exists()


def test_the_slots_live_beside_the_persons_skills_under_a_reserved_name(tmp_path: Path) -> None:
    owner = uuid4()

    assert previous_slot(str(tmp_path), owner, "notes") == (
        tmp_path / str(owner) / SKILLS_PREVIOUS_VERSIONS_DIR / "notes"
    )


def test_only_the_persons_own_skill_offers_its_previous_version() -> None:
    replaced = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)
    previous = {"notes": replaced}

    def listed(scope: str, provenance: str) -> dict[str, str]:
        return {"name": "notes", "scope": scope, "provenance": provenance}

    assert restorable_at(listed("user", "authored"), previous) == replaced
    assert restorable_at({**listed("user", "authored"), "name": "drafts"}, previous) is None
    # A slot never outlives a replacement by another channel; if one ever did,
    # it would not be offered.
    assert restorable_at(listed("user", "url"), previous) is None
    assert restorable_at(listed("admin", "system"), previous) is None


def test_the_previous_versions_are_read_with_when_they_were_replaced(tmp_path: Path) -> None:
    owner = uuid4()
    slot = _package(previous_slot(str(tmp_path), owner, "notes"), "v1")
    replaced = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)
    os.utime(slot, (replaced.timestamp(), replaced.timestamp()))
    # Not a version: no SKILL.md, or not a directory.
    (slot.parent / "half").mkdir()
    (slot.parent / "stray.txt").write_text("x", encoding="utf-8")

    assert previous_versions(str(tmp_path), owner) == {"notes": replaced}
    assert previous_versions(str(tmp_path), uuid4()) == {}
