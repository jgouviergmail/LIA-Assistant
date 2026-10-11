"""Exact personal skill removal never deletes files before known approved commit."""

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.skill_delete import (
    execute_skill_deletion,
    prepare_skill_deletion,
)
from src.domains.agents.application.skill_delete_schemas import SkillDeleteInput
from src.domains.skills.cache import SkillsCache
from src.domains.skills.models import Skill
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skills.test_per_account_skill_names import _skill

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "changed",
        "lost_ack",
        "cancelled_ack",
        "expired",
        "revoked",
        "operator_off",
        "cleanup_changed",
        "cache_failed",
    ],
)
async def test_personal_skill_deletion_is_sealed_and_keeps_unknown_outcome_bytes(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    owner = test_user.id
    row = await _skill(async_session, "delete-card", owner)
    identity = row.id
    root = tmp_path / str(owner) / row.name
    root.mkdir(parents=True)
    file = root / "SKILL.md"
    file.write_text("Private approved instructions", encoding="utf-8")
    cached = {"name": row.name, "scope": "user", "owner_id": str(owner), "source_path": str(file)}
    monkeypatch.setattr(SkillsCache, "get_exact", lambda *args: cached)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(SkillsCache, "invalidate_and_reload", AsyncMock())
    await async_session.commit()
    draft = await prepare_skill_deletion(async_session, owner, SkillDeleteInput(skill_id=identity))
    assert "Private approved instructions" not in draft.model_dump_json()
    assert str(tmp_path) not in str(draft.after)
    assert file.exists()
    if scenario == "changed":
        file.write_text("Changed before confirmation", encoding="utf-8")
    elif scenario in {"lost_ack", "cancelled_ack"}:

        async def lose_ack():
            if scenario == "cancelled_ack":
                import asyncio

                raise asyncio.CancelledError()
            raise OSError("lost commit acknowledgement")

        monkeypatch.setattr(async_session, "commit", lose_ack)
    elif scenario == "expired":
        from datetime import UTC, datetime, timedelta

        draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif scenario == "operator_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "cleanup_changed":
        original_commit = async_session.commit

        async def change_after_commit():
            await original_commit()
            if file.exists():
                file.write_text("Newer post-commit bytes", encoding="utf-8")

        monkeypatch.setattr(async_session, "commit", change_after_commit)
    elif scenario == "cache_failed":
        monkeypatch.setattr(
            SkillsCache,
            "invalidate_and_reload",
            AsyncMock(side_effect=OSError("cache unavailable")),
        )
    receipt = PreferenceWriteReceipt()
    if scenario in {"changed", "lost_ack", "cancelled_ack", "expired", "revoked", "operator_off"}:
        from src.core.exceptions import BaseAPIException

        with pytest.raises((CommandRejected, ValueError, BaseAPIException)):
            await execute_skill_deletion(async_session, owner, draft, receipt)
        assert file.exists() and not receipt.committed
    else:
        await execute_skill_deletion(async_session, owner, draft, receipt)
        assert receipt.committed
        assert file.exists() == (scenario == "cleanup_changed")
        assert receipt.values["file_cleanup_pending"] == (scenario == "cleanup_changed")
        assert receipt.values["cache_refresh_pending"] == (scenario == "cache_failed")
        assert await async_session.scalar(select(Skill.id).where(Skill.id == identity)) is None
