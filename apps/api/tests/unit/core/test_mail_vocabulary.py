"""What the e-mail vocabulary says of a message: one reading, and never a guess."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.mail_vocabulary import UNREAD_LABEL, instant_of, is_unread, labels_of

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("message", "unread"),
    [
        ({"labelIds": ["INBOX", UNREAD_LABEL]}, True),
        ({"labelIds": ("INBOX", UNREAD_LABEL)}, True),
        ({"labelIds": ["INBOX"]}, False),
        ({"labelIds": []}, False),
        # Nothing vouches for the state: never « unread » by default.
        ({}, False),
        ({"labelIds": None}, False),
        ({"labelIds": "UNREAD"}, False),
    ],
)
def test_a_message_is_unread_only_when_its_labels_say_so(
    message: dict[str, object], unread: bool
) -> None:
    assert is_unread(message) is unread


def test_only_the_words_of_a_label_list_are_labels() -> None:
    assert labels_of({"labelIds": ["INBOX", 3, None, "SENT"]}) == ("INBOX", "SENT")


@pytest.mark.parametrize("value", ["1762761600000", 1762761600000])
def test_an_instant_is_read_from_epoch_milliseconds(value: object) -> None:
    assert instant_of(value) == datetime(2025, 11, 10, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("value", [None, "", "0", 0, "-5", "yesterday", 10**30])
def test_what_states_no_instant_reads_as_none(value: object) -> None:
    assert instant_of(value) is None
