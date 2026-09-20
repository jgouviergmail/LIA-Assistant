"""What Gemini's live provider sends, mints and probes — without the network (ADR-299)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.live.preferences import LivePreferences
from src.domains.live.providers.gemini import GEMINI_VOICES, GeminiLiveProvider
from src.domains.live.providers.protocol import LiveSetupInputs

pytestmark = pytest.mark.unit

MODULE = "src.domains.live.providers.gemini"
LISTING = "src.infrastructure.llm.providers.gemini_live_listing"


def _inputs(**overrides: object) -> LiveSetupInputs:
    base: dict[str, object] = {
        "model": "gemini-3.8-live",
        "voice": "Kore",
        "thinking_level": None,
        "system_instruction": "You are LIA's voice.",
        "tool_declaration": {
            "name": "send_to_lia",
            "description": "d",
            "parameters": {"type": "object", "properties": {"request": {"type": "string"}}},
            "behavior": "NON_BLOCKING",
        },
        "preferences": LivePreferences(),
        "trigger_tokens": 25_000,
        "target_tokens": 8_000,
    }
    base.update(overrides)
    return LiveSetupInputs(**base)  # type: ignore[arg-type]


def test_setup_carries_the_mandate_the_tool_and_both_transcriptions() -> None:
    setup = GeminiLiveProvider().build_setup(_inputs())
    assert setup["model"] == "models/gemini-3.8-live"
    assert setup["systemInstruction"]["parts"][0]["text"] == "You are LIA's voice."
    assert setup["tools"][0]["functionDeclarations"][0]["name"] == "send_to_lia"
    assert setup["tools"][0]["functionDeclarations"][0]["behavior"] == "NON_BLOCKING"
    generation = setup["generationConfig"]
    assert generation["responseModalities"] == ["AUDIO"]
    assert generation["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert setup["inputAudioTranscription"] == {}
    assert setup["outputAudioTranscription"] == {}
    assert setup["contextWindowCompression"]["slidingWindow"]["targetTokens"] == 8_000
    assert setup["contextWindowCompression"]["triggerTokens"] == 25_000
    assert setup["sessionResumption"] == {}
    assert "thinkingConfig" not in generation


def test_setup_renders_the_preferences() -> None:
    prefs = LivePreferences(interruptions=False, end_of_speech="calm")
    setup = GeminiLiveProvider().build_setup(_inputs(preferences=prefs))
    realtime = setup["realtimeInputConfig"]
    assert realtime["activityHandling"] == "NO_INTERRUPTION"
    # Always automatic: the provider's VAD decides the turns, never a held button.
    assert "disabled" not in realtime["automaticActivityDetection"]
    assert realtime["automaticActivityDetection"]["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    assert realtime["automaticActivityDetection"]["silenceDurationMs"] == 800


def test_setup_default_preferences_interrupt_and_keep_the_provider_sensitivity() -> None:
    realtime = GeminiLiveProvider().build_setup(_inputs())["realtimeInputConfig"]
    assert realtime["activityHandling"] == "START_OF_ACTIVITY_INTERRUPTS"
    assert "disabled" not in realtime["automaticActivityDetection"]
    assert "endOfSpeechSensitivity" not in realtime["automaticActivityDetection"]


@pytest.mark.parametrize("model", ["gemini-3.8-live", "gemini-3.8-live-extended-thinking"])
def test_the_setup_never_asks_for_affective_dialog(model: str) -> None:
    # MEASURED 2026-09-19 on the browser's own path: the flag earns a
    # setupComplete and then a 1007 at the first thing the model must answer
    # (text, realtime text or a spoken question alike; only silence survives).
    # The documentation invites it; this pins the measurement against the next
    # reader of that documentation.
    setup = GeminiLiveProvider().build_setup(_inputs(model=model))
    assert "enableAffectiveDialog" not in setup["generationConfig"]
    assert "enableAffectiveDialog" not in setup


def test_setup_renders_a_thinking_level_only_when_given() -> None:
    setup = GeminiLiveProvider().build_setup(
        _inputs(model="gemini-3.8-live-extended-thinking", thinking_level="high")
    )
    # The documented JSON enum is upper-case; the stored ladder is the ADR-245 one.
    assert setup["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "HIGH"}


@pytest.mark.parametrize(
    ("model", "async_delegation", "delivery_scheduling", "reports_idle", "thinking"),
    [
        ("gemini-3.8-live-extended-thinking", True, False, True, True),
        ("gemini-3.8-live", True, True, False, False),
        ("gemini-3.1-flash-live-preview", False, False, False, False),
        ("gemini-2.5-flash-native-audio-latest", True, True, False, False),
        ("gemini-99-live-unknown", False, False, False, False),
    ],
)
def test_capabilities_follow_the_documented_rules_per_model(
    model: str,
    async_delegation: bool,
    delivery_scheduling: bool,
    reports_idle: bool,
    thinking: bool,
) -> None:
    # Documented 2026-09-19: async function calling is unsupported on 3.1 Flash
    # Live (the model waits for the response), scheduling is refused and
    # interactionStatus reported on Extended Thinking, which also REQUIRES a
    # thinking level; an unknown model gets the conservative row.
    caps = GeminiLiveProvider().capabilities_of(model)
    assert caps.async_delegation is async_delegation
    assert caps.delivery_scheduling is delivery_scheduling
    assert caps.reports_idle is reports_idle
    assert caps.thinking is thinking
    assert caps.cancels_on_interruption is True and caps.configurable_vad is True


def test_thinking_capability_is_the_profiles_ladder_not_a_second_table() -> None:
    provider = GeminiLiveProvider()
    for model in ("gemini-3.8-live-extended-thinking", "gemini-3.8-live"):
        assert provider.capabilities_of(model).thinking is bool(provider.thinking_levels_of(model))


async def test_voices_are_the_published_list_with_their_provenance() -> None:
    listing = await GeminiLiveProvider().list_voices("k")
    assert listing.provenance == "published"
    assert listing.published_at and listing.source
    assert len(listing.voices) == len(GEMINI_VOICES) == 30
    assert listing.voices[0].name == "Zephyr"
    assert GeminiLiveProvider().knows_voice("Kore")
    assert not GeminiLiveProvider().knows_voice("not-a-voice")


async def test_models_carry_the_thinking_ladder_and_the_capabilities() -> None:
    listing = SimpleNamespace(
        name="models/gemini-3.8-live-extended-thinking", supported_actions=["bidiGenerateContent"]
    )

    async def _aiter():
        yield listing

    with patch(f"{LISTING}._models_of", AsyncMock(return_value=_aiter())):
        models = await GeminiLiveProvider().list_models("k")
    assert models[0].thinking_levels == ["low", "medium", "high"]
    assert models[0].capabilities.reports_idle is True
    assert models[0].capabilities.delivery_scheduling is False


async def test_sample_voice_asks_the_tts_model_for_the_voice_and_returns_its_pcm() -> None:
    # The live models refuse no voice name and offer no listing; the TTS model
    # speaks the same published voices, so the person hears what they choose.
    part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01\x02"))
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    generate = AsyncMock(return_value=response)
    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    )
    with (
        patch(f"{MODULE}.gemini_client_of", return_value=fake_client),
        patch(f"{MODULE}.settings") as cfg,
    ):
        cfg.live_voice_sample_model = "tts-model"
        pcm = await GeminiLiveProvider().sample_voice("k", "Kore", "Hello.")
    assert pcm == b"\x01\x02"
    assert GeminiLiveProvider().sample_rate == 24_000
    kwargs = generate.call_args.kwargs
    assert kwargs["model"] == "tts-model" and kwargs["contents"] == "Hello."
    assert kwargs["config"].response_modalities == ["AUDIO"]
    assert kwargs["config"].speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"


async def test_sample_voice_without_audio_is_an_error_not_silence() -> None:
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])
    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=AsyncMock(return_value=response))
        )
    )
    with (
        patch(f"{MODULE}.gemini_client_of", return_value=fake_client),
        patch(f"{MODULE}.settings") as cfg,
    ):
        cfg.live_voice_sample_model = "tts-model"
        with pytest.raises(ValueError):
            await GeminiLiveProvider().sample_voice("k", "Kore", "Hello.")


async def test_mint_constrains_the_model_and_the_setup() -> None:
    created = SimpleNamespace(name="auth_tokens/abc")
    create = AsyncMock(return_value=created)
    fake_client = SimpleNamespace(aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=create)))
    now = datetime.now(UTC)
    with patch(f"{MODULE}.gemini_client_of", return_value=fake_client):
        credential = await GeminiLiveProvider().mint(
            "k",
            _inputs(),
            expires_at=now + timedelta(minutes=30),
            connect_deadline_at=now + timedelta(minutes=1),
        )
    assert credential.name == "auth_tokens/abc"
    config = create.call_args.kwargs["config"]
    assert config.uses == 1
    assert config.live_connect_constraints.model == "gemini-3.8-live"
    assert config.live_connect_constraints.config.system_instruction == "You are LIA's voice."
    assert config.live_connect_constraints.config.thinking_config is None
    assert config.http_options.api_version == "v1alpha"


async def test_mint_constraint_carries_the_thinking_level_of_the_setup() -> None:
    created = SimpleNamespace(name="auth_tokens/abc")
    create = AsyncMock(return_value=created)
    fake_client = SimpleNamespace(aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=create)))
    now = datetime.now(UTC)
    with patch(f"{MODULE}.gemini_client_of", return_value=fake_client):
        await GeminiLiveProvider().mint(
            "k",
            _inputs(model="gemini-3.8-live-extended-thinking", thinking_level="medium"),
            expires_at=now + timedelta(minutes=30),
            connect_deadline_at=now + timedelta(minutes=1),
        )
    config = create.call_args.kwargs["config"].live_connect_constraints.config
    assert str(config.thinking_config.thinking_level).endswith("MEDIUM")
    # The constraint asks for no affective dialog either (measured, see build_setup).
    assert config.enable_affective_dialog is None


async def test_probe_reports_the_providers_refusal_in_its_words() -> None:
    class _Refusing:
        async def __aenter__(self) -> None:
            raise RuntimeError("model not found")

        async def __aexit__(self, *_: object) -> None:
            return None

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_: _Refusing()))
    )
    with patch(f"{MODULE}.gemini_client_of", return_value=fake_client):
        ok, detail = await GeminiLiveProvider().probe("k", _inputs(model="gemini-nope"), timeout=5)
    assert ok is False and "model not found" in detail


async def test_probe_accepts_an_opened_session() -> None:
    class _Opening:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_: object) -> None:
            return None

    seen: dict[str, object] = {}

    def _connect(**kwargs: object) -> _Opening:
        seen.update(kwargs)
        return _Opening()

    fake_client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=_connect)))
    with patch(f"{MODULE}.gemini_client_of", return_value=fake_client):
        ok, detail = await GeminiLiveProvider().probe(
            "k",
            _inputs(model="gemini-3.8-live-extended-thinking", thinking_level="low"),
            timeout=5,
        )
    assert ok is True and detail == "ok"
    # The probe replays the REAL setup: the owner's activation of Extended
    # Thinking was refused (1007 « Thinking level must be specified ») because
    # the probe opened the session with the response modality alone.
    config = seen["config"]
    assert seen["model"] == "gemini-3.8-live-extended-thinking"
    assert str(config.thinking_config.thinking_level).endswith("LOW")  # type: ignore[attr-defined]
    assert config.tools[0].function_declarations[0].name == "send_to_lia"  # type: ignore[attr-defined]
