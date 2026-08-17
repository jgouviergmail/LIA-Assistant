"""Unit tests for the plugin-facing extensions of the skills import pipeline.

ADR-225 adds two things to :class:`SkillImportService` without touching the
behavior of the existing upload/chat/url paths:

- ``import_directory``: import one already-staged skill directory (a plugin's
  ``skills/<name>/`` child) through the exact same S1-S4 + ``_finalize``
  pipeline, carrying the plugin provenance into the DB row atomically;
- the provenance collision invariant: a name collision is allowed only
  within the same provenance — a plugin import never silently captures a
  manual skill, a manual import never silently captures a plugin's skill
  (arbitrage F), and plugin P updating its own skill stays an upsert.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException, ValidationError
from src.domains.skills.import_service import SkillImportService

pytestmark = pytest.mark.unit

_OWNER = uuid4()
_PLUGIN = uuid4()


def _skill_md(name: str) -> str:
    return f"---\nname: {name}\ndescription: Does something useful.\n---\n\n# {name}\nBody.\n"


def _empty_cache() -> MagicMock:
    cache = MagicMock()
    cache.get_all.return_value = []
    cache.invalidate_and_reload = AsyncMock()
    return cache


class TestProvenanceCollisionInvariant:
    """Name collisions are allowed only within the same provenance."""

    def _svc(self, db_row: object) -> SkillImportService:
        svc = SkillImportService(db=MagicMock())
        svc.skill_repo = MagicMock()
        svc.skill_repo.get_by_name = AsyncMock(return_value=db_row)
        return svc

    @pytest.mark.asyncio
    async def test_plugin_import_over_manual_skill_rejected(self) -> None:
        manual_row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=None)
        svc = self._svc(manual_row)
        with patch("src.domains.skills.cache.SkillsCache", _empty_cache()):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("mine", _OWNER, plugin_id=_PLUGIN)

    @pytest.mark.asyncio
    async def test_manual_import_over_plugin_skill_rejected(self) -> None:
        plugin_row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=_PLUGIN)
        svc = self._svc(plugin_row)
        with patch("src.domains.skills.cache.SkillsCache", _empty_cache()):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("mine", _OWNER, plugin_id=None)

    @pytest.mark.asyncio
    async def test_same_plugin_update_is_allowed(self) -> None:
        plugin_row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=_PLUGIN)
        svc = self._svc(plugin_row)
        with patch("src.domains.skills.cache.SkillsCache", _empty_cache()):
            await svc._check_user_conflict("mine", _OWNER, plugin_id=_PLUGIN)  # no raise

    @pytest.mark.asyncio
    async def test_other_plugin_capture_rejected(self) -> None:
        plugin_row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=_PLUGIN)
        svc = self._svc(plugin_row)
        with patch("src.domains.skills.cache.SkillsCache", _empty_cache()):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("mine", _OWNER, plugin_id=uuid4())

    @pytest.mark.asyncio
    async def test_manual_over_manual_upsert_still_allowed(self) -> None:
        manual_row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=None)
        svc = self._svc(manual_row)
        with patch("src.domains.skills.cache.SkillsCache", _empty_cache()):
            await svc._check_user_conflict("mine", _OWNER, plugin_id=None)  # no raise


class TestImportDirectory:
    def _scaffold(
        self, tmp_path: Path
    ) -> tuple[SkillImportService, MagicMock, MagicMock, MagicMock]:
        db = MagicMock()
        db.commit = AsyncMock()
        svc = SkillImportService(db=db)
        svc.skill_repo = MagicMock()
        svc.skill_repo.get_by_name = AsyncMock(return_value=None)
        svc.skill_repo.get_user_skills = AsyncMock(return_value=[])
        settings = MagicMock(
            skills_users_path=str(tmp_path / "live"),
            skills_max_per_user=20,
            skills_zip_max_files=64,
            skills_zip_max_decompressed_kb=2048,
        )
        pref = MagicMock()
        pref.create_skill_for_import = AsyncMock()
        return svc, db, settings, pref

    @pytest.mark.asyncio
    async def test_happy_path_commits_tree_and_links_provenance(self, tmp_path: Path) -> None:
        svc, db, settings, pref = self._scaffold(tmp_path)
        source = tmp_path / "staged" / "alpha"
        (source / "references").mkdir(parents=True)
        (source / "SKILL.md").write_text(_skill_md("alpha"), encoding="utf-8")
        (source / "references" / "notes.md").write_text("# notes\n", encoding="utf-8")

        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.cache.SkillsCache", _empty_cache()),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=pref,
            ),
        ):
            result = await svc.import_directory(source, owner_id=_OWNER, plugin_id=_PLUGIN)

        assert result["name"] == "alpha"
        live = tmp_path / "live" / str(_OWNER) / "alpha"
        assert (live / "SKILL.md").is_file()
        assert (live / "references" / "notes.md").is_file()
        pref.create_skill_for_import.assert_awaited_once()
        assert pref.create_skill_for_import.await_args.kwargs["plugin_id"] == _PLUGIN
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_directory_without_skill_md_rejected(self, tmp_path: Path) -> None:
        svc, _, settings, _ = self._scaffold(tmp_path)
        source = tmp_path / "staged" / "empty"
        source.mkdir(parents=True)

        with patch("src.core.config.get_settings", return_value=settings):
            with pytest.raises(ValidationError):
                await svc.import_directory(source, owner_id=_OWNER, plugin_id=_PLUGIN)

    @pytest.mark.asyncio
    async def test_invalid_frontmatter_name_rejected(self, tmp_path: Path) -> None:
        svc, _, settings, _ = self._scaffold(tmp_path)
        source = tmp_path / "staged" / "bad"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            "---\nname: ../../evil\ndescription: x\n---\nBody\n", encoding="utf-8"
        )

        with patch("src.core.config.get_settings", return_value=settings):
            with pytest.raises(ValidationError):
                await svc.import_directory(source, owner_id=_OWNER, plugin_id=_PLUGIN)


class TestCreateSkillForImportProvenance:
    """Defense-in-depth in the registration authority itself (race safety)."""

    def _pref(self, existing: object):
        from src.domains.skills.preference_service import SkillPreferenceService

        pref = SkillPreferenceService.__new__(SkillPreferenceService)
        pref.db = MagicMock()
        pref.db.flush = AsyncMock()
        pref.skill_repo = MagicMock()
        pref.skill_repo.get_by_name = AsyncMock(return_value=existing)
        pref.state_repo = MagicMock()
        pref.state_repo.ensure_state = AsyncMock()
        return pref

    @pytest.mark.asyncio
    async def test_provenance_mismatch_raises_value_error(self) -> None:
        existing = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=None)
        pref = self._pref(existing)

        with pytest.raises(ValueError):
            await pref.create_skill_for_import(
                name="mine",
                description="d",
                is_system=False,
                owner_id=_OWNER,
                plugin_id=_PLUGIN,
            )

    @pytest.mark.asyncio
    async def test_new_skill_row_carries_plugin_id(self) -> None:
        pref = self._pref(existing=None)

        skill = await pref.create_skill_for_import(
            name="fresh",
            description="d",
            is_system=False,
            owner_id=_OWNER,
            plugin_id=_PLUGIN,
        )

        assert skill.plugin_id == _PLUGIN
