"""One exact URL package is confirmed; changed remote/local bytes cannot retarget it."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skill_library.test_library_install import (
    _user,
)
from tests.integration.domains.skill_library.test_library_install import (
    skill_dirs as skill_dirs,
)
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "valid_replace",
        "changed_remote",
        "disabled",
        "changed_local",
        "lost_ack",
        "cache_failed",
    ],
)
async def test_url_import_observes_exact_source_and_whole_owned_replacement(
    async_session: AsyncSession,
    skill_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    from sqlalchemy import select

    from src.domains.agents.application import skill_url_import as native
    from src.domains.agents.application.skill_url_import_schemas import SkillUrlImportInput
    from src.domains.skills.import_service import SkillImportService
    from src.domains.skills.models import Skill

    for setting in ("application_tools_enabled", "skills_enabled", "skills_url_import_enabled"):
        monkeypatch.setattr(settings, setting, True)
    actor = await _user(async_session)
    monkeypatch.setattr(native, "rate_limit_url_import", AsyncMock())
    content = manifest("url-card", "Approved public metadata")
    fetch = AsyncMock(return_value=(content, "SKILL.md"))
    monkeypatch.setattr(native, "fetch_skill_from_url", fetch)
    target = None
    if scenario in {"changed_local", "valid_replace"}:
        await SkillImportService(async_session).import_upload(
            content,
            "SKILL.md",
            owner_id=actor,
            is_system=False,
            provenance=native.SkillProvenance.URL,
        )
        row = await async_session.scalar(select(Skill).where(Skill.owner_id == actor))
        target = row.id
    request = SkillUrlImportInput(url="https://public.example/SKILL.md", replace_skill_id=target)
    draft = await native.prepare_skill_url_import(async_session, actor, request)
    live = skill_dirs / "users" / str(actor) / "url-card" / "SKILL.md"
    assert live.exists() == (target is not None)
    assert "Body." not in draft.model_dump_json() and str(skill_dirs) not in str(draft.after)
    if scenario == "changed_remote":
        fetch.return_value = (content + b"changed instructions", "SKILL.md")
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "skills_url_import_enabled", False)
    elif scenario == "changed_local":
        live.write_bytes(content + b"local change")
    elif scenario == "lost_ack":
        original = async_session.commit

        async def after_first(*args, **kwargs):
            async def lost():
                await original()
                raise OSError("lost ACK")

            monkeypatch.setattr(async_session, "commit", lost)
            return (content, "SKILL.md")

        fetch.side_effect = after_first
    elif scenario == "cache_failed":
        from src.domains.skills.cache import SkillsCache

        monkeypatch.setattr(
            SkillsCache, "invalidate_and_reload", AsyncMock(side_effect=OSError("cache"))
        )
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "valid_replace", "cache_failed"}:
        await native.execute_skill_url_import(async_session, actor, draft, receipt)
        assert receipt.committed and live.read_text(encoding="utf-8") == content.decode("utf-8")
        assert receipt.values["cache_refresh_pending"] == (scenario == "cache_failed")
    else:
        code = {
            "changed_remote": "STALE_STATE",
            "disabled": "CAPABILITY_DISABLED",
            "changed_local": "STALE_STATE",
            "lost_ack": "COMPLETION_UNKNOWN",
        }[scenario]
        with pytest.raises(CommandRejected, match=code):
            await native.execute_skill_url_import(async_session, actor, draft, receipt)
        assert not receipt.committed
        if scenario not in {"changed_local", "lost_ack"}:
            assert not live.exists()
