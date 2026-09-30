"""A manifest the library stages to read it is not an installed skill folder (ADR-327).

The loader warns when a skill's name differs from its folder — the
agentskills.io convention for INSTALLED skills. The library parses the
manifest from a temporary folder whose name is random, so every preview
and every install logged `skill_name_dir_mismatch` (three on dev,
2026-09-30) about a convention that cannot apply there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from structlog.testing import capture_logs

from src.domains.skill_library.resolver import _parse_manifest
from src.domains.skills.loader import parse_skill_file
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.unit


def test_the_library_reads_a_manifest_without_the_folder_convention() -> None:
    with capture_logs() as logs:
        parsed = _parse_manifest(manifest("web-artifacts-builder"))
    assert parsed is not None and parsed["name"] == "web-artifacts-builder"
    assert not [log for log in logs if log.get("event") == "skill_name_dir_mismatch"]


def test_an_installed_folder_keeps_the_convention(tmp_path: Path) -> None:
    folder = tmp_path / "not-its-name"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(manifest("pdf-tools"))
    with capture_logs() as logs:
        parsed = parse_skill_file(folder / "SKILL.md")
    assert parsed is not None
    assert [log for log in logs if log.get("event") == "skill_name_dir_mismatch"]
