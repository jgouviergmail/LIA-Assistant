"""What makes a finished meeting worth a word, and what makes it noise.

No model decides this. Measured elsewhere and applied here: a deterministic
trigger beats an LLM on both accuracy and latency for the « should I wake »
question, and ADR-261 already settled the doctrine — spending a model call to
decide whether to spend a model call IS the noise.

So the rule is a table, and this is that table. Two halves, and they answer
different questions:

- **necessary conditions** — a single one missing and there is no moment at all.
  They describe events a debrief would be absurd about: a solo slot, a five
  minute call, a whole day off, something declined, something cancelled.
- **points** — among the events that could earn a debrief, which ones actually
  do. The threshold is a published setting, so an operator can make LIA quieter
  or more forthcoming without a deploy.

Every bound is read from ``settings``; a threshold restated here would drift the
day someone tunes the real one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.domains.moments.importance import BlockedBy, ScoreReason, score_event

pytestmark = pytest.mark.unit

ME = "moi@example.com"
UTC_TZ = ZoneInfo("UTC")
START = datetime(2026, 9, 11, 14, 0, tzinfo=UTC)


def _event(**overrides: Any) -> dict[str, Any]:
    """A meeting that clears every necessary condition and scores one point.

    One other attendee, an hour long, timed, accepted, live. On its own that is
    one point (nothing else), which is deliberately BELOW the default threshold:
    every test that expects a moment has to say what earns it.
    """
    minutes = overrides.pop("minutes", 60)
    event: dict[str, Any] = {
        "id": "evt-1",
        "summary": "Point budget",
        "start": {"dateTime": START.isoformat()},
        "end": {"dateTime": (START + timedelta(minutes=minutes)).isoformat()},
        "attendees": [
            {"email": ME, "responseStatus": "accepted"},
            {"email": "marc@example.com", "responseStatus": "accepted"},
        ],
        "organizer": {"email": "marc@example.com"},
    }
    event.update(overrides)
    return event


def _score(event: dict[str, Any], **kwargs: Any) -> Any:
    defaults: dict[str, Any] = {
        "user_email": ME,
        "favorite_keys": frozenset(),
        "linked_keys": frozenset(),
        "user_tz": UTC_TZ,
    }
    defaults.update(kwargs)
    return score_event(event, **defaults)


class TestWhatIsNecessary:
    """One missing and there is no moment — no points are even counted."""

    def test_an_event_with_no_other_attendee_earns_nothing(self) -> None:
        """A solo slot is a block in a calendar, not a meeting to debrief."""
        verdict = _score(_event(attendees=[{"email": ME, "responseStatus": "accepted"}]))

        assert verdict.worthy is False
        assert verdict.blocked_by is BlockedBy.NO_OTHER_ATTENDEE

    def test_an_event_with_no_attendee_list_at_all_earns_nothing(self) -> None:
        """Apple and Microsoft both normalize to the Google shape, but an event
        created without guests simply has no list."""
        event = _event()
        event.pop("attendees")

        assert _score(event).blocked_by is BlockedBy.NO_OTHER_ATTENDEE

    def test_a_short_event_earns_nothing(self) -> None:
        verdict = _score(_event(minutes=settings.moments_event_min_duration_minutes - 1))

        assert verdict.worthy is False
        assert verdict.blocked_by is BlockedBy.TOO_SHORT

    def test_an_event_exactly_at_the_minimum_duration_is_long_enough(self) -> None:
        """The bound is inclusive: read from the setting, never restated."""
        verdict = _score(_event(minutes=settings.moments_event_min_duration_minutes))

        assert verdict.blocked_by is not BlockedBy.TOO_SHORT

    def test_an_all_day_event_earns_nothing(self) -> None:
        """« How did your day off go » is not a meeting debrief."""
        event = _event()
        event["start"] = {"date": "2026-09-11"}
        event["end"] = {"date": "2026-09-12"}

        assert _score(event).blocked_by is BlockedBy.ALL_DAY

    def test_an_event_the_person_declined_earns_nothing(self) -> None:
        """They said they would not be there; asking how it went is absurd."""
        event = _event(
            attendees=[
                {"email": ME, "responseStatus": "declined"},
                {"email": "marc@example.com", "responseStatus": "accepted"},
            ]
        )

        assert _score(event).blocked_by is BlockedBy.DECLINED

    def test_a_cancelled_event_earns_nothing(self) -> None:
        assert _score(_event(status="cancelled")).blocked_by is BlockedBy.CANCELLED

    def test_an_unparseable_event_earns_nothing_rather_than_raising(self) -> None:
        """A provider shape drift must not take the whole sweep down."""
        event = _event()
        event["end"] = {"dateTime": "not-a-date"}

        assert _score(event).worthy is False


class TestWhatEarnsPoints:
    """Among the events that could earn a debrief, which ones do."""

    def test_a_bare_two_person_meeting_scores_one(self) -> None:
        verdict = _score(_event())

        assert verdict.score == 1
        assert verdict.reasons == (ScoreReason.HAS_OTHER_ATTENDEE,)

    def test_several_other_attendees_add_a_point(self) -> None:
        verdict = _score(
            _event(
                attendees=[
                    {"email": ME},
                    {"email": "marc@example.com"},
                    {"email": "julie@example.com"},
                ]
            )
        )

        assert ScoreReason.SEVERAL_ATTENDEES in verdict.reasons
        assert verdict.score == 2

    def test_a_location_adds_a_point(self) -> None:
        verdict = _score(_event(location="Salle Jaures"))

        assert ScoreReason.HAS_LOCATION in verdict.reasons

    def test_a_video_link_counts_as_a_place(self) -> None:
        """A remote meeting is still a meeting held somewhere."""
        verdict = _score(_event(hangoutLink="https://meet.example/abc"))

        assert ScoreReason.HAS_LOCATION in verdict.reasons

    def test_organising_it_adds_a_point(self) -> None:
        verdict = _score(_event(organizer={"email": ME}))

        assert ScoreReason.IS_ORGANIZER in verdict.reasons

    def test_a_favourite_attendee_adds_a_point(self) -> None:
        """``relation_favorites`` names the people who matter to them."""
        verdict = _score(
            _event(
                attendees=[
                    {"email": ME},
                    {"email": "marc@example.com", "displayName": "Marc Dupont"},
                ]
            ),
            favorite_keys=frozenset({"marc dupont"}),
        )

        assert ScoreReason.FAVORITE_ATTENDEE in verdict.reasons

    def test_a_linked_commitment_adds_a_point(self) -> None:
        """An open loop or a ticket naming an attendee makes it consequential."""
        verdict = _score(
            _event(
                attendees=[
                    {"email": ME},
                    {"email": "marc@example.com", "displayName": "Marc Dupont"},
                ]
            ),
            linked_keys=frozenset({"marc dupont"}),
        )

        assert ScoreReason.LINKED_COMMITMENT in verdict.reasons

    def test_matching_a_person_ignores_case_and_accents(self) -> None:
        """One implementation of folding identity, shared with the CRM."""
        verdict = _score(
            _event(
                attendees=[
                    {"email": ME},
                    {"email": "j@example.com", "displayName": "Jérôme GOUVIER"},
                ]
            ),
            favorite_keys=frozenset({"jerome gouvier"}),
        )

        assert ScoreReason.FAVORITE_ATTENDEE in verdict.reasons

    def test_a_favourite_who_is_not_there_adds_nothing(self) -> None:
        verdict = _score(_event(), favorite_keys=frozenset({"quelquun dautre"}))

        assert ScoreReason.FAVORITE_ATTENDEE not in verdict.reasons


class TestTheThreshold:
    def test_below_the_threshold_there_is_no_moment(self) -> None:
        verdict = _score(_event())

        assert verdict.score < settings.moments_event_followup_min_score
        assert verdict.worthy is False
        assert verdict.blocked_by is BlockedBy.BELOW_THRESHOLD

    def test_at_the_threshold_there_is_one(self) -> None:
        verdict = _score(_event(location="Salle Jaures"))

        assert verdict.score >= settings.moments_event_followup_min_score
        assert verdict.worthy is True
        assert verdict.blocked_by is None

    def test_the_reasons_are_stable_and_ordered(self) -> None:
        """They land in the payload and in the operator log: a set would make
        two identical events read differently from one pass to the next."""
        event = _event(
            location="Salle Jaures",
            organizer={"email": ME},
            attendees=[{"email": ME}, {"email": "a@x.fr"}, {"email": "b@x.fr"}],
        )

        first = _score(event).reasons
        second = _score(event).reasons

        assert first == second
        assert first == (
            ScoreReason.HAS_OTHER_ATTENDEE,
            ScoreReason.SEVERAL_ATTENDEES,
            ScoreReason.HAS_LOCATION,
            ScoreReason.IS_ORGANIZER,
        )


class TestWhoIsTheOtherPerson:
    def test_the_person_is_recognised_whatever_the_case_of_their_address(self) -> None:
        event = _event(
            attendees=[
                {"email": ME.upper(), "responseStatus": "declined"},
                {"email": "marc@example.com"},
            ]
        )

        assert _score(event).blocked_by is BlockedBy.DECLINED

    def test_without_a_known_address_everyone_counts_as_someone_else(self) -> None:
        """An account with no resolvable address still gets its debriefs; it
        simply cannot be told apart from its guests, which only ever makes the
        rule more permissive — never wrong about a decline it cannot read."""
        verdict = _score(_event(), user_email=None)

        assert verdict.blocked_by is not BlockedBy.NO_OTHER_ATTENDEE
