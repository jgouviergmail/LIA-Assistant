"""A skill written in the chat is PROPOSED, never installed by the model (ADR-327).

What the person approves is exactly what the card showed: the proposal keeps
the files it was validated on, states what a replacement changes, and names the
exact version of the skill it replaces so a later change is caught at install.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from src.domains.skills.proposals import (
    ProposalChanges,
    SkillProposal,
    describe_changes,
    package_fingerprint,
    read_text_package,
)

pytestmark = pytest.mark.unit


def _proposal(**overrides: object) -> SkillProposal:
    values: dict[str, object] = {
        "id": "a" * 32,
        "owner_id": "11111111-1111-1111-1111-111111111111",
        "name": "ma-skill",
        "description": "Does something useful.",
        "files": {"SKILL.md": "---\nname: ma-skill\n---\n", "references/r.md": "é"},
        "sizes": {"SKILL.md": 23, "references/r.md": 2},
        "created_at": "2026-09-30T10:00:00+00:00",
        "expires_at": "2026-10-01T10:00:00+00:00",
        "replaces": "f" * 64,
        "changes": ProposalChanges(added=("references/r.md",), modified=("SKILL.md",), removed=()),
        "status": "pending",
    }
    values.update(overrides)
    return SkillProposal(**values)  # type: ignore[arg-type]


class TestFingerprint:
    def test_is_independent_of_the_map_order(self) -> None:
        one = package_fingerprint({"a.md": "x", "SKILL.md": "y"})
        two = package_fingerprint({"SKILL.md": "y", "a.md": "x"})

        assert one == two

    def test_a_changed_byte_changes_it(self) -> None:
        assert package_fingerprint({"SKILL.md": "y"}) != package_fingerprint({"SKILL.md": "z"})

    def test_a_moved_content_changes_it(self) -> None:
        """The path is part of what is approved, not only the text."""
        assert package_fingerprint({"a.md": "x"}) != package_fingerprint({"b.md": "x"})

    def test_line_endings_do_not_count(self) -> None:
        """A package written on Windows reads back with CRLF: it is the same package."""
        assert package_fingerprint({"SKILL.md": "a\r\nb"}) == package_fingerprint(
            {"SKILL.md": "a\nb"}
        )


class TestChanges:
    def test_a_replacement_states_what_it_adds_changes_and_removes(self) -> None:
        current = {"SKILL.md": "old", "references/keep.md": "k", "references/gone.md": "g"}
        incoming = {"SKILL.md": "new", "references/keep.md": "k", "scripts/new.py": "p"}

        changes = describe_changes(current, incoming)

        assert changes == ProposalChanges(
            added=("scripts/new.py",), modified=("SKILL.md",), removed=("references/gone.md",)
        )

    def test_an_identical_package_changes_nothing(self) -> None:
        files = {"SKILL.md": "same"}

        assert describe_changes(files, dict(files)) == ProposalChanges((), (), ())


class TestReadingTheInstalledPackage:
    def test_reads_text_files_and_never_a_binary_asset(self, tmp_path: Path) -> None:
        """A binary asset is carried over by the import: it is never « removed »."""
        (tmp_path / "references").mkdir()
        (tmp_path / "assets").mkdir()
        (tmp_path / "SKILL.md").write_text("manifest", encoding="utf-8")
        (tmp_path / "references" / "r.md").write_text("ref", encoding="utf-8")
        (tmp_path / "assets" / "preview.png").write_bytes(b"\x89PNG\r\n")

        package = read_text_package(tmp_path)

        assert package == {"SKILL.md": "manifest", "references/r.md": "ref"}

    def test_a_missing_folder_reads_as_empty(self, tmp_path: Path) -> None:
        assert read_text_package(tmp_path / "nowhere") == {}

    def test_a_link_is_never_followed(self, tmp_path: Path) -> None:
        """A link inside a skill could name a file outside it."""
        outside = tmp_path / "secret.md"
        outside.write_text("not the skill's", encoding="utf-8")
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("manifest", encoding="utf-8")
        try:
            (skill / "leak.md").symlink_to(outside)
        except OSError:
            pytest.skip("this system refuses to create a symbolic link")

        assert read_text_package(skill) == {"SKILL.md": "manifest"}


class TestRecord:
    def test_round_trips_every_field(self) -> None:
        proposal = _proposal()

        restored = SkillProposal.from_json(proposal.to_json())

        assert restored == proposal
        # A field added on one side only is the recurring silent bug (CLAUDE.md).
        assert {f.name for f in fields(SkillProposal)} == {
            "id",
            "owner_id",
            "name",
            "description",
            "files",
            "sizes",
            "created_at",
            "expires_at",
            "replaces",
            "changes",
            "status",
        }

    def test_a_new_skill_round_trips_without_changes(self) -> None:
        proposal = _proposal(replaces=None, changes=None)

        assert SkillProposal.from_json(proposal.to_json()) == proposal

    @pytest.mark.parametrize("raw", ["", "{", "[]", '{"id": 1}', '{"status": "weird"}'])
    def test_an_unreadable_record_is_none(self, raw: str) -> None:
        assert SkillProposal.from_json(raw) is None

    def test_installed_forgets_the_contents_and_keeps_the_sizes(self) -> None:
        installed = _proposal().installed()

        assert installed.status == "installed"
        assert installed.files == {}
        assert installed.sizes == _proposal().sizes


class TestCard:
    def test_lists_the_manifest_first_then_by_path(self) -> None:
        card = _proposal(
            files={"z.md": "z", "SKILL.md": "s", "a.md": "a"},
            sizes={"z.md": 1, "SKILL.md": 1, "a.md": 1},
        ).to_card()

        assert [f["path"] for f in card["files"]] == ["SKILL.md", "a.md", "z.md"]

    def test_carries_what_the_person_decides_on_and_no_content(self) -> None:
        card = _proposal().to_card()

        assert card == {
            "id": "a" * 32,
            "name": "ma-skill",
            "description": "Does something useful.",
            "replaces": True,
            "files": [
                {"path": "SKILL.md", "size": 23},
                {"path": "references/r.md", "size": 2},
            ],
            "changes": {
                "added": ["references/r.md"],
                "modified": ["SKILL.md"],
                "removed": [],
            },
            "expires_at": "2026-10-01T10:00:00+00:00",
        }

    def test_a_new_skill_replaces_nothing(self) -> None:
        card = _proposal(replaces=None, changes=None).to_card()

        assert card["replaces"] is False
        assert card["changes"] is None
