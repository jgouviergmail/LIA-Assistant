"""The notification audit trail on interest feedback.

Measured on the production database on 2026-07-27: 989 notification rows, all
with ``user_feedback`` NULL — forever. The repository method that writes that
column had no caller, so the only readable trace of a verdict lived on the
interest itself. Anyone reading the audit table (a human, a dashboard)
concluded the user never gave feedback; that conclusion was wrong.

These tests pin the repaired path AND the two properties that make it safe:
the write is scoped to the owner, and a verdict is never attributed to a
notification we are not sure about.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.interests.repository import InterestNotificationRepository
from src.domains.interests.router import submit_feedback
from src.domains.interests.schemas import InterestFeedbackRequest

pytestmark = pytest.mark.unit


# =============================================================================
# Repository
# =============================================================================


class TestUpdateFeedbackByRunId:
    async def test_the_write_is_scoped_to_the_owner(self) -> None:
        # A forged run_id from another tenant must update nothing: the WHERE
        # clause carries the user, not only the run.
        db = AsyncMock()
        db.execute.return_value = MagicMock(rowcount=1)
        repo = InterestNotificationRepository(db)

        await repo.update_feedback_by_run_id(
            run_id="interest_abc_123", user_id=uuid.uuid4(), feedback="thumbs_up"
        )

        statement = str(db.execute.await_args.args[0])
        assert "run_id" in statement
        assert "user_id" in statement

    async def test_it_reports_whether_a_row_was_touched(self) -> None:
        db = AsyncMock()
        db.execute.return_value = MagicMock(rowcount=1)

        assert await InterestNotificationRepository(db).update_feedback_by_run_id(
            run_id="r", user_id=uuid.uuid4(), feedback="block"
        )

    async def test_an_unknown_run_reports_nothing_touched(self) -> None:
        db = AsyncMock()
        db.execute.return_value = MagicMock(rowcount=0)

        assert not await InterestNotificationRepository(db).update_feedback_by_run_id(
            run_id="does-not-exist", user_id=uuid.uuid4(), feedback="thumbs_up"
        )


# =============================================================================
# Route
# =============================================================================


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _interest_of(owner_id: uuid.UUID) -> MagicMock:
    interest = MagicMock()
    interest.user_id = owner_id
    interest.status = "active"
    return interest


class TestSubmitFeedbackRoute:
    async def test_a_verdict_with_a_run_id_reaches_the_audit_trail(self) -> None:
        user = _user()
        interest_id = uuid.uuid4()

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository") as notif_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=_interest_of(user.id))
            repo_cls.return_value.apply_feedback = AsyncMock()
            notif_cls.return_value.update_feedback_by_run_id = AsyncMock(return_value=True)
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_feedback(
                interest_id=interest_id,
                data=InterestFeedbackRequest(feedback="thumbs_up", run_id="interest_x_1"),
                user=user,
                db=AsyncMock(),
            )

            notif_cls.return_value.update_feedback_by_run_id.assert_awaited_once_with(
                run_id="interest_x_1", user_id=user.id, feedback="thumbs_up"
            )

    async def test_without_a_run_id_nothing_is_attributed_by_guesswork(self) -> None:
        # Feedback from the settings list has no notification behind it. Writing
        # it onto the "most recent" row would be a fabricated audit entry.
        user = _user()

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository") as notif_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=_interest_of(user.id))
            repo_cls.return_value.apply_feedback = AsyncMock()
            notif_cls.return_value.update_feedback_by_run_id = AsyncMock()
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=0)

            await submit_feedback(
                interest_id=uuid.uuid4(),
                data=InterestFeedbackRequest(feedback="block"),
                user=user,
                db=AsyncMock(),
            )

            notif_cls.return_value.update_feedback_by_run_id.assert_not_awaited()

    async def test_the_interest_itself_is_always_updated(self) -> None:
        # The audit trail is secondary: the verdict must reach the interest even
        # when the card carried no run_id.
        user = _user()
        interest = _interest_of(user.id)

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository"),
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=interest)
            repo_cls.return_value.apply_feedback = AsyncMock()
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=0)

            await submit_feedback(
                interest_id=uuid.uuid4(),
                data=InterestFeedbackRequest(feedback="thumbs_down"),
                user=user,
                db=AsyncMock(),
            )

            repo_cls.return_value.apply_feedback.assert_awaited_once_with(interest, "thumbs_down")

    async def test_the_archived_card_is_marked_so_the_buttons_stay_hidden(self) -> None:
        user = _user()
        interest_id = uuid.uuid4()

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository"),
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=_interest_of(user.id))
            repo_cls.return_value.apply_feedback = AsyncMock()
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=2)

            await submit_feedback(
                interest_id=interest_id,
                data=InterestFeedbackRequest(feedback="thumbs_up"),
                user=user,
                db=AsyncMock(),
            )

            conv_cls.return_value.mark_proactive_feedback_submitted.assert_awaited_once_with(
                user_id=user.id,
                target_id=interest_id,
                feedback_value="thumbs_up",
                # No card behind this verdict (settings list): the historical
                # breadth applies, which is what `None` selects.
                run_id=None,
            )

    async def test_a_verdict_from_a_card_locks_only_that_card(self) -> None:
        """The card's run_id decides the BREADTH of the archived-card write.

        An interest card's `target_id` is the INTEREST, so without the run_id
        one verdict marks every notification that interest ever produced —
        measured at NINE cards for a single interest on 2026-08-03. Those
        cards then show as answered while the audit trail holds one verdict,
        so they read "no feedback" in the history with no way left to answer
        them.
        """
        user = _user()
        interest_id = uuid.uuid4()

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository") as notif_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=_interest_of(user.id))
            repo_cls.return_value.apply_feedback = AsyncMock()
            notif_cls.return_value.update_feedback_by_run_id = AsyncMock(return_value=True)
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_feedback(
                interest_id=interest_id,
                data=InterestFeedbackRequest(feedback="block", run_id="proactive_interest_a_1"),
                user=user,
                db=AsyncMock(),
            )

            conv_cls.return_value.mark_proactive_feedback_submitted.assert_awaited_once_with(
                user_id=user.id,
                target_id=interest_id,
                feedback_value="block",
                run_id="proactive_interest_a_1",
            )


class TestSchema:
    def test_the_run_id_is_optional(self) -> None:
        assert InterestFeedbackRequest(feedback="thumbs_up").run_id is None

    def test_a_blank_run_id_reads_as_absent(self) -> None:
        """An empty string identifies nothing — it must not travel as a value.

        Both consumers branch on the run_id: the audit write already uses
        truthiness, while the archived-card write compares against NULL. Left
        as `""` the two would disagree — the audit skipped, the card write
        narrowed to a run_id no row carries, so the verdict would reach the
        interest and NOTHING else, silently. Normalising once here keeps every
        consumer honest without each remembering to write `or None`.
        """
        assert InterestFeedbackRequest(feedback="thumbs_up", run_id="").run_id is None
        assert InterestFeedbackRequest(feedback="thumbs_up", run_id="   ").run_id is None

    def test_a_real_run_id_keeps_its_exact_value(self) -> None:
        """Normalisation must never rewrite an identifier it did not create."""
        request = InterestFeedbackRequest(feedback="block", run_id="proactive_interest_a_1")

        assert request.run_id == "proactive_interest_a_1"

    def test_an_oversized_run_id_is_rejected(self) -> None:
        # The column is varchar(100); a longer value would fail at the database
        # instead of at the boundary.
        with pytest.raises(ValueError):
            InterestFeedbackRequest(feedback="thumbs_up", run_id="x" * 101)


class TestThumbIsPresence:
    """ADR-214 amendment (owner decision 2026-09-03): a thumb on an interest
    notification is a reading-presence signal for the rhythm detector."""

    async def test_a_thumb_records_feedback_presence(self) -> None:
        user = _user()
        interest_id = uuid.uuid4()
        recorder = AsyncMock(return_value="banked")

        with (
            patch("src.domains.interests.router.InterestRepository") as repo_cls,
            patch("src.domains.interests.router.InterestNotificationRepository") as notif_cls,
            patch("src.domains.conversations.repository.ConversationRepository") as conv_cls,
            patch("src.domains.habits.presence.record_presence", recorder),
        ):
            repo_cls.return_value.get_by_id = AsyncMock(return_value=_interest_of(user.id))
            repo_cls.return_value.apply_feedback = AsyncMock()
            notif_cls.return_value.update_feedback_by_run_id = AsyncMock(return_value=True)
            conv_cls.return_value.mark_proactive_feedback_submitted = AsyncMock(return_value=1)

            await submit_feedback(
                interest_id=interest_id,
                data=InterestFeedbackRequest(feedback="thumbs_down", run_id="interest_x_2"),
                user=user,
                db=AsyncMock(),
            )

        recorder.assert_awaited_once()
        assert recorder.await_args.args[1] is user
        assert recorder.await_args.kwargs["kind"] == "feedback"
