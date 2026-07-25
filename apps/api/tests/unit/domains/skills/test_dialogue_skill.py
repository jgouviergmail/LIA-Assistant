"""Dialogue-skill mechanism (ADR-118) — chat override preservation.

The QueryAnalyzer's chat override clears ``skill_name`` on confidently
conversational turns (anti-contamination for one-shot skills). Skills that
declare ``dialogue: true`` in their frontmatter run a multi-turn process:
the user's answers to the skill's questions ARE conversational, so the
override must preserve their detection or the dialogue breaks across turns.

Pins:
- the loader parses the ``dialogue`` extension field (default False)
- ``_is_dialogue_skill`` resolves the flag from the cache
- the shipped skill-generator actually declares ``dialogue: true``
  (data-level pin: removing the flag re-breaks the guided flow)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.query_analyzer_service import _is_dialogue_skill
from src.domains.skills.loader import parse_skill_file

pytestmark = pytest.mark.unit


def _write_skill(tmp_path: Path, name: str, extra_frontmatter: str = "") -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: Test skill.\n{extra_frontmatter}---\n\n# T\nBody\n",
        encoding="utf-8",
    )
    return path


class TestLoaderDialogueField:
    def test_dialogue_true_parsed(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "dlg-skill", "dialogue: true\n"))
        assert skill is not None
        assert skill["dialogue"] is True

    def test_dialogue_defaults_to_false(self, tmp_path: Path) -> None:
        skill = parse_skill_file(_write_skill(tmp_path, "oneshot-skill"))
        assert skill is not None
        assert skill["dialogue"] is False


class TestIsDialogueSkill:
    def _cache(self, skill: dict | None):
        m = MagicMock()
        m.get_by_name.return_value = skill
        return m

    def test_true_for_dialogue_skill(self) -> None:
        cache = self._cache({"name": "gen", "dialogue": True})
        with patch("src.domains.skills.cache.SkillsCache", cache):
            assert _is_dialogue_skill("gen") is True

    def test_false_for_oneshot_skill(self) -> None:
        cache = self._cache({"name": "qr-code", "dialogue": False})
        with patch("src.domains.skills.cache.SkillsCache", cache):
            assert _is_dialogue_skill("qr-code") is False

    def test_false_for_unknown_skill(self) -> None:
        cache = self._cache(None)
        with patch("src.domains.skills.cache.SkillsCache", cache):
            assert _is_dialogue_skill("ghost") is False

    def test_false_for_none(self) -> None:
        assert _is_dialogue_skill(None) is False


def _find_skill_generator_md() -> Path | None:
    """Locate the shipped skill-generator SKILL.md, or None if not vendored.

    ``data/skills`` is gitignored (ADR-118) and only present in a full checkout,
    so the presence of the file is a genuine environmental condition — hence a
    ``skipif`` rather than an unconditional (allowlisted) skip.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "skills" / "system" / "skill-generator" / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


_SKILL_GENERATOR_MD = _find_skill_generator_md()


class TestSkillGeneratorDeclaresDialogue:
    @pytest.mark.skipif(
        _SKILL_GENERATOR_MD is None,
        reason="skill-generator SKILL.md not vendored in this checkout (data/skills is gitignored)",
    )
    def test_shipped_skill_generator_is_a_dialogue_skill(self) -> None:
        """Data pin: the guided 4-phase flow depends on this flag staying set."""
        skill = parse_skill_file(_SKILL_GENERATOR_MD)
        assert skill is not None
        assert skill["dialogue"] is True, (
            "skill-generator must declare dialogue: true — without it the "
            "chat override clears its detection on follow-up turns and the "
            "guided flow (clarify → answer → generate) breaks"
        )
