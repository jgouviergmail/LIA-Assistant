"""Obsolete proposals must fail before another model or paid resolver sees them."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


async def test_domain_disabled_pending_channel_proposal_is_refused_before_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings
    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application.channel_schemas import ChannelBindingUpdatePatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.channels.preference_commands import ChannelBindingSnapshot

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "channels_enabled", True)
    actor_id = uuid4()
    binding = ChannelBindingSnapshot(
        id=uuid4(),
        channel_type="telegram",
        channel_user_id="private-id",
        channel_username="@reader",
        is_active=False,
    )
    content = _preference_content(
        actor_id,
        ChannelBindingUpdatePatch(channel_binding=binding),
        {"channel_binding": binding.model_dump(mode="json")},
    )
    db = AsyncMock()
    db.scalar.side_effect = [None, "false"]

    @asynccontextmanager
    async def session():
        yield db

    service = object.__new__(DraftModificationService)
    service.llm = AsyncMock()
    with (
        installed_runtime_context(user_id=actor_id),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        pytest.raises(AuthorizationError),
    ):
        await service.modify(
            content.model_dump(mode="json"),
            "Active ce canal",
            "application_action",
            run_id="draft-channel",
        )
    service.llm.ainvoke.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "fault,expected",
    [("expired", "EXPIRED"), ("schema", "SCHEMA_CHANGED"), ("read", "INVALID_INPUT")],
)
async def test_obsolete_pending_proposal_cannot_be_revised(fault: str, expected: str) -> None:
    actor_id = uuid4()
    operation = "preferences.read" if fault == "read" else "preferences.update"
    spec = APPLICATION_OPERATIONS.get(operation)
    content = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=actor_id,
        operation_id=operation,
        schema_fingerprint=(
            "c" * 64 if fault == "schema" else payload_digest(spec.input_model.model_json_schema())
        ),
        expected_digest=payload_digest({"font_size": 16}),
        intent={"font_size": 17},
        before={"font_size": 16},
        after={"font_size": 17},
        title="Preferences",
        expires_at=datetime.now(UTC) + timedelta(minutes=-1 if fault == "expired" else 15),
    )
    service = object.__new__(DraftModificationService)
    service.llm = AsyncMock()
    with (
        installed_runtime_context(user_id=actor_id),
        patch(
            "src.domains.agents.application.command_service.get_db_context",
            side_effect=AssertionError("An obsolete proposal reached the persistence boundary"),
        ) as session,
        pytest.raises(CommandRejected, match=f"^{expected}$"),
    ):
        await service.modify(
            content.model_dump(mode="json"),
            "Set the font size to 18",
            "application_action",
            run_id="draft-1",
        )
    session.assert_not_called()
    service.llm.ainvoke.assert_not_awaited()
