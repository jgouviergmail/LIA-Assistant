"""The instance's Fish Audio voice library, for administrators (ADR-345).

``/admin/voice/fishaudio/library``: list the account's own voices, clone one
from recordings (with the administrator's consent attestation), design some
from a description and save one, rename, delete — and pin a public voice of the
vendor's library for every voice slot (with the administrator's attestation of
the right to use it), or unpin it. The key and the catalogue are the
instance's, so the section is the administrators' alone.

Every route authenticates on a session of its own, closed before the route
runs (ADR-304): a clone or a design waits on the vendor for up to two minutes,
and a request session would pin a PostgreSQL backend in ``idle in transaction``
all along. The superuser check is therefore a CALL in each endpoint.
"""

from __future__ import annotations

import base64
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from src.core.client_ip import resolve_client_ip
from src.core.config import settings
from src.core.constants import (
    FISHAUDIO_CLONE_PREFILL_MAX_SECONDS,
    FISHAUDIO_CLONE_SAMPLE_EXTENSIONS,
    FISHAUDIO_CLONE_SAMPLE_MAX_BYTES,
    FISHAUDIO_CLONE_SAMPLES_MAX,
    FISHAUDIO_CLONE_TOTAL_MAX_BYTES,
    FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS,
    FISHAUDIO_DESIGN_CANDIDATES_MAX,
    FISHAUDIO_DESIGN_INSTRUCTION_MAX_CHARS,
    FISHAUDIO_DESIGN_PREVIEW_MAX_CHARS,
    FISHAUDIO_VOICE_TITLE_MAX_CHARS,
    RATE_LIMIT_FISHAUDIO_VOICE_LIBRARY_PER_MINUTE,
)
from src.core.security.authorization import require_superuser
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User
from src.domains.voice.fishaudio import library_service
from src.domains.voice.fishaudio.library import LibraryVoice, VoiceSample
from src.domains.voice.fishaudio.library_errors import (
    SAMPLE_FORMAT,
    SAMPLE_TOO_LARGE,
    SAMPLES_COUNT,
    TEXTS_MISMATCH,
    TITLE_INVALID,
    VOICE_NOT_FOUND,
    refuse,
)
from src.domains.voice.fishaudio.library_schemas import (
    DesignCandidatePayload,
    DesignRequest,
    DesignResponse,
    LibraryLanguage,
    LibraryVoicePayload,
    PinnedVoicesResponse,
    PinVoiceRequest,
    SampleTranscriptResponse,
    VoiceLibraryBounds,
    VoiceLibraryResponse,
    VoiceTitleRequest,
)
from src.domains.voice.fishaudio.voices import VOICE_ID_PATTERN

router = APIRouter(prefix="/admin/voice/fishaudio/library", tags=["admin", "voice"])

#: One budget for every request that writes to the vendor, pays, or decodes.
rate_limit_library = create_user_rate_limiter(
    action="fishaudio_voice_library",
    max_calls=RATE_LIMIT_FISHAUDIO_VOICE_LIBRARY_PER_MINUTE,
    authenticate=get_current_active_session_for_stream,
)

Administrator = Annotated[User, Depends(get_current_active_session_for_stream)]


def _actor(user: User, request: Request) -> library_service.Actor:
    return library_service.Actor(
        admin_id=user.id,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _payload(voice: LibraryVoice, slots: list[str]) -> LibraryVoicePayload:
    return LibraryVoicePayload(
        voice_id=voice.voice_id,
        title=voice.title,
        state=voice.state,
        languages=list(voice.languages),
        created_at=voice.created_at,
        used_by_slots=slots,
    )


def _pins(voice_ids: tuple[str, ...]) -> PinnedVoicesResponse:
    return PinnedVoicesResponse(
        voice_ids=list(voice_ids), max_pins=settings.fishaudio_pinned_voices_max
    )


def _voice_id(raw: str) -> str:
    """A vendor model id, or a 404: anything else names no voice, and never reaches a URL."""
    if not VOICE_ID_PATTERN.fullmatch(raw):
        refuse(status.HTTP_404_NOT_FOUND, VOICE_NOT_FOUND)
    return raw


def _title(raw: str) -> str:
    """A form's title, held to the JSON routes' rule."""
    words = " ".join(raw.split())
    if not words or len(words) > FISHAUDIO_VOICE_TITLE_MAX_CHARS:
        refuse(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            TITLE_INVALID,
            max_chars=FISHAUDIO_VOICE_TITLE_MAX_CHARS,
        )
    return words


def _size(upload: UploadFile) -> int:
    if upload.size is not None:
        return upload.size
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)
    return size


def _extension(upload: UploadFile) -> str:
    name = upload.filename or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in FISHAUDIO_CLONE_SAMPLE_EXTENSIONS:
        refuse(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            SAMPLE_FORMAT,
            formats=list(FISHAUDIO_CLONE_SAMPLE_EXTENSIONS),
        )
    return extension


def _samples(uploads: list[UploadFile]) -> list[VoiceSample]:
    """The recordings, bounded one by one and together, under neutral names.

    The administrator's file names never leave: the vendor reads the container
    from the extension, and a name may be a person's.
    """
    if not 1 <= len(uploads) <= FISHAUDIO_CLONE_SAMPLES_MAX:
        refuse(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            SAMPLES_COUNT,
            max_samples=FISHAUDIO_CLONE_SAMPLES_MAX,
        )
    sizes = [_size(upload) for upload in uploads]
    if (
        max(sizes) > FISHAUDIO_CLONE_SAMPLE_MAX_BYTES
        or sum(sizes) > FISHAUDIO_CLONE_TOTAL_MAX_BYTES
    ):
        refuse(
            status.HTTP_413_CONTENT_TOO_LARGE,
            SAMPLE_TOO_LARGE,
            max_bytes=FISHAUDIO_CLONE_SAMPLE_MAX_BYTES,
            total_max_bytes=FISHAUDIO_CLONE_TOTAL_MAX_BYTES,
        )
    return [
        VoiceSample(
            filename=f"sample-{index}.{_extension(upload)}",
            content=upload.file,
            mime_type=upload.content_type or "application/octet-stream",
        )
        for index, upload in enumerate(uploads, start=1)
    ]


def _texts(raw: list[str], samples: int) -> list[str]:
    """What each recording says: one per recording, or none at all."""
    texts = [" ".join(text.split()) for text in raw]
    if not any(texts):
        return []
    if len(texts) != samples or not all(texts):
        refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, TEXTS_MISMATCH)
    return texts


@router.get("", response_model=VoiceLibraryResponse, summary="The account's voice library")
async def get_library(user: Administrator) -> VoiceLibraryResponse:
    """The account's own voices, what the instance allows, and every bound the routes enforce."""
    require_superuser(user, "read the voice library")
    voices = await library_service.library_voices()
    return VoiceLibraryResponse(
        configured=library_service.fish_api_key() is not None,
        creation_enabled=library_service.creation_enabled(),
        prefill_available=library_service.prefill_available(),
        design_cost_usd=float(settings.fishaudio_voice_design_cost_usd),
        candidate_ttl_seconds=FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS,
        voices=[_payload(voice, slots) for voice, slots in voices],
        bounds=VoiceLibraryBounds(
            samples_max=FISHAUDIO_CLONE_SAMPLES_MAX,
            sample_max_bytes=FISHAUDIO_CLONE_SAMPLE_MAX_BYTES,
            total_max_bytes=FISHAUDIO_CLONE_TOTAL_MAX_BYTES,
            sample_extensions=list(FISHAUDIO_CLONE_SAMPLE_EXTENSIONS),
            title_max_chars=FISHAUDIO_VOICE_TITLE_MAX_CHARS,
            instruction_max_chars=FISHAUDIO_DESIGN_INSTRUCTION_MAX_CHARS,
            preview_max_chars=FISHAUDIO_DESIGN_PREVIEW_MAX_CHARS,
            candidates_max=FISHAUDIO_DESIGN_CANDIDATES_MAX,
            prefill_max_seconds=FISHAUDIO_CLONE_PREFILL_MAX_SECONDS,
        ),
    )


@router.post(
    "/clone",
    response_model=LibraryVoicePayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_library)],
    summary="Clone a voice from recordings, under the administrator's attestation",
)
async def clone_voice(
    request: Request,
    user: Administrator,
    title: Annotated[str, Form()],
    samples: Annotated[list[UploadFile], File()],
    consent: Annotated[bool, Form()] = False,
    texts: Annotated[list[str] | None, Form()] = None,
    enhance_audio_quality: Annotated[bool, Form()] = True,
) -> LibraryVoicePayload:
    """A private voice from recordings the administrator attests the right to clone."""
    require_superuser(user, "clone a voice")
    library_service.require_creation()  # the operator's switch refuses first
    recordings = _samples(samples)
    voice = await library_service.clone_voice(
        _actor(user, request),
        title=_title(title),
        samples=recordings,
        texts=_texts(texts or [], len(recordings)),
        enhance_audio_quality=enhance_audio_quality,
        consent=consent,
    )
    return _payload(voice, [])


@router.post(
    "/transcript",
    response_model=SampleTranscriptResponse,
    dependencies=[Depends(rate_limit_library)],
    summary="What a recording says, heard by the local engine",
)
async def sample_transcript(
    user: Administrator,
    sample: Annotated[UploadFile, File()],
    language: Annotated[LibraryLanguage | None, Form()] = None,
) -> SampleTranscriptResponse:
    """The clone form's prefill: the words of one recording, to check before cloning."""
    require_superuser(user, "transcribe a voice sample")
    library_service.require_creation()
    _samples([sample])  # the clone's own bounds: format and size
    audio = await sample.read()
    return SampleTranscriptResponse(
        text=await library_service.sample_transcript(audio, language=language)
    )


@router.post(
    "/designs",
    response_model=DesignResponse,
    dependencies=[Depends(rate_limit_library)],
    summary="Design voices from a description (paid by the instance)",
)
async def design_voices(
    request: Request, user: Administrator, body: DesignRequest
) -> DesignResponse:
    """Candidates to listen to; one of them may then be saved."""
    require_superuser(user, "design a voice")
    stored, cost_usd = await library_service.design(
        _actor(user, request),
        instruction=body.instruction,
        count=body.count,
        preview_text=body.preview_text,
        language=body.language,
    )
    return DesignResponse(
        candidates=[
            DesignCandidatePayload(
                candidate_id=item.candidate_id,
                duration_ms=item.candidate.duration_ms,
                text=item.candidate.text,
                language=item.candidate.language,
                audio_base64=base64.b64encode(item.candidate.audio).decode("ascii"),
            )
            for item in stored
        ],
        cost_usd=float(cost_usd),
        expires_in_seconds=FISHAUDIO_DESIGN_CANDIDATE_TTL_SECONDS,
    )


@router.post(
    "/designs/{candidate_id}/save",
    response_model=LibraryVoicePayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_library)],
    summary="Save a designed voice into the library",
)
async def save_design(
    candidate_id: str, request: Request, user: Administrator, body: VoiceTitleRequest
) -> LibraryVoicePayload:
    """The designed voice, kept in the account's library under its name."""
    require_superuser(user, "save a designed voice")
    voice = await library_service.save_design(_actor(user, request), candidate_id, title=body.title)
    return _payload(voice, [])


@router.get(
    "/pins",
    response_model=PinnedVoicesResponse,
    summary="The public voices pinned for every voice slot",
)
async def get_pins(user: Administrator) -> PinnedVoicesResponse:
    """The pinned voice ids, in their order, and how many may be pinned."""
    require_superuser(user, "read the pinned voices")
    return _pins(await library_service.pinned_voices())


@router.put(
    "/pins/{voice_id}",
    response_model=PinnedVoicesResponse,
    dependencies=[Depends(rate_limit_library)],
    summary="Pin a public voice for every voice slot, under the administrator's attestation",
)
async def pin_voice(
    voice_id: str, request: Request, user: Administrator, body: PinVoiceRequest
) -> PinnedVoicesResponse:
    """A public voice the administrator attests the right to use, offered to every voice slot."""
    require_superuser(user, "pin a voice")
    pins = await library_service.pin(
        _actor(user, request), _voice_id(voice_id), attested=body.attested
    )
    return _pins(pins)


@router.delete(
    "/pins/{voice_id}",
    response_model=PinnedVoicesResponse,
    summary="Unpin a public voice",
)
async def unpin_voice(voice_id: str, request: Request, user: Administrator) -> PinnedVoicesResponse:
    """Unpin a public voice — refused while a TTS slot speaks with it."""
    require_superuser(user, "unpin a voice")
    return _pins(await library_service.unpin(_actor(user, request), _voice_id(voice_id)))


@router.patch("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Rename a voice")
async def rename_voice(
    voice_id: str, request: Request, user: Administrator, body: VoiceTitleRequest
) -> None:
    """A new name for one of the account's voices."""
    require_superuser(user, "rename a voice")
    await library_service.rename(_actor(user, request), _voice_id(voice_id), title=body.title)


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a voice")
async def delete_voice(voice_id: str, request: Request, user: Administrator) -> None:
    """Delete one of the account's voices — refused while a TTS slot speaks with it."""
    require_superuser(user, "delete a voice")
    await library_service.delete(_actor(user, request), _voice_id(voice_id))


__all__ = ["router"]
