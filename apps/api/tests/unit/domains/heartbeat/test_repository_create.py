"""What ``HeartbeatNotificationRepository.create`` actually persists.

``test_notification_identity`` pins that the task CALLS create with the
notification's identifier; it mocks the repository, so it cannot tell whether
create honours that argument. This file closes the other half: the row the
repository builds is inspected directly, through a session that captures what
was added rather than a mock of the repository itself.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.heartbeat.repository import HeartbeatNotificationRepository

pytestmark = pytest.mark.unit


def _capturing_session() -> tuple[MagicMock, list[HeartbeatNotification]]:
    """A session that records what it is handed, and flushes to nothing."""
    added: list[HeartbeatNotification] = []
    session = MagicMock()
    session.add = added.append
    session.flush = AsyncMock()
    return session, added


async def _create(
    *,
    notification_id: uuid.UUID | None = None,
    run_id: str = "proactive_heartbeat_abc_deadbeef",
) -> HeartbeatNotification:
    """Build one row through the real repository and return what it added.

    Explicit keywords rather than a `**overrides` dict: the production
    signature is what this file exists to check, so the call has to type-check
    against it instead of being widened to `object`.
    """
    session, added = _capturing_session()
    repo = HeartbeatNotificationRepository(session)
    await repo.create(
        user_id=uuid.uuid4(),
        run_id=run_id,
        content="body",
        content_hash="hash",
        sources_used="[]",
        notification_id=notification_id,
    )
    assert len(added) == 1
    return added[0]


class TestCreate:
    async def test_the_row_is_built_under_the_requested_identifier(self) -> None:
        """The caller owns the primary key — the archived card points at it."""
        wanted = uuid.uuid4()

        notification = await _create(notification_id=wanted)

        assert notification.id == wanted

    async def test_without_an_identifier_the_model_default_still_applies(self) -> None:
        """A degraded caller must not produce a row with a NULL primary key.

        SQLAlchemy's `default=uuid.uuid4` fires for an explicitly-None primary
        key, which is what lets `create` take the argument as optional without
        a conditional. Pinned because the whole optionality rests on it.
        """
        notification = await _create(notification_id=None)

        # The default is applied at flush time; the session here is a stub, so
        # assert the column default itself rather than a flushed value.
        assert notification.id is None
        default = HeartbeatNotification.__table__.c.id.default
        assert default is not None
        assert isinstance(default.arg(None), uuid.UUID)

    async def test_the_tracking_run_is_stored_verbatim(self) -> None:
        """`run_id` joins `message_token_summary`; it must not be rewritten."""
        notification = await _create(run_id="proactive_heartbeat_xyz_01234567")

        assert notification.run_id == "proactive_heartbeat_xyz_01234567"
