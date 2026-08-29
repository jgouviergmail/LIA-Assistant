"""Editing an existing skill by full regeneration (L6).

The write engine already existed — re-importing one's own skill is an upsert,
tested and documented in ADR-118 — but three locks made it unreachable:

- the assistant could not READ a skill's ``SKILL.md`` (activation strips the
  frontmatter, and the manifest is deliberately absent from ``all_resources``);
- a replacement dropped every file not resent, including the binary gallery
  thumbnail that chat cannot carry;
- the generator's own instructions told it to rename on conflict, steering it
  into creating duplicates.

Confirmation is enforced IN the tool, in two calls, because the HITL machinery
is unavailable where the generator runs: a skill shipping ``scripts/`` executes
inside an isolated ReAct sub-agent whose drafts never reach the main graph.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.skills.import_service import (
    _carry_over_untransportable,
    _declared_resources,
    _validate_package_integrity,
    parse_incoming_skill_name,
)
from src.domains.skills.tools import (
    _describe_replacement,
    _resolve_edit_target,
    replacement_token,
)
from tests.helpers.runtime_context import make_tool_runtime

_USER = uuid4()

_VALID_SKILL_MD = """---
name: ma-skill
description: >
  Does something useful.
category: perso
priority: 50
---

# Ma Skill

## Instructions
1. Do the thing.
"""


@pytest.mark.unit
class TestIncomingNameParsing:
    def test_valid_package_yields_its_name(self):
        name, error = parse_incoming_skill_name({"SKILL.md": _VALID_SKILL_MD})
        assert name == "ma-skill"
        assert error is None

    def test_missing_manifest_is_an_error(self):
        name, error = parse_incoming_skill_name({"scripts/x.py": "print()"})
        assert name == ""
        assert error is not None

    def test_traversal_name_is_rejected_before_any_write(self):
        malicious = _VALID_SKILL_MD.replace("name: ma-skill", "name: ../../system/x")
        name, error = parse_incoming_skill_name({"SKILL.md": malicious})
        assert name == ""
        assert error is not None


@pytest.mark.unit
class TestEditTargetGuards:
    """The three refusals, exactly as arbitrated."""

    async def test_free_name_is_a_creation(self):
        with patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=None):
            existing, refusal = await _resolve_edit_target("brand-new", str(_USER))
        assert existing is None
        assert refusal is None

    async def test_system_skill_is_refused_without_offering_a_fork(self):
        system_skill = {"name": "pomodoro-timer", "scope": "admin", "owner_id": None}
        with patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=system_skill):
            existing, refusal = await _resolve_edit_target("pomodoro-timer", str(_USER))

        assert existing is None
        assert refusal is not None
        assert refusal.error_code == "SYSTEM_SKILL_READ_ONLY"
        assert "fork" not in refusal.message.lower()

    async def test_another_users_skill_does_not_leak_its_existence(self):
        other = {"name": "leur-skill", "scope": "user", "owner_id": str(uuid4())}
        with patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=other):
            existing, refusal = await _resolve_edit_target("leur-skill", str(_USER))

        assert existing is None
        assert refusal is not None
        assert refusal.error_code == "NAME_UNAVAILABLE"
        # Must not reveal that someone else owns it.
        assert "another user" not in refusal.message.lower()
        assert "owner" not in refusal.message.lower()

    async def test_disabled_skill_must_be_reenabled_first(self):
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER)}

        class _Ctx:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                return None

        service = MagicMock()
        service.get_active_skills_for_user = AsyncMock(return_value=set())

        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=mine),
            patch("src.infrastructure.database.session.get_db_context", return_value=_Ctx()),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=service,
            ),
        ):
            existing, refusal = await _resolve_edit_target("ma-skill", str(_USER))

        assert existing is None
        assert refusal is not None
        assert refusal.error_code == "SKILL_DISABLED"

    async def test_own_active_skill_is_an_editable_target(self):
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER)}

        class _Ctx:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                return None

        service = MagicMock()
        service.get_active_skills_for_user = AsyncMock(return_value={"ma-skill"})

        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=mine),
            patch("src.infrastructure.database.session.get_db_context", return_value=_Ctx()),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=service,
            ),
        ):
            existing, refusal = await _resolve_edit_target("ma-skill", str(_USER))

        assert refusal is None
        assert existing is not None
        assert existing["name"] == "ma-skill"


@pytest.mark.unit
class TestReplacementConfirmation:
    """Fail-closed: the model cannot overwrite in a single call."""

    def test_impact_lists_files_that_would_be_lost(self):
        existing = {
            "name": "ma-skill",
            "all_resources": ["references/rules.md", "scripts/render.py", "assets/preview.png"],
        }
        result = _describe_replacement(existing, {"SKILL.md": "new"})

        assert result.success is False
        assert result.error_code == "CONFIRMATION_REQUIRED"
        assert "references/rules.md" in result.message
        assert "scripts/render.py" in result.message

    def test_binary_assets_are_not_reported_as_lost(self):
        """The server carries them over — claiming otherwise would be a lie."""
        existing = {"name": "ma-skill", "all_resources": ["assets/preview.png"]}
        result = _describe_replacement(existing, {"SKILL.md": "new"})

        removed_section = [
            line for line in result.message.splitlines() if line.startswith("REMOVED")
        ]
        assert not removed_section

    def test_added_files_are_announced(self):
        existing = {"name": "ma-skill", "all_resources": []}
        result = _describe_replacement(
            existing, {"SKILL.md": "new", "references/guide.md": "content"}
        )
        assert "references/guide.md" in result.message

    def test_irreversibility_is_stated(self):
        """The confirmation IS the safeguard — no version history exists."""
        existing = {"name": "ma-skill", "all_resources": []}
        result = _describe_replacement(existing, {"SKILL.md": "new"})
        assert "cannot be restored" in result.message


@pytest.mark.unit
class TestPrecheckOrchestration:
    """The single gate every import passes through before touching disk."""

    async def _precheck(self, files, *, existing=None, active=True, token=""):
        from src.domains.skills.tools import _precheck_import

        class _Ctx:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                return None

        service = MagicMock()
        service.get_active_skills_for_user = AsyncMock(
            return_value={"ma-skill"} if active else set()
        )
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=existing),
            patch("src.infrastructure.database.session.get_db_context", return_value=_Ctx()),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=service,
            ),
        ):
            return await _precheck_import(files, str(_USER), replace_token=token)

    async def test_creation_passes_straight_through(self):
        assert await self._precheck({"SKILL.md": _VALID_SKILL_MD}) is None

    async def test_malformed_manifest_is_refused_before_anything_else(self):
        result = await self._precheck({"SKILL.md": "no frontmatter here"})
        assert result is not None
        assert result.error_code == "IMPORT_REJECTED"

    async def test_replacement_without_confirmation_is_refused(self):
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER), "all_resources": []}
        result = await self._precheck({"SKILL.md": _VALID_SKILL_MD}, existing=mine)
        assert result is not None
        assert result.error_code == "CONFIRMATION_REQUIRED"

    async def test_replacement_with_the_right_token_proceeds(self):
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER), "all_resources": []}
        files = {"SKILL.md": _VALID_SKILL_MD}
        token = replacement_token("ma-skill", files)
        assert await self._precheck(files, existing=mine, token=token) is None

    async def test_a_guessed_token_is_refused(self):
        """The flag-style bypass: asserting confirmation without having been refused."""
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER), "all_resources": []}
        result = await self._precheck({"SKILL.md": _VALID_SKILL_MD}, existing=mine, token="true")
        assert result is not None
        assert result.error_code == "CONFIRMATION_REQUIRED"

    async def test_a_token_from_a_different_package_is_refused(self):
        """The user approved one package; another one must not ride on it."""
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER), "all_resources": []}
        approved = {"SKILL.md": _VALID_SKILL_MD}
        tampered = {"SKILL.md": _VALID_SKILL_MD + "\n## Extra\nsomething else\n"}
        result = await self._precheck(
            tampered, existing=mine, token=replacement_token("ma-skill", approved)
        )
        assert result is not None
        assert result.error_code == "CONFIRMATION_REQUIRED"

    async def test_confirmation_cannot_bypass_the_system_guard(self):
        """The token is not a master key."""
        system = {"name": "ma-skill", "scope": "admin", "owner_id": None}
        result = await self._precheck(
            {"SKILL.md": _VALID_SKILL_MD},
            existing=system,
            token=replacement_token("ma-skill", {"SKILL.md": _VALID_SKILL_MD}),
        )
        assert result is not None
        assert result.error_code == "SYSTEM_SKILL_READ_ONLY"

    async def test_confirmation_cannot_bypass_the_disabled_guard(self):
        mine = {"name": "ma-skill", "scope": "user", "owner_id": str(_USER), "all_resources": []}
        result = await self._precheck(
            {"SKILL.md": _VALID_SKILL_MD},
            existing=mine,
            active=False,
            token=replacement_token("ma-skill", {"SKILL.md": _VALID_SKILL_MD}),
        )
        assert result is not None
        assert result.error_code == "SKILL_DISABLED"


@pytest.mark.unit
class TestPackageIntegrity:
    """A regeneration that breaks the package must be refused, not stored."""

    def test_declared_resources_are_parsed(self):
        body = (
            "# Title\n\n## Instructions\n1. go\n\n"
            "## Ressources disponibles\n"
            "- references/rules.md — the rules\n"
            "- scripts/render.py — the renderer\n"
        )
        assert _declared_resources(body) == ["references/rules.md", "scripts/render.py"]

    def test_no_resources_section_declares_nothing(self):
        assert _declared_resources("# Title\n\n## Instructions\n1. go\n") == []

    def test_missing_declared_resource_is_rejected(self, tmp_path: Path):
        skill = {
            "instructions": "## Ressources disponibles\n- references/missing.md — gone\n",
            "outputs": None,
        }
        with pytest.raises(Exception, match="declares resources"):
            _validate_package_integrity(skill, tmp_path)

    def test_present_declared_resource_passes(self, tmp_path: Path):
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "rules.md").write_text("x", encoding="utf-8")
        skill = {
            "instructions": "## Ressources disponibles\n- references/rules.md — the rules\n",
            "outputs": None,
        }
        _validate_package_integrity(skill, tmp_path)  # must not raise

    def test_interactive_output_without_script_is_rejected(self, tmp_path: Path):
        skill = {"instructions": "", "outputs": ["text", "frame"]}
        with pytest.raises(Exception, match="ships no scripts"):
            _validate_package_integrity(skill, tmp_path)

    def test_interactive_output_with_script_passes(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "render.py").write_text("print()", encoding="utf-8")
        skill = {"instructions": "", "outputs": ["text", "frame"]}
        _validate_package_integrity(skill, tmp_path)  # must not raise

    def test_text_only_skill_needs_no_script(self, tmp_path: Path):
        skill = {"instructions": "", "outputs": ["text"]}
        _validate_package_integrity(skill, tmp_path)  # must not raise


@pytest.mark.unit
class TestManifestIsReadable:
    """Understanding a skill before rewriting it requires reading its manifest."""

    async def _read(self, tmp_path: Path, path: str):
        from src.domains.skills.tools import read_skill_resource

        skill_dir = tmp_path / "ma-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(_VALID_SKILL_MD, encoding="utf-8")
        (skill_dir / "translations.json").write_text('{"fr": "Ma Skill"}', encoding="utf-8")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "rules.md").write_text("the rules", encoding="utf-8")

        cached = {
            "name": "ma-skill",
            "scope": "user",
            "owner_id": str(_USER),
            "source_path": str(skill_dir / "SKILL.md"),
            "all_resources": ["references/rules.md"],
        }
        # The identity travels on the typed context since ADR-231.
        runtime = make_tool_runtime(
            user_id=_USER if isinstance(_USER, UUID) else UUID(str(_USER)),
            thread_id="t",
            conversation_id="t",
            store=MagicMock(),
        )

        with patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=cached
        ):
            return await read_skill_resource.coroutine(
                skill_name="ma-skill", path=path, runtime=runtime
            )

    async def test_skill_md_is_served(self, tmp_path: Path):
        """Activation strips the frontmatter — this is the only way to see it."""
        result = await self._read(tmp_path, "SKILL.md")
        assert result.success is True
        assert "name: ma-skill" in result.message
        assert "category: perso" in result.message

    async def test_translations_are_served(self, tmp_path: Path):
        result = await self._read(tmp_path, "translations.json")
        assert result.success is True
        assert "Ma Skill" in result.message

    async def test_ordinary_resources_still_work(self, tmp_path: Path):
        result = await self._read(tmp_path, "references/rules.md")
        assert result.success is True
        assert result.message == "the rules"

    async def test_undeclared_path_is_still_refused(self, tmp_path: Path):
        """Unlocking the manifest must not unlock arbitrary reads."""
        result = await self._read(tmp_path, "references/secret.md")
        assert result.success is False
        assert result.error_code == "NOT_FOUND"


@pytest.mark.unit
class TestBinaryCarryOver:
    """Chat cannot transport a .png — the server must preserve it."""

    def test_thumbnail_is_restored_from_the_previous_version(self, tmp_path: Path):
        backup = tmp_path / "__previous__"
        (backup / "assets").mkdir(parents=True)
        (backup / "assets" / "preview.png").write_bytes(b"\x89PNG-old")
        target = tmp_path / "ma-skill"
        (target).mkdir()
        (target / "SKILL.md").write_text("new", encoding="utf-8")

        _carry_over_untransportable(backup, target)

        assert (target / "assets" / "preview.png").read_bytes() == b"\x89PNG-old"

    def test_text_files_are_never_carried_over(self, tmp_path: Path):
        """Dropping a reference file must remain possible — that is an edit."""
        backup = tmp_path / "__previous__"
        (backup / "references").mkdir(parents=True)
        (backup / "references" / "old.md").write_text("stale", encoding="utf-8")
        target = tmp_path / "ma-skill"
        target.mkdir()

        _carry_over_untransportable(backup, target)

        assert not (target / "references" / "old.md").exists()

    def test_a_provided_file_is_never_overwritten(self, tmp_path: Path):
        backup = tmp_path / "__previous__"
        (backup / "assets").mkdir(parents=True)
        (backup / "assets" / "preview.png").write_bytes(b"old")
        target = tmp_path / "ma-skill"
        (target / "assets").mkdir(parents=True)
        (target / "assets" / "preview.png").write_bytes(b"new")

        _carry_over_untransportable(backup, target)

        assert (target / "assets" / "preview.png").read_bytes() == b"new"

    def test_first_import_without_backup_is_a_noop(self, tmp_path: Path):
        target = tmp_path / "ma-skill"
        target.mkdir()
        _carry_over_untransportable(tmp_path / "__previous__", target)  # must not raise
        assert list(target.iterdir()) == []
