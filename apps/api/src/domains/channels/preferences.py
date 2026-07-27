"""Per-user conversation preferences, resolved once for every channel entry point.

Two entry points feed the agent pipeline from an external channel — the inbound
message route and the HITL callback route — and both need the same set of user
preferences. They resolved it independently, and that duplication is exactly how
defect D1 shipped: when personal journals and the psyche engine were added, only
the web chat learned to forward them. The channel routes kept sending memory
alone, the service defaults (``False``) silently applied, and a Telegram
conversation never fed the journals whatever the user had enabled.

One resolver, one contract, two callers. Adding a preference here now reaches
every channel by construction.

Fail-closed by design: with no user row (lookup failed, account unresolved) the
long-term-state preferences are off. We never write to the personal journals or
the psyche state of someone we could not identify.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.user_display import resolve_user_display_name


@dataclass(frozen=True, slots=True)
class ChannelUserPreferences:
    """Everything a channel hop must forward to ``stream_chat_response``.

    Attributes:
        language: Resolved language code, never empty.
        timezone: IANA timezone for display, never empty.
        memory_enabled: User preference for long-term memory.
        journals_enabled: User preference for personal journals.
        psyche_enabled: User preference for the psyche engine.
        display_name: Friendly name for sender/signature context, or None.
    """

    language: str
    timezone: str
    memory_enabled: bool
    journals_enabled: bool
    psyche_enabled: bool
    display_name: str | None


def resolve_channel_preferences(user: Any | None) -> ChannelUserPreferences:
    """Resolve the conversation preferences of a channel-bound user.

    The ``getattr`` fallbacks mirror ``agents/api/router.py`` exactly, so a
    conversation behaves identically whatever transport it arrived on. They only
    fire on an incomplete object — on a real row both journal and psyche columns
    default to true.

    Args:
        user: Loaded ``User`` row, or None when the lookup failed or returned
            nothing.

    Returns:
        Fully resolved preferences; fail-closed on journals and psyche when
        ``user`` is None.
    """
    if user is None:
        return ChannelUserPreferences(
            language=settings.default_language,
            timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
            memory_enabled=True,
            journals_enabled=False,
            psyche_enabled=False,
            display_name=None,
        )

    return ChannelUserPreferences(
        language=getattr(user, "language", None) or settings.default_language,
        timezone=getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE,
        memory_enabled=getattr(user, "memory_enabled", True),
        journals_enabled=getattr(user, "journals_enabled", False),
        psyche_enabled=getattr(user, "psyche_enabled", False),
        display_name=resolve_user_display_name(
            getattr(user, "full_name", None), getattr(user, "email", None)
        ),
    )
