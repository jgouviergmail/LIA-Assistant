"""A tool result projected for a VOICE model (lot 8 of the phone channel).

Measured on production 2026-09-16: a weekend agenda lookup returned four
events and the voice agent saw ONE — the projection paged the RAW Google
event JSON (ids, links, attendees, reminders, colour ids…) under an 800-token
budget, and a single event ate it. The remedy is not a bigger budget alone:
a voice never reads an identifier, a link or a nested structure. Each item is
reduced to what can be SAID — its scalar fields, a nested value's spoken
form when it has one — before the item-by-item paging decides how many fit.
"""

from __future__ import annotations

import json

import pytest

from src.domains.agents.telephony.voice_projection import compact_item, compact_items

#: The shape of one calendar event as the tool returns it (one real event,
#: names replaced, structure kept).
_EVENT = {
    "id": "_64p36cpn6h0j6b9g60o30b9k6kq3ab9p6ss32b9n60qj6dho8gs3ee1j8s",
    "summary": "Dentist",
    "description": "Bring the X-ray results from last time and the insurance card.",
    "location": "12 High Street",
    "start": {
        "dateTime": "2026-09-20T14:00:00+02:00",
        "timeZone": "Europe/Paris",
        "formatted": "dimanche 20 septembre 2026 à 14:00",
    },
    "end": {
        "dateTime": "2026-09-20T15:00:00+02:00",
        "timeZone": "Europe/Paris",
        "formatted": "dimanche 20 septembre 2026 à 15:00",
    },
    "htmlLink": "https://www.google.com/calendar/event?eid=X2",
    "status": "confirmed",
    "attendees": [
        {"email": "someone@example.com", "responseStatus": "accepted", "self": True},
        {"email": "other@example.com", "responseStatus": "needsAction"},
    ],
    "reminders": {"useDefault": True},
    "iCalUID": "abc@google.com",
    "etag": '"3456"',
    "colorId": "7",
    "all_day": False,
    "calendar_id": "family@group.calendar.google.com",
}


@pytest.mark.unit
def test_an_item_keeps_what_a_voice_can_say_and_nothing_a_voice_cannot() -> None:
    item = compact_item(_EVENT)
    assert item == {
        "summary": "Dentist",
        "description": "Bring the X-ray results from last time and the insurance card.",
        "location": "12 High Street",
        "start": "dimanche 20 septembre 2026 à 14:00",
        "end": "dimanche 20 septembre 2026 à 15:00",
        "status": "confirmed",
        "attendees": 2,
        "all_day": False,
    }


@pytest.mark.unit
def test_a_nested_value_without_a_spoken_form_is_dropped_and_a_long_text_is_cut() -> None:
    item = compact_item(
        {
            "subject": "Re: the plan",
            "snippet": "x" * 500,
            "from": {"name": "A Sender", "email": "a@example.com"},
            "labels": ["INBOX", "UNREAD"],
            "payload": {"mimeType": "multipart/alternative", "parts": [{"body": "…"}]},
            "internalDate": "1758000000000",
            "thread_id": "18f2",
            "size_estimate": 12345,
            "unread": True,
        }
    )
    assert item["subject"] == "Re: the plan"
    assert len(item["snippet"]) <= 241 and item["snippet"].endswith("…")
    assert item["from"] == "A Sender"  # a nested value speaks through its name
    assert item["labels"] == "INBOX, UNREAD"  # a list of words is spoken as words
    assert "payload" not in item and "thread_id" not in item
    assert item["size_estimate"] == 12345 and item["unread"] is True


@pytest.mark.unit
def test_compact_items_reduces_only_the_item_lists_of_the_data() -> None:
    data = {
        "count": 4,
        "events": [_EVENT, _EVENT],
        "from_cache": False,
        "user_timezone": "Europe/Paris",
        "calendar_id": "family@group.calendar.google.com",
    }
    out = compact_items(data)
    assert out["count"] == 4 and out["from_cache"] is False
    assert out["user_timezone"] == "Europe/Paris"
    assert "calendar_id" not in out  # an identifier at the top level goes too
    assert [e["summary"] for e in out["events"]] == ["Dentist", "Dentist"]
    # The point of the exercise, measured: four such events fit where one did.
    raw = len(json.dumps([_EVENT] * 4))
    compact = len(json.dumps(compact_items({"events": [_EVENT] * 4})["events"]))
    assert compact * 3 < raw


@pytest.mark.unit
def test_compact_items_leaves_data_without_item_lists_intact() -> None:
    assert compact_items({"temperature": 21.5, "summary": "Sunny"}) == {
        "temperature": 21.5,
        "summary": "Sunny",
    }
