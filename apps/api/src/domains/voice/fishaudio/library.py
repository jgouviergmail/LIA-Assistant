"""The voices the instance's Fish Audio account OWNS: listed, created, renamed, deleted (ADR-345).

The library an administrator manages is the account's own voices, its clones
and its designs. Read from the vendor's documentation on 2026-10-14 — no paid
request was run (owner decision):

- ``POST /model`` (multipart) creates a voice: ``type=tts``, ``train_mode=fast``
  (usable at once), ``visibility`` — always ``private`` here: publishing is the
  vendor's web flow —, the ``voices`` recordings and their ``texts`` (absent,
  the vendor transcribes them itself), ``enhance_audio_quality`` (its default
  is on). The vendor publishes no price for it: nothing is recorded.
- ``PATCH /model/{id}`` renames, ``DELETE /model/{id}`` deletes.
- ``POST /v1/voice-design`` (JSON only, header ``model: voice-design-1``)
  answers 1 to 4 candidates, each a base64 WAV, and is billed ONCE per
  successful request — an empty answer is not billed, and is no success here.

Every request holds one slot of the account's allowance, its wait included in
its bound (:func:`~src.domains.voice.fishaudio.voices.fish_request`). A refusal
is read by its facts, never its body, which may quote the title, the
instruction or the words of a recording.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO, Final

import httpx

from src.core.constants import (
    DEFAULT_FISHAUDIO_BASE_URL,
    FISHAUDIO_DESIGN_MODEL,
    FISHAUDIO_LIBRARY_WRITE_TIMEOUT_SECONDS,
    FISHAUDIO_VOICES_MAX_PAGES,
    FISHAUDIO_VOICES_PAGE_SIZE,
)
from src.domains.voice.fishaudio.voices import FishVoicesError, fish_request
from src.domains.voice.fishaudio.wire import auth_headers

#: The vendor's model states (``created`` → ``trained``, or ``failed``).
STATE_TRAINED: Final[str] = "trained"


@dataclass(frozen=True, slots=True)
class LibraryVoice:
    """One voice the account owns, as the library shows it.

    Attributes:
        voice_id: The vendor's model id (32 hexadecimal digits).
        title: Its name.
        state: The vendor's state (``created``, ``training``, ``trained``, ``failed``).
        languages: The languages the vendor detected.
        created_at: When it was created, as the vendor wrote it (ISO 8601).
    """

    voice_id: str
    title: str
    state: str
    languages: tuple[str, ...]
    created_at: str | None


@dataclass(frozen=True, slots=True)
class VoiceSample:
    """One recording a clone is made from.

    Attributes:
        filename: Its name (the vendor reads the container from it).
        content: Its bytes, or a file positioned at its start.
        mime_type: Its media type.
    """

    filename: str
    content: bytes | BinaryIO
    mime_type: str


@dataclass(frozen=True, slots=True)
class DesignCandidate:
    """One voice the vendor designed from a description.

    Attributes:
        audio: Its preview, a WAV file.
        duration_ms: How long the preview lasts.
        text: What the preview says, when the vendor said.
        language: The preview's language, when the vendor said.
    """

    audio: bytes
    duration_ms: int
    text: str | None
    language: str | None


def library_voice(entity: Mapping[str, Any]) -> LibraryVoice | None:
    """The voice a model of the account is, or ``None`` when it is not a speech voice.

    Args:
        entity: One ``ModelEntity`` of the vendor's API.

    Returns:
        The voice, whatever its state — the library shows a failed one too, so it
        can be deleted.
    """
    voice_id = entity.get("_id")
    if not isinstance(voice_id, str) or entity.get("type") != "tts":
        return None
    title = entity.get("title")
    languages = entity.get("languages")
    created_at = entity.get("created_at")
    return LibraryVoice(
        voice_id=voice_id,
        title=title if isinstance(title, str) and title.strip() else voice_id,
        state=str(entity.get("state") or ""),
        languages=tuple(str(lang) for lang in languages) if isinstance(languages, list) else (),
        created_at=created_at if isinstance(created_at, str) else None,
    )


def _client(
    api_key: str, base_url: str, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=FISHAUDIO_LIBRARY_WRITE_TIMEOUT_SECONDS,
        transport=transport,
        headers=auth_headers(api_key),
    )


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise FishVoicesError("Fish Audio library answer is not JSON") from exc


async def list_own_voices(
    api_key: str,
    *,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[LibraryVoice]:
    """Every voice the account owns, newest first as the vendor orders them.

    Raises:
        FishVoicesError: When the vendor cannot be read.
    """
    voices: list[LibraryVoice] = []
    async with _client(api_key, base_url, transport) as client:
        for page in range(1, FISHAUDIO_VOICES_MAX_PAGES + 1):
            response = await fish_request(
                client,
                api_key,
                "GET",
                "/model",
                params={"self": True, "page_size": FISHAUDIO_VOICES_PAGE_SIZE, "page_number": page},
            )
            payload = _json(response)
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or not isinstance(items, list):
                raise FishVoicesError("Fish Audio library answer carries no items")
            voices.extend(
                voice
                for item in items
                if isinstance(item, dict) and (voice := library_voice(item)) is not None
            )
            if len(items) < FISHAUDIO_VOICES_PAGE_SIZE or not payload.get("has_more", True):
                break
    return voices


async def create_voice(
    api_key: str,
    *,
    title: str,
    samples: Sequence[VoiceSample],
    texts: Sequence[str] = (),
    enhance_audio_quality: bool = True,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LibraryVoice:
    """Create a private voice from recordings.

    Args:
        api_key: The account's key.
        title: Its name.
        samples: The recordings, at least one.
        texts: What each recording says, in order — all of them or none (the
            vendor transcribes them itself when none is given).
        enhance_audio_quality: Let the vendor clean the recordings first.
        base_url: The vendor's API root.
        transport: A test transport.

    Returns:
        The voice the vendor created.

    Raises:
        ValueError: No recording, or texts that do not match them one for one.
        FishVoicesError: When the vendor refuses or cannot be reached.
    """
    if not samples:
        raise ValueError("a voice is created from at least one recording")
    if texts and len(texts) != len(samples):
        raise ValueError("one text per recording, or none")
    data: dict[str, str | list[str]] = {
        "type": "tts",
        "train_mode": "fast",
        "visibility": "private",
        "title": title,
        "enhance_audio_quality": "true" if enhance_audio_quality else "false",
    }
    if texts:
        data["texts"] = list(texts)
    files = [("voices", (s.filename, s.content, s.mime_type)) for s in samples]
    async with _client(api_key, base_url, transport) as client:
        response = await fish_request(
            client,
            api_key,
            "POST",
            "/model",
            bound_s=FISHAUDIO_LIBRARY_WRITE_TIMEOUT_SECONDS,
            data=data,
            files=files,
        )
    voice = library_voice(entity) if isinstance(entity := _json(response), dict) else None
    if voice is None:
        raise FishVoicesError("Fish Audio created no speech voice")
    return voice


async def rename_voice(
    api_key: str,
    voice_id: str,
    title: str,
    *,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Give one of the account's voices a new name.

    Raises:
        FishVoicesError: When the vendor refuses (``not_found`` included).
    """
    async with _client(api_key, base_url, transport) as client:
        await fish_request(client, api_key, "PATCH", f"/model/{voice_id}", json={"title": title})


async def delete_voice(
    api_key: str,
    voice_id: str,
    *,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Delete one of the account's voices.

    Raises:
        FishVoicesError: When the vendor refuses (``not_found`` included).
    """
    async with _client(api_key, base_url, transport) as client:
        await fish_request(client, api_key, "DELETE", f"/model/{voice_id}")


def _candidate(item: object) -> tuple[int, DesignCandidate] | None:
    if not isinstance(item, dict) or not isinstance(item.get("audio_base64"), str):
        return None
    try:
        audio = base64.b64decode(item["audio_base64"], validate=True)
    except binascii.Error, ValueError:
        return None
    index, duration = item.get("index"), item.get("duration_ms")
    text, language = item.get("text"), item.get("language")
    return (
        index if isinstance(index, int) else 0,
        DesignCandidate(
            audio=audio,
            duration_ms=duration if isinstance(duration, int) and duration >= 0 else 0,
            text=text if isinstance(text, str) and text.strip() else None,
            language=language if isinstance(language, str) and language else None,
        ),
    )


async def design_voices(
    api_key: str,
    *,
    instruction: str,
    count: int,
    preview_text: str | None = None,
    language: str | None = None,
    base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[DesignCandidate]:
    """Voices the vendor designs from a description, in the order it answered them.

    Args:
        api_key: The account's key.
        instruction: The description (the caller bounds it).
        count: How many candidates (1 to 4).
        preview_text: What each candidate reads, when given.
        language: A language hint, when given.
        base_url: The vendor's API root.
        transport: A test transport.

    Returns:
        The candidates, at least one — the request the vendor billed.

    Raises:
        FishVoicesError: When the vendor refuses, cannot be reached, or answers
            no usable candidate (an empty answer is not billed).
    """
    body: dict[str, object] = {"instruction": instruction, "n": count}
    if preview_text:
        body["reference_text"] = preview_text
    if language:
        body["language"] = language
    async with _client(api_key, base_url, transport) as client:
        response = await fish_request(
            client,
            api_key,
            "POST",
            "/v1/voice-design",
            bound_s=FISHAUDIO_LIBRARY_WRITE_TIMEOUT_SECONDS,
            json=body,
            headers={"model": FISHAUDIO_DESIGN_MODEL},
        )
    payload = _json(response)
    items = payload.get("candidates") if isinstance(payload, dict) else None
    ranked = [c for item in items if (c := _candidate(item))] if isinstance(items, list) else []
    if not ranked:
        raise FishVoicesError("Fish Audio designed no usable voice")
    return [candidate for _, candidate in sorted(ranked, key=lambda pair: pair[0])]


__all__ = [
    "STATE_TRAINED",
    "DesignCandidate",
    "LibraryVoice",
    "VoiceSample",
    "create_voice",
    "delete_voice",
    "design_voices",
    "library_voice",
    "list_own_voices",
    "rename_voice",
]
