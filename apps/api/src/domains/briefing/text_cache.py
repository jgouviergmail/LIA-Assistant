"""The dashboard's greeting and synthesis, generated once per distinct input (spec 2026-10-21 §5.8).

The progressive dashboard asks for its text once every pending section has
settled (``POST /briefing/text``). The text reads published caches only, and
what it says depends on exactly these inputs: the projected sections (their
content and statuses), the windows the cards were built with, the briefing
slot's effective configuration, the prompt versions, the local hour (the
greeting speaks to a moment of the day), what the prompts read of the person
(display name, LIA's personality, the user model block) and — when SMS fed the
prompts — the SMS witness. Their fingerprint keys the generated text for
``BRIEFING_TEXT_CACHE_TTL_SECONDS``: two tabs, or a reload, reuse it instead of
paying the slot twice.

Generation is claimed across workers. A waiter takes what the holder
publishes; a holder whose lease was lost mid-generation answers ``uncertain``
and nothing relaunches it — its outcome, and its bill, are unknown (Q3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.briefing.constants import BRIEFING_CACHE_PREFIX
from src.domains.briefing.schemas import BriefingWindows, CardsBundle, SynthesisResponse
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

#: Fields of a section that change at every fetch without changing what it says.
_VOLATILE = {"generated_at", "from_cache", "stale_generated_at", "last_attempt_at"}


def project_cards(cards: CardsBundle) -> tuple[str, dict[str, str]]:
    """What the prompts read of the cards: their content and their statuses.

    Args:
        cards: The bundle the text is generated from.

    Returns:
        The canonical content projection, and each section's status.
    """
    dumped = cards.model_dump(mode="json")
    projected = {
        name: {key: value for key, value in section.items() if key not in _VOLATILE}
        for name, section in dumped.items()
    }
    statuses = {name: str(section.get("status")) for name, section in dumped.items()}
    return json.dumps(projected, sort_keys=True, separators=(",", ":")), statuses


def text_fingerprint(
    projected: str,
    statuses: Mapping[str, str],
    windows: BriefingWindows,
    slot_config_digest: str,
    prompt_version: str,
    sms_witness: str | None,
    *,
    local_hour: str,
    person: str,
) -> str:
    """The identity of one generated text: equal inputs, equal text.

    Args:
        projected: ``project_cards``' content projection.
        statuses: Each section's status.
        windows: The windows the cards were built with.
        slot_config_digest: The briefing slot's effective configuration.
        prompt_version: The greeting and synthesis prompt versions.
        sms_witness: The SMS snapshot the prompts read, or None.
        local_hour: The person's local date and hour.
        person: ``person_inputs_digest`` — what the prompts read of the person.

    Returns:
        A hex digest.
    """
    material = {
        "projected": projected,
        "statuses": dict(sorted(statuses.items())),
        "windows": windows.model_dump(mode="json"),
        "slot": slot_config_digest,
        "prompt": prompt_version,
        "sms": sms_witness,
        "hour": local_hour,
        "person": person,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:40]


def text_cache_key(*, user_id: UUID | str, language: str, fingerprint: str) -> str:
    """Where a generated text is kept (``briefing:v2`` family, a user cache)."""
    return f"{BRIEFING_CACHE_PREFIX}:text:{user_id}:{language}:{fingerprint}"


def local_hour(now_local: datetime) -> str:
    """The moment of day a greeting speaks to."""
    return now_local.strftime("%Y-%m-%dT%H")


async def read_text(key: str) -> SynthesisResponse | None:
    """A text generated for the same inputs, or None (best-effort)."""
    try:
        redis = await get_redis_cache()
        raw = await redis.get(key)
        if raw is None:
            return None
        return SynthesisResponse.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort
        logger.debug("briefing_text_cache_read_failed", error_type=type(exc).__name__)
        return None


async def write_text(key: str, text: SynthesisResponse) -> None:
    """Keep a generated text for the setting's lifetime (best-effort); 0 keeps nothing."""
    if settings.briefing_text_cache_ttl_seconds <= 0:
        return
    try:
        redis = await get_redis_cache()
        await redis.set(key, text.model_dump_json(), ex=settings.briefing_text_cache_ttl_seconds)
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort
        logger.debug("briefing_text_cache_write_failed", error_type=type(exc).__name__)


__all__ = [
    "local_hour",
    "project_cards",
    "read_text",
    "text_cache_key",
    "text_fingerprint",
    "write_text",
]
