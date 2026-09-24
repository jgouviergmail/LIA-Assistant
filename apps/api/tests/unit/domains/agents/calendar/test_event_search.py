"""Loose event search: the same words, found the same way, on every provider.

The calendar tool used to read ``query`` as a PERSON: it looked the word up in
the contacts, searched the provider for that person's e-mail, and silently
dropped anything else. « déjeuner » became a contacts lookup that failed (a
WARNING and a People API call), and the window was returned as if it were the
result of the search (measured 2026-09-23). The providers disagree on what a
server-side query covers (title only, title and description, everything), so the
match is made HERE, on the normalised events, identically for Google, Microsoft
and Apple: title, location, organizer and attendees, names and e-mails, case and
accents ignored, each word matching the start of a word.
"""

from typing import Any

import pytest

from src.domains.agents.calendar.event_search import filter_events, search_terms

pytestmark = pytest.mark.unit


def _event(**fields: Any) -> dict[str, Any]:
    return {"id": fields.pop("id", "evt"), **fields}


LUNCH = _event(
    id="lunch",
    summary="Déjeuner en terrasse",
    location="Terrasse du Parc, Lyon",
    attendees=[{"email": "alex.li@example.com", "displayName": "Alex Li"}],
    organizer={"email": "me@example.com", "displayName": "Moi"},
)
REVIEW = _event(
    id="review",
    summary="Revue de projet",
    location="Salle Hôtel de Ville",
    attendees=[{"email": "jdupont@corp.example"}],
    organizer={"email": "paul.martin@corp.example", "displayName": "Paul Martin"},
)
APPLE_NO_ORGANIZER = _event(id="apple", summary="Dentiste", location="Cabinet Médical")


def _ids(events: list[dict[str, Any]]) -> list[str]:
    return [event["id"] for event in events]


class TestWhatIsSearched:
    def test_the_title(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "revue")) == ["review"]

    def test_the_location(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "Lyon")) == ["lunch"]

    def test_an_attendee_name(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "Alex")) == ["lunch"]

    def test_an_attendee_email_with_no_name(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "jdupont")) == ["review"]

    def test_the_organizer(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "Martin")) == ["review"]

    def test_an_event_without_organizer_or_attendees(self) -> None:
        assert _ids(filter_events([APPLE_NO_ORGANIZER, REVIEW], "médical")) == ["apple"]


class TestHowLoose:
    def test_case_and_accents_are_ignored(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "DEJEUNER")) == ["lunch"]
        assert _ids(filter_events([LUNCH, REVIEW], "hotel")) == ["review"]

    def test_a_word_matches_the_start_of_a_word(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "déjeun")) == ["lunch"]

    def test_not_the_middle_of_a_word(self) -> None:
        assert filter_events([LUNCH, REVIEW], "euner") == []

    def test_every_word_must_be_found(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "déjeuner Alex")) == ["lunch"]
        assert filter_events([LUNCH, REVIEW], "déjeuner Paul") == []

    def test_words_may_be_found_in_different_fields(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "terrasse Alex")) == ["lunch"]
        assert filter_events([LUNCH, REVIEW], "terrasse Martin") == []

    def test_short_words_are_not_required(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "le déjeuner")) == ["lunch"]

    def test_a_query_of_short_words_only_still_searches(self) -> None:
        assert _ids(filter_events([LUNCH, REVIEW], "Li")) == ["lunch"]

    def test_the_window_order_is_kept(self) -> None:
        both = _event(id="both", summary="Revue du déjeuner")
        assert _ids(filter_events([both, LUNCH, REVIEW], "déjeuner")) == ["both", "lunch"]


class TestTheTerms:
    def test_a_blank_query_has_no_terms(self) -> None:
        assert search_terms("   ") == []

    def test_terms_are_folded(self) -> None:
        assert search_terms("Déjeuner HÔTEL") == ["dejeuner", "hotel"]
