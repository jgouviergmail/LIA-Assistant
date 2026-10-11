"""Stored transport binding identifies a command; live authority is reread on every use."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.digest import draft_digest
from tests.unit.domains.agents.application.test_native_draft import content

pytestmark = pytest.mark.unit


def origin_of(draft: ApplicationActionDraftContent) -> ApplicationOrigin:
    return ApplicationOrigin(
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


def row_of(draft: ApplicationActionDraftContent, encrypted: str) -> ApplicationCommand:
    return ApplicationCommand(
        id=draft.command_id,
        actor_id=draft.actor_id,
        operation_id=draft.operation_id,
        content_digest=draft_digest(draft.model_dump(mode="json")),
        expires_at=draft.expires_at,
        origin_binding_encrypted=encrypted,
    )


async def test_capture_contains_no_cookie_or_stored_permission_and_current_authority_is_reread() -> (
    None
):
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = origin_of(draft)
    encrypted = await module.capture_command_origin(draft, origin)
    assert encrypted is not None and "a" * 64 not in encrypted
    row = row_of(draft, encrypted)
    await module.require_command_origin(row, origin)
    origin.read_current.return_value = None
    with pytest.raises(AuthorizationError):
        await module.require_command_origin(row, origin)


@pytest.mark.parametrize(
    "field", ["actor_id", "id", "operation_id", "content_digest", "expires_at"]
)
async def test_binding_cannot_be_reused_for_another_command_or_extended_approval(
    field: str,
) -> None:
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = origin_of(draft)
    encrypted = await module.capture_command_origin(draft, origin)
    row = row_of(draft, encrypted)
    setattr(
        row,
        field,
        {
            "actor_id": uuid4(),
            "id": uuid4(),
            "operation_id": "different.action",
            "content_digest": "b" * 64,
            "expires_at": draft.expires_at + timedelta(seconds=1),
        }[field],
    )
    with pytest.raises(AuthorizationError):
        await module.require_command_origin(row, origin)


async def test_another_session_and_unbound_or_corrupt_records_are_refused() -> None:
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = origin_of(draft)
    encrypted = await module.capture_command_origin(draft, origin)
    row = row_of(draft, encrypted)
    other = ApplicationOrigin(draft.actor_id, "b" * 64, AsyncMock())
    with pytest.raises(AuthorizationError):
        await module.require_command_origin(row, other)
    other.read_current.assert_not_called()
    for invalid in [None, "corrupt"]:
        row.origin_binding_encrypted = invalid
        with pytest.raises(AuthorizationError):
            await module.require_command_origin(row, origin)


async def test_expired_command_can_be_observed_but_cannot_grant_resume_authority() -> None:
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = origin_of(draft)
    encrypted = await module.capture_command_origin(draft, origin)
    row = row_of(draft, encrypted)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await module.require_command_origin(row, origin, allow_expired=True)
    with pytest.raises(AuthorizationError):
        await module.require_command_origin(row, origin)


async def test_addressed_command_refuses_another_tab_in_the_same_authenticated_session() -> None:
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    original = origin_of(draft)
    origin = ApplicationOrigin(
        original.user_id, original.binding_id, original.read_current, device_id=uuid4()
    )
    encrypted = await module.capture_command_origin(draft, origin, bind_device=True)
    assert encrypted is not None
    row = row_of(draft, encrypted)
    await module.require_command_origin(row, origin)
    for device_id in [uuid4(), None]:
        other = ApplicationOrigin(
            original.user_id, original.binding_id, original.read_current, device_id=device_id
        )
        with pytest.raises(AuthorizationError):
            await module.require_command_origin(row, other)


async def test_addressed_capture_requires_a_device_but_existing_handoffs_remain_session_bound() -> (
    None
):
    module = import_module("src.domains.agents.application.command_origin_binding")
    draft = ApplicationActionDraftContent.model_validate(content())
    origin = origin_of(draft)
    with pytest.raises(AuthorizationError):
        await module.capture_command_origin(draft, origin, bind_device=True)
    encrypted = await module.capture_command_origin(draft, origin)
    assert encrypted is not None
    other = ApplicationOrigin(
        origin.user_id, origin.binding_id, origin.read_current, device_id=uuid4()
    )
    await module.require_command_origin(row_of(draft, encrypted), other)
    with pytest.raises(AuthorizationError):
        await module.require_command_origin(row_of(draft, encrypted), other, require_device=True)
