"""What an administrator does to the instance's Fish Audio voices, and what each act owes (ADR-345).

- CREATING — a clone or a saved design — is the operator's switch
  (``FISHAUDIO_VOICE_CREATION_ENABLED``); renaming and deleting stay open, so a
  library can always be tidied.
- A clone is made from a voice its administrator ATTESTS is theirs, or whose
  owner consented in writing: the attestation is filed in the admin audit log
  BEFORE the vendor is called — no attestation on record, no clone — and the
  voice is always private.
- A design is paid by the INSTANCE: its daily ceiling is asked first, its price
  (``FISHAUDIO_VOICE_DESIGN_COST_USD``) charged after a success and filed under
  the administrator who asked. Its candidates wait server-side.
- A PUBLIC voice of the vendor's library is offered once an administrator
  pinned it (amendment 2026-10-14): ONE list for every voice slot, the voice read
  first — a trained speech voice the vendor serves — and the right to use it
  attested in the admin audit log BEFORE the pin is stored, like a clone's.
- A voice a TTS slot speaks with is never deleted, nor unpinned, from under it
  (409 naming the slots); a deleted voice a person had chosen for LIA gives them
  the instance's voice back.
- Every change to the account's own voices forgets its cached voice lists, so
  the pickers and the radio see it at once; a list is cached per set of pins, so
  a pin needs no forgetting.

No act holds a database session while the vendor answers (ADR-304): the
records are written on short sessions of their own, before or after.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NoReturn
from uuid import UUID

import structlog
from fastapi import status

from src.core.config import settings
from src.core.constants import (
    FISHAUDIO_CLONE_PREFILL_MAX_SECONDS,
    FISHAUDIO_PROVIDER_NAME,
    STT_BYTES_PER_SECOND_AT_16KHZ_INT16,
)
from src.core.exceptions import BaseAPIException, STTError, STTModelNotFoundError
from src.domains.llm_config.authorization import lock_current_admin
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
from src.domains.usage_limits.instance_spend import record_instance_fixed_spend
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import AdminAuditLog
from src.domains.voice.fishaudio import slot_references
from src.domains.voice.fishaudio.catalogue_revision import (
    clear_removal,
    lock_catalogue,
    reserve_removal,
)
from src.domains.voice.fishaudio.credential import require_current_account
from src.domains.voice.fishaudio.design_store import (
    CandidateSavePending,
    DesignStoreUnavailable,
    StoredCandidate,
    claim_candidate,
    forget_candidate,
    keep_candidates,
    release_candidate,
)
from src.domains.voice.fishaudio.library import (
    LibraryVoice,
    VoiceSample,
    create_voice,
    delete_voice,
    design_voices,
    list_own_voices,
    rename_voice,
)
from src.domains.voice.fishaudio.library_errors import (
    ACCOUNT_CHANGED,
    API_KEY_MISSING,
    AUDIT_UNAVAILABLE,
    CANDIDATE_EXPIRED,
    CANDIDATE_SAVE_PENDING,
    CONSENT_REQUIRED,
    CREATION_DISABLED,
    DESIGN_STORE_UNAVAILABLE,
    PIN_AUDIT_UNAVAILABLE,
    PIN_CONSENT_REQUIRED,
    PIN_UNAVAILABLE,
    PINS_FULL,
    PREFILL_TOO_LONG,
    PREFILL_UNAVAILABLE,
    SAMPLE_UNREADABLE,
    VOICE_IN_USE,
    refuse,
    refuse_vendor,
)
from src.domains.voice.fishaudio.pins import PinsFull, add_pin, read_pins, remove_pin
from src.domains.voice.fishaudio.voices import (
    FishVoicesError,
    fetch_fish_voice,
    invalidate_fish_voices,
)
from src.domains.voice.lia_voices import forget_voice
from src.domains.voice.stt.sherpa_stt import get_stt_service
from src.infrastructure.database.session import get_db_context
from src.infrastructure.media.ffmpeg import FfmpegError, transcode

logger = structlog.get_logger(__name__)

#: What the admin audit log files these acts under.
AUDIT_RESOURCE = "fishaudio_voice"

#: How long the local engine may take to decode a sample, and to hear it.
_PREFILL_DECODE_TIMEOUT_S = 30.0


@dataclass(frozen=True, slots=True)
class Actor:
    """Who acts, as the admin audit log records them.

    Attributes:
        admin_id: The administrator.
        ip_address: Where the request came from.
        user_agent: What sent it.
    """

    admin_id: UUID
    ip_address: str | None
    user_agent: str | None


def fish_api_key() -> str | None:
    """The instance's Fish Audio key, or ``None`` when none is configured."""
    return LLMConfigOverrideCache.get_api_key(FISHAUDIO_PROVIDER_NAME) or None


def _required_key() -> str:
    api_key = fish_api_key()
    if api_key is None:
        refuse(status.HTTP_409_CONFLICT, API_KEY_MISSING)
    return api_key


def creation_enabled() -> bool:
    """Whether the operator lets administrators create voices."""
    return bool(settings.fishaudio_voice_creation_enabled)


def prefill_available() -> bool:
    """Whether the local engine can offer a sample's transcript."""
    return bool(settings.voice_stt_enabled)


def require_creation() -> None:
    """Refuse (403, coded) when the operator switched voice creation off."""
    if not creation_enabled():
        refuse(status.HTTP_403_FORBIDDEN, CREATION_DISABLED)


async def slots_by_voice() -> dict[str, list[str]]:
    """Committed TTS references in one query, closed before any vendor wait.

    A worker's cache may lag another administrator's committed configuration;
    it cannot authorize deletion of a voice that configuration already uses.
    """
    async with get_db_context() as db:
        return await slot_references.slots_by_voice(db)


async def _begin_delete(actor: Actor, voice_id: str, api_key: str) -> tuple[str, bool]:
    async with get_db_context() as db:
        await lock_catalogue(db)
        await require_current_account(db, credential_fingerprint(api_key))
        await lock_current_admin(db, actor.admin_id, action="delete a Fish Audio voice")
        slots = (await slot_references.slots_by_voice(db)).get(voice_id, [])
        if slots:
            refuse(status.HTTP_409_CONFLICT, VOICE_IN_USE, slots=slots)
        return await reserve_removal(db, voice_id)


async def _clear_delete(voice_id: str, token: str) -> None:
    async with get_db_context() as db:
        await lock_catalogue(db)
        await clear_removal(db, voice_id, token)


async def _authorize(actor: Actor, api_key: str) -> None:
    """Admit an external mutation using current rights, releasing SQL before I/O."""
    async with get_db_context() as db:
        await require_current_account(db, credential_fingerprint(api_key))
        await lock_current_admin(db, actor.admin_id, action="manage the Fish Audio voice library")


async def _audit(
    actor: Actor,
    action: str,
    details: dict[str, Any],
    *,
    authorize: bool = False,
    api_key: str | None = None,
) -> None:
    async with get_db_context() as db:
        if authorize:
            await require_current_account(db, credential_fingerprint(api_key or ""))
            await lock_current_admin(
                db, actor.admin_id, action="manage the Fish Audio voice library"
            )
        db.add(
            AdminAuditLog(
                admin_user_id=actor.admin_id,
                action=action,
                resource_type=AUDIT_RESOURCE,
                resource_id=None,
                details=details,
                ip_address=actor.ip_address,
                user_agent=actor.user_agent,
            )
        )


async def _audit_done(actor: Actor, action: str, details: dict[str, Any]) -> None:
    """File an act already performed: a failure is logged, never raised."""
    try:
        await _audit(actor, action, details)
    except Exception as exc:  # noqa: BLE001 — the act happened; the answer must say so
        logger.error("fishaudio_library_audit_failed", action=action, error_type=type(exc).__name__)


async def library_voices() -> list[tuple[LibraryVoice, list[str]]]:
    """The account's own voices, each with the TTS slots speaking with it.

    Raises:
        BaseAPIException: When the vendor cannot be read.
    """
    api_key = fish_api_key()
    if api_key is None:
        return []
    try:
        voices = await list_own_voices(api_key)
    except FishVoicesError as exc:
        refuse_vendor(exc)
    speaking = await slots_by_voice()
    return [(voice, speaking.get(voice.voice_id, [])) for voice in voices]


async def clone_voice(
    actor: Actor,
    *,
    title: str,
    samples: Sequence[VoiceSample],
    texts: Sequence[str],
    enhance_audio_quality: bool,
    consent: bool,
) -> LibraryVoice:
    """Create a private voice from recordings its administrator attested the right to clone.

    Args:
        actor: The administrator.
        title: The voice's name.
        samples: The recordings (the router bounds them).
        texts: What each says — all or none.
        enhance_audio_quality: Let the vendor clean the recordings first.
        consent: The attestation; without it, nothing happens.

    Returns:
        The voice.

    Raises:
        BaseAPIException: A coded refusal.
    """
    require_creation()
    if not consent:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, CONSENT_REQUIRED)
    api_key = _required_key()
    attestation = {
        "consent_attested": True,
        "title": title,
        "samples": len(samples),
        "texts_given": bool(texts),
    }
    try:
        await _audit(
            actor, "fishaudio_voice_clone_attested", attestation, authorize=True, api_key=api_key
        )
    except BaseAPIException:
        raise
    except Exception as exc:  # noqa: BLE001 — no attestation on record, no clone
        logger.error("fishaudio_clone_attestation_failed", error_type=type(exc).__name__)
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, AUDIT_UNAVAILABLE)
    try:
        voice = await create_voice(
            api_key,
            title=title,
            samples=samples,
            texts=texts,
            enhance_audio_quality=enhance_audio_quality,
        )
    except FishVoicesError as exc:
        refuse_vendor(exc)
    await invalidate_fish_voices(api_key)
    await _audit_done(
        actor, "fishaudio_voice_created", {"voice_id": voice.voice_id, "origin": "clone"}
    )
    logger.info("fishaudio_voice_cloned", voice_id=voice.voice_id, samples=len(samples))
    return voice


async def design(
    actor: Actor,
    *,
    instruction: str,
    count: int,
    preview_text: str | None,
    language: str | None,
) -> tuple[list[StoredCandidate], Decimal]:
    """Voices designed from a description, kept until one is saved; paid by the instance.

    Returns:
        The candidates, and what the request cost (USD).

    Raises:
        BaseAPIException: A coded refusal, or the instance pause (429).
    """
    require_creation()
    api_key = _required_key()
    paused = await UsageLimitService.instance_budget_block()
    if paused is not None:
        raise_for_blocked_verdict(paused, layer="fishaudio_voice_design")
    await _authorize(actor, api_key)
    try:
        candidates = await design_voices(
            api_key,
            instruction=instruction,
            count=count,
            preview_text=preview_text,
            language=language,
        )
    except FishVoicesError as exc:
        refuse_vendor(exc)
    cost_usd = Decimal(str(settings.fishaudio_voice_design_cost_usd))
    await record_instance_fixed_spend(surface="fishaudio_voice_design", cost_usd=cost_usd)
    await _audit_done(
        actor,
        "fishaudio_voice_designed",
        {"candidates": len(candidates), "cost_usd": str(cost_usd)},
    )
    try:
        return (
            await keep_candidates(
                candidates, credential_fingerprint=credential_fingerprint(api_key)
            ),
            cost_usd,
        )
    except DesignStoreUnavailable:
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, DESIGN_STORE_UNAVAILABLE)


async def save_design(actor: Actor, candidate_id: str, *, title: str) -> LibraryVoice:
    """Save a designed voice into the library.

    Raises:
        BaseAPIException: A coded refusal (an expired candidate included).
    """
    require_creation()
    api_key = _required_key()
    try:
        claim = await claim_candidate(candidate_id)
    except CandidateSavePending:
        refuse(status.HTTP_409_CONFLICT, CANDIDATE_SAVE_PENDING)
    except DesignStoreUnavailable:
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, DESIGN_STORE_UNAVAILABLE)
    if claim is None:
        refuse(status.HTTP_410_GONE, CANDIDATE_EXPIRED)
    try:
        if claim.credential_fingerprint != credential_fingerprint(api_key):
            refuse(status.HTTP_409_CONFLICT, ACCOUNT_CHANGED)
        await _authorize(actor, api_key)
    except BaseException:
        # No vendor dispatch yet, so even cancellation may safely release it.
        await release_candidate(claim)
        raise
    candidate = claim.candidate
    try:
        voice = await create_voice(
            api_key,
            title=title,
            samples=[VoiceSample("design.wav", candidate.audio, "audio/wav")],
            texts=[candidate.text] if candidate.text else (),
        )
    except FishVoicesError as exc:
        if not exc.effect_may_have_occurred:
            await release_candidate(claim)
        refuse_vendor(exc)
    await forget_candidate(claim)
    await invalidate_fish_voices(api_key)
    await _audit_done(
        actor, "fishaudio_voice_created", {"voice_id": voice.voice_id, "origin": "design"}
    )
    return voice


async def rename(actor: Actor, voice_id: str, *, title: str) -> None:
    """Rename one of the account's voices.

    Raises:
        BaseAPIException: A coded refusal.
    """
    api_key = _required_key()
    await _authorize(actor, api_key)
    try:
        await rename_voice(api_key, voice_id, title)
    except FishVoicesError as exc:
        refuse_vendor(exc)
    await invalidate_fish_voices(api_key)
    await _audit_done(actor, "fishaudio_voice_renamed", {"voice_id": voice_id, "title": title})


async def delete(actor: Actor, voice_id: str) -> None:
    """Delete one of the account's voices, unless a TTS slot speaks with it.

    Raises:
        BaseAPIException: 409 naming the slots, or a coded refusal.
    """
    api_key = _required_key()
    token, fresh = await _begin_delete(actor, voice_id, api_key)
    try:
        await delete_voice(api_key, voice_id)
    except FishVoicesError as exc:
        if exc.kind != "not_found":
            # A definitive refusal can release only a fresh reservation. An
            # unavailable transport or an explicit retry leaves prior uncertainty.
            if fresh and not exc.effect_may_have_occurred:
                await _clear_delete(voice_id, token)
            refuse_vendor(exc)
    await invalidate_fish_voices(api_key)
    given_back = await forget_voice(voice_id)
    # Preferences are purged before releasing the pending deletion. If the
    # process stops earlier, another explicit delete can confirm absence (404).
    await _clear_delete(voice_id, token)
    await _audit_done(
        actor, "fishaudio_voice_deleted", {"voice_id": voice_id, "accounts_given_back": given_back}
    )


async def pinned_voices() -> tuple[str, ...]:
    """The public voices the instance pinned, in the order they were pinned."""
    return await read_pins()


def _refuse_full() -> NoReturn:
    refuse(status.HTTP_409_CONFLICT, PINS_FULL, max_pins=settings.fishaudio_pinned_voices_max)


async def pin(actor: Actor, voice_id: str, *, attested: bool) -> tuple[str, ...]:
    """Pin a public library voice for every voice slot, under its administrator's attestation.

    Pinning a voice already pinned changes nothing and files nothing.

    Args:
        actor: The administrator.
        voice_id: A well-formed vendor model id (the router checks it).
        attested: The attestation; without it, nothing happens.

    Returns:
        The pins after the act.

    Raises:
        BaseAPIException: A coded refusal.
    """
    if not attested:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, PIN_CONSENT_REQUIRED)
    pins = await read_pins()
    if voice_id in pins:
        return pins
    if len(pins) >= settings.fishaudio_pinned_voices_max:
        _refuse_full()
    api_key = _required_key()
    try:
        voice = await fetch_fish_voice(api_key, voice_id)
    except FishVoicesError as exc:
        refuse_vendor(exc)
    if voice is None:
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, PIN_UNAVAILABLE)
    attestation = {
        "rights_attested": True,
        "voice_id": voice_id,
        "label": voice.label,
        "language": voice.language,
    }
    try:
        await _audit(
            actor, "fishaudio_voice_pin_attested", attestation, authorize=True, api_key=api_key
        )
    except BaseAPIException:
        raise
    except Exception as exc:  # noqa: BLE001 — no attestation on record, no pin
        logger.error("fishaudio_pin_attestation_failed", error_type=type(exc).__name__)
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, PIN_AUDIT_UNAVAILABLE)
    try:
        pins, pinned = await add_pin(
            voice_id, actor.admin_id, credential_fingerprint=credential_fingerprint(api_key)
        )
    except PinsFull:
        # Another administrator filled the list since it was read.
        _refuse_full()
    if pinned:
        await _audit_done(actor, "fishaudio_voice_pinned", {"voice_id": voice_id})
        logger.info("fishaudio_voice_pinned", voice_id=voice_id, pins=len(pins))
    return pins


async def unpin(actor: Actor, voice_id: str) -> tuple[str, ...]:
    """Unpin a public voice, unless a voice slot speaks with it.

    Unpinning a voice that is not pinned changes nothing and files nothing.

    Args:
        actor: The administrator.
        voice_id: A well-formed vendor model id (the router checks it).

    Returns:
        The pins after the act.

    Raises:
        BaseAPIException: 409 naming the slots speaking with it.
    """
    pins, unpinned = await remove_pin(voice_id, actor.admin_id)
    if unpinned:
        await _audit_done(actor, "fishaudio_voice_unpinned", {"voice_id": voice_id})
        logger.info("fishaudio_voice_unpinned", voice_id=voice_id, pins=len(pins))
    return pins


async def sample_transcript(audio: bytes, *, language: str | None) -> str:
    """What a recording says, heard by the local engine — the clone form's prefill.

    Args:
        audio: The recording (any container ffmpeg reads).
        language: The language it is spoken in, when the administrator said.

    Returns:
        The words, blanks collapsed.

    Raises:
        BaseAPIException: The engine is off or failed, the file is unreadable,
            or the recording is longer than the prefill hears.
    """
    require_creation()
    if not prefill_available():
        refuse(status.HTTP_409_CONFLICT, PREFILL_UNAVAILABLE)
    try:
        # One second past the cap tells an over-long recording from one that fits.
        pcm = await transcode(
            audio,
            output_format="s16le",
            args=["-ac", "1", "-ar", "16000", "-t", str(FISHAUDIO_CLONE_PREFILL_MAX_SECONDS + 1)],
            timeout_s=_PREFILL_DECODE_TIMEOUT_S,
        )
    except FfmpegError as exc:
        if exc.kind == "failed":
            refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, SAMPLE_UNREADABLE)
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, PREFILL_UNAVAILABLE)
    if len(pcm) > FISHAUDIO_CLONE_PREFILL_MAX_SECONDS * STT_BYTES_PER_SECOND_AT_16KHZ_INT16:
        refuse(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            PREFILL_TOO_LONG,
            max_seconds=FISHAUDIO_CLONE_PREFILL_MAX_SECONDS,
        )
    try:
        text = await get_stt_service().transcribe_unbounded_pcm_async(pcm, language=language)
    except (STTError, STTModelNotFoundError) as exc:
        logger.warning("fishaudio_prefill_failed", error_type=type(exc).__name__)
        refuse(status.HTTP_503_SERVICE_UNAVAILABLE, PREFILL_UNAVAILABLE)
    return " ".join(text.split())


__all__ = [
    "AUDIT_RESOURCE",
    "Actor",
    "clone_voice",
    "creation_enabled",
    "delete",
    "design",
    "fish_api_key",
    "library_voices",
    "pin",
    "pinned_voices",
    "prefill_available",
    "require_creation",
    "rename",
    "sample_transcript",
    "save_design",
    "slots_by_voice",
    "unpin",
]
