"""CA-4: skills endpoints must offload blocking file I/O off the event loop.

The admin/user skill endpoints read whole skill directories (zip creation) and
read/write SKILL.md files directly on the request path. These blocking calls
are offloaded via ``asyncio.to_thread``.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from src.domains.skills import router as skills_router


@pytest.mark.unit
@pytest.mark.asyncio
async def test_download_admin_skill_zips_off_event_loop(tmp_path) -> None:
    # Real skill directory so _create_skill_zip has files to archive.
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\nbody", encoding="utf-8")

    skill = {"name": "demo-skill", "scope": "admin", "source_path": str(skill_dir / "SKILL.md")}

    main_tid = threading.get_ident()
    zip_tid: dict[str, int] = {}
    real_zip = skills_router._create_skill_zip

    def spy_zip(arg):
        zip_tid["tid"] = threading.get_ident()
        return real_zip(arg)

    with (
        patch("src.domains.skills.cache.SkillsCache.get_by_name", return_value=skill),
        patch.object(skills_router, "_create_skill_zip", spy_zip),
    ):
        response = await skills_router.download_admin_skill(
            skill_name="demo-skill", user=MagicMock()
        )

    # Zip creation ran in a worker thread, not the event-loop thread.
    assert zip_tid["tid"] != main_tid
    # Behavior preserved: a non-empty zip payload is returned.
    assert response.media_type == "application/zip"
