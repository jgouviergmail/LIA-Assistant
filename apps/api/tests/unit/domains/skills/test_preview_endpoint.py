"""GET /skills/{name}/preview (UXR Lot 10, B12).

Only ``assets/preview.png`` is ever served; the skill-name pattern is the
traversal guard; missing/oversized files and admin-disabled system skills are a plain 404
(no distinction leaked); ownership goes through
``SkillsCache.get_by_name_for_user``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.constants import SKILL_PREVIEW_MAX_BYTES
from src.domains.skills.router import skill_preview

pytestmark = pytest.mark.unit


def _skill_fixture(tmp_path: Path, *, with_preview: bool, size: int = 128) -> dict[str, Any]:
    skill_dir = tmp_path / "demo-skill"
    (skill_dir / "assets").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\nb", encoding="utf-8")
    if with_preview:
        (skill_dir / "assets" / "preview.png").write_bytes(b"\x89PNG" + b"0" * size)
    return {"name": "demo-skill", "source_path": str(skill_dir / "SKILL.md")}


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    return user


def _db_skill(*, is_system: bool = False, admin_enabled: bool = True) -> MagicMock:
    row = MagicMock()
    row.is_system = is_system
    row.admin_enabled = admin_enabled
    return row


def _repo_patch(row: MagicMock | None):
    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=row)
    return patch("src.domains.skills.repository.SkillRepository", return_value=repo)


class TestSkillPreview:
    async def test_serves_preview_png(self, tmp_path: Path) -> None:
        skill = _skill_fixture(tmp_path, with_preview=True)
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill),
            _repo_patch(_db_skill()),
        ):
            response = await skill_preview(skill_name="demo-skill", user=_user(), db=MagicMock())
        assert response.media_type == "image/png"
        assert Path(response.path).name == "preview.png"

    async def test_missing_preview_is_404(self, tmp_path: Path) -> None:
        skill = _skill_fixture(tmp_path, with_preview=False)
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill),
            _repo_patch(_db_skill()),
        ):
            with pytest.raises(HTTPException) as exc:
                await skill_preview(skill_name="demo-skill", user=_user(), db=MagicMock())
        assert exc.value.status_code == 404

    async def test_oversized_preview_is_404(self, tmp_path: Path) -> None:
        skill = _skill_fixture(tmp_path, with_preview=True, size=SKILL_PREVIEW_MAX_BYTES + 1)
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill),
            _repo_patch(_db_skill()),
        ):
            with pytest.raises(HTTPException) as exc:
                await skill_preview(skill_name="demo-skill", user=_user(), db=MagicMock())
        assert exc.value.status_code == 404

    async def test_unknown_skill_is_404(self) -> None:
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=None),
            _repo_patch(None),
        ):
            with pytest.raises(HTTPException) as exc:
                await skill_preview(skill_name="ghost-skill", user=_user(), db=MagicMock())
        assert exc.value.status_code == 404

    async def test_admin_disabled_system_skill_is_404(self, tmp_path: Path) -> None:
        """A system skill hidden by the admin must not leak its assets."""
        skill = _skill_fixture(tmp_path, with_preview=True)
        with (
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill),
            _repo_patch(_db_skill(is_system=True, admin_enabled=False)),
        ):
            with pytest.raises(HTTPException) as exc:
                await skill_preview(skill_name="demo-skill", user=_user(), db=MagicMock())
        assert exc.value.status_code == 404

    @pytest.mark.parametrize("bad_name", ["../etc", "a/b", "UPPER", "sneaky..dots"])
    async def test_invalid_name_refused_before_any_lookup(self, bad_name: str) -> None:
        with pytest.raises(HTTPException) as exc:
            await skill_preview(skill_name=bad_name, user=_user(), db=MagicMock())
        assert exc.value.status_code == 400
