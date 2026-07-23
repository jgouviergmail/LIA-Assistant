"""Declarative ``outputs:`` frontmatter field (UXR Lot 10, B12).

The generator has always validated ``outputs`` (``VALID_OUTPUTS`` in
``validate_skill.py``) and 8 system skills declare it — but the loader
silently dropped it. These tests pin the whole chain: loader parsing
(tolerant: invalid ⇒ warn + None, never a crashed scan), API exposure in
both response builders, and three-way parity with the sandboxed generator
script (same pattern as the name-contract parity tests).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.core.constants import SKILL_OUTPUT_CHANNELS
from src.domains.skills.loader import parse_skill_file
from src.domains.skills.router import _skill_to_response

pytestmark = pytest.mark.unit


def _write_skill(tmp_path: Path, frontmatter_extra: str) -> Path:
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(
        f"---\nname: test-skill\ndescription: A test skill.\n{frontmatter_extra}---\nBody.\n",
        encoding="utf-8",
    )
    return path


class TestLoaderOutputsField:
    def test_valid_subset_is_kept(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "outputs: [text, frame]\n"))
        assert skill is not None
        assert skill["outputs"] == ["text", "frame"]

    def test_absent_defaults_to_none(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, ""))
        assert skill is not None
        assert skill["outputs"] is None

    def test_invalid_entry_yields_none(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "outputs: [text, bogus]\n"))
        assert skill is not None
        assert skill["outputs"] is None

    def test_non_list_yields_none(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "outputs: text\n"))
        assert skill is not None
        assert skill["outputs"] is None

    def test_non_string_entry_yields_none(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "outputs: [text, 3]\n"))
        assert skill is not None
        assert skill["outputs"] is None


class TestApiExposure:
    def test_skill_to_response_exposes_outputs(self) -> None:
        skill: dict[str, Any] = {
            "name": "s",
            "description": "d",
            "outputs": ["text", "image"],
        }
        assert _skill_to_response(skill, "user")["outputs"] == ["text", "image"]

    def test_skill_to_response_defaults_to_none(self) -> None:
        assert _skill_to_response({"name": "s", "description": "d"}, "user")["outputs"] is None


def _find_validator_script() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        script = (
            parent
            / "data"
            / "skills"
            / "system"
            / "skill-generator"
            / "scripts"
            / "validate_skill.py"
        )
        if script.is_file():
            return script
    return None


def _load_validator_module() -> ModuleType:
    script = _find_validator_script()
    if script is None:
        pytest.skip("generator validate_skill.py not found in this checkout")
    spec = importlib.util.spec_from_file_location("validate_skill", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGeneratorParity:
    def test_allowed_channels_match_generator(self) -> None:
        """Loader's allowed set and the generator's VALID_OUTPUTS never drift."""
        module = _load_validator_module()
        assert frozenset(SKILL_OUTPUT_CHANNELS) == module.VALID_OUTPUTS
