"""The Fish Audio voices LIA offers: the account's own, the vendor's licensed, the admin's pins.

Three sources, one list (owner decision 2026-10-14, ADR-345), in this order:

- the voices the ACCOUNT owns (``GET /model?self=true``): its clones and designs;
- public voices an administrator PINNED by id, once for every voice slot
  (:mod:`~src.domains.voice.fishaudio.pins`), after attesting the right to use
  them — the vendor's public library is mostly clones nobody licensed; the admin
  audit log records who pinned what, and when;
- the voices the vendor LICENSED (``licensed=true``: rights secured from the
  voice's owner — 113 on 2026-10-13, one language each).

The vendor lists by pages of 100 at most, and every request takes a slot of the
account's allowance (:mod:`~src.domains.voice.provider_capacity`), which
synthesis shares: the merged list is cached under the account's digest and the
pins it was built with, so a radio start or a picker rarely spends a slot. A
voice that is not a trained speech model, or that the vendor took down, is not
offered — and a pin that became one is logged, never silently kept.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any, BinaryIO, Final, Literal
from uuid import UUID

import httpx
import structlog
from redis.exceptions import RedisError

from src.core.constants import (
    DEFAULT_FISHAUDIO_BASE_URL,
    FISHAUDIO_PROVIDER_NAME,
    FISHAUDIO_VOICES_CACHE_TTL_SECONDS,
    FISHAUDIO_VOICES_MAX_PAGES,
    FISHAUDIO_VOICES_PAGE_SIZE,
    FISHAUDIO_VOICES_TIMEOUT_SECONDS,
    REDIS_KEY_FISHAUDIO_VOICES_PREFIX,
)
from src.domains.voice.fishaudio.catalogue_revision import catalogue_revision
from src.domains.voice.fishaudio.wire import auth_headers, refusal_of
from src.domains.voice.provider_capacity import ProviderCapacityUnavailable, provider_slot
from src.domains.voice.voices_catalog import (
    VoiceOption,
    cached_voice_list,
    keep_voice_list,
)
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

#: Where a voice comes from, as the picker shows it.
SOURCE_OWN: Final[str] = "own"
SOURCE_PINNED: Final[str] = "pinned"
SOURCE_LICENSED: Final[str] = "licensed"

#: A library voice id: the 32 lowercase hex digits of a vendor model.
VOICE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{32}")


#: Why a library request failed, as an administrator is told it: the vendor's
#: allowance, the account's credit, its key, a voice that is not there, a request
#: the vendor refused, or a vendor that could not be reached.
FishVoicesFailure = Literal[
    "rate_limited", "payment_required", "unauthorized", "not_found", "rejected", "unavailable"
]


class FishVoicesError(RuntimeError):
    """The vendor's voice library could not be read or written (its facts in ``details``).

    Attributes:
        kind: Why, so a caller answers without reading the message.
        details: The status and bounded vendor code of a refusal, never its prose.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: FishVoicesFailure = "unavailable",
        details: Mapping[str, object] | None = None,
        effect_may_have_occurred: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.kind: FishVoicesFailure = kind
        self.details = dict(details or {})
        self.effect_may_have_occurred = (
            kind == "unavailable" if effect_may_have_occurred is None else effect_may_have_occurred
        )


def _failure_of(status: int) -> FishVoicesFailure:
    """The kind of a refusal, by its status alone."""
    if status == 429:
        return "rate_limited"
    if status == 402:
        return "payment_required"
    if status in (401, 403):
        return "unauthorized"
    if status == 404:
        return "not_found"
    return "unavailable" if status >= 500 else "rejected"


def _gender(tags: object) -> str | None:
    if not isinstance(tags, list):
        return None
    lowered = {str(tag).lower() for tag in tags}
    if "female" in lowered:
        return "female"
    return "male" if "male" in lowered else None


def voice_option(entity: Mapping[str, Any], source: str) -> VoiceOption | None:
    """The voice a library model is, or ``None`` when it cannot speak.

    Args:
        entity: One ``ModelEntity`` of the vendor's API.
        source: ``own``, ``pinned`` or ``licensed``.

    Returns:
        The option, or ``None`` for a model that is not a trained speech voice
        or that the vendor took down.
    """
    voice_id = entity.get("_id")
    if (
        not isinstance(voice_id, str)
        or entity.get("type") != "tts"
        or entity.get("state") != "trained"
        or entity.get("dmca_taken_down") is True
    ):
        return None
    languages = entity.get("languages")
    language = str(languages[0]) if isinstance(languages, list) and len(languages) == 1 else None
    title = entity.get("title")
    return VoiceOption(
        voice_id=voice_id,
        label=str(title) if isinstance(title, str) and title.strip() else voice_id,
        gender=_gender(entity.get("tags")),
        language=language,
        extra={"source": source},
    )


async def fish_request(
    client: httpx.AsyncClient,
    api_key: str,
    method: str,
    path: str,
    *,
    bound_s: float | None = None,
    params: Mapping[str, str | int | bool] | None = None,
    json: object = None,
    data: Mapping[str, str | list[str]] | None = None,
    files: Sequence[tuple[str, tuple[str, bytes | BinaryIO, str]]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """One library request on the account's allowance, its failures typed.

    The wait for a slot and the request share one bound, so a lease always
    outlives the request it covers (the provider_slot contract).

    Args:
        client: A client on the vendor's root, its key in the headers.
        api_key: The account's key (its allowance).
        method: The HTTP method.
        path: The vendor path.
        bound_s: The whole call's bound; the listing's when omitted.
        params: The query.
        json: A JSON body.
        data: Multipart form fields (a list repeats its field).
        files: Multipart files, as ``(field, (name, content, type))``.
        headers: Headers beyond the client's (a model header).

    Returns:
        The vendor's answer, a success.

    Raises:
        FishVoicesError: Its kind and facts, never the vendor's prose.
    """
    bound = FISHAUDIO_VOICES_TIMEOUT_SECONDS if bound_s is None else bound_s
    dispatched = False
    try:
        async with asyncio.timeout(bound):
            async with provider_slot(FISHAUDIO_PROVIDER_NAME, api_key, timeout_seconds=bound):
                dispatched = True
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    headers=headers,
                )
    except ProviderCapacityUnavailable as exc:
        raise FishVoicesError(
            "Fish Audio capacity could not be reserved", effect_may_have_occurred=dispatched
        ) from exc
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise FishVoicesError(
            "Fish Audio library request timed out", effect_may_have_occurred=dispatched
        ) from exc
    except httpx.HTTPError as exc:
        raise FishVoicesError(
            "Fish Audio library transport error",
            details={"exception_type": type(exc).__name__},
            effect_may_have_occurred=dispatched,
        ) from exc
    if response.status_code >= 400:
        refusal = refusal_of(response)
        raise FishVoicesError(
            "Fish Audio refused the library request",
            kind=_failure_of(refusal.status),
            details=refusal.details(),
        )
    return response


async def _get(
    client: httpx.AsyncClient, api_key: str, path: str, **params: str | int | bool
) -> Any:
    response = await fish_request(client, api_key, "GET", path, params=params or None)
    try:
        return response.json()
    except ValueError as exc:
        raise FishVoicesError("Fish Audio voices answer is not JSON") from exc


async def _pages(
    client: httpx.AsyncClient, api_key: str, source: str, **filters: str | int | bool
) -> list[VoiceOption]:
    voices: list[VoiceOption] = []
    for page in range(1, FISHAUDIO_VOICES_MAX_PAGES + 1):
        payload = await _get(
            client,
            api_key,
            "/model",
            page_size=FISHAUDIO_VOICES_PAGE_SIZE,
            page_number=page,
            **filters,
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise FishVoicesError("Fish Audio voices answer carries no items")
        voices.extend(
            option
            for item in items
            if isinstance(item, dict) and (option := voice_option(item, source)) is not None
        )
        if len(items) < FISHAUDIO_VOICES_PAGE_SIZE or not payload.get("has_more", True):
            break
    return voices


async def fetch_fish_voice(
    api_key: str,
    voice_id: str,
    *,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> VoiceOption | None:
    """One library voice, as a pin would offer it; ``None`` when it cannot speak.

    Raises:
        FishVoicesError: When the vendor cannot be read (a 404 is no error: ``None``).
    """
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=FISHAUDIO_VOICES_TIMEOUT_SECONDS,
        transport=transport,
        headers=auth_headers(api_key),
    ) as client:
        entity = await _get_pin(client, api_key, voice_id)
    return voice_option(entity, SOURCE_PINNED) if entity is not None else None


async def list_fish_voices(
    api_key: str,
    pinned: Sequence[str],
    *,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[VoiceOption]:
    """The account's voices, then the pinned ones, then the licensed ones — each once.

    Args:
        api_key: The account's key.
        pinned: The ids an administrator pinned.
        base_url: The vendor's API root.
        transport: A test transport.

    Returns:
        The voices, first source winning when a voice is in two.

    Raises:
        FishVoicesError: When the vendor cannot be read.
    """
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=FISHAUDIO_VOICES_TIMEOUT_SECONDS,
        transport=transport,
        headers=auth_headers(api_key),
    ) as client:
        own = await _pages(client, api_key, SOURCE_OWN, self=True)
        pins: list[VoiceOption] = []
        for voice_id in pinned:
            entity = await _get_pin(client, api_key, voice_id)
            option = voice_option(entity, SOURCE_PINNED) if entity is not None else None
            if option is None:
                # Taken down, retired or never a speech voice: say so, offer nothing.
                logger.warning("fishaudio_pinned_voice_unavailable", voice_id=voice_id)
                continue
            pins.append(option)
        licensed = await _pages(client, api_key, SOURCE_LICENSED, licensed=True)
    seen: set[str] = set()
    merged: list[VoiceOption] = []
    for option in (*own, *pins, *licensed):
        if option.voice_id not in seen:
            seen.add(option.voice_id)
            merged.append(option)
    return merged


async def _get_pin(client: httpx.AsyncClient, api_key: str, voice_id: str) -> Any | None:
    try:
        entity = await _get(client, api_key, f"/model/{voice_id}")
    except FishVoicesError as error:
        if error.details.get("status_code") == 404:
            return None
        raise
    return entity if isinstance(entity, dict) else None


def _account_digest(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _cache_key(api_key: str, pinned: Sequence[str], revision: UUID | None) -> str:
    pins = hashlib.sha256(",".join(sorted(pinned)).encode()).hexdigest()[:16]
    generation = revision.hex if revision is not None else "initial"
    return f"{REDIS_KEY_FISHAUDIO_VOICES_PREFIX}{_account_digest(api_key)}:{pins}:{generation}"


async def get_fish_voices(api_key: str, pinned: Sequence[str] = ()) -> list[VoiceOption]:
    """The voices to offer for ``api_key``'s account, from cache when it holds them.

    Args:
        api_key: The account's key.
        pinned: The ids the instance pinned (:func:`~src.domains.voice.fishaudio.pins.read_pins`).

    Returns:
        The account's voices, the pinned ones, the licensed ones.

    Raises:
        FishVoicesError: When the vendor cannot be read and nothing is cached.
    """
    key = _cache_key(api_key, pinned, await catalogue_revision())
    voices = await cached_voice_list(key)
    if voices is not None:
        return voices
    voices = await list_fish_voices(api_key, pinned)
    await keep_voice_list(key, voices, FISHAUDIO_VOICES_CACHE_TTL_SECONDS, catalogue="fishaudio")
    return voices


async def peek_fish_voices(api_key: str, pinned: Sequence[str] = ()) -> list[VoiceOption] | None:
    """The voices ``api_key``'s account offers as the cache holds them — the vendor is never asked.

    Args:
        api_key: The account's key.
        pinned: The ids the instance pinned.

    Returns:
        The cached list, or ``None`` when none is cached for these pins.
    """
    return await cached_voice_list(_cache_key(api_key, pinned, await catalogue_revision()))


async def invalidate_fish_voices(api_key: str) -> None:
    """Forget every cached list of ``api_key``'s account: its own voices just changed.

    One list is cached per set of pins, so every key of the account goes.
    Best effort: a cache Redis cannot reach expires by itself
    (``FISHAUDIO_VOICES_CACHE_TTL_SECONDS``), and the change is not undone.

    Args:
        api_key: The account's key.
    """
    pattern = f"{REDIS_KEY_FISHAUDIO_VOICES_PREFIX}{_account_digest(api_key)}:*"
    try:
        redis = await get_redis_cache()
        keys = [key async for key in redis.scan_iter(match=pattern, count=500)]
        if keys:
            await redis.delete(*keys)
    except RedisError, OSError:
        logger.warning("fishaudio_voices_cache_invalidation_failed")


__all__ = [
    "SOURCE_LICENSED",
    "SOURCE_OWN",
    "SOURCE_PINNED",
    "VOICE_ID_PATTERN",
    "FishVoicesError",
    "FishVoicesFailure",
    "fetch_fish_voice",
    "fish_request",
    "get_fish_voices",
    "invalidate_fish_voices",
    "list_fish_voices",
    "peek_fish_voices",
    "voice_option",
]
