"""The original upload checks can preview a whole package without installing it."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill
from tests.integration.domains.skill_library.test_library_install import (
    _user,
)
from tests.integration.domains.skill_library.test_library_install import (
    skill_dirs as skill_dirs,
)
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("zipped", [False, True])
async def test_original_upload_validation_is_read_only_and_body_free(
    async_session: AsyncSession, skill_dirs: Path, zipped: bool
) -> None:
    owner = await _user(async_session)
    content = manifest("preview-card") + b"Secret executable instructions"
    filename = "SKILL.md"
    if zipped:
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("preview-card/SKILL.md", content)
            archive.writestr("preview-card/references/r.md", b"Complete private resource")
        content, filename = stream.getvalue(), "package.zip"
    preview = await SkillImportService(async_session).validate_upload(
        content, filename, owner_id=owner
    )
    assert preview.name == "preview-card"
    assert {f.path for f in preview.files} == (
        {"SKILL.md", "references/r.md"} if zipped else {"SKILL.md"}
    )
    serialized = preview.model_dump_json()
    assert "Secret executable instructions" not in serialized and str(skill_dirs) not in serialized
    assert await async_session.scalar(select(Skill.id).where(Skill.owner_id == owner)) is None
    assert not (skill_dirs / "users" / str(owner) / "preview-card").exists()


@pytest.mark.parametrize("bad", ["traversal", "invalid", "missing_resource"])
async def test_preview_refuses_the_same_invalid_packages_as_import(
    async_session: AsyncSession, skill_dirs: Path, bad: str
) -> None:
    from src.core.exceptions import BaseAPIException

    owner = await _user(async_session)
    if bad == "traversal":
        content = manifest("../../escape")
    elif bad == "invalid":
        content = b"not a skill"
    else:
        content = (
            manifest("preview-card") + b"\n## Available resources\n\n- `references/absent.md`\n"
        )
    service = SkillImportService(async_session)
    with pytest.raises(BaseAPIException):
        await service.validate_upload(content, "SKILL.md", owner_id=owner)
    with pytest.raises(BaseAPIException):
        await service.import_upload(content, "SKILL.md", owner_id=owner, is_system=False)
