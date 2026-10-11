"""Current browser status never revives an expired handoff or discloses private intent."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_origin_binding import capture_command_origin
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.effects.digest import draft_digest
from src.domains.users.models import User
from tests.unit.domains.agents.application.test_native_draft import content

pytestmark = pytest.mark.unit


async def prepared_status(monkeypatch: pytest.MonkeyPatch):
    module = import_module("src.domains.agents.application.command_status")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = ApplicationOrigin(
        draft.actor_id,
        "a" * 64,
        AsyncMock(
            return_value=ApplicationSessionFacts(
                user_id=draft.actor_id,
                binding_id="a" * 64,
                display_id="display",
                step_up_at=None,
            )
        ),
    )
    row = ApplicationCommand(
        id=draft.command_id,
        actor_id=draft.actor_id,
        operation_id=draft.operation_id,
        content_digest=draft_digest(draft.model_dump(mode="json")),
        content_encrypted=encrypt_data(draft.model_dump_json()),
        expires_at=draft.expires_at,
        phase=ApplicationPhase.PENDING,
        origin_binding_encrypted=await capture_command_origin(draft, origin),
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    monkeypatch.setattr(module, "get_command", AsyncMock(return_value=row))
    monkeypatch.setattr(
        module, "load_actor", AsyncMock(return_value=User(id=draft.actor_id, is_active=True))
    )
    return module, db, row, origin


async def test_status_withholds_intent_binding_and_source_private_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    status = await module.read_command_status(db, row.actor_id, row.id, origin)
    assert status.phase == ApplicationPhase.PENDING and status.outcome is None
    serialized = status.model_dump_json()
    assert "content_digest" not in serialized and "intent" not in serialized
    assert "origin_binding" not in serialized and "a" * 64 not in serialized
    db.commit.assert_not_awaited()


async def test_expired_waiting_status_keeps_commit_truth_without_live_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    row.phase = ApplicationPhase.WAITING
    row.result_encrypted = encrypt_data(
        ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.WAITING,
            committed=True,
            values={"font_size": 17},
            interaction=PendingApplicationInteraction(
                interaction_id=row.id, kind="device", expires_at=row.expires_at
            ),
        ).model_dump_json()
    )
    status = await module.read_command_status(db, row.actor_id, row.id, origin)
    assert status.phase == ApplicationPhase.EXPIRED and status.interaction is None
    assert status.outcome.committed and status.outcome.values == {"font_size": 17}
    assert status.outcome.error_code == "COMPLETION_UNKNOWN"
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("fault", ["missing", "other_owner", "operator_off", "revoked_session"])
async def test_status_refuses_lost_ownership_or_authority(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    if fault == "missing":
        module.get_command.return_value = None
    elif fault == "operator_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif fault == "revoked_session":
        origin.read_current.return_value = None
    actor_id = uuid4() if fault == "other_owner" else row.actor_id
    with pytest.raises((AuthorizationError, ResourceNotFoundError)):
        await module.read_command_status(db, actor_id, row.id, origin)


async def test_authority_is_rechecked_after_the_final_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)

    async def withdraw():
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return ApplicationSessionFacts(
            user_id=row.actor_id, binding_id="a" * 64, display_id="display", step_up_at=None
        )

    origin.read_current.side_effect = withdraw
    with pytest.raises(AuthorizationError):
        await module.read_command_status(db, row.actor_id, row.id, origin)


@pytest.mark.parametrize("fault", ["corrupt", "phase", "foreign_interaction", "extended_deadline"])
async def test_incoherent_receipt_cannot_publish_a_current_status(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    row.phase = ApplicationPhase.WAITING
    receipt = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.WAITING,
        interaction=PendingApplicationInteraction(
            interaction_id=uuid4() if fault == "foreign_interaction" else row.id,
            kind="secure",
            expires_at=row.expires_at + timedelta(seconds=int(fault == "extended_deadline")),
        ),
    )
    row.result_encrypted = (
        "corrupt" if fault == "corrupt" else encrypt_data(receipt.model_dump_json())
    )
    if fault == "phase":
        row.phase = ApplicationPhase.COMMITTED
    with pytest.raises(AuthorizationError):
        await module.read_command_status(db, row.actor_id, row.id, origin)


async def test_claimed_work_is_not_reported_as_expired_while_its_receipt_is_still_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    row.phase = ApplicationPhase.CLAIMED
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    status = await module.read_command_status(db, row.actor_id, row.id, origin)
    assert status.phase == ApplicationPhase.CLAIMED and status.outcome is None


async def test_resuming_retains_partial_truth_without_offering_the_previous_interaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, db, row, origin = await prepared_status(monkeypatch)
    row.phase = ApplicationPhase.RESUMING
    row.result_encrypted = encrypt_data(
        ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.WAITING,
            committed=True,
            values={"font_size": 17},
            interaction=PendingApplicationInteraction(
                interaction_id=row.id, kind="device", expires_at=row.expires_at
            ),
        ).model_dump_json()
    )
    status = await module.read_command_status(db, row.actor_id, row.id, origin)
    assert status.phase == ApplicationPhase.RESUMING
    assert status.outcome is None and status.interaction is None
    assert status.prior_outcome.committed and status.prior_outcome.values == {"font_size": 17}


async def test_admin_downgrade_during_final_session_read_withholds_the_whole_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from src.domains.agents.application.authorization import authorize_actor
    from src.domains.agents.application.operation_spec import OperationRegistry

    module, db, row, origin = await prepared_status(monkeypatch)
    operations = OperationRegistry()
    operations.register(
        replace(module.APPLICATION_OPERATIONS.get(row.operation_id), administrative=True)
    )
    monkeypatch.setattr(module, "APPLICATION_OPERATIONS", operations)
    actor = User(id=row.actor_id, is_active=True, is_superuser=True)

    async def fresh_actor(db, actor_id, *, administrative=False):
        return authorize_actor(actor, administrative=administrative, owner_id=actor_id)

    async def downgrade():
        actor.is_superuser = False
        return ApplicationSessionFacts(
            user_id=row.actor_id, binding_id="a" * 64, display_id="display", step_up_at=None
        )

    monkeypatch.setattr(module, "load_actor", fresh_actor)
    origin.read_current.side_effect = downgrade
    with pytest.raises(AuthorizationError):
        await module.read_command_status(db, row.actor_id, row.id, origin)
