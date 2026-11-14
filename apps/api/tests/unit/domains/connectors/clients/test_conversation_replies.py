"""What a conversation says of one message's reply state — one decider for three mailboxes.

A received message is ANSWERED when the person sent, later and in the same conversation,
a message addressed to its sender — or when the mailbox itself marks it answered. A
message the person sent got a REPLY when someone else wrote after it. Whatever cannot be
established is not claimed: the answer is then no state at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.core.field_names import (
    FIELD_MAIL_ANSWERED,
    FIELD_MAIL_ANSWERED_AT,
    FIELD_MAIL_IN_REPLY_TO,
)
from src.core.mail_reply_state import ReplyState
from src.domains.connectors.clients.conversation_replies import reply_state_of
from src.domains.connectors.clients.mail_conversation import Conversation

pytestmark = pytest.mark.unit

ZONE = ZoneInfo("Europe/Paris")
OBSERVED = datetime(2026, 11, 10, 12, 0, tzinfo=ZONE)
START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
ME = "Me <me@example.org>"
MARC = "Marc Dupont <marc@example.org>"
PAUL = "Paul <paul@example.org>"
EXCERPT_MAX = 40


def _millis(minute: int) -> str:
    return str(int((START + timedelta(minutes=minute)).timestamp() * 1000))


def _row(message_id: str, minute: int | None, labels: list[str], **over: Any) -> dict[str, Any]:
    return {
        "id": message_id,
        "threadId": "t-1",
        "rfc_message_id": f"<{message_id}@mail>",
        "internalDate": _millis(minute) if minute is not None else None,
        "labelIds": labels,
        "snippet": f"words of {message_id}",
        "to": "",
        "cc": "",
        **over,
    }


def received(message_id: str, minute: int | None, **over: Any) -> dict[str, Any]:
    return _row(message_id, minute, ["INBOX"], **{"from": MARC, "to": ME, **over})


def sent(message_id: str, minute: int | None, **over: Any) -> dict[str, Any]:
    return _row(message_id, minute, ["SENT"], **{"from": ME, "to": MARC, **over})


def draft(message_id: str, minute: int | None, **over: Any) -> dict[str, Any]:
    return _row(message_id, minute, ["DRAFT"], **{"from": ME, "to": MARC, **over})


def decide(
    message: dict[str, Any],
    *said: dict[str, Any],
    drafts: tuple[dict[str, Any], ...] = (),
    truncated: bool = False,
) -> ReplyState | None:
    conversation = Conversation(messages=said, drafts=drafts, truncated=truncated)
    return reply_state_of(
        message,
        conversation,
        observed_at=OBSERVED,
        validity=timedelta(minutes=2),
        excerpt_max_chars=EXCERPT_MAX,
    )


def _status(state: ReplyState | None) -> str | None:
    return state.status if state is not None else None


class TestAReceivedMessage:
    def test_nothing_after_it_is_unanswered(self) -> None:
        asked = received("asked", 0)

        state = decide(asked, asked)

        assert state is not None
        assert (state.status, state.message, state.conversation_size) == ("unanswered", None, 1)

    def test_the_persons_later_message_to_its_sender_answers_it(self) -> None:
        asked = received("asked", 0)
        reply = sent("reply", 30, snippet="Noted for Friday.")

        state = decide(asked, asked, reply)

        assert state is not None and state.message is not None
        assert state.status == "answered"
        assert state.message.message_id == "reply"
        assert state.message.correspondents == "Marc Dupont"
        assert state.message.excerpt == "Noted for Friday."
        assert state.conversation_size == 2

    def test_the_reply_is_dated_in_the_accounts_own_zone(self) -> None:
        """08:30 UTC is 09:30 for an account in Paris: the clock a model is given."""
        asked = received("asked", 0)

        state = decide(asked, asked, sent("reply", 30))

        assert state is not None and state.message is not None
        assert state.message.at.isoformat() == "2026-11-10T09:30:00+01:00"

    def test_the_latest_of_several_replies_is_the_one_carried(self) -> None:
        asked = received("asked", 0)

        state = decide(asked, asked, sent("first", 10), sent("second", 50))

        assert state is not None and state.message is not None
        assert state.message.message_id == "second"

    def test_a_message_sent_to_someone_else_is_no_answer(self) -> None:
        """A forward to a third party leaves the sender unanswered."""
        asked = received("asked", 0)

        assert _status(decide(asked, asked, sent("forward", 20, to=PAUL))) == "unanswered"

    def test_a_reply_to_all_that_copies_the_sender_answers_it(self) -> None:
        asked = received("asked", 0)

        assert _status(decide(asked, asked, sent("all", 20, to=PAUL, cc=MARC))) == "answered"

    @pytest.mark.parametrize("answered_to", ["List <list@example.org>", MARC])
    def test_a_reply_address_and_the_sender_both_count(self, answered_to: str) -> None:
        asked = received("asked", 0, reply_to="List <list@example.org>")

        assert _status(decide(asked, asked, sent("reply", 20, to=answered_to))) == "answered"

    def test_an_address_is_compared_whatever_its_case_and_its_display_name(self) -> None:
        asked = received("asked", 0, **{"from": '"Dupont, Marc" <Marc@Example.org>'})

        assert _status(decide(asked, asked, sent("reply", 20, to="marc@example.org"))) == "answered"

    def test_a_message_the_person_sent_before_it_is_no_answer(self) -> None:
        earlier = sent("earlier", 0)
        asked = received("asked", 30)

        assert _status(decide(asked, earlier, asked)) == "unanswered"

    def test_a_message_of_the_same_instant_crossed_it_and_answers_nothing(self) -> None:
        """Graph dates to the second (measured 2026-11-11): « later » is strict, so what
        cannot be told from a crossing is never read as an answer."""
        asked = received("asked", 30)

        assert _status(decide(asked, asked, sent("crossing", 30))) == "unanswered"

    def test_a_new_message_from_the_sender_is_unanswered_again(self) -> None:
        """Answered, then written to again: the ball is back with the person."""
        asked = received("asked", 0)
        reply = sent("reply", 30)
        again = received("again", 60)

        assert _status(decide(asked, asked, reply, again)) == "answered"
        assert _status(decide(again, asked, reply, again)) == "unanswered"


class TestTheMailboxOwnMark:
    def test_a_marked_message_is_answered_even_when_the_reply_is_not_found(self) -> None:
        """A reply filed under another subject leaves the conversation; the mark stays."""
        asked = received("asked", 0, **{FIELD_MAIL_ANSWERED: True})

        state = decide(asked, asked)

        assert state is not None
        assert (state.status, state.message, state.marked_at) == ("answered", None, None)

    def test_the_mark_is_read_on_the_conversations_own_copy_of_the_message(self) -> None:
        """A listing does not carry the mark; the conversation read does, dated."""
        listed = received("asked", 0)
        row = received(
            "asked", 0, **{FIELD_MAIL_ANSWERED: True, FIELD_MAIL_ANSWERED_AT: _millis(45)}
        )

        state = decide(listed, row)

        assert state is not None and state.marked_at is not None
        assert state.status == "answered"
        assert state.marked_at.isoformat() == "2026-11-10T09:45:00+01:00"

    def test_a_reply_found_is_carried_rather_than_the_bare_mark(self) -> None:
        asked = received("asked", 0, **{FIELD_MAIL_ANSWERED: True})

        state = decide(asked, asked, sent("reply", 30))

        assert state is not None and state.message is not None
        assert state.message.message_id == "reply" and state.marked_at is None


class TestAnUnsentAnswer:
    def test_a_draft_to_the_sender_is_an_answer_drafted(self) -> None:
        asked = received("asked", 0)

        state = decide(asked, asked, drafts=(draft("d1", 15, snippet="Hello Marc,"),))

        assert state is not None and state.message is not None
        assert state.status == "answer_drafted"
        assert (state.message.message_id, state.message.excerpt) == ("d1", "Hello Marc,")
        assert state.conversation_size == 1  # a draft is no part of what was said

    def test_a_draft_to_someone_else_is_no_answer_drafted(self) -> None:
        asked = received("asked", 0)

        assert _status(decide(asked, asked, drafts=(draft("d1", 15, to=PAUL),))) == "unanswered"

    def test_a_sent_answer_wins_over_a_draft_left_behind(self) -> None:
        asked = received("asked", 0)

        state = decide(asked, asked, sent("reply", 30), drafts=(draft("d1", 15),))

        assert _status(state) == "answered"


class TestTheSameMessageTwice:
    def test_the_sent_copy_of_a_message_is_not_its_answer(self) -> None:
        """A mailbox keeps a sent copy beside the received one, under one Message-ID."""
        asked = received("inbox-copy", 1, **{"from": MARC, "rfc_message_id": "<same@mail>"})
        other_copy = sent("sent-copy", 2, rfc_message_id="<same@mail>")

        state = decide(asked, asked, other_copy)

        assert state is not None
        assert (state.status, state.conversation_size) == ("unanswered", 1)

    def test_a_message_the_person_addressed_to_themselves_has_no_reply_state(self) -> None:
        note = sent("note", 0, to=ME, labelIds=["SENT", "INBOX"])

        assert decide(note, note) is None

    def test_a_listing_that_names_no_message_id_still_knows_its_other_copy(self) -> None:
        """A listing may carry less than the conversation read (measured on Graph,
        2026-11-11): the conversation's own copy of the message is the one read."""
        listed = received("inbox-copy", 1)
        del listed["rfc_message_id"]
        own_copy = received("inbox-copy", 1, rfc_message_id="<same@mail>")
        sent_copy = sent("sent-copy", 2, rfc_message_id="<same@mail>")

        state = decide(listed, own_copy, sent_copy)

        assert state is not None
        assert (state.status, state.conversation_size) == ("unanswered", 1)

    def test_what_the_conversation_knows_of_the_message_wins_over_its_listing(self) -> None:
        """A provider that labels nothing says « the owner's own » in the conversation read."""
        listed = _row("mine", 0, ["INBOX"], **{"from": ME, "to": MARC})
        own_copy = _row("mine", 0, ["INBOX", "SENT"], **{"from": ME, "to": MARC})

        assert _status(decide(listed, own_copy)) == "awaiting_reply"

    def test_a_received_note_to_oneself_has_no_reply_state_either(self) -> None:
        """A provider files the note in the inbox with no mark that the owner sent it."""
        note = received("note", 0, **{"from": ME, "to": ME})

        assert decide(note, note) is None


class TestAMessageThePersonSent:
    def test_someone_writing_after_it_is_a_reply_received(self) -> None:
        mine = sent("mine", 0)
        answer = received("answer", 40, snippet="Thanks, see you Friday.")

        state = decide(mine, mine, answer)

        assert state is not None and state.message is not None
        assert state.status == "reply_received"
        assert state.message.message_id == "answer"
        assert state.message.correspondents == "Marc Dupont"

    def test_nobody_writing_after_it_is_awaiting_a_reply(self) -> None:
        mine = sent("mine", 0)

        assert _status(decide(mine, received("before", -30), mine)) == "awaiting_reply"

    def test_the_persons_own_follow_up_is_no_reply_received(self) -> None:
        mine = sent("mine", 0)

        assert _status(decide(mine, mine, sent("follow-up", 20))) == "awaiting_reply"

    def test_unsent_words_filed_among_the_messages_are_nobodys_reply(self) -> None:
        """A client that left a draft in what was said must not invent an answer."""
        mine = sent("mine", 0)

        state = decide(mine, mine, draft("left-behind", 20))

        assert state is not None
        assert (state.status, state.conversation_size) == ("awaiting_reply", 1)


class TestWhatCannotBeEstablishedIsNotClaimed:
    def test_a_cut_conversation_still_answers_for_a_message_it_holds(self) -> None:
        """The newest messages are kept: nothing after a kept message is missing."""
        asked = received("asked", 60)

        state = decide(asked, asked, truncated=True)

        assert state is not None
        assert (state.status, state.conversation_size) == ("unanswered", None)

    def test_a_message_older_than_what_was_read_is_not_said_unanswered(self) -> None:
        old = received("old", 0)

        assert decide(old, received("recent", 600), truncated=True) is None

    def test_a_reply_found_in_what_was_read_still_answers_an_older_message(self) -> None:
        old = received("old", 0)

        assert _status(decide(old, sent("reply", 600), truncated=True)) == "answered"

    def test_a_message_with_no_date_has_no_reply_state(self) -> None:
        undated = received("undated", None)

        assert decide(undated, undated, sent("reply", 30)) is None

    def test_a_message_the_conversation_files_as_unsent_has_no_state_either(self) -> None:
        """IMAP labels nothing: only the conversation read knows a listed message is a draft."""
        unsent = draft("unsent", 10)
        listed = {**unsent, "labelIds": []}

        assert decide(listed, received("asked", 0), drafts=(unsent,)) is None

    def test_a_draft_has_no_reply_state_of_its_own(self) -> None:
        unsent = draft("d1", 0)

        assert decide(unsent, received("asked", -10)) is None

    def test_a_sender_nobody_can_read_leaves_the_message_unanswered(self) -> None:
        asked = received("asked", 0, **{"from": "not an address"})

        assert _status(decide(asked, asked, sent("reply", 20))) == "unanswered"


class TestAReplySentFromASlowClock:
    def test_a_message_that_names_the_one_it_answers_is_later_whatever_its_date(self) -> None:
        """IMAP dates a message by its author's clock: a quick reply may read earlier."""
        asked = received("asked", 10)
        reply = sent("reply", 8, **{FIELD_MAIL_IN_REPLY_TO: "<asked@mail>"})

        assert _status(decide(asked, asked, reply)) == "answered"


class TestWhatIsCarried:
    def test_an_excerpt_is_one_line_cut_on_a_word(self) -> None:
        asked = received("asked", 0)
        long_words = (
            "Thank you for your message,\nI will come back to you before the end of the week."
        )

        state = decide(asked, asked, sent("reply", 30, snippet=long_words))

        assert state is not None and state.message is not None
        assert "\n" not in state.message.excerpt
        assert len(state.message.excerpt) <= EXCERPT_MAX
        assert state.message.excerpt.endswith("…")

    def test_the_excerpt_is_the_reply_itself_never_the_history_it_quotes(self) -> None:
        """A provider's preview runs a short reply into what it answers (measured on
        Graph, 2026-11-11): « what I answered » is the person's words alone."""
        asked = received("asked", 0)
        preview = (
            "Yes, Friday. On Tue, Nov 10, 2026 at 9:00 AM Marc Dupont <marc@example.org> "
            "wrote: Can you make it on Friday?"
        )

        state = decide(asked, asked, sent("reply", 30, snippet=preview))

        assert state is not None and state.message is not None
        assert state.message.excerpt == "Yes, Friday."

    def test_many_recipients_are_named_up_to_a_few_and_counted(self) -> None:
        asked = received("asked", 0)
        everyone = ", ".join([MARC, PAUL, "Zoé <zoe@example.org>", "Ali <ali@example.org>"])

        state = decide(asked, asked, sent("reply", 30, to=everyone))

        assert state is not None and state.message is not None
        assert state.message.correspondents == "Marc Dupont, Paul, Zoé +1"

    def test_a_recipient_without_a_name_is_named_by_its_address(self) -> None:
        asked = received("asked", 0, **{"from": "marc@example.org"})

        state = decide(asked, asked, sent("reply", 30, to="marc@example.org"))

        assert state is not None and state.message is not None
        assert state.message.correspondents == "marc@example.org"

    def test_the_reading_is_stamped_with_its_instant_and_its_validity(self) -> None:
        asked = received("asked", 0)

        state = decide(asked, asked)

        assert state is not None
        assert state.observed_at == OBSERVED
        assert state.valid_until == OBSERVED + timedelta(minutes=2)
