"""The instance's Fish Audio voice library, as an administrator drives it (ADR-345).

The vendor, the audit log, the ledger, the candidate store and the pins are
replaced by recorders: what is asserted is what each act OWES — the attestation
filed before a clone or a pin, the ceiling asked before a design and the price
charged after it, a voice in use never deleted nor unpinned, a refusal named by
its code.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.constants import (
    FISHAUDIO_CLONE_SAMPLE_MAX_BYTES,
    FISHAUDIO_CLONE_SAMPLES_MAX,
    FISHAUDIO_CLONE_TOTAL_MAX_BYTES,
    FISHAUDIO_DESIGN_CANDIDATES_MAX,
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
)
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.voice import library_router
from src.domains.voice.fishaudio import library_service
from src.domains.voice.fishaudio.design_store import CandidateClaim, StoredCandidate
from src.domains.voice.fishaudio.library import DesignCandidate, LibraryVoice, VoiceSample
from src.domains.voice.fishaudio.pins import PinsFull
from src.domains.voice.fishaudio.voices import FishVoicesError
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit

VOICE = "a" * 32
PUBLIC = "c" * 32
BASE = "/admin/voice/fishaudio/library"


def voice(voice_id: str = VOICE, state: str = "trained") -> LibraryVoice:
    return LibraryVoice(voice_id, "Narrator", state, ("fr",), "2026-10-14T08:00:00Z")


@dataclass
class World:
    """What the acts did, in the order they did it."""

    events: list[tuple[str, Any]] = field(default_factory=list)
    slots: dict[str, list[str]] = field(default_factory=dict)
    paused: Any = None
    vendor_error: FishVoicesError | None = None
    audit_fails: bool = False
    stored: dict[str, DesignCandidate] = field(default_factory=dict)
    pins: list[str] = field(default_factory=list)
    #: What the vendor answers for a public voice: ``None`` when it cannot speak.
    public: VoiceOption | None = field(
        default_factory=lambda: VoiceOption(PUBLIC, "Narrator", "male", "en", {"source": "pinned"})
    )
    #: Another administrator fills the list between the read and the write.
    filled_meanwhile: bool = False

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    state = World()
    monkeypatch.setattr(library_service, "fish_api_key", lambda: "fish-key")
    monkeypatch.setattr(settings, "fishaudio_voice_creation_enabled", True)
    monkeypatch.setattr(settings, "fishaudio_voice_design_cost_usd", 0.01)
    monkeypatch.setattr(settings, "voice_stt_enabled", True)
    # This HTTP-unit world replaces SQL ports; current-role races use PostgreSQL.
    monkeypatch.setattr(library_service, "_authorize", AsyncMock())

    def vendor(name: str, result: Any = None) -> Any:
        async def call(*args: Any, **kwargs: Any) -> Any:
            if state.vendor_error is not None:
                raise state.vendor_error
            state.events.append((name, (args, kwargs)))
            return result

        return call

    monkeypatch.setattr(library_service, "create_voice", vendor("create", voice()))
    monkeypatch.setattr(library_service, "rename_voice", vendor("rename"))
    monkeypatch.setattr(library_service, "delete_voice", vendor("delete"))
    monkeypatch.setattr(library_service, "list_own_voices", vendor("list", [voice()]))
    monkeypatch.setattr(
        library_service,
        "design_voices",
        vendor("design", [DesignCandidate(b"RIFF-one", 3100, "Hello.", "en")]),
    )

    async def audit(
        actor: Any,
        action: str,
        details: dict[str, Any],
        *,
        authorize: bool = False,
        api_key: str | None = None,
    ) -> None:
        if state.audit_fails:
            raise RuntimeError("database down")
        state.events.append((f"audit:{action}", details))

    async def invalidate(api_key: str) -> None:
        state.events.append(("invalidate", api_key))

    async def spend(*, surface: str, cost_usd: Decimal) -> None:
        state.events.append(("spend", cost_usd))

    async def slots() -> dict[str, list[str]]:
        return state.slots

    async def budget_block() -> Any:
        return state.paused

    async def keep(
        candidates: list[DesignCandidate], *, credential_fingerprint: str
    ) -> list[StoredCandidate]:
        kept = [StoredCandidate(f"{i:032x}", c) for i, c in enumerate(candidates)]
        state.stored.update({item.candidate_id: item.candidate for item in kept})
        return kept

    async def claim(candidate_id: str) -> CandidateClaim | None:
        candidate = state.stored.get(candidate_id)
        return (
            CandidateClaim(
                candidate_id, "test-token", candidate, credential_fingerprint("fish-key")
            )
            if candidate
            else None
        )

    async def forget(claim: CandidateClaim) -> None:
        state.events.append(("forget", claim.candidate_id))
        state.stored.pop(claim.candidate_id, None)

    async def fetch(api_key: str, voice_id: str) -> VoiceOption | None:
        if state.vendor_error is not None:
            raise state.vendor_error
        state.events.append(("fetch", voice_id))
        return state.public

    async def read_pins() -> tuple[str, ...]:
        return tuple(state.pins)

    async def add_pin(
        voice_id: str, pinned_by: Any, *, credential_fingerprint: str
    ) -> tuple[tuple[str, ...], bool]:
        if voice_id in state.pins:
            return tuple(state.pins), False
        if state.filled_meanwhile or len(state.pins) >= settings.fishaudio_pinned_voices_max:
            raise PinsFull(len(state.pins))
        state.pins.append(voice_id)
        state.events.append(("store:pin", voice_id))
        return tuple(state.pins), True

    async def forget_choices(voice_id: str) -> int:
        state.events.append(("forget_choices", voice_id))
        return 2

    async def remove_pin(voice_id: str, admin_id: Any) -> tuple[tuple[str, ...], bool]:
        if slots := state.slots.get(voice_id):
            library_service.refuse(409, "fishaudio_voice_in_use", slots=slots)
        if voice_id not in state.pins:
            return tuple(state.pins), False
        state.pins.remove(voice_id)
        state.events.append(("store:unpin", voice_id))
        return tuple(state.pins), True

    monkeypatch.setattr(library_service, "_audit", audit)
    monkeypatch.setattr(library_service, "invalidate_fish_voices", invalidate)
    monkeypatch.setattr(library_service, "record_instance_fixed_spend", spend)
    monkeypatch.setattr(library_service, "slots_by_voice", slots)
    monkeypatch.setattr(
        library_service.UsageLimitService, "instance_budget_block", staticmethod(budget_block)
    )
    monkeypatch.setattr(library_service, "keep_candidates", keep)
    monkeypatch.setattr(library_service, "claim_candidate", claim)
    monkeypatch.setattr(library_service, "release_candidate", AsyncMock())
    monkeypatch.setattr(library_service, "forget_candidate", forget)
    monkeypatch.setattr(library_service, "fetch_fish_voice", fetch)
    monkeypatch.setattr(library_service, "read_pins", read_pins)
    monkeypatch.setattr(library_service, "add_pin", add_pin)
    monkeypatch.setattr(library_service, "remove_pin", remove_pin)
    monkeypatch.setattr(library_service, "forget_voice", forget_choices)

    async def begin_delete(
        actor: library_service.Actor, voice_id: str, api_key: str
    ) -> tuple[str, bool]:
        if slots := state.slots.get(voice_id):
            library_service.refuse(409, "fishaudio_voice_in_use", slots=slots)
        return "test-token", True

    monkeypatch.setattr(library_service, "_begin_delete", begin_delete)
    monkeypatch.setattr(library_service, "_clear_delete", AsyncMock())
    return state


def make_client(*, superuser: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(library_router.router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=uuid4(), is_superuser=superuser
    )
    app.dependency_overrides[library_router.rate_limit_library] = lambda: None
    return TestClient(app)


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    with make_client() as test_client:
        yield test_client


def code(response: Any) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def pin(client: TestClient, voice_id: str = PUBLIC, *, attested: bool = True) -> Any:
    return client.put(f"{BASE}/pins/{voice_id}", json={"attested": attested})


def wav(size: int = 4) -> bytes:
    return b"R" * size


def clone(client: TestClient, *, files: list[tuple[str, bytes]] | None = None, **form: Any) -> Any:
    data: dict[str, Any] = {"title": "My voice", "consent": "true", **form}
    uploads = [
        ("samples", (name, body, "audio/wav")) for name, body in (files or [("a.wav", wav())])
    ]
    return client.post(f"{BASE}/clone", data=data, files=uploads)


class TestOnlyAnAdministrator:
    def test_anyone_else_is_refused_before_anything_happens(self, world: World) -> None:
        world.pins = [PUBLIC]
        with make_client(superuser=False) as test_client:
            assert test_client.get(BASE).status_code == 403
            assert clone(test_client).status_code == 403
            assert test_client.get(f"{BASE}/pins").status_code == 403
            assert pin(test_client, VOICE).status_code == 403
            assert test_client.delete(f"{BASE}/pins/{PUBLIC}").status_code == 403
        assert world.events == []
        assert world.pins == [PUBLIC]


class TestTheLibrary:
    def test_each_voice_says_which_slots_speak_with_it_and_every_bound_is_published(
        self, client: TestClient, world: World
    ) -> None:
        world.slots = {VOICE: ["radio_voice", "voice_tts"]}

        body = client.get(BASE).json()

        assert body["configured"] and body["creation_enabled"] and body["prefill_available"]
        assert body["voices"][0]["used_by_slots"] == ["radio_voice", "voice_tts"]
        assert body["bounds"]["samples_max"] == FISHAUDIO_CLONE_SAMPLES_MAX
        assert body["bounds"]["total_max_bytes"] == FISHAUDIO_CLONE_TOTAL_MAX_BYTES
        assert body["bounds"]["candidates_max"] == FISHAUDIO_DESIGN_CANDIDATES_MAX
        assert body["design_cost_usd"] == 0.01

    def test_without_a_key_the_library_is_empty_and_says_so(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(library_service, "fish_api_key", lambda: None)

        body = client.get(BASE).json()

        assert (body["configured"], body["voices"]) == (False, [])
        assert world.names() == []


class TestTheClone:
    def test_the_attestation_is_filed_before_the_vendor_creates_the_voice(
        self, client: TestClient, world: World
    ) -> None:
        response = clone(
            client,
            files=[("Jane Doe interview.wav", wav()), ("b.mp3", wav())],
            texts=["First clip.", "Second  clip."],
            enhance_audio_quality="false",
        )

        assert response.status_code == 201 and response.json()["voice_id"] == VOICE
        assert world.names() == [
            "audit:fishaudio_voice_clone_attested",
            "create",
            "invalidate",
            "audit:fishaudio_voice_created",
        ]
        attestation = world.events[0][1]
        assert attestation["consent_attested"] is True and attestation["samples"] == 2
        _, kwargs = world.events[1][1]
        samples: list[VoiceSample] = kwargs["samples"]
        # The administrator's file names never leave: a name may be a person's.
        assert [s.filename for s in samples] == ["sample-1.wav", "sample-2.mp3"]
        assert kwargs["texts"] == ["First clip.", "Second clip."]
        assert kwargs["enhance_audio_quality"] is False

    def test_without_the_attestation_nothing_happens(
        self, client: TestClient, world: World
    ) -> None:
        response = clone(client, consent="false")

        assert (response.status_code, code(response)) == (422, "fishaudio_clone_consent_required")
        assert world.events == []

    def test_an_attestation_that_cannot_be_filed_stops_the_clone(
        self, client: TestClient, world: World
    ) -> None:
        world.audit_fails = True

        response = clone(client)

        assert (response.status_code, code(response)) == (503, "fishaudio_audit_unavailable")
        assert "create" not in world.names()

    def test_the_operator_can_switch_creation_off(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "fishaudio_voice_creation_enabled", False)

        # Even a recording the routes would refuse meets the switch first.
        response = clone(client, files=[("a.ogg", wav())])

        assert (response.status_code, code(response)) == (403, "fishaudio_voice_creation_disabled")
        assert world.events == []

    @pytest.mark.parametrize(
        ("files", "form", "status", "refusal"),
        [
            ([("a.ogg", wav())], {}, 415, "fishaudio_clone_sample_format"),
            (
                [("a.wav", wav(FISHAUDIO_CLONE_SAMPLE_MAX_BYTES + 1))],
                {},
                413,
                "fishaudio_clone_sample_too_large",
            ),
            (
                [("a.wav", wav(FISHAUDIO_CLONE_SAMPLE_MAX_BYTES))] * 3,
                {},
                413,
                "fishaudio_clone_sample_too_large",
            ),
            (
                [(f"{i}.wav", wav()) for i in range(FISHAUDIO_CLONE_SAMPLES_MAX + 1)],
                {},
                422,
                "fishaudio_clone_samples_count",
            ),
            (
                [("a.wav", wav()), ("b.wav", wav())],
                {"texts": ["only one", " "]},
                422,
                "fishaudio_clone_texts_mismatch",
            ),
            ([("a.wav", wav())], {"title": "   "}, 422, "fishaudio_voice_title_invalid"),
        ],
    )
    def test_what_the_routes_do_not_accept_never_reaches_the_vendor(
        self,
        client: TestClient,
        world: World,
        files: list[tuple[str, bytes]],
        form: dict[str, Any],
        status: int,
        refusal: str,
    ) -> None:
        response = clone(client, files=files, **form)

        assert (response.status_code, code(response)) == (status, refusal)
        assert world.events == []

    def test_blank_transcripts_let_the_vendor_transcribe(
        self, client: TestClient, world: World
    ) -> None:
        clone(client, texts=["  "])

        _, kwargs = world.events[1][1]
        assert kwargs["texts"] == []

    def test_a_vendor_refusal_is_named_by_its_code(self, client: TestClient, world: World) -> None:
        world.vendor_error = FishVoicesError("refused", kind="payment_required")

        response = clone(client)

        assert (response.status_code, code(response)) == (402, "fishaudio_payment_required")
        assert "invalidate" not in world.names()


class TestTheDesign:
    def design(self, client: TestClient, **body: Any) -> Any:
        return client.post(f"{BASE}/designs", json={"instruction": "A warm narrator", **body})

    def test_the_instance_pays_after_the_vendor_answered(
        self, client: TestClient, world: World
    ) -> None:
        response = self.design(client, count=1, preview_text="Hello.", language="en")

        assert response.status_code == 200
        body = response.json()
        assert base64.b64decode(body["candidates"][0]["audio_base64"]) == b"RIFF-one"
        assert body["cost_usd"] == 0.01
        assert world.names() == ["design", "spend", "audit:fishaudio_voice_designed"]
        assert world.events[1][1] == Decimal("0.01")

    def test_a_paused_instance_spends_nothing(self, client: TestClient, world: World) -> None:
        world.paused = SimpleNamespace(
            exceeded_limit="instance_daily_budget",
            blocked_reason=None,
            status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
        )

        response = self.design(client)

        assert response.status_code == 429
        assert INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE in response.text
        assert world.events == []

    def test_a_failed_design_is_never_charged(self, client: TestClient, world: World) -> None:
        world.vendor_error = FishVoicesError("busy", kind="unavailable")

        response = self.design(client)

        assert (response.status_code, code(response)) == (502, "fishaudio_unavailable")
        assert "spend" not in world.names()

    @pytest.mark.parametrize(
        "body", [{"instruction": "   "}, {"count": FISHAUDIO_DESIGN_CANDIDATES_MAX + 1}]
    )
    def test_a_request_out_of_bounds_is_refused_unpaid(
        self, client: TestClient, world: World, body: dict[str, Any]
    ) -> None:
        assert self.design(client, **body).status_code == 422
        assert world.events == []

    def test_a_saved_candidate_becomes_a_voice_and_leaves_the_store(
        self, client: TestClient, world: World
    ) -> None:
        candidate_id = self.design(client).json()["candidates"][0]["candidate_id"]
        world.events.clear()

        response = client.post(f"{BASE}/designs/{candidate_id}/save", json={"title": "Warm"})

        assert response.status_code == 201
        _, kwargs = world.events[0][1]
        assert [s.content for s in kwargs["samples"]] == [b"RIFF-one"]
        assert kwargs["texts"] == ["Hello."]
        assert world.names() == ["create", "forget", "invalidate", "audit:fishaudio_voice_created"]

    def test_an_expired_candidate_is_gone(self, client: TestClient, world: World) -> None:
        response = client.post(f"{BASE}/designs/{'f' * 32}/save", json={"title": "Warm"})

        assert (response.status_code, code(response)) == (410, "fishaudio_design_candidate_expired")
        assert world.events == []


class TestRenameAndDelete:
    def test_a_voice_a_slot_speaks_with_is_never_deleted(
        self, client: TestClient, world: World
    ) -> None:
        world.slots = {VOICE: ["voice_tts"]}

        response = client.delete(f"{BASE}/{VOICE}")

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "fishaudio_voice_in_use",
            "slots": ["voice_tts"],
        }
        assert world.events == []

    def test_a_free_voice_is_deleted_and_forgotten(self, client: TestClient, world: World) -> None:
        assert client.delete(f"{BASE}/{VOICE}").status_code == 204
        # The people who had chosen it for LIA get the instance's voice back.
        assert world.names() == [
            "delete",
            "invalidate",
            "forget_choices",
            "audit:fishaudio_voice_deleted",
        ]
        assert world.events[-1][1] == {"voice_id": VOICE, "accounts_given_back": 2}

    def test_a_rename_reaches_the_vendor_and_the_pickers(
        self, client: TestClient, world: World
    ) -> None:
        assert client.patch(f"{BASE}/{VOICE}", json={"title": " New  name "}).status_code == 204
        args, _ = world.events[0][1]
        assert args[1:] == (VOICE, "New name")
        assert world.names() == ["rename", "invalidate", "audit:fishaudio_voice_renamed"]

    @pytest.mark.parametrize("voice_id", ["%2E%2E", "A" * 32, "a" * 31, "a" * 31 + "!"])
    def test_an_id_that_names_no_voice_never_reaches_a_url(
        self, client: TestClient, world: World, voice_id: str
    ) -> None:
        response = client.delete(f"{BASE}/{voice_id}")

        assert (response.status_code, code(response)) == (404, "fishaudio_voice_not_found")
        assert world.events == []


class TestThePins:
    """One list of public voices for every voice slot, each pinned under an attestation."""

    def test_the_list_and_its_ceiling_are_published(self, client: TestClient, world: World) -> None:
        world.pins = [VOICE, PUBLIC]

        assert client.get(f"{BASE}/pins").json() == {
            "voice_ids": [VOICE, PUBLIC],
            "max_pins": settings.fishaudio_pinned_voices_max,
        }

    def test_the_voice_is_read_and_the_attestation_filed_before_it_is_pinned(
        self, client: TestClient, world: World
    ) -> None:
        response = pin(client)

        assert response.status_code == 200
        assert response.json()["voice_ids"] == [PUBLIC]
        # A list is cached per set of pins: nothing needs forgetting.
        assert world.names() == [
            "fetch",
            "audit:fishaudio_voice_pin_attested",
            "store:pin",
            "audit:fishaudio_voice_pinned",
        ]
        assert world.events[1][1] == {
            "rights_attested": True,
            "voice_id": PUBLIC,
            "label": "Narrator",
            "language": "en",
        }

    def test_without_the_attestation_nothing_happens(
        self, client: TestClient, world: World
    ) -> None:
        response = pin(client, attested=False)

        assert (response.status_code, code(response)) == (422, "fishaudio_pin_consent_required")
        assert (world.events, world.pins) == ([], [])

    def test_a_voice_already_pinned_files_nothing(self, client: TestClient, world: World) -> None:
        world.pins = [PUBLIC]

        response = pin(client)

        assert (response.status_code, response.json()["voice_ids"]) == (200, [PUBLIC])
        assert world.events == []

    def test_a_full_list_is_refused_before_the_vendor_is_asked(
        self, client: TestClient, world: World
    ) -> None:
        world.pins = [f"{index:032x}" for index in range(settings.fishaudio_pinned_voices_max)]

        response = pin(client)

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "fishaudio_pins_full",
            "max_pins": settings.fishaudio_pinned_voices_max,
        }
        assert world.events == []

    def test_the_ceiling_is_the_setting_read_at_the_act(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An operator's .env value takes effect on the next request, never frozen at import.
        lowered = 2
        monkeypatch.setattr(settings, "fishaudio_pinned_voices_max", lowered)
        world.pins = [f"{index:032x}" for index in range(lowered)]

        assert client.get(f"{BASE}/pins").json()["max_pins"] == lowered
        response = pin(client)

        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "fishaudio_pins_full", "max_pins": lowered}
        assert world.events == []

    def test_a_list_filled_meanwhile_refuses_the_pin_it_attested(
        self, client: TestClient, world: World
    ) -> None:
        world.filled_meanwhile = True

        response = pin(client)

        assert (response.status_code, code(response)) == (409, "fishaudio_pins_full")
        # The attestation is on record; the pin is not, nor is any act « pinned ».
        assert world.names() == ["fetch", "audit:fishaudio_voice_pin_attested"]

    def test_a_voice_the_vendor_does_not_serve_is_never_pinned(
        self, client: TestClient, world: World
    ) -> None:
        world.public = None

        response = pin(client)

        assert (response.status_code, code(response)) == (422, "fishaudio_pin_unavailable")
        assert (world.names(), world.pins) == (["fetch"], [])

    def test_an_attestation_that_cannot_be_filed_stops_the_pin(
        self, client: TestClient, world: World
    ) -> None:
        world.audit_fails = True

        response = pin(client)

        assert (response.status_code, code(response)) == (503, "fishaudio_pin_audit_unavailable")
        assert (world.names(), world.pins) == (["fetch"], [])

    def test_a_vendor_refusal_is_named_by_its_code(self, client: TestClient, world: World) -> None:
        world.vendor_error = FishVoicesError("busy", kind="rate_limited")

        response = pin(client)

        assert (response.status_code, code(response)) == (429, "fishaudio_rate_limited")
        assert world.pins == []

    def test_without_a_key_nothing_is_pinned(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(library_service, "fish_api_key", lambda: None)

        response = pin(client)

        assert (response.status_code, code(response)) == (409, "fishaudio_api_key_missing")
        assert (world.events, world.pins) == ([], [])

    @pytest.mark.parametrize("voice_id", ["%2E%2E", "A" * 32, "a" * 31, "a" * 31 + "!"])
    def test_an_id_that_names_no_voice_never_reaches_the_vendor(
        self, client: TestClient, world: World, voice_id: str
    ) -> None:
        pinned = pin(client, voice_id)
        unpinned = client.delete(f"{BASE}/pins/{voice_id}")

        assert (pinned.status_code, code(pinned)) == (404, "fishaudio_voice_not_found")
        assert (unpinned.status_code, code(unpinned)) == (404, "fishaudio_voice_not_found")
        assert world.events == []

    def test_a_voice_a_slot_speaks_with_is_never_unpinned(
        self, client: TestClient, world: World
    ) -> None:
        world.pins = [PUBLIC]
        world.slots = {PUBLIC: ["radio_voice"]}

        response = client.delete(f"{BASE}/pins/{PUBLIC}")

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "fishaudio_voice_in_use",
            "slots": ["radio_voice"],
        }
        assert (world.events, world.pins) == ([], [PUBLIC])

    def test_a_free_voice_is_unpinned_and_the_act_filed(
        self, client: TestClient, world: World
    ) -> None:
        world.pins = [VOICE, PUBLIC]

        response = client.delete(f"{BASE}/pins/{PUBLIC}")

        assert (response.status_code, response.json()["voice_ids"]) == (200, [VOICE])
        assert world.names() == ["store:unpin", "audit:fishaudio_voice_unpinned"]

    def test_unpinning_a_voice_that_is_not_pinned_files_nothing(
        self, client: TestClient, world: World
    ) -> None:
        response = client.delete(f"{BASE}/pins/{PUBLIC}")

        assert (response.status_code, response.json()["voice_ids"]) == (200, [])
        assert world.events == []


class TestTheTranscript:
    def test_the_local_engine_hears_the_recording(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        heard: list[Any] = []

        async def transcode(audio: bytes, **kwargs: Any) -> bytes:
            heard.append(audio)
            return b"\x00\x00" * 16000

        class _Engine:
            async def transcribe_unbounded_pcm_async(
                self, pcm: bytes, *, language: str | None
            ) -> str:
                heard.append(language)
                return "  Bonjour,   je suis là. "

        monkeypatch.setattr(library_service, "transcode", transcode)
        monkeypatch.setattr(library_service, "get_stt_service", lambda: _Engine())

        response = client.post(
            f"{BASE}/transcript",
            data={"language": "fr"},
            files={"sample": ("a.wav", b"RIFF-sample", "audio/wav")},
        )

        assert response.json() == {"text": "Bonjour, je suis là."}
        assert heard == [b"RIFF-sample", "fr"]

    def test_an_instance_without_the_local_engine_says_so(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "voice_stt_enabled", False)

        response = client.post(
            f"{BASE}/transcript", files={"sample": ("a.wav", b"RIFF", "audio/wav")}
        )

        assert (response.status_code, code(response)) == (409, "fishaudio_prefill_unavailable")

    def test_a_recording_longer_than_the_prefill_hears_is_refused(
        self, client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def transcode(audio: bytes, **kwargs: Any) -> bytes:
            return b"\x00\x00" * 16000 * 121

        monkeypatch.setattr(library_service, "transcode", transcode)

        response = client.post(
            f"{BASE}/transcript", files={"sample": ("a.wav", b"RIFF", "audio/wav")}
        )

        assert (response.status_code, code(response)) == (422, "fishaudio_prefill_too_long")
