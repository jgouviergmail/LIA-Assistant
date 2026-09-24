"""Loose calendar event search, made identically for every provider.

The calendar tool used to read ``query`` as a PERSON: it looked the word up in
the contacts, searched the provider for that person's e-mail and silently
dropped anything else, so « déjeuner » cost a contacts lookup, logged a WARNING
and came back as the unfiltered window (measured 2026-09-23). The providers do
not agree on what a server-side query covers — Google searches everything,
Microsoft the subject only, the Apple client the title and description — so the
search is made HERE, on the events every client already normalises to one shape:
title, location, organizer and attendees (names and e-mail addresses), case and
accents ignored, each word of the query matching the start of a word.

Folding and tokenising are the shared implementations (``fold_name``,
``TOKEN_RE``): a second notion of « the same word » would be a second authority.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from src.domains.shared.name_mentions import MIN_TOKEN_LEN, TOKEN_RE
from src.domains.shared.text_normalization import fold_name

#: The event fields a query is matched against, named in every search statement.
SEARCHED_FIELDS: Final[tuple[str, ...]] = ("title", "location", "organizer", "attendees")

#: What ``query`` means — published verbatim to the planner catalogue AND to the
#: ReAct tool, because the rule the tool applies is the rule both producers read.
QUERY_CONTRACT: Final[str] = (
    "Words to find in an event's title, location, organizer or attendees (names and "
    "e-mail addresses). Case and accents are ignored, a word matches the start of a "
    f"word, words shorter than {MIN_TOKEN_LEN} letters are ignored, and every other word "
    "must be found. Use one or two distinctive words: a name, a subject word, a place. "
    "For a theme or a category (medical, important), omit query and judge the listed "
    "events yourself."
)


def search_terms(query: str) -> list[str]:
    """The folded words a query requires.

    Words shorter than ``MIN_TOKEN_LEN`` are not required (articles and
    prepositions in any language), unless the query has no other word.

    Args:
        query: The raw query.

    Returns:
        Folded terms, in query order; empty for a blank query.
    """
    tokens: list[str] = TOKEN_RE.findall(fold_name(query))
    long_tokens = [token for token in tokens if len(token) >= MIN_TOKEN_LEN]
    return long_tokens or tokens


def _event_words(event: dict[str, Any]) -> set[str]:
    """Every folded word of the searched fields of one normalised event."""
    texts: list[Any] = [event.get("summary"), event.get("location")]
    organizer = event.get("organizer")
    people: list[Any] = [organizer] if isinstance(organizer, dict) else []
    people.extend(event.get("attendees") or [])
    for person in people:
        if isinstance(person, dict):
            texts.extend((person.get("displayName"), person.get("email")))
    return {
        word
        for text in texts
        if isinstance(text, str)
        for word in TOKEN_RE.findall(fold_name(text))
    }


def event_matches(event: dict[str, Any], terms: list[str]) -> bool:
    """Whether every term starts a word of the event's searched fields.

    Args:
        event: One event in the normalised (Google-shaped) form.
        terms: Terms from :func:`search_terms`.

    Returns:
        True when each term is found.
    """
    words = _event_words(event)
    return all(any(word.startswith(term) for word in words) for term in terms)


def filter_events(events: Iterable[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """The events a query finds, in the window's order.

    Args:
        events: Normalised events of the searched window.
        query: The raw query.

    Returns:
        The matching events; every event when the query has no term.
    """
    terms = search_terms(query)
    return [event for event in events if not terms or event_matches(event, terms)]


def describe_search(search: dict[str, Any], *, shown: int, preview: str) -> str:
    """The line the model reads first: what was searched, found and left out.

    Technical English, like every tool payload message (ADR-256).

    Args:
        search: The search record the tool built (query, fields, matched,
            searched, window_complete).
        shown: How many matching events the result carries.
        preview: Short listing of the shown events' titles.

    Returns:
        One statement; a window read only in part says how to reach the rest.
    """
    query = search["query"]
    scope = f"in {', '.join(search['fields'])}, among {search['searched']} read in the window"
    if search["matched"]:
        line = f"[search] {search['matched']} event(s) matching '{query}' {scope}"
        if shown < search["matched"]:
            line += f" (first {shown} shown)"
        line += f": {preview}"
    else:
        line = f"[search] no event matching '{query}' {scope}"
    if not search["window_complete"]:
        line += (
            ". The window holds more events than one read covers: narrow or move it to "
            "search the rest"
        )
    return line
