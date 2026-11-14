"""When an earlier message was written reaches the model reading it (lot 17).

Measured on three families (``scripts/agents/measure_message_timestamps.py``):
with no time on any earlier message, a model reads a history restored days later
as if everything had been said just now — « the dentist tomorrow », said three
days ago, is still ahead. The person's message carries the moment it was written
(``WRITTEN_AT_KEY``, set when the turn begins; a message restored from the
archive carries its own), and every projection a model reads prefixes it, in the
person's zone — the current question too, so its bytes never change once earlier.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infrastructure.llm.message_view import (
    WRITTEN_AT_KEY,
    present_label,
    stamped_now,
    with_written_at,
    written_at,
    written_prefix,
)

pytestmark = pytest.mark.unit

#: A zone away from UTC: a stamp proven in UTC proves nothing about a person's clock.
TOKYO = ZoneInfo("Asia/Tokyo")
TUESDAY = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)  # Tue 10 Nov 2026, 09:12 in Tokyo
FRIDAY = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)


def _said(text: str, at: datetime) -> HumanMessage:
    return HumanMessage(text, additional_kwargs={WRITTEN_AT_KEY: at.isoformat()})


def test_the_moment_a_message_was_written_is_read_back_as_an_instant() -> None:
    assert written_at(_said("Hello", TUESDAY)) == TUESDAY
    assert written_at(HumanMessage("Hello")) is None
    # A wall time with no offset is no instant: never guessed into one.
    naive = HumanMessage("x", additional_kwargs={WRITTEN_AT_KEY: "2026-11-10T09:12:00"})
    assert written_at(naive) is None
    assert written_at(HumanMessage("x", additional_kwargs={WRITTEN_AT_KEY: "soon"})) is None


def test_a_message_is_stamped_when_written_without_touching_what_it_says() -> None:
    message = HumanMessage("Hello", additional_kwargs={"other": 1})

    stamped = stamped_now(message, TUESDAY)

    assert stamped.content == "Hello"
    assert stamped.additional_kwargs == {"other": 1, WRITTEN_AT_KEY: TUESDAY.isoformat()}
    assert WRITTEN_AT_KEY not in message.additional_kwargs  # a copy, never the original


def test_a_message_carrying_its_instant_reads_with_it_and_the_others_as_before() -> None:
    history = [
        _said("I have the dentist tomorrow at 10.", TUESDAY),
        AIMessage("Noted."),
        _said("Is it still ahead of me?", FRIDAY),
    ]

    read = with_written_at(history, TOKYO)

    assert read[0].content == "[Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10."
    assert read[1].content == "Noted."  # LIA's answer follows the person's message at once
    # The current question too: the same bytes now as once it is earlier, so a
    # prompt cache that reads a turn back through its question still holds.
    assert read[2].content == "[Fri 13 Nov 2026, 18:30] Is it still ahead of me?"
    # Nothing a caller holds is changed.
    assert history[0].content == "I have the dentist tomorrow at 10."


def test_a_message_restored_from_the_archive_reads_its_own_time() -> None:
    notification = AIMessage(
        "Your parcel was delivered.",
        additional_kwargs={"proactive_notification": True, WRITTEN_AT_KEY: TUESDAY.isoformat()},
    )

    (read,) = with_written_at([notification], TOKYO)

    assert read.content == "[Tue 10 Nov 2026, 09:12] Your parcel was delivered."
    assert read.additional_kwargs == notification.additional_kwargs


def test_a_message_of_blocks_gets_its_time_as_a_first_text_block() -> None:
    blocks = [{"type": "text", "text": "Look at this"}, {"type": "image_url", "image_url": "x"}]
    message = HumanMessage(blocks, additional_kwargs={WRITTEN_AT_KEY: TUESDAY.isoformat()})

    (read,) = with_written_at([message], TOKYO)

    assert read.content == [{"type": "text", "text": "[Tue 10 Nov 2026, 09:12]"}, *blocks]


def test_a_text_reader_prepends_the_same_stamp_and_nothing_to_a_message_with_no_instant() -> None:
    """A reader that flattens messages to text writes the stamp in ONE shape."""
    assert written_prefix(_said("Words.", TUESDAY), TOKYO) == "[Tue 10 Nov 2026, 09:12] "
    assert written_prefix(AIMessage("Noted."), TOKYO) == ""
    (read,) = with_written_at([_said("Words.", TUESDAY)], TOKYO)
    assert read.content == written_prefix(_said("Words.", TUESDAY), TOKYO) + "Words."


def test_the_stamp_never_depends_on_the_process_locale_or_the_reading_moment() -> None:
    """Read twice, a history is the same bytes: a cached prefix stays valid."""
    history = [_said("Words.", TUESDAY)]

    first = with_written_at(history, TOKYO)
    second = with_written_at(history, TOKYO)

    assert first[0].content == second[0].content == "[Tue 10 Nov 2026, 09:12] Words."


def test_the_present_is_written_like_a_stamp_in_the_persons_zone_and_names_it() -> None:
    """The extractions read their present beside stamped messages: one shape, the zone said."""
    now = datetime(2026, 11, 13, 19, 30, tzinfo=UTC)

    assert present_label(TOKYO, now) == "Sat 14 Nov 2026, 04:30 (Asia/Tokyo)"
    assert present_label(ZoneInfo("America/Los_Angeles"), now) == (
        "Fri 13 Nov 2026, 11:30 (America/Los_Angeles)"
    )
