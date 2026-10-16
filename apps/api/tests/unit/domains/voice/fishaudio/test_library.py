"""The account's own Fish Audio voices: listed, created, renamed, deleted, designed (ADR-345).

Every shape is the vendor's documentation (read 2026-10-14); no paid request
was run (owner decision). No test here reaches the network.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from src.domains.voice.fishaudio import voices as voices_module
from src.domains.voice.fishaudio.library import (
    VoiceSample,
    create_voice,
    delete_voice,
    design_voices,
    library_voice,
    list_own_voices,
    rename_voice,
)
from src.domains.voice.fishaudio.voices import FishVoicesError

pytestmark = pytest.mark.unit

Respond = Callable[[httpx.Request], httpx.Response]
VOICE = "a" * 32


@pytest.fixture(autouse=True)
def slots(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    taken: list[str] = []

    @asynccontextmanager
    async def recording(
        provider: str, api_key: str, *, timeout_seconds: float
    ) -> AsyncIterator[None]:
        taken.append(provider)
        yield

    monkeypatch.setattr(voices_module, "provider_slot", recording)
    return taken


def transport(respond: Respond, sent: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return respond(request)

    return httpx.MockTransport(handler)


def entity(voice_id: str = VOICE, **fields: Any) -> dict[str, Any]:
    return {
        "_id": voice_id,
        "type": "tts",
        "state": "trained",
        "title": "Narrator",
        "languages": ["fr"],
        "created_at": "2026-10-14T08:00:00Z",
        **fields,
    }


def multipart_fields(request: httpx.Request) -> list[tuple[str, str]]:
    """The text fields of a multipart request, repeated ones in order."""
    body = request.content.decode("latin-1")
    fields: list[tuple[str, str]] = []
    for part in body.split("--")[1:]:
        header, _, value = part.partition("\r\n\r\n")
        if 'name="' in header and "filename=" not in header:
            name = header.split('name="', 1)[1].split('"', 1)[0]
            fields.append((name, value.rstrip("\r\n-")))
    return fields


class TestTheList:
    async def test_every_state_is_shown_so_a_failed_voice_can_go(self, slots: list[str]) -> None:
        sent: list[httpx.Request] = []
        items = [entity(), entity("b" * 32, state="failed"), entity("c" * 32, type="svc")]
        voices = await list_own_voices(
            "key",
            transport=transport(
                lambda r: httpx.Response(200, json={"items": items, "has_more": False}), sent
            ),
        )

        assert [(v.voice_id, v.state) for v in voices] == [(VOICE, "trained"), ("b" * 32, "failed")]
        assert sent[0].url.params["self"] == "true"
        assert slots == ["fishaudio"]

    def test_an_untitled_voice_is_named_by_its_id(self) -> None:
        voice = library_voice(entity(title="  ", languages="fr", created_at=None))

        assert voice is not None
        assert (voice.title, voice.languages, voice.created_at) == (VOICE, (), None)


class TestTheClone:
    async def test_a_clone_is_private_fast_and_carries_its_texts_in_order(self) -> None:
        sent: list[httpx.Request] = []
        voice = await create_voice(
            "key",
            title="My voice",
            samples=[
                VoiceSample("a.wav", b"RIFF-a", "audio/wav"),
                VoiceSample("b.mp3", b"ID3-b", "audio/mpeg"),
            ],
            texts=["First clip.", "Second clip."],
            enhance_audio_quality=False,
            transport=transport(lambda r: httpx.Response(201, json=entity()), sent),
        )

        (request,) = sent
        assert (request.method, request.url.path) == ("POST", "/model")
        fields = multipart_fields(request)
        assert ("visibility", "private") in fields and ("train_mode", "fast") in fields
        assert ("type", "tts") in fields and ("title", "My voice") in fields
        assert ("enhance_audio_quality", "false") in fields
        assert [v for k, v in fields if k == "texts"] == ["First clip.", "Second clip."]
        assert request.content.count(b'name="voices"') == 2
        assert voice.voice_id == VOICE

    async def test_without_texts_the_vendor_transcribes(self) -> None:
        sent: list[httpx.Request] = []
        await create_voice(
            "key",
            title="My voice",
            samples=[VoiceSample("a.wav", b"RIFF", "audio/wav")],
            transport=transport(lambda r: httpx.Response(201, json=entity()), sent),
        )

        assert "texts" not in dict(multipart_fields(sent[0]))

    @pytest.mark.parametrize(
        ("samples", "texts"),
        [([], []), ([VoiceSample("a.wav", b"RIFF", "audio/wav")], ["one", "two"])],
    )
    async def test_recordings_and_texts_go_one_for_one(
        self, samples: list[VoiceSample], texts: list[str]
    ) -> None:
        sent: list[httpx.Request] = []

        with pytest.raises(ValueError):
            await create_voice(
                "key",
                title="x",
                samples=samples,
                texts=texts,
                transport=transport(lambda r: httpx.Response(201, json=entity()), sent),
            )

        assert sent == []

    async def test_an_answer_that_is_no_speech_voice_is_an_error(self) -> None:
        with pytest.raises(FishVoicesError):
            await create_voice(
                "key",
                title="x",
                samples=[VoiceSample("a.wav", b"RIFF", "audio/wav")],
                transport=transport(lambda r: httpx.Response(201, json={"_id": 1}), []),
            )


class TestRenameAndDelete:
    async def test_a_rename_patches_the_title_alone(self) -> None:
        sent: list[httpx.Request] = []
        await rename_voice(
            "key", VOICE, "New name", transport=transport(lambda r: httpx.Response(200), sent)
        )

        assert (sent[0].method, sent[0].url.path) == ("PATCH", f"/model/{VOICE}")
        assert json.loads(sent[0].content) == {"title": "New name"}

    async def test_a_voice_that_is_not_there_is_named_so(self) -> None:
        with pytest.raises(FishVoicesError) as caught:
            await delete_voice("key", VOICE, transport=transport(lambda r: httpx.Response(404), []))

        assert caught.value.kind == "not_found"


def candidate(index: int, audio: bytes = b"RIFF-wav", **fields: Any) -> dict[str, Any]:
    return {
        "id": f"vendor-{index}",
        "index": index,
        "audio_base64": base64.b64encode(audio).decode(),
        "sample_rate": 44100,
        "duration_ms": 3100,
        **fields,
    }


class TestTheDesign:
    async def test_a_design_names_its_model_and_answers_its_candidates_in_order(self) -> None:
        sent: list[httpx.Request] = []
        answer = {"candidates": [candidate(1, b"second"), candidate(0, b"first", text="Hello.")]}
        candidates = await design_voices(
            "key",
            instruction="A warm narrator",
            count=2,
            preview_text="Hello.",
            language="en",
            transport=transport(lambda r: httpx.Response(200, json=answer), sent),
        )

        (request,) = sent
        assert request.url.path == "/v1/voice-design"
        assert request.headers["model"] == "voice-design-1"
        assert json.loads(request.content) == {
            "instruction": "A warm narrator",
            "n": 2,
            "reference_text": "Hello.",
            "language": "en",
        }
        assert [c.audio for c in candidates] == [b"first", b"second"]
        assert candidates[0].text == "Hello." and candidates[1].text is None

    async def test_an_optional_field_is_never_sent_empty(self) -> None:
        sent: list[httpx.Request] = []
        await design_voices(
            "key",
            instruction="A warm narrator",
            count=1,
            transport=transport(
                lambda r: httpx.Response(200, json={"candidates": [candidate(0)]}), sent
            ),
        )

        assert json.loads(sent[0].content) == {"instruction": "A warm narrator", "n": 1}

    @pytest.mark.parametrize(
        "answer",
        [{"candidates": []}, {"candidates": [{"index": 0, "audio_base64": "%%%"}]}, {}],
    )
    async def test_no_usable_candidate_is_no_success(self, answer: dict[str, Any]) -> None:
        with pytest.raises(FishVoicesError):
            await design_voices(
                "key",
                instruction="x",
                count=1,
                transport=transport(lambda r: httpx.Response(200, json=answer), []),
            )


class TestTheRefusals:
    @pytest.mark.parametrize(
        ("status", "kind"),
        [
            (429, "rate_limited"),
            (402, "payment_required"),
            (401, "unauthorized"),
            (422, "rejected"),
            (503, "unavailable"),
        ],
    )
    async def test_a_refusal_is_typed_by_its_status_never_its_words(
        self, status: int, kind: str
    ) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"status": status, "message": "the « secret »"})

        with pytest.raises(FishVoicesError) as caught:
            await design_voices("key", instruction="x", count=1, transport=transport(respond, []))

        assert caught.value.kind == kind
        assert "secret" not in repr((str(caught.value), caught.value.details))
