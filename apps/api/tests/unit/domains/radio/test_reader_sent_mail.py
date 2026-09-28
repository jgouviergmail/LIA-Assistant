"""The e-mails sent today, read from the sent folder's headers on the listener's clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domains.radio.facts import FactKind
from src.domains.radio.personal import JournalPart
from src.domains.radio.readers.sent_mail import SentMail, sent_mail_drafts, sent_mail_line

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)  # Saturday
PLUS_TWO = timezone(timedelta(hours=2))


def test_a_search_hit_is_read_from_its_normalised_headers() -> None:
    hit = {
        "id": "m1",
        "to": "Sam <sam@example.org>",
        "subject": " Quote ",
        "date": "Sat, 26 Sep 2026 10:12:00 +0200",
        "snippet": "never read",
    }
    assert sent_mail_line(hit) == SentMail(
        id="m1",
        to="Sam <sam@example.org>",
        subject="Quote",
        sent_at=datetime(2026, 9, 26, 10, 12, tzinfo=PLUS_TWO),
    )
    assert sent_mail_line({"subject": "no id"}) is None
    bare = sent_mail_line({"id": "m2", "date": "not a date"})
    assert bare == SentMail(
        id="m2", to="an unnamed recipient", subject="(no subject)", sent_at=None
    )


def test_a_mail_sent_today_is_done_with_its_time_and_yesterday_s_is_left_out() -> None:
    today = SentMail(
        id="m1", to="Sam <sam@example.org>", subject="Quote", sent_at=NOW - timedelta(hours=3)
    )
    yesterday = SentMail(id="m2", to="Alex", subject="Old", sent_at=NOW - timedelta(days=1))
    undated = SentMail(id="m3", to="Kim", subject="Notes", sent_at=None)
    drafts = sent_mail_drafts([today, yesterday, undated], now=NOW, tz=UTC)
    assert [d.text for d in drafts] == [
        'E-mail sent to Sam <sam@example.org>: "Quote" on Saturday 2026-09-26, 10:00',
        'E-mail sent to Kim: "Notes"',
    ]
    assert [d.key for d in drafts] == ["done:email:m1", "done:email:m3"]
    assert {d.kind for d in drafts} == {FactKind.EMAIL} and {d.part for d in drafts} == {
        JournalPart.DONE
    }


def test_the_day_is_the_listener_s() -> None:
    # 23:30 UTC yesterday is 01:30 today two hours east.
    late = SentMail(
        id="m4", to="Sam", subject="Late", sent_at=datetime(2026, 9, 25, 23, 30, tzinfo=UTC)
    )
    assert sent_mail_drafts([late], now=NOW, tz=UTC) == []
    [east] = sent_mail_drafts([late], now=NOW, tz=PLUS_TWO)
    assert east.text.endswith("on Saturday 2026-09-26, 01:30")
