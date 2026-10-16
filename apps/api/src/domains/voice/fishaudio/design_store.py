"""The voices designed and not yet saved, kept server-side for a while (ADR-345).

A design answers previews the administrator listens to before saving one. The
previews stay HERE, under ids LIA mints, so a save uploads the very audio the
vendor designed — never bytes a browser sends back — and an abandoned design
costs nothing more than its expiry (``FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS``).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import secrets
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Final

from redis.exceptions import RedisError

from src.core.constants import (
    FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS,
    REDIS_KEY_FISHAUDIO_DESIGN_PREFIX,
)
from src.domains.voice.fishaudio.library import DesignCandidate
from src.infrastructure.cache.redis import get_redis_cache

#: A candidate id LIA mints: 32 lowercase hexadecimal digits.
CANDIDATE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{32}")


class DesignStoreUnavailable(RuntimeError):
    """The candidates could not be kept or read: Redis is unreachable."""


class CandidateSavePending(RuntimeError):
    """A save owns this candidate, possibly awaiting an uncertain vendor outcome."""


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    """A designed voice waiting to be saved.

    Attributes:
        candidate_id: The id LIA minted for it.
        candidate: What the vendor designed.
    """

    candidate_id: str
    candidate: DesignCandidate


@dataclass(frozen=True, slots=True)
class CandidateClaim:
    """The audio and the token of the one request allowed to save it."""

    candidate_id: str
    token: str
    candidate: DesignCandidate
    credential_fingerprint: str = field(repr=False)


# Keep ownership WITH the audio, under its original expiry. A separate lock key
# could be evicted while the audio survives, admitting a second vendor creation.
# Nesting the old record also makes ordinary preview reads fail closed in flight.
_CLAIM = """
local raw = redis.call('GET', KEYS[1])
if not raw or redis.call('PTTL', KEYS[1]) <= 0 then return {'missing'} end
local ok, item = pcall(cjson.decode, raw)
if not ok or type(item) ~= 'table' then return {'missing'} end
if item.phase == 'saving' then return {'busy'} end
if type(item.audio) ~= 'string' then return {'missing'} end
redis.call('SET', KEYS[1], cjson.encode({phase='saving', token=ARGV[1], payload=raw}),
           'XX', 'KEEPTTL')
return {'claimed', raw}
"""

_SETTLE = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, item = pcall(cjson.decode, raw)
if not ok or type(item) ~= 'table' or item.token ~= ARGV[1]
   or item.phase ~= 'saving' then return 0 end
if ARGV[2] == 'release' and type(item.payload) == 'string' then
    redis.call('SET', KEYS[1], item.payload, 'XX', 'KEEPTTL')
else
    redis.call('DEL', KEYS[1])
end
return 1
"""


def _key(candidate_id: str) -> str:
    return f"{REDIS_KEY_FISHAUDIO_DESIGN_PREFIX}{candidate_id}"


def _encode(candidate: DesignCandidate, credential_fingerprint: str) -> str:
    return json.dumps(
        {
            "audio": base64.b64encode(candidate.audio).decode("ascii"),
            "duration_ms": candidate.duration_ms,
            "text": candidate.text,
            "language": candidate.language,
            "credential_fingerprint": credential_fingerprint,
        }
    )


def _decode(raw: str | bytes) -> DesignCandidate | None:
    try:
        item = json.loads(raw)
        return DesignCandidate(
            audio=base64.b64decode(item["audio"], validate=True),
            duration_ms=int(item["duration_ms"]),
            text=item.get("text"),
            language=item.get("language"),
        )
    except ValueError, TypeError, KeyError, binascii.Error:
        return None


async def keep_candidates(
    candidates: Sequence[DesignCandidate], *, credential_fingerprint: str
) -> list[StoredCandidate]:
    """Keep each candidate under a fresh id until it is saved or expires.

    Args:
        candidates: What the vendor designed.
        credential_fingerprint: Internal identity of the account which generated the audio.

    Returns:
        The candidates with their ids, in order.

    Raises:
        DesignStoreUnavailable: When Redis cannot keep them.
    """
    stored = [StoredCandidate(secrets.token_hex(16), candidate) for candidate in candidates]
    try:
        redis = await get_redis_cache()
        for item in stored:
            await redis.set(
                _key(item.candidate_id),
                _encode(item.candidate, credential_fingerprint),
                ex=FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS,
            )
    except (RedisError, OSError) as exc:
        raise DesignStoreUnavailable("the designed voices could not be kept") from exc
    return stored


async def stored_candidate(candidate_id: str) -> DesignCandidate | None:
    """The available preview, or ``None`` while saving, once saved or expired.

    Raises:
        DesignStoreUnavailable: When Redis cannot be read.
    """
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        return None
    try:
        redis = await get_redis_cache()
        raw = await redis.get(_key(candidate_id))
    except (RedisError, OSError) as exc:
        raise DesignStoreUnavailable("the designed voices could not be read") from exc
    return _decode(raw) if raw is not None else None


async def _settle(candidate_id: str, token: str, *, release: bool) -> None:
    # Failure leaves the SAME key claimed until its original expiry. It must
    # never restore audio after a successful or uncertain vendor dispatch.
    with suppress(RedisError, OSError):
        redis = await get_redis_cache()
        await redis.eval(_SETTLE, 1, _key(candidate_id), token, "release" if release else "forget")


async def claim_candidate(candidate_id: str) -> CandidateClaim | None:
    """Atomically admit one save without extending the preview's lifetime.

    Redis acknowledgement loss or cancellation before returning the claim may
    release OUR token: no vendor call has begun. A failed release stays closed.
    """
    if not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        return None
    token = secrets.token_hex(16)
    try:
        redis = await get_redis_cache()
        result = await redis.eval(_CLAIM, 1, _key(candidate_id), token)
    except (RedisError, OSError, asyncio.CancelledError) as exc:
        await _settle(candidate_id, token, release=True)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise DesignStoreUnavailable("the designed voice could not be reserved") from exc
    if result[0] in {"busy", b"busy"}:
        raise CandidateSavePending("a save has already reserved this preview")
    if result[0] not in {"claimed", b"claimed"}:
        return None
    candidate = _decode(result[1])
    fingerprint = json.loads(result[1]).get("credential_fingerprint")
    if candidate is None or not isinstance(fingerprint, str):
        await _settle(candidate_id, token, release=False)
        return None
    return CandidateClaim(candidate_id, token, candidate, fingerprint)


async def release_candidate(claim: CandidateClaim) -> None:
    """Restore a preview only after a known pre-dispatch or definitive refusal."""
    await _settle(claim.candidate_id, claim.token, release=True)


async def forget_candidate(claim: CandidateClaim) -> None:
    """Drop only the saved candidate still owned by this request."""
    await _settle(claim.candidate_id, claim.token, release=False)


__all__ = [
    "CANDIDATE_ID_PATTERN",
    "CandidateClaim",
    "CandidateSavePending",
    "DesignStoreUnavailable",
    "StoredCandidate",
    "claim_candidate",
    "forget_candidate",
    "keep_candidates",
    "release_candidate",
    "stored_candidate",
]
