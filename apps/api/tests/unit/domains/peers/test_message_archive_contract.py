"""Peer-message archive contract — the delivery WRITER vs the CRM READER.

The Relations CRM reads delivered peer messages back from the recipient's
conversation archive. That read is only sound if the metadata the delivery
engine writes is exactly what the reader looks for, and nothing else can
imitate it. Writer and reader sit in different layers
(``infrastructure/scheduler`` vs ``domains/relations``) with no type system
between them — this module is the contract.

What must hold:

- a delivered relayed message archives ``message_metadata["type"] ==
  PROACTIVE_PEER_MESSAGE_TYPE``, obtained through the REAL dispatcher
  composition (``f"proactive_{task_type}"``), never a re-implementation of it;
- the sender's id and display name travel under the contract keys, so the CRM
  can attribute the message without a name match;
- NO other peers dispatch can produce that type: lifecycle events (request,
  accepted, declined, removed) and the sender's own delivery notice must stay
  distinguishable, or an "X accepted your request" notice would surface in the
  CRM as a message received from X.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.peers.constants import (
    PEER_MESSAGE_TASK_TYPE,
    PEER_META_SENDER_ID,
    PEER_META_SENDER_NAME,
    PEER_UNKNOWN_DISPLAY_NAME,
    PROACTIVE_PEER_MESSAGE_TYPE,
)
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.scheduler import peer_message_delivery as delivery

pytestmark = pytest.mark.unit


async def _capture_archived_metadata(*, task_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Run the REAL dispatcher archive path; return what it persisted.

    Only the archive channel is enabled: FCM/SSE/channels are irrelevant to the
    contract and would need infrastructure the unit tier does not have.

    Args:
        task_type: Proactive task type, as the caller passes it.
        metadata: Caller-supplied metadata (merged by the dispatcher).

    Returns:
        The metadata dict handed to ``ConversationService.archive_message``.
    """
    captured: dict[str, Any] = {}

    class _ConversationServiceStub:
        async def get_or_create_conversation(
            self, user_id: Any, db: Any, language: str | None = None
        ) -> SimpleNamespace:
            return SimpleNamespace(id=uuid4())

        async def archive_message(
            self,
            conversation_id: Any,
            role: str,
            content: str,
            metadata: dict[str, Any],
            db: Any,
        ) -> SimpleNamespace:
            captured.update(metadata)
            return SimpleNamespace(id=uuid4())

    with patch("src.domains.conversations.service.ConversationService", _ConversationServiceStub):
        dispatcher = NotificationDispatcher(
            fcm_enabled=False, sse_enabled=False, channel_enabled=False
        )
        await dispatcher.dispatch(
            user=SimpleNamespace(id=uuid4(), language="fr"),
            content="Jérôme vous fait dire qu'il sera en retard.",
            task_type=task_type,
            target_id=str(uuid4()),
            metadata=metadata,
            db=AsyncMock(),
        )
    return captured


class TestDeliveredMessageContract:
    """What the CRM reader is allowed to rely on."""

    async def test_archived_type_is_the_reader_constant(self) -> None:
        archived = await _capture_archived_metadata(task_type=PEER_MESSAGE_TASK_TYPE, metadata={})
        # The dispatcher composes f"proactive_{task_type}" internally — this
        # proves the constant matches that composition, not a copy of it.
        assert archived["type"] == PROACTIVE_PEER_MESSAGE_TYPE

    async def test_sender_identity_travels_under_the_contract_keys(self) -> None:
        sender_id = uuid4()
        archived = await _capture_archived_metadata(
            task_type=PEER_MESSAGE_TASK_TYPE,
            metadata={
                PEER_META_SENDER_ID: str(sender_id),
                PEER_META_SENDER_NAME: "Jérôme Lefèvre",
            },
        )
        assert archived[PEER_META_SENDER_ID] == str(sender_id)
        assert archived[PEER_META_SENDER_NAME] == "Jérôme Lefèvre"


class TestNoOtherPeersDispatchCanImitateIt:
    """Every other peers notification must stay distinguishable."""

    @pytest.mark.parametrize(
        "kind",
        ["request_created", "request_accepted", "request_declined", "connection_removed"],
    )
    def test_lifecycle_event_task_types_differ(self, kind: str) -> None:
        from src.domains.peers.notifications import _body_for

        task_type, _body = _body_for(
            kind,
            SimpleNamespace(id=uuid4(), full_name="Marie Leroy"),
            SimpleNamespace(context_message=None),
            "fr",
        )
        assert f"proactive_{task_type}" != PROACTIVE_PEER_MESSAGE_TYPE

    async def test_sender_delivery_notice_differs(self) -> None:
        dispatch = AsyncMock()
        with patch(
            "src.infrastructure.scheduler.peer_message_delivery.NotificationDispatcher"
        ) as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await delivery._notify_sender(
                SimpleNamespace(id=uuid4(), language="fr", full_name="Moi"),
                "Message remis.",
                SimpleNamespace(id=uuid4()),
                AsyncMock(),
            )
        task_type = dispatch.await_args.kwargs["task_type"]
        assert f"proactive_{task_type}" != PROACTIVE_PEER_MESSAGE_TYPE


class TestUnknownSenderPlaceholder:
    """The '?' fallback is shared, so the CRM can reject it in one place."""

    def test_notifications_display_name_uses_the_constant(self) -> None:
        from src.domains.peers.notifications import _display_name

        assert _display_name(None) == PEER_UNKNOWN_DISPLAY_NAME
        assert _display_name(SimpleNamespace(full_name=None)) == PEER_UNKNOWN_DISPLAY_NAME
        assert _display_name(SimpleNamespace(full_name="Marie")) == "Marie"
