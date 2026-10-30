"""What one page load showed, kept for the act so its text speaks of the same page.

The progressive dashboard's text reads published caches only (spec 2026-10-21 §5.8).
A section the first response served from the cache could expire before the text was
asked for — the text is asked once every pending section settled — and the synthesis
then read it as « not configured »: a card the person sees, missing from what LIA says
of the day, and that partial text kept under its own fingerprint (fresh review B2).

The first response therefore keeps the sections it served for the act's lifetime; the
text reads that copy only for a section the cache no longer holds, so a section re-read
since (a push, a refresh) still reads its newer payload. SMS is left out: its text
reads the live witness on its own terms.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.briefing.cache_keys import act_snapshot_key
from src.domains.briefing.constants import SECTION_SMS
from src.domains.briefing.schemas import CardSection, CardStatus
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

#: What a first response shows without having read it: nothing to keep.
_NOT_SHOWN = frozenset({CardStatus.PENDING, CardStatus.HIDDEN})


async def keep_served(*, user_id: UUID, act_id: str, sections: Mapping[str, CardSection]) -> None:
    """Keep the sections a first response served, for the act's lifetime (best-effort).

    Args:
        user_id: Whose dashboard.
        act_id: The act the first response opened.
        sections: Every section of the first response, by name.
    """
    served = {
        name: section.model_dump_json()
        for name, section in sections.items()
        if name != SECTION_SMS and section.status not in _NOT_SHOWN
    }
    if not served:
        return
    try:
        redis = await get_redis_cache()
        await redis.set(
            act_snapshot_key(user_id=user_id, act_id=act_id),
            _encode(served),
            ex=settings.briefing_act_token_ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - the copy is best-effort, the cache decides
        logger.debug("briefing_act_snapshot_write_failed", error_type=type(exc).__name__)


async def served_sections(*, user_id: UUID, act_id: str) -> dict[str, CardSection]:
    """The sections the act's first response served, or nothing (best-effort).

    Args:
        user_id: Whose dashboard.
        act_id: The act.

    Returns:
        The kept sections, by name; empty when none was kept or the copy is unreadable.
    """
    try:
        redis = await get_redis_cache()
        raw = await redis.get(act_snapshot_key(user_id=user_id, act_id=act_id))
        if raw is None:
            return {}
        return {name: CardSection.model_validate_json(value) for name, value in _decode(raw)}
    except Exception as exc:  # noqa: BLE001 - an unreadable copy is no copy
        logger.debug("briefing_act_snapshot_read_failed", error_type=type(exc).__name__)
        return {}


def _encode(served: Mapping[str, str]) -> str:
    return json.dumps(dict(served), separators=(",", ":"))


def _decode(raw: str | bytes) -> list[tuple[str, str]]:
    return [(str(name), str(value)) for name, value in json.loads(raw).items()]


__all__ = ["keep_served", "served_sections"]
