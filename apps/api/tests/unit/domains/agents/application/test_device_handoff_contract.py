"""Browser operations retain the original exact approval and derive their proof kind."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.application_interaction import PendingApplicationInteraction
from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_service import (
    CommandRejected,
    _current_operation,
    _validate_bound_origin,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_action import (
    EXPORT_REQUEST_OPERATION,
    AccountExportRequest,
)
from src.domains.agents.application.interaction_claim import _waiting_payload
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.secure_handoff import secure_handoff_outcome
from src.domains.agents.effects.digest import draft_digest

pytestmark = pytest.mark.unit


def device_spec(monkeypatch: pytest.MonkeyPatch) -> ApplicationOperationSpec:
    spec = replace(EXPORT_REQUEST_OPERATION, kind=OperationKind.DEVICE)
    monkeypatch.setitem(APPLICATION_OPERATIONS._operations, spec.operation_id, spec)
    return spec


def content() -> ApplicationActionDraftContent:
    return build_action_content(
        uuid4(),
        EXPORT_REQUEST_OPERATION,
        AccountExportRequest(),
        {"account_export": False},
        {"account_export": True},
    )


def test_device_action_stays_pending_without_fabricating_a_secure_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = device_spec(monkeypatch)
    draft = build_action_content(
        uuid4(), spec, AccountExportRequest(), {"account_export": False}, {"account_export": True}
    )
    assert _current_operation(draft) == spec
    outcome = secure_handoff_outcome(draft)
    assert outcome is not None and outcome.interaction is not None
    assert outcome.interaction.kind == "device"
    assert (
        not outcome.success and not outcome.committed and outcome.phase == ApplicationPhase.WAITING
    )


async def test_device_action_requires_original_session_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = device_spec(monkeypatch)
    draft = content()
    command = ApplicationCommand(
        id=draft.command_id,
        actor_id=draft.actor_id,
        operation_id=draft.operation_id,
        origin_binding_encrypted=None,
    )
    with pytest.raises(CommandRejected, match="SESSION_UNAVAILABLE"):
        await _validate_bound_origin(AsyncMock(), command, spec, None)


@pytest.mark.parametrize("wrong_proof", [False, True])
def test_device_waiting_receipt_cannot_replace_the_declared_proof_kind(
    monkeypatch: pytest.MonkeyPatch, wrong_proof: bool
) -> None:
    device_spec(monkeypatch)
    draft = content()
    outcome = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.WAITING,
        interaction=PendingApplicationInteraction(
            interaction_id=draft.command_id,
            kind="secure" if wrong_proof else "device",
            expires_at=draft.expires_at,
        ),
    )
    command = ApplicationCommand(
        id=draft.command_id,
        actor_id=draft.actor_id,
        operation_id=draft.operation_id,
        content_digest=draft_digest(draft.model_dump(mode="json")),
        content_encrypted=encrypt_data(draft.model_dump_json()),
        result_encrypted=encrypt_data(outcome.model_dump_json()),
        expires_at=draft.expires_at,
        draft_id="device-draft",
        claim_token=uuid4(),
    )
    if wrong_proof:
        with pytest.raises(AuthorizationError):
            _waiting_payload(command)
    else:
        parsed, _, spec, interaction = _waiting_payload(command)
        assert (
            parsed == draft and spec.kind == OperationKind.DEVICE and interaction.kind == "device"
        )
