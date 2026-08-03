"""Grounded suggestions for the empty chat.

The empty chat showed three generic examples. It can instead prove that LIA
already knows the day — but only where the evidence exists, and that is the
whole difficulty.

**Why this reads a cache instead of fetching.** The chat page deliberately
knows nothing about the account's connectors (`lib/chat-starters` documents
why: offering "show my last emails" to someone with no mail connector turns
the very first interaction into a failure). Fetching here would fix the
knowledge and break three other things — it would wake connectors, spend
quotas, and make opening an empty chat slower than it is today.

So a suggestion is produced only when the briefing has ALREADY computed the
evidence for it. A cold cache yields nothing, and the client falls back to its
generic starters: the normal case, not a degraded one.

**No LLM.** The selection is a handful of conditions over data that already
exists — exactly what the brief asked for.

**One source is read LIVE, and only one.** Measured on a real account
(2026-08-03): `agenda` and `mails` were NOT_CONFIGURED — no connector — and
`for_you` EMPTY, so the rail could never be anything but generic. The three
cache-backed sources are exactly the ones a connector-less account cannot
fill. Reminders close that gap without costing anything the rule above
forbids: they live in a LOCAL table, `fetch_reminders` is documented as
"always succeeds — does not raise ConnectorNotConfiguredError", and the
briefing rates the read at < 10 ms. That is why the section is `TTL = 0` and
never cached — which is also why a cache-only reader could not see the
cheapest source in the system.

**Nothing is auto-sent.** These become editable drafts in the composer, like
the starters and the follow-up chips they share a rail with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import CHAT_SUGGESTIONS_MAX
from src.domains.briefing.schemas import CardStatus

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChatSuggestion:
    """One grounded suggestion.

    Carries an id and parameters, never a sentence: the wording is resolved
    client-side from the locale, as every other backend contract does.

    Attributes:
        id: Stable identifier — also the i18n key suffix.
        params: Interpolation values (a person, an event, a commitment).
    """

    id: str
    params: dict[str, str] = field(default_factory=dict)


def _usable(section: Any) -> Any | None:
    """The section's payload when it is evidence, else None.

    ``OK`` is required on purpose. ``ERROR`` means the connector failed — an
    absence of knowledge, not a fact — and ``HIDDEN`` means the reader removed
    that card, which a suggestion must not override.
    """
    if section is None or getattr(section, "status", None) is not CardStatus.OK:
        return None
    return getattr(section, "data", None)


async def build_chat_suggestions(user: Any) -> list[ChatSuggestion]:
    """Suggestions backed by what the briefing cache already holds.

    Order is stable and starts with the day itself: an upcoming meeting is the
    most time-bound thing a reader can act on, then the mail batch, then a
    commitment that has been waiting.

    Only the FIRST event and the FIRST commitment are quoted — three cards
    should give three different suggestions, not three variants of one.

    Args:
        user: The authenticated user.

    Returns:
        At most ``CHAT_SUGGESTIONS_MAX`` suggestions; empty when the cache
        holds no evidence, which is the ordinary cold-start case.
    """
    from src.domains.briefing.service import BriefingService

    # Built OUTSIDE the guard on purpose: the constructor only resolves the
    # timezone and the display preferences, both tolerant by design, so a
    # failure there would be a programming error — and swallowing it as "cache
    # unavailable" would hide it forever. Only the Redis read is best-effort.
    service = BriefingService(user)
    try:
        cards = await service.read_cached_cards()
    except Exception as exc:
        # A suggestion is a bonus: never let it stand between the reader and
        # their empty chat.
        logger.debug("chat_suggestions_cache_unavailable", error=str(exc))
        return []

    suggestions: list[ChatSuggestion] = []

    agenda = _usable(getattr(cards, "agenda", None))
    events = getattr(agenda, "events", None) or []
    if events:
        suggestions.append(ChatSuggestion(id="next_event", params={"subject": events[0].title}))

    mails = _usable(getattr(cards, "mails", None))
    if getattr(mails, "items", None):
        # No sender or subject quoted: the suggestion is about the batch, and
        # naming one correspondent would pick for the reader.
        suggestions.append(ChatSuggestion(id="important_mails"))

    for_you = _usable(getattr(cards, "for_you", None))
    loops = getattr(for_you, "open_loops", None) or []
    if loops:
        suggestions.append(ChatSuggestion(id="close_loop", params={"subject": loops[0].subject}))

    # Read live, deliberately — see the module docstring. Last in the order:
    # a meeting and a mail batch are more time-bound than a reminder, which
    # will fire on its own anyway.
    if len(suggestions) < CHAT_SUGGESTIONS_MAX:
        suggestions.extend(await _reminder_suggestions(user))

    # Count only — an event title and a commitment subject are the user's own
    # words and never belong in a log (PII rule).
    logger.debug("chat_suggestions_built", count=len(suggestions))
    return suggestions[:CHAT_SUGGESTIONS_MAX]


async def _reminder_suggestions(user: Any) -> list[ChatSuggestion]:
    """The first pending reminder, as a suggestion — or nothing.

    Its own function so the live read has exactly one failure boundary: a
    suggestion is a bonus and must never stand between the reader and their
    empty chat.

    Args:
        user: The authenticated user.

    Returns:
        At most one suggestion. Only the FIRST reminder is quoted — three
        cards should give three different suggestions, not three of one.
    """
    from src.core.time_utils import resolve_user_timezone
    from src.domains.briefing import fetchers

    try:
        data = await fetchers.fetch_reminders(
            user_id=user.id,
            user_tz=resolve_user_timezone(user),
            language=getattr(user, "language", None),
        )
    except Exception as exc:
        logger.debug("chat_suggestions_reminders_unavailable", error=str(exc))
        return []

    items = getattr(data, "items", None) or []
    if not items:
        return []
    return [ChatSuggestion(id="reminder", params={"subject": items[0].content})]


class ChatSuggestionItem(BaseModel):
    """API view of one grounded suggestion."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable identifier; also the i18n key suffix.")
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Interpolation values resolved into the localized wording client-side.",
    )


class ChatSuggestionsResponse(BaseModel):
    """Suggestions the empty chat may offer, possibly none."""

    suggestions: list[ChatSuggestionItem] = Field(
        default_factory=list,
        description=(
            "Empty when the briefing cache holds no evidence — the ordinary "
            "cold-start case, where the client shows its generic starters."
        ),
    )
