"""Security + correctness tests for :mod:`src.domains.skills.import_service`.

These pin the four hardening guarantees of the shared import pipeline
(audited 2026-07-09):

- **S1** path traversal via the frontmatter ``name`` is rejected before any write
- **S2** user imports that shadow a system skill or collide with another user
  are rejected; a user re-importing their own skill upserts
- **S3** zip expansion (bomb, member count, zip-slip) is bounded; only the
  SKILL.md subtree is extracted
- **S4** content lacking a description is rejected

The filesystem-only stages use ``tmp_path``; the full paths mock ``SkillsCache``
and the DB layer so no Postgres is required.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException, ValidationError
from src.domains.skills.import_service import (
    SkillImportService,
    validate_skill_name,
)

pytestmark = pytest.mark.unit

_OWNER = uuid4()


def _skill_md(name: str, description: str = "Does a useful thing for tests.") -> str:
    return f"---\nname: {name}\ndescription: >\n  {description}\ncategory: test\npriority: 50\n---\n\n# {name}\n\n## Instructions\nDo the thing.\n"


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, data in members.items():
            zf.writestr(arc, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# validate_skill_name — S1 traversal guard (pure)
# ---------------------------------------------------------------------------


class TestValidateSkillName:
    @pytest.mark.parametrize("name", ["weather", "bulletin-meteo", "qr-code", "a1", "x9y"])
    def test_valid_names_pass(self, name: str) -> None:
        validate_skill_name(name)  # must not raise

    @pytest.mark.parametrize(
        "name",
        [
            "../../system/skill-generator",  # traversal
            "..",
            "foo/bar",  # separator
            "foo\\bar",
            "Foo",  # uppercase
            "foo--bar",  # consecutive hyphens
            "-foo",  # leading hyphen
            "foo-",  # trailing hyphen
            "a",  # too short
            "claude-x",  # reserved prefix
            "anthropic-y",
            "",
        ],
    )
    def test_invalid_names_rejected(self, name: str) -> None:
        with pytest.raises(ValidationError):
            validate_skill_name(name)

    def test_over_length_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_skill_name("a" * 65)


# ---------------------------------------------------------------------------
# _stage_single_md / _stage_zip / _write_text_files — S1 + S3 (filesystem)
# ---------------------------------------------------------------------------


class TestStaging:
    def _svc(self) -> SkillImportService:
        return SkillImportService(db=MagicMock())

    def test_single_md_traversal_name_never_writes(self, tmp_path: Path) -> None:
        svc = self._svc()
        content = _skill_md("../../evil").encode("utf-8")
        with pytest.raises(ValidationError):
            svc._stage_single_md(content, tmp_path)
        # Nothing escaped the staging root.
        assert list(tmp_path.rglob("*.md")) == []

    def test_single_md_valid_writes_under_name(self, tmp_path: Path) -> None:
        svc = self._svc()
        name = svc._stage_single_md(_skill_md("good-skill").encode("utf-8"), tmp_path)
        assert name == "good-skill"
        assert (tmp_path / "good-skill" / "SKILL.md").is_file()

    def test_zip_nested_extracts_only_subtree(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=2048)
        data = _zip_bytes(
            {
                "my-skill/SKILL.md": _skill_md("my-skill").encode("utf-8"),
                "my-skill/scripts/run.py": b"print('hi')\n",
                "my-skill/references/doc.md": b"# ref\n",
            }
        )
        name = svc._stage_zip(data, tmp_path, settings)
        assert name == "my-skill"
        assert (tmp_path / "my-skill" / "scripts" / "run.py").is_file()
        assert (tmp_path / "my-skill" / "references" / "doc.md").is_file()

    def test_zip_flat_uses_frontmatter_name(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=2048)
        data = _zip_bytes({"SKILL.md": _skill_md("flat-skill").encode("utf-8")})
        name = svc._stage_zip(data, tmp_path, settings)
        assert name == "flat-skill"
        assert (tmp_path / "flat-skill" / "SKILL.md").is_file()

    def test_zip_too_many_files_rejected(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=3, skills_zip_max_decompressed_kb=2048)
        members = {"s/SKILL.md": _skill_md("s").encode("utf-8")}
        for i in range(5):
            members[f"s/f{i}.txt"] = b"x"
        with pytest.raises(ValidationError):
            svc._stage_zip(_zip_bytes(members), tmp_path, settings)

    def test_zip_bomb_decompressed_size_rejected(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=1)
        data = _zip_bytes(
            {
                "s/SKILL.md": _skill_md("s").encode("utf-8"),
                "s/big.txt": b"0" * (5 * 1024),  # 5KB decompressed > 1KB budget
            }
        )
        with pytest.raises(ValidationError):
            svc._stage_zip(data, tmp_path, settings)

    def test_zip_traversal_name_rejected(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=2048)
        data = _zip_bytes({"SKILL.md": _skill_md("../../evil").encode("utf-8")})
        with pytest.raises(ValidationError):
            svc._stage_zip(data, tmp_path, settings)

    def test_write_text_files_rejects_binary_extension(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=2048)
        skill_dir = tmp_path / "s"
        skill_dir.mkdir()
        with pytest.raises(ValidationError):
            svc._write_text_files(
                {"SKILL.md": _skill_md("s"), "assets/logo.png": "not-really"},
                skill_dir,
                settings,
            )

    def test_write_text_files_rejects_traversal_path(self, tmp_path: Path) -> None:
        svc = self._svc()
        settings = MagicMock(skills_zip_max_files=64, skills_zip_max_decompressed_kb=2048)
        skill_dir = tmp_path / "s"
        skill_dir.mkdir()
        with pytest.raises(ValidationError):
            svc._write_text_files(
                {"SKILL.md": _skill_md("s"), "../escape.txt": "x"},
                skill_dir,
                settings,
            )


# ---------------------------------------------------------------------------
# _check_user_conflict / _check_quota — S2 (mock cache)
# ---------------------------------------------------------------------------


class TestConflictAndQuota:
    def _svc(self, db_row: object = None, db_user_skills: list | None = None) -> SkillImportService:
        svc = SkillImportService(db=MagicMock())
        svc.skill_repo = MagicMock()
        svc.skill_repo.get_by_name = AsyncMock(return_value=db_row)
        svc.skill_repo.get_user_skills = AsyncMock(return_value=db_user_skills or [])
        return svc

    def _cache(self, skills: list[dict]):
        m = MagicMock()
        m.get_all.return_value = skills
        return m

    @pytest.mark.asyncio
    async def test_shadowing_system_skill_rejected(self) -> None:
        svc = self._svc()
        cache = self._cache([{"name": "briefing", "scope": "admin", "owner_id": None}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("briefing", _OWNER)

    @pytest.mark.asyncio
    async def test_shadowing_system_skill_rejected_by_db_row(self) -> None:
        """The DB registration view alone must be enough to reject (race-safe)."""
        row = MagicMock(is_system=True, owner_id=None)
        svc = self._svc(db_row=row)
        cache = self._cache([])  # cache stale/empty — DB still catches it
        with patch("src.domains.skills.cache.SkillsCache", cache):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("briefing", _OWNER)

    @pytest.mark.asyncio
    async def test_cross_user_collision_rejected(self) -> None:
        svc = self._svc()
        other = str(uuid4())
        cache = self._cache([{"name": "mine", "scope": "user", "owner_id": other}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            with pytest.raises(BaseAPIException):
                await svc._check_user_conflict("mine", _OWNER)

    @pytest.mark.asyncio
    async def test_own_reimport_allowed(self) -> None:
        row = MagicMock(is_system=False, owner_id=_OWNER, plugin_id=None)
        svc = self._svc(db_row=row)
        cache = self._cache([{"name": "mine", "scope": "user", "owner_id": str(_OWNER)}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            await svc._check_user_conflict("mine", _OWNER)  # must not raise

    @pytest.mark.asyncio
    async def test_novel_name_allowed(self) -> None:
        svc = self._svc()
        cache = self._cache([{"name": "other", "scope": "admin", "owner_id": None}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            await svc._check_user_conflict("brand-new", _OWNER)  # must not raise

    @pytest.mark.asyncio
    async def test_admin_import_over_user_skill_rejected(self) -> None:
        svc = self._svc()
        cache = self._cache([{"name": "mine", "scope": "user", "owner_id": str(_OWNER)}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            with pytest.raises(BaseAPIException):
                await svc._check_admin_conflict("mine")

    @pytest.mark.asyncio
    async def test_admin_reimport_of_system_skill_allowed(self) -> None:
        row = MagicMock(is_system=True, owner_id=None)
        svc = self._svc(db_row=row)
        cache = self._cache([{"name": "briefing", "scope": "admin", "owner_id": None}])
        with patch("src.domains.skills.cache.SkillsCache", cache):
            await svc._check_admin_conflict("briefing")  # must not raise

    @pytest.mark.asyncio
    async def test_quota_exceeded_rejected(self) -> None:
        svc = self._svc()
        skills = [{"name": f"s{i}", "scope": "user", "owner_id": str(_OWNER)} for i in range(3)]
        cache = self._cache(skills)
        settings = MagicMock(skills_max_per_user=3)
        with patch("src.domains.skills.cache.SkillsCache", cache):
            with pytest.raises(BaseAPIException):
                await svc._check_quota(_OWNER, "brand-new", settings)

    @pytest.mark.asyncio
    async def test_quota_reimport_at_cap_allowed(self) -> None:
        """Re-importing an existing own skill at the cap must NOT be rejected."""
        svc = self._svc()
        skills = [{"name": f"s{i}", "scope": "user", "owner_id": str(_OWNER)} for i in range(3)]
        cache = self._cache(skills)
        settings = MagicMock(skills_max_per_user=3)
        with patch("src.domains.skills.cache.SkillsCache", cache):
            await svc._check_quota(_OWNER, "s1", settings)  # must not raise

    @pytest.mark.asyncio
    async def test_quota_under_cap_allowed(self) -> None:
        svc = self._svc()
        cache = self._cache([{"name": "s0", "scope": "user", "owner_id": str(_OWNER)}])
        settings = MagicMock(skills_max_per_user=20)
        with patch("src.domains.skills.cache.SkillsCache", cache):
            await svc._check_quota(_OWNER, "brand-new", settings)  # must not raise


# ---------------------------------------------------------------------------
# _swap_in / _roll_back_disk — disk atomicity (B)
# ---------------------------------------------------------------------------


class TestDiskAtomicity:
    def test_swap_in_fresh_import(self, tmp_path: Path) -> None:
        staged = tmp_path / "staging" / "s"
        staged.mkdir(parents=True)
        (staged / "SKILL.md").write_text("new", encoding="utf-8")
        target = tmp_path / "live" / "s"
        backup = tmp_path / "staging" / "__previous__"

        SkillImportService._swap_in(staged, target, backup)
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "new"
        assert not backup.exists()

    def test_swap_in_reimport_parks_previous_version(self, tmp_path: Path) -> None:
        staged = tmp_path / "staging" / "s"
        staged.mkdir(parents=True)
        (staged / "SKILL.md").write_text("v2", encoding="utf-8")
        target = tmp_path / "live" / "s"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("v1", encoding="utf-8")
        backup = tmp_path / "staging" / "__previous__"

        SkillImportService._swap_in(staged, target, backup)
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "v2"
        assert (backup / "SKILL.md").read_text(encoding="utf-8") == "v1"

    def test_roll_back_disk_restores_previous_version(self, tmp_path: Path) -> None:
        target = tmp_path / "live" / "s"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("v2", encoding="utf-8")
        backup = tmp_path / "staging" / "__previous__"
        backup.mkdir(parents=True)
        (backup / "SKILL.md").write_text("v1", encoding="utf-8")

        SkillImportService._roll_back_disk(target, backup)
        assert (target / "SKILL.md").read_text(encoding="utf-8") == "v1"
        assert not backup.exists()

    def test_roll_back_disk_fresh_import_removes_target(self, tmp_path: Path) -> None:
        target = tmp_path / "live" / "s"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("new", encoding="utf-8")
        backup = tmp_path / "staging" / "__previous__"  # does not exist

        SkillImportService._roll_back_disk(target, backup)
        assert not target.exists()


# ---------------------------------------------------------------------------
# import_files — full chat path (S4 + commit), DB + cache mocked
# ---------------------------------------------------------------------------


class TestImportFilesEndToEnd:
    @pytest.mark.asyncio
    async def test_missing_description_rejected(self, tmp_path: Path) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        svc = SkillImportService(db=db)
        no_desc = "---\nname: nodesc\n---\n\n# NoDesc\nbody\n"
        settings = MagicMock(
            skills_users_path=str(tmp_path),
            skills_max_per_user=20,
            skills_zip_max_files=64,
            skills_zip_max_decompressed_kb=2048,
        )
        cache = MagicMock()
        cache.get_all.return_value = []
        cache.invalidate_and_reload = AsyncMock()
        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.cache.SkillsCache", cache),
        ):
            with pytest.raises(ValidationError):
                await svc.import_files({"SKILL.md": no_desc}, owner_id=_OWNER)

    @staticmethod
    def _mock_repo(svc: SkillImportService) -> None:
        svc.skill_repo = MagicMock()
        svc.skill_repo.get_by_name = AsyncMock(return_value=None)
        svc.skill_repo.get_user_skills = AsyncMock(return_value=[])

    @pytest.mark.asyncio
    async def test_happy_path_commits_and_registers(self, tmp_path: Path) -> None:
        db = MagicMock()
        db.commit = AsyncMock()
        svc = SkillImportService(db=db)
        self._mock_repo(svc)
        settings = MagicMock(
            skills_users_path=str(tmp_path),
            skills_max_per_user=20,
            skills_zip_max_files=64,
            skills_zip_max_decompressed_kb=2048,
        )
        cache = MagicMock()
        cache.get_all.return_value = []
        cache.invalidate_and_reload = AsyncMock()

        pref = MagicMock()
        pref.create_skill_for_import = AsyncMock()

        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.cache.SkillsCache", cache),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=pref,
            ),
        ):
            result = await svc.import_files(
                {
                    "SKILL.md": _skill_md("chat-skill"),
                    "references/notes.md": "# notes\n",
                },
                owner_id=_OWNER,
            )

        assert result["name"] == "chat-skill"
        # Skill committed to the live tree under the owner's dir.
        committed = tmp_path / str(_OWNER) / "chat-skill" / "SKILL.md"
        assert committed.is_file()
        assert (tmp_path / str(_OWNER) / "chat-skill" / "references" / "notes.md").is_file()
        pref.create_skill_for_import.assert_awaited_once()
        db.commit.assert_awaited_once()
        cache.invalidate_and_reload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lost_race_rolls_back_disk_and_answers_409(self, tmp_path: Path) -> None:
        """A concurrent import winning the name between check and flush must
        leave the disk clean and surface the same 409 as the up-front check."""
        db = MagicMock()
        db.commit = AsyncMock()
        svc = SkillImportService(db=db)
        self._mock_repo(svc)
        settings = MagicMock(
            skills_users_path=str(tmp_path),
            skills_max_per_user=20,
            skills_zip_max_files=64,
            skills_zip_max_decompressed_kb=2048,
        )
        cache = MagicMock()
        cache.get_all.return_value = []
        cache.invalidate_and_reload = AsyncMock()

        pref = MagicMock()
        pref.create_skill_for_import = AsyncMock(
            side_effect=ValueError("already registered with a different owner")
        )

        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.cache.SkillsCache", cache),
            patch(
                "src.domains.skills.preference_service.SkillPreferenceService",
                return_value=pref,
            ),
        ):
            with pytest.raises(BaseAPIException) as exc_info:
                await svc.import_files({"SKILL.md": _skill_md("raced-skill")}, owner_id=_OWNER)

        assert exc_info.value.status_code == 409
        # Disk rolled back: nothing left in the live tree.
        assert not (tmp_path / str(_OWNER) / "raced-skill").exists()
        # No commit, no cache reload on the failure path.
        db.commit.assert_not_awaited()
        cache.invalidate_and_reload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_import_files_requires_skill_md(self, tmp_path: Path) -> None:
        svc = SkillImportService(db=MagicMock())
        settings = MagicMock(
            skills_users_path=str(tmp_path),
            skills_zip_max_files=64,
            skills_zip_max_decompressed_kb=2048,
        )
        with patch("src.core.config.get_settings", return_value=settings):
            with pytest.raises(ValidationError):
                await svc.import_files({"references/x.md": "# x"}, owner_id=_OWNER)
