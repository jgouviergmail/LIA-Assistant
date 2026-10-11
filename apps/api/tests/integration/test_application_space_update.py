"""One confirmed exact space update uses source rename, description and activation rules."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.space_update import execute_space_update, prepare_space_update
from src.domains.agents.application.space_update_schemas import SpaceUpdateInput
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "change", ["metadata", "activation", "clear", "whitespace_clear", "combined"]
)
async def test_native_space_update_prepares_without_effect_then_applies_exact_source_fields(
    async_session, test_user, monkeypatch, change
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(
        user_id=test_user.id,
        name="Original space",
        description="Original purpose",
        is_active=True,
        kind="meetings",
    )
    async_session.add(space)
    await async_session.commit()
    identity, actor = space.id, test_user.id
    values = (
        {"name": "  New name  ", "description": "  New purpose  "}
        if change == "metadata"
        else (
            {"is_active": False}
            if change == "activation"
            else (
                {"description": "" if change == "clear" else "   "}
                if change in {"clear", "whitespace_clear"}
                else {"name": "Changed and paused", "is_active": False}
            )
        )
    )
    draft = await prepare_space_update(
        async_session, actor, SpaceUpdateInput.model_validate({"space_id": identity, **values})
    )
    assert space.name == "Original space" and space.is_active
    receipt = PreferenceWriteReceipt()
    await execute_space_update(async_session, actor, draft, receipt)
    actual = await async_session.get(RAGSpace, identity, populate_existing=True)
    assert receipt.committed and actual.kind == "meetings" and actual.user_id == actor
    assert actual.name == (
        "New name"
        if change == "metadata"
        else "Changed and paused" if change == "combined" else "Original space"
    )
    assert actual.description == (
        "New purpose"
        if change == "metadata"
        else None if change in {"clear", "whitespace_clear"} else "Original purpose"
    )
    assert actual.is_active == (change not in {"activation", "combined"})


async def test_space_update_refuses_a_changed_owned_snapshot(async_session, test_user, monkeypatch):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(user_id=test_user.id, name="Original")
    async_session.add(space)
    await async_session.commit()
    identity, actor = space.id, test_user.id
    draft = await prepare_space_update(
        async_session, actor, SpaceUpdateInput(space_id=identity, is_active=False)
    )
    await async_session.execute(
        update(RAGSpace).where(RAGSpace.id == identity).values(description="Changed elsewhere")
    )
    await async_session.commit()
    with pytest.raises(ResourceConflictError):
        await execute_space_update(async_session, actor, draft, PreferenceWriteReceipt())
    await async_session.rollback()
    assert (await async_session.get(RAGSpace, identity)).is_active


async def test_personal_space_update_cannot_read_system_identity(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(user_id=None, name="System corpus", is_system=True)
    async_session.add(space)
    await async_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await prepare_space_update(
            async_session, test_user.id, SpaceUpdateInput(space_id=space.id, name="Forbidden")
        )


@pytest.mark.parametrize(
    "obstacle", ["late_capability", "false_source", "wrong_source", "lost_ack", "cancelled_ack"]
)
async def test_update_refuses_unapproved_source_effects_and_ambiguous_completion(
    async_session, test_user, monkeypatch, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    actor = test_user.id
    space = RAGSpace(user_id=actor, name="Approved original", kind="meetings")
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    draft = await prepare_space_update(
        async_session, actor, SpaceUpdateInput(space_id=identity, name="Approved rename")
    )
    await async_session.commit()
    if obstacle == "late_capability":
        monkeypatch.setattr(settings, "rag_spaces_enabled", False)
    elif obstacle == "false_source":
        monkeypatch.setattr(RAGSpaceService, "update_space", AsyncMock(return_value=space))
    elif obstacle == "wrong_source":
        source_update = RAGSpaceService.update_space

        async def wrong_source(service, *args, **kwargs):
            actual = await source_update(service, *args, **kwargs)
            actual.created_at += timedelta(days=1)
            await async_session.flush()
            return actual

        monkeypatch.setattr(RAGSpaceService, "update_space", wrong_source)
    else:
        original = async_session.commit

        async def lost_ack():
            await original()
            if obstacle == "cancelled_ack":
                raise asyncio.CancelledError()
            raise OSError("Controlled lost acknowledgement")

        monkeypatch.setattr(async_session, "commit", lost_ack)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(
        (AuthorizationError, ResourceNotFoundError, CommandRejected, ValueError)
    ) as refusal:
        await execute_space_update(async_session, actor, draft, receipt)
    assert not receipt.committed
    if obstacle in {"lost_ack", "cancelled_ack"}:
        assert (
            isinstance(refusal.value, CommandRejected)
            and refusal.value.code == "COMPLETION_UNKNOWN"
        )
    await async_session.rollback()
    actual = await async_session.get(RAGSpace, identity)
    assert actual.name == (
        "Approved rename" if obstacle in {"lost_ack", "cancelled_ack"} else "Approved original"
    )
    assert actual.kind == "meetings" and not actual.is_system


async def test_foreign_space_id_is_unavailable_without_disclosing_metadata(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    other_id = uuid4()
    async_session.add(
        User(id=other_id, email=f"foreign-space-{other_id}@example.test", is_active=True)
    )
    await async_session.flush()
    space = RAGSpace(user_id=other_id, name="Private other space")
    async_session.add(space)
    await async_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await prepare_space_update(
            async_session, test_user.id, SpaceUpdateInput(space_id=space.id, is_active=False)
        )


async def test_desired_state_already_present_is_a_noop_without_source_write(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = RAGSpace(user_id=test_user.id, name="Original", is_active=False)
    async_session.add(space)
    await async_session.commit()
    identity, actor = space.id, test_user.id
    draft = await prepare_space_update(
        async_session, actor, SpaceUpdateInput(space_id=identity, is_active=False)
    )
    update_source = AsyncMock(side_effect=AssertionError("No source update for identical state"))
    monkeypatch.setattr(RAGSpaceService, "update_space", update_source)
    receipt = PreferenceWriteReceipt()
    await execute_space_update(async_session, actor, draft, receipt)
    assert receipt.committed and receipt.no_op
    update_source.assert_not_awaited()
    assert not (await async_session.get(RAGSpace, identity)).is_active
