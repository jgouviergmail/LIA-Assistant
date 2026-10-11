"""Waiting command deadlines and completion claims obey actual PostgreSQL fencing."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.config import settings
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    save_command,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind,committed", [("secure", False), ("device", False), ("device", True)])
async def test_waiting_deadline_is_bound_and_expiry_never_claims_completion(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    committed: bool,
) -> None:
    module = import_module("src.domains.agents.application.command_waiting")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    draft = await prepare_preference_content(
        async_session, test_user.id, PreferencePatch(font_size=17)
    )
    await save_command(async_session, draft, f"draft-{uuid4()}")
    await async_session.commit()
    token = await claim_command(async_session, draft.command_id, test_user.id)
    assert token is not None
    deadline = datetime.now(UTC) + timedelta(minutes=1)
    outcome = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.WAITING,
        committed=committed,
        values={"font_size": 17} if committed else {},
        interaction=PendingApplicationInteraction(
            interaction_id=draft.command_id, kind=kind, expires_at=deadline
        ),
    )
    assert await close_command(async_session, draft.command_id, test_user.id, token, outcome)
    command = await get_command(async_session, draft.command_id, test_user.id)
    assert command is not None and command.expires_at == deadline
    assert command.phase == ApplicationPhase.WAITING
    assert (
        ApplicationExecutionOutcome.model_validate_json(decrypt_data(command.result_encrypted))
        == outcome
    )
    # A callback must explicitly claim the current waiting state, once; generic replay cannot.
    assert await claim_command(async_session, draft.command_id, test_user.id) is None
    assert not await module.expire_waiting_command(
        async_session, command, now=deadline - timedelta(microseconds=1)
    )
    await module.expire_waiting_command(async_session, command, now=deadline + timedelta(seconds=1))
    await async_session.refresh(command)
    assert command.phase == ApplicationPhase.EXPIRED
    expired = ApplicationExecutionOutcome.model_validate_json(
        decrypt_data(command.result_encrypted)
    )
    assert expired.success is False and expired.committed is committed
    assert expired.values == outcome.values
    assert expired.error_code == (
        "INTERACTION_EXPIRED" if kind == "secure" else "COMPLETION_UNKNOWN"
    )
    assert not await module.expire_waiting_command(async_session, command, now=deadline)


@pytest.mark.parametrize("invalid", ["foreign_id", "extended_deadline"])
async def test_waiting_receipt_cannot_change_command_identity_or_extend_approval(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    draft = await prepare_preference_content(
        async_session, test_user.id, PreferencePatch(font_size=17)
    )
    await save_command(async_session, draft, f"draft-{uuid4()}")
    await async_session.commit()
    token = await claim_command(async_session, draft.command_id, test_user.id)
    assert token is not None
    outcome = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.WAITING,
        interaction=PendingApplicationInteraction(
            interaction_id=uuid4() if invalid == "foreign_id" else draft.command_id,
            kind="secure",
            expires_at=(
                draft.expires_at + timedelta(seconds=1)
                if invalid == "extended_deadline"
                else draft.expires_at
            ),
        ),
    )
    assert not await close_command(async_session, draft.command_id, test_user.id, token, outcome)
    command = await get_command(async_session, draft.command_id, test_user.id)
    assert (
        command is not None
        and command.phase == ApplicationPhase.CLAIMED
        and command.result_encrypted is None
    )
