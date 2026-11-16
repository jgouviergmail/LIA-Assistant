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

Both callers resolve a real account row: a lookup that failed or found nobody
is answered and refused before this resolver runs (ADR-323), so nothing is ever
written to the journals or the psyche state of someone unidentified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.constants import DEFAULT_EXECUTION_MODE, DEFAULT_USER_DISPLAY_TIMEZONE, ExecutionMode
from src.core.execution_mode import is_execution_mode_choice
from src.core.i18n import normalize_language
from src.core.user_display import resolve_user_display_name

if TYPE_CHECKING:
    from src.domains.users.models import User


@dataclass(frozen=True, slots=True)
class ChannelUserPreferences:
    """Everything a channel hop must forward to ``stream_chat_response``.

    Attributes:
        language: Resolved language code, never empty.
        timezone: IANA timezone for display, never empty.
        memory_enabled: User preference for long-term memory.
        journals_enabled: User preference for personal journals.
        psyche_enabled: User preference for the psyche engine.
        voice_enabled: User preference for voice comments: a voice note is
            answered aloud too (Telegram lot 25).
        execution_mode: The mode the person chose (pipeline | react | auto,
            ADR-390): a channel turn runs in it like a chat turn.
        display_name: Friendly name for sender/signature context, or None.
    """

    language: str
    timezone: str
    memory_enabled: bool
    journals_enabled: bool
    psyche_enabled: bool
    voice_enabled: bool
    execution_mode: ExecutionMode
    display_name: str | None


def _execution_mode_of(user: User) -> ExecutionMode:
    """The person's execution mode; a value no choice names reads as the default."""
    stored = getattr(user, "execution_mode", None)
    return stored if is_execution_mode_choice(stored) else DEFAULT_EXECUTION_MODE


def resolve_channel_preferences(user: User) -> ChannelUserPreferences:
    """Resolve the conversation preferences of a channel-bound user.

    The ``getattr`` fallbacks mirror ``agents/api/router.py`` exactly, so a
    conversation behaves identically whatever transport it arrived on. They only
    fire on an incomplete object — on a real row both journal and psyche columns
    default to true.

    Args:
        user: The loaded account row.

    Returns:
        Fully resolved preferences.
    """
    return ChannelUserPreferences(
        language=normalize_language(getattr(user, "language", None)),
        timezone=getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE,
        memory_enabled=getattr(user, "memory_enabled", True),
        journals_enabled=getattr(user, "journals_enabled", False),
        psyche_enabled=getattr(user, "psyche_enabled", False),
        voice_enabled=getattr(user, "voice_enabled", False),
        execution_mode=_execution_mode_of(user),
        display_name=resolve_user_display_name(
            getattr(user, "full_name", None), getattr(user, "email", None)
        ),
    )
