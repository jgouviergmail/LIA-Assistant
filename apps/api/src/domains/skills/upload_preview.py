"""Read-only original upload validation returns complete metadata/files, never body text."""

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.core.config import settings
from src.domains.skills.models import SkillProvenance
from src.domains.skills.ui_projection import parsed_skill_metadata

if TYPE_CHECKING:
    from src.domains.skills.import_service import SkillImportService


class SkillPackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    size: StrictInt = Field(ge=0)


class SkillPackagePreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    descriptions: dict[str, str] | None
    scope: Literal["user"]
    category: str | None
    priority: int
    always_loaded: bool
    has_scripts: bool
    has_plan_template: bool
    enabled_for_user: bool
    dialogue: bool
    outputs: list[str] | None
    files: tuple[SkillPackageFile, ...]


def _files(root: Path) -> tuple[SkillPackageFile, ...]:
    # The original bounded ZIP extractor wrote this private staging tree.
    return tuple(
        SkillPackageFile(path=path.relative_to(root).as_posix(), size=path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


async def preview_upload(
    service: SkillImportService,
    content: bytes,
    filename: str,
    *,
    owner_id: UUID,
    provenance: SkillProvenance,
) -> SkillPackagePreview:
    with tempfile.TemporaryDirectory(prefix="skill_validate_") as staging_root:
        root = Path(staging_root)
        name = await service._stage_upload(content, filename, root, settings)
        directory = root / name
        parsed = await service._validated(
            directory,
            name,
            owner_id=owner_id,
            is_system=False,
            settings=settings,
            provenance=provenance,
        )
        return SkillPackagePreview(
            **parsed_skill_metadata(parsed, "user"),
            files=await asyncio.to_thread(_files, directory),
        )
