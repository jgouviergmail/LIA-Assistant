"""The existing chat-skill tool and pending card respect the same fresh management switch."""

from pathlib import Path

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.conversation_target import ConversationRef
from src.core.exceptions import AuthorizationError
from src.domains.skills import proposal_service
from tests.integration.domains.skills.test_proposal_install_db import (
    _manifest,
    _propose,
)
from tests.integration.domains.skills.test_proposal_install_db import (
    one_session as one_session,
)
from tests.integration.domains.skills.test_proposal_install_db import (
    recorder as recorder,
)
from tests.integration.domains.skills.test_proposal_install_db import (
    redis_client as redis_client,
)
from tests.integration.domains.skills.test_proposal_install_db import (
    skill_dirs as skill_dirs,
)
from tests.integration.domains.skills.test_proposal_install_db import (
    target as target,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("boundary", ["prepare", "click", "before_commit"])
async def test_operator_disables_generation_or_pending_card_before_any_saved_effect(
    one_session: AsyncSession,
    skill_dirs: Path,
    redis_client: Redis,
    recorder,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    target: ConversationRef,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    actor = target.owner_id
    files = {"SKILL.md": _manifest("Controlled instructions.")}
    if boundary == "prepare":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        with pytest.raises(AuthorizationError):
            await _propose(target, files, redis=redis_client)
    else:
        proposal, _ = await _propose(target, files, redis=redis_client)
        if boundary == "click":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        else:
            from src.domains.skills.import_service import SkillImportService

            original = SkillImportService._register_row

            async def register_then_disable(service, *args, **kwargs):
                row = await original(service, *args, **kwargs)
                monkeypatch.setattr(settings, "application_tools_enabled", False)
                return row

            monkeypatch.setattr(SkillImportService, "_register_row", register_then_disable)
        with pytest.raises(AuthorizationError):
            await proposal_service.install(one_session, actor, proposal.id, redis=redis_client)
    assert not (skill_dirs / "users" / str(actor) / "chat-made").exists()
    assert True not in recorder.settled


async def test_proposal_redis_reads_never_hold_the_request_sql_transaction(
    one_session: AsyncSession,
    skill_dirs: Path,
    redis_client: Redis,
    recorder,
    monkeypatch: pytest.MonkeyPatch,
    target: ConversationRef,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    actor = target.owner_id
    proposal, _ = await _propose(
        target,
        {"SKILL.md": _manifest("Controlled instructions.")},
        redis=redis_client,
    )
    original_get = redis_client.get

    async def checked_get(key):
        assert not one_session.in_transaction(), "The proposal's Redis read held a SQL transaction"
        return await original_get(key)

    monkeypatch.setattr(redis_client, "get", checked_get)
    installed = await proposal_service.install(one_session, actor, proposal.id, redis=redis_client)
    assert installed.status == "installed" and recorder.settled == [True]
