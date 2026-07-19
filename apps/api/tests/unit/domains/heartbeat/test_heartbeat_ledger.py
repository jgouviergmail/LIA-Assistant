"""Tests for the heartbeat -> interest unified mention ledger (ADR-135).

When a heartbeat centers on an interest, the mention is recorded as an
`InterestNotification(source="heartbeat")` so BOTH proactive flows see the
subject as served. Eligibility queries exclude these rows (see
tests/unit/infrastructure/proactive/test_eligibility_filters.py).
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.infrastructure.proactive.base import ProactiveTaskResult


def _result(metadata: dict) -> ProactiveTaskResult:
    return ProactiveTaskResult(
        success=True,
        content="notification body",
        target_id="hbtest",
        metadata=metadata,
    )


def _patch_db():
    @asynccontextmanager
    async def _ctx():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    return patch("src.domains.heartbeat.proactive_task.get_db_context", new=_ctx)


def _patch_store():
    """Neutralize the LangGraph Store write (step 2 of on_notification_sent)."""
    store = AsyncMock()
    return patch(
        "src.domains.agents.context.store.get_tool_context_store",
        new=AsyncMock(return_value=store),
    )


@pytest.mark.unit
class TestUnifiedLedger:
    async def test_ledger_written_when_interest_topic_present(self) -> None:
        task = HeartbeatProactiveTask()
        interest = MagicMock()
        interest.id = uuid.uuid4()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.interests.repository.InterestRepository") as interest_repo_cls,
            patch(
                "src.domains.interests.repository.InterestNotificationRepository"
            ) as ledger_repo_cls,
        ):
            hb_repo_cls.return_value.create = AsyncMock()
            interest_repo_cls.return_value.get_by_user_and_topic_ci = AsyncMock(
                return_value=interest
            )
            interest_repo_cls.return_value.mark_notified = AsyncMock()
            ledger_repo_cls.return_value.create = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(),
                MagicMock(),
                _result({"interest_topic": "Cinéma A24", "sources_used": ["USER_INTERESTS"]}),
            )

            interest_repo_cls.return_value.mark_notified.assert_awaited_once()
            kwargs = ledger_repo_cls.return_value.create.await_args.kwargs
            assert kwargs["source"] == "heartbeat"
            assert kwargs["interest_id"] == interest.id

    async def test_ledger_row_carries_content_embedding(self) -> None:
        """Symmetry with the interest flow: heartbeat-served content must be
        embeddable so future fetches dedupe against it (ADR-135)."""
        task = HeartbeatProactiveTask()
        interest = MagicMock()
        interest.id = uuid.uuid4()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.interests.repository.InterestRepository") as interest_repo_cls,
            patch(
                "src.domains.interests.repository.InterestNotificationRepository"
            ) as ledger_repo_cls,
            patch(
                "src.domains.interests.helpers.generate_interest_embedding",
                new=AsyncMock(return_value=[0.5, 0.6]),
            ),
        ):
            hb_repo_cls.return_value.create = AsyncMock()
            interest_repo_cls.return_value.get_by_user_and_topic_ci = AsyncMock(
                return_value=interest
            )
            interest_repo_cls.return_value.mark_notified = AsyncMock()
            ledger_repo_cls.return_value.create = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(), MagicMock(), _result({"interest_topic": "Cinéma A24"})
            )

            kwargs = ledger_repo_cls.return_value.create.await_args.kwargs
            assert kwargs["content_embedding"] == [0.5, 0.6]

    async def test_no_ledger_without_interest_topic(self) -> None:
        task = HeartbeatProactiveTask()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.interests.repository.InterestRepository") as interest_repo_cls,
        ):
            hb_repo_cls.return_value.create = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(), MagicMock(), _result({"sources_used": ["UNREAD_EMAILS"]})
            )

            interest_repo_cls.return_value.get_by_user_and_topic_ci.assert_not_called()

    async def test_unresolved_topic_does_not_write_ledger(self) -> None:
        """A topic that no longer resolves (renamed/deleted) is skipped silently."""
        task = HeartbeatProactiveTask()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.interests.repository.InterestRepository") as interest_repo_cls,
            patch(
                "src.domains.interests.repository.InterestNotificationRepository"
            ) as ledger_repo_cls,
        ):
            hb_repo_cls.return_value.create = AsyncMock()
            interest_repo_cls.return_value.get_by_user_and_topic_ci = AsyncMock(return_value=None)
            ledger_repo_cls.return_value.create = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(), MagicMock(), _result({"interest_topic": "Gone topic"})
            )

            ledger_repo_cls.return_value.create.assert_not_called()
