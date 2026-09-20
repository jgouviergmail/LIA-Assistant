"""What GPT-Live's provider sends, mints, exchanges and probes — without the network (wave 2 A9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.core.constants import OPENAI_LIVE_DEFAULT_MODEL, OPENAI_LIVE_SAMPLE_RATE
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import PROVIDERS, OfferExchanging, provider_by_id
from src.domains.live.providers.openai_live import OPENAI_LIVE_VOICES, OpenAiLiveProvider
from src.domains.live.providers.openai_live_socket import OpenAiLiveRefused
from src.domains.live.providers.protocol import LiveSetupInputs

pytestmark = pytest.mark.unit

MODULE = "src.domains.live.providers.openai_live"
NOW = datetime.now(UTC)


def _inputs(**overrides: object) -> LiveSetupInputs:
    base: dict[str, object] = {
        "model": OPENAI_LIVE_DEFAULT_MODEL,
        "voice": "quartz",
        "thinking_level": None,
        "system_instruction": "You are LIA's voice.",
        "tool_declaration": {"name": "send_to_lia"},
        "preferences": LivePreferences(),
        "trigger_tokens": 25_000,
        "target_tokens": 8_000,
    }
    base.update(overrides)
    return LiveSetupInputs(**base)  # type: ignore[arg-type]


def _mock_client(handler):  # type: ignore[no-untyped-def]
    """An httpx client on a MockTransport, in place of the listing module's seam."""
    return httpx.AsyncClient(
        base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
    )


def test_the_provider_is_registered_as_an_offer_connection_with_native_delegation() -> None:
    provider = provider_by_id("openai")
    assert isinstance(provider, OpenAiLiveProvider)
    assert PROVIDERS[provider.connector_type] is provider
    assert provider.connection == "offer"
    assert provider.delegation_wire == "native"
    assert isinstance(provider, OfferExchanging)
    # Gemini stays what it was: the browser opens the socket itself, the model calls a function.
    gemini = provider_by_id("gemini")
    assert gemini is not None and gemini.connection == "token" and gemini.delegation_wire == "tool"


def test_setup_is_the_documented_session_with_client_delegation_and_no_format() -> None:
    # Documented 2026-09-19: over WebRTC the audio format is negotiated in the
    # SDP (« omit audio.format »), and the delegation is the model's own act —
    # no function declaration travels.
    setup = OpenAiLiveProvider().build_setup(_inputs())
    assert setup == {
        "model": OPENAI_LIVE_DEFAULT_MODEL,
        "instructions": "You are LIA's voice.",
        "delegation": {"type": "client"},
        "audio": {"output": {"voice": "quartz"}},
    }


def test_capabilities_say_what_the_family_cannot_do() -> None:
    row = OpenAiLiveProvider().capabilities_of(OPENAI_LIVE_DEFAULT_MODEL)
    assert row.async_delegation is True
    assert row.delivery_scheduling is False
    assert row.reports_idle is False
    assert row.cancels_on_interruption is False
    assert row.configurable_vad is False
    assert row.resumes is False
    assert row.thinking is False
    assert OpenAiLiveProvider().thinking_levels_of(OPENAI_LIVE_DEFAULT_MODEL) == ()


async def test_voices_are_the_twelve_documented_ones_with_their_provenance() -> None:
    provider = OpenAiLiveProvider()
    listing = await provider.list_voices("")
    assert listing.provider == "openai"
    assert listing.provenance == "published"
    assert [v.name for v in listing.voices] == [name for name, _ in OPENAI_LIVE_VOICES]
    assert len(listing.voices) == 12
    assert provider.knows_voice("quartz") and not provider.knows_voice("marin")
    assert provider.sample_rate == OPENAI_LIVE_SAMPLE_RATE


async def test_listing_names_every_conversational_live_model_with_its_capabilities() -> None:
    with patch(f"{MODULE}.list_live_model_names", AsyncMock(return_value=["gpt-live-1"])):
        models = await OpenAiLiveProvider().list_models("sk-test")
    assert [m.name for m in models] == ["gpt-live-1"]
    assert models[0].provider == "openai"
    assert models[0].thinking_levels == []
    assert models[0].capabilities.configurable_vad is False


async def test_mint_is_lias_own_single_use_nonce_locked_to_the_deadlines() -> None:
    # No ephemeral token exists for GPT-Live (documented): the credential is a
    # nonce the browser hands back with its offer, and two mints never collide.
    provider = OpenAiLiveProvider()
    first = await provider.mint(
        "sk-test", _inputs(), expires_at=NOW + timedelta(minutes=10), connect_deadline_at=NOW
    )
    second = await provider.mint(
        "sk-test", _inputs(), expires_at=NOW + timedelta(minutes=10), connect_deadline_at=NOW
    )
    assert first.name != second.name and len(first.name) >= 32
    assert first.expires_at == NOW + timedelta(minutes=10)
    assert first.connect_deadline_at == NOW


async def test_exchange_offer_posts_the_session_and_the_sdp_on_the_persons_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "session": {"id": "live_1"},
                "transport": {"type": "webrtc", "sdp": "v=0 answer"},
            },
        )

    with patch(f"{MODULE}.http_client", lambda **_: _mock_client(handler)):
        answer = await OpenAiLiveProvider().exchange_offer(
            "sk-test", _inputs(), "v=0 offer", timeout=5
        )
    assert answer == "v=0 answer"
    assert seen["url"] == "https://api.openai.com/v1/live/sessions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {
        "session": OpenAiLiveProvider().build_setup(_inputs()),
        "transport": {"type": "webrtc", "sdp": "v=0 offer"},
    }


async def test_exchange_offer_reports_the_providers_own_refusal() -> None:
    def refused(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"error": {"code": "forbidden", "message": "Voice session access denied."}}
        )

    with (
        patch(f"{MODULE}.http_client", lambda **_: _mock_client(refused)),
        pytest.raises(OpenAiLiveRefused) as caught,
    ):
        await OpenAiLiveProvider().exchange_offer("sk-test", _inputs(), "v=0 offer", timeout=5)
    assert caught.value.code == "forbidden"
    assert "denied" in caught.value.message


async def test_exchange_offer_refuses_an_answer_without_sdp() -> None:
    def empty(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"session": {"id": "live_1"}})

    with (
        patch(f"{MODULE}.http_client", lambda **_: _mock_client(empty)),
        pytest.raises(OpenAiLiveRefused) as caught,
    ):
        await OpenAiLiveProvider().exchange_offer("sk-test", _inputs(), "v=0 offer", timeout=5)
    assert caught.value.code == "no_answer"


class _FakeSocket:
    """An `OpenAiLiveSocket` that answers the scripted verdict and records what it was sent."""

    instances: list[_FakeSocket] = []

    def __init__(self, api_key: str, *, timeout: float) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.started: dict[str, object] | None = None
        self.closed = False
        _FakeSocket.instances.append(self)

    async def __aenter__(self) -> _FakeSocket:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def start(self, session_config: dict[str, object]) -> dict[str, object]:
        self.started = session_config
        verdict = _FakeSocket.verdict
        if isinstance(verdict, Exception):
            raise verdict
        return {"id": "live_1"}

    async def close(self) -> None:
        self.closed = True

    verdict: object = None


async def test_probe_opens_the_real_session_with_the_pcm_format_and_closes_it() -> None:
    # The provider judges model AND voice at start (measured 2026-09-19: an
    # unknown voice answers `forbidden` before any `session.started`).
    _FakeSocket.instances.clear()
    _FakeSocket.verdict = None
    with patch(f"{MODULE}.OpenAiLiveSocket", _FakeSocket):
        accepted, detail = await OpenAiLiveProvider().probe("sk-test", _inputs(), timeout=7)
    assert (accepted, detail) == (True, "ok")
    socket = _FakeSocket.instances[0]
    assert socket.timeout == 7 and socket.closed
    assert socket.started is not None
    assert socket.started["audio"] == {
        "format": {"type": "audio/pcm", "rate": OPENAI_LIVE_SAMPLE_RATE},
        "output": {"voice": "quartz"},
    }
    assert socket.started["delegation"] == {"type": "client"}


async def test_probe_reports_a_refusal_in_the_providers_words() -> None:
    _FakeSocket.verdict = OpenAiLiveRefused("invalid_model", "Model x is not supported")
    with patch(f"{MODULE}.OpenAiLiveSocket", _FakeSocket):
        accepted, detail = await OpenAiLiveProvider().probe("sk-test", _inputs(), timeout=7)
    assert accepted is False and detail == "invalid_model: Model x is not supported"
    _FakeSocket.verdict = TimeoutError()
    with patch(f"{MODULE}.OpenAiLiveSocket", _FakeSocket):
        accepted, detail = await OpenAiLiveProvider().probe("sk-test", _inputs(), timeout=7)
    assert accepted is False and "in time" in detail


async def test_sample_voice_is_a_live_utterance_trimmed_of_its_silence() -> None:
    # The speech endpoint does not serve these voices (measured): the sample
    # is the live model speaking, and the continuous stream's silence is cut.
    _FakeSocket.instances.clear()
    _FakeSocket.verdict = None
    audible = (b"\x10\x27" * 240) + (b"\xf0\xd8" * 240)  # 10 000 / -10 000
    pcm = bytes(48_000) + audible + bytes(48_000)  # 1 s of silence on each side

    async def fake_utterance(_events, greeting, *, max_seconds):  # type: ignore[no-untyped-def]
        assert 'say exactly "Hello, I am LIA."' in greeting
        assert max_seconds > 0
        return pcm

    with (
        patch(f"{MODULE}.OpenAiLiveSocket", _FakeSocket),
        patch(f"{MODULE}.sample_utterance", fake_utterance),
    ):
        out = await OpenAiLiveProvider().sample_voice("sk-test", "quartz", "Hello, I am LIA.")
    assert len(out) < len(pcm) and audible in out
    socket = _FakeSocket.instances[0]
    assert socket.started is not None
    assert socket.started["model"] == OPENAI_LIVE_DEFAULT_MODEL
    assert socket.started["audio"]["output"] == {"voice": "quartz"}
    assert socket.closed


async def test_sample_voice_refuses_a_silent_stream() -> None:
    _FakeSocket.verdict = None

    async def silent(_events, _greeting, *, max_seconds):  # type: ignore[no-untyped-def]
        return bytes(9600)

    with (
        patch(f"{MODULE}.OpenAiLiveSocket", _FakeSocket),
        patch(f"{MODULE}.sample_utterance", silent),
        pytest.raises(ValueError, match="no audio"),
    ):
        await OpenAiLiveProvider().sample_voice("sk-test", "quartz", "Hello")
