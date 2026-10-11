"""A source knowledge space is created only by one exact confirmed native command."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.space_create import (
    execute_space_creation,
    prepare_space_creation,
)
from src.domains.agents.application.space_create_schemas import SpaceCreateInput
from src.domains.rag_spaces.models import RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def test_space_preparation_has_no_effect_and_confirmation_creates_actual_source_row(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    actor_id = test_user.id
    request = SpaceCreateInput(
        name="  Literal <script>space</script>  ", description="  My documents  "
    )
    draft = await prepare_space_creation(async_session, actor_id, request)
    assert (
        await async_session.scalar(
            select(func.count(RAGSpace.id)).where(RAGSpace.user_id == actor_id)
        )
        == 0
    )
    assert draft.after["space_create"]["configuration"] == {
        "name": "Literal <script>space</script>",
        "description": "My documents",
    }
    receipt = PreferenceWriteReceipt()
    await execute_space_creation(async_session, actor_id, draft, receipt)
    actual = await async_session.get(RAGSpace, draft.command_id, populate_existing=True)
    assert (
        receipt.committed
        and actual.user_id == actor_id
        and actual.is_active
        and not actual.is_system
    )
    assert actual.name == "Literal <script>space</script>" and actual.description == "My documents"
    assert receipt.values["space_create"]["space_id"] == str(actual.id)


@pytest.mark.parametrize(
    "obstacle",
    ["new_space", "late_capability", "lost_ack", "cancelled_ack", "false_source", "wrong_source"],
)
async def test_space_creation_refuses_stale_or_ambiguous_completion(
    async_session, test_user, monkeypatch, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    actor_id = test_user.id
    draft = await prepare_space_creation(
        async_session, actor_id, SpaceCreateInput(name="Confirmed space")
    )
    await async_session.commit()
    if obstacle == "new_space":
        async_session.add(RAGSpace(user_id=actor_id, name="Created elsewhere"))
        await async_session.commit()
    elif obstacle == "late_capability":
        monkeypatch.setattr(settings, "rag_spaces_enabled", False)
    elif obstacle == "false_source":
        monkeypatch.setattr(
            "src.domains.rag_spaces.space_creation.create_space_row",
            AsyncMock(
                return_value=RAGSpace(id=draft.command_id, user_id=actor_id, name="Confirmed space")
            ),
        )
    elif obstacle == "wrong_source":
        from src.domains.rag_spaces import space_creation

        source_create = space_creation.create_space_row

        async def wrong_source(*args, **kwargs):
            actual = await source_create(*args, **kwargs)
            actual.description = "Unapproved source description"
            await async_session.flush()
            return actual

        monkeypatch.setattr(space_creation, "create_space_row", wrong_source)
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
        (
            AuthorizationError,
            ResourceConflictError,
            ResourceNotFoundError,
            CommandRejected,
            ValueError,
        )
    ) as refusal:
        await execute_space_creation(async_session, actor_id, draft, receipt)
    assert not receipt.committed
    if obstacle in {"lost_ack", "cancelled_ack"}:
        assert (
            isinstance(refusal.value, CommandRejected)
            and refusal.value.code == "COMPLETION_UNKNOWN"
        )
    await async_session.rollback()
    actual = await async_session.get(RAGSpace, draft.command_id)
    assert (actual is not None) == (obstacle in {"lost_ack", "cancelled_ack"})
