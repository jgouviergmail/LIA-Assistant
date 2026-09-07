"""Where a briefing section's cached payload lives — one builder, every reader.

The key carries the LANGUAGE, because the payloads are pre-formatted
server-side: an agenda time, a mail date, a reminder's "tomorrow 09:00", a
document's modification time. Keyed on the account alone, the cache served the
previous language until each TTL elapsed.

This module exists because that key had **four** builders — three literal
f-strings inside ``BriefingService`` and a fourth in the push invalidation,
which is in another domain and was not going to be found by reading the
service. Adding the language segment to three of them left the fourth deleting
a key that no longer exists, and ``redis.delete`` on an absent key returns 0:
a Gmail or Calendar push would have stopped invalidating anything, in silence,
with the staleness bounded only by the TTL the push exists to short-circuit.

So: one builder, and the invalidation asks it for every variant rather than
guessing which language the person is reading in.

The family prefixes are untouched, so ``briefing:v2`` and
``briefing:v2:lastgood`` keep the scopes they declare in
``infrastructure/cache/key_families.py`` (ADR-260) and the conversation
reset's ``*:{user_id}:*`` scan still reaches every key.
"""

from __future__ import annotations

from uuid import UUID

from src.core.i18n import SUPPORTED_LANGUAGES
from src.domains.briefing.constants import BRIEFING_CACHE_PREFIX

_LAST_GOOD = "lastgood"

# Completeness raised, not asserted, so it survives -O — the same shape
# ``push_channels/cache_invalidation`` already uses for its provider table
# (ADR-085). Its caller runs under ``contextlib.suppress(Exception)`` by
# doctrine, and ``redis.delete()`` with no arguments is an error: an empty
# language list would turn every push invalidation into a silent no-op, which
# is the exact failure this module was written to end. ``SUPPORTED_LANGUAGES=``
# in the environment reaches an empty list — the validator filters blanks and
# nothing rejects the result.
if not SUPPORTED_LANGUAGES:
    raise RuntimeError(
        "SUPPORTED_LANGUAGES is empty: briefing cache keys could not be enumerated, "
        "and push-driven cache invalidation would silently stop working."
    )


def section_cache_key(*, user_id: UUID | str, language: str, section: str) -> str:
    """The cache key holding one section's payload.

    Args:
        user_id: Whose dashboard.
        language: The language the payload was formatted in.
        section: Section name.

    Returns:
        The fully scoped Redis key.
    """
    return f"{BRIEFING_CACHE_PREFIX}:{user_id}:{language}:{section}"


def last_good_key(*, user_id: UUID | str, language: str, section: str) -> str:
    """The long-TTL side key holding one section's last known-good payload.

    Args:
        user_id: Whose dashboard.
        language: The language the payload was formatted in.
        section: Section name.

    Returns:
        The fully scoped Redis key.
    """
    return f"{BRIEFING_CACHE_PREFIX}:{_LAST_GOOD}:{user_id}:{language}:{section}"


def section_keys_every_language(*, user_id: UUID | str, section: str) -> list[str]:
    """Every cache key one section can occupy, across the supported languages.

    For callers that know a source changed but not which language the person
    reads in — the push invalidation above all. Enumerating the supported
    languages costs one DELETE of six keys; matching them with a SCAN would
    walk the keyspace on a path that runs on every push notification.

    The bounded gap that buys: an account whose stored language is no longer
    in the deployment's supported set keeps a stale card until its TTL. That is
    exactly what this module's caller already accepts by doctrine — "failing to
    drop them only means the TTL bounds staleness".

    Args:
        user_id: Whose dashboard.
        section: Section name.

    Returns:
        One key per supported language.
    """
    return [
        section_cache_key(user_id=user_id, language=language, section=section)
        for language in SUPPORTED_LANGUAGES
    ]


__all__ = ["last_good_key", "section_cache_key", "section_keys_every_language"]
