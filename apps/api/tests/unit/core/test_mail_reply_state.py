"""Where an e-mail stands in its conversation: the annotation, and what a model is told of it.

Until 2026-11-11 a message reached every reader alone: the assistant offered to answer
mail the person had answered already. The annotation states the fact read from the
mailbox; its view tells a model the fact, in the account's own zone, and never repeats
as current a « no reply yet » read on an earlier turn.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.mail_reply_state import (
    ReplyMessage,
    ReplyState,
    answered_when,
    read_reply_state,
    reply_state_text,
    reply_state_view,
)

pytestmark = pytest.mark.unit

ZONE = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=ZONE)
REPLIED = datetime(2026, 11, 10, 9, 12, tzinfo=ZONE)


def _message(**over: object) -> ReplyMessage:
    return ReplyMessage.model_validate(
        {
            "message_id": "reply-1",
            "at": REPLIED,
            "correspondents": "Marc Dupont",
            "excerpt": "Noted for Friday.",
            **over,
        }
    )


def _state(status: str, **over: object) -> dict[str, object]:
    return ReplyState.model_validate(
        {
            "status": status,
            "observed_at": NOW,
            "valid_until": NOW + timedelta(minutes=2),
            **over,
        }
    ).model_dump(mode="json")


class TestTheAnnotation:
    @pytest.mark.parametrize("status", ["answer_drafted", "reply_received"])
    def test_a_status_that_names_a_message_carries_it(self, status: str) -> None:
        with pytest.raises(ValidationError):
            _state(status)

    @pytest.mark.parametrize("status", ["unanswered", "awaiting_reply"])
    def test_a_status_that_found_nothing_carries_no_message(self, status: str) -> None:
        with pytest.raises(ValidationError):
            _state(status, message=_message())

    def test_its_validity_is_positive(self) -> None:
        with pytest.raises(ValidationError):
            _state("unanswered", valid_until=NOW)

    def test_it_survives_its_json_form(self) -> None:
        stored = _state("answered", message=_message(), conversation_size=3)

        assert read_reply_state(stored) == ReplyState.model_validate(stored)

    @pytest.mark.parametrize("value", [None, "answered", {"status": "answered"}, 3, []])
    def test_what_is_no_annotation_is_not_read(self, value: object) -> None:
        assert read_reply_state(value) is None
        assert reply_state_view(value, NOW) is None
        assert reply_state_text(value, NOW) == ""


class TestTheView:
    def test_an_answered_message_says_when_to_whom_and_what(self) -> None:
        view = reply_state_view(_state("answered", message=_message()), NOW)

        assert view == {
            "status": "answered",
            "summary": "answered on 2026-11-10T09:12+01:00 to Marc Dupont — Noted for Friday.",
        }

    def test_the_mailbox_mark_alone_says_the_reply_was_not_found(self) -> None:
        view = reply_state_view(_state("answered", marked_at=REPLIED), NOW)

        assert view is not None
        assert view["status"] == "answered"
        assert "2026-11-10T09:12+01:00" in view["summary"]
        assert "not found" in view["summary"]

    def test_a_reply_received_names_who_wrote_it(self) -> None:
        view = reply_state_view(_state("reply_received", message=_message()), NOW)

        assert view is not None
        assert view["summary"] == (
            "reply received on 2026-11-10T09:12+01:00 from Marc Dupont — Noted for Friday."
        )

    def test_an_unsent_answer_is_said_unsent(self) -> None:
        view = reply_state_view(_state("answer_drafted", message=_message()), NOW)

        assert view is not None
        assert view["status"] == "answer_drafted"
        assert "not sent" in view["summary"]

    @pytest.mark.parametrize("status", ["unanswered", "awaiting_reply"])
    def test_nothing_found_is_a_status_and_no_more(self, status: str) -> None:
        assert reply_state_view(_state(status), NOW) == {"status": status}

    def test_the_conversation_size_is_said_when_it_holds_several_messages(self) -> None:
        several = reply_state_view(_state("unanswered", conversation_size=4), NOW)
        alone = reply_state_view(_state("unanswered", conversation_size=1), NOW)

        assert several == {"status": "unanswered", "conversation_messages": "4"}
        assert alone == {"status": "unanswered"}

    @pytest.mark.parametrize("status", ["answered", "reply_received"])
    def test_what_happened_stays_true_once_the_reading_is_old(self, status: str) -> None:
        stored = _state(status, message=_message())

        assert reply_state_view(stored, NOW + timedelta(days=30)) == reply_state_view(stored, NOW)

    @pytest.mark.parametrize(
        ("status", "over"),
        [
            ("unanswered", {}),
            ("awaiting_reply", {}),
            ("answer_drafted", {"message": _message()}),
        ],
    )
    def test_a_reading_of_a_moment_is_not_repeated_past_its_validity(
        self, status: str, over: dict[str, object]
    ) -> None:
        """« No reply yet » read on an earlier turn says nothing of now."""
        view = reply_state_view(_state(status, **over), NOW + timedelta(minutes=3))

        assert view == {"status": "not_checked"}

    def test_the_reading_instants_never_reach_a_model(self) -> None:
        view = reply_state_view(_state("answered", message=_message()), NOW)

        assert view is not None
        assert "observed_at" not in view and "valid_until" not in view
        assert "reply-1" not in str(view)  # an identifier is no fact for a model


class TestTheText:
    def test_it_states_the_fact_on_one_line(self) -> None:
        text = reply_state_text(_state("answered", message=_message()), NOW)

        assert text == (
            "Reply state: answered on 2026-11-10T09:12+01:00 to Marc Dupont — Noted for Friday."
        )

    def test_a_bare_status_is_stated_as_it_is(self) -> None:
        assert reply_state_text(_state("unanswered"), NOW) == "Reply state: unanswered"

    def test_an_old_reading_of_a_moment_says_nothing(self) -> None:
        assert reply_state_text(_state("unanswered"), NOW + timedelta(hours=1)) == ""


class TestWhenItWasAnswered:
    """What a directive states OUTSIDE the data it qualifies: the instant, and nothing a
    correspondent wrote (a name, a first line) — those stay in the record, marked external."""

    def test_it_says_the_instant_alone(self) -> None:
        said = answered_when(_state("answered", message=_message()))

        assert said == "answered on 2026-11-10T09:12+01:00"

    def test_the_mailbox_mark_dates_it_when_it_can(self) -> None:
        assert answered_when(_state("answered", marked_at=REPLIED)) == (
            "answered on 2026-11-10T09:12+01:00"
        )
        assert answered_when(_state("answered")) == "answered"

    def test_it_stays_true_once_the_reading_is_old(self) -> None:
        old = _state(
            "answered",
            message=_message(),
            observed_at=NOW - timedelta(days=3),
            valid_until=NOW - timedelta(days=3) + timedelta(minutes=2),
        )

        assert answered_when(old) == "answered on 2026-11-10T09:12+01:00"

    @pytest.mark.parametrize(
        "status", ["answer_drafted", "unanswered", "reply_received", "awaiting_reply"]
    )
    def test_any_other_status_is_no_answer(self, status: str) -> None:
        settled = {"message": _message()} if status in {"answer_drafted", "reply_received"} else {}

        assert answered_when(_state(status, **settled)) is None

    def test_what_is_no_annotation_is_no_answer(self) -> None:
        assert answered_when({"status": "answered"}) is None
