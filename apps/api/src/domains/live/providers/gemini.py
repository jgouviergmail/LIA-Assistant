"""Gemini as a live provider: what the key discovers, what LIA sends, what it mints.

The SDK client is built per call on the PERSON's key and never kept (the
singleton rule). Two facts measured on 2026-09-18 shape this module:

- **the listing marks non-conversational models live too** — the filter lives
  in ``infrastructure/llm/providers/gemini_live_listing.py``, shared with the
  API-key verifier so ``connectors`` never imports ``live``;
- **an unknown voice name is never refused**, not at setup and not once the
  model speaks: the provider falls back to a default voice in silence. So the
  voices are VENDORED with their date and source (Gemini offers no listing
  endpoint), the form shows that provenance, and a name off the list is
  refused by LIA — the only place a wrong name can be caught.

The activation probe therefore validates the KEY and the MODEL (a session
opened and closed at once, no audio, no token consumed) and nothing about the
voice.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, Final

from src.core.config import settings
from src.core.constants import GEMINI_LIVE_DEFAULT_MODEL, GEMINI_TTS_SAMPLE_RATE
from src.core.reasoning_profiles import resolve_reasoning_profile
from src.domains.connectors.models import ConnectorType
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers.protocol import (
    LiveBilling,
    LiveConnection,
    LiveCredential,
    LiveDelegationWire,
    LiveModelCapabilities,
    LiveSetupInputs,
)
from src.domains.live.schemas import (
    LiveModel,
    LiveModelCapabilitiesResponse,
    LiveVoice,
    LiveVoicesResponse,
)
from src.infrastructure.llm.providers.gemini_live_listing import (
    gemini_client_of,
    list_live_model_names,
)

#: The reasoning-profile provider id (a rule key of ``core/reasoning_profiles``).
_REASONING_PROVIDER: Final = "gemini_live"
#: The voices Google publishes for its TTS and Live models, with the one-word
#: character the documentation gives each. Vendored: no listing endpoint exists.
GEMINI_VOICES: Final[tuple[tuple[str, str], ...]] = (
    ("Zephyr", "Bright"),
    ("Puck", "Upbeat"),
    ("Charon", "Informative"),
    ("Kore", "Firm"),
    ("Fenrir", "Excitable"),
    ("Leda", "Youthful"),
    ("Orus", "Firm"),
    ("Aoede", "Breezy"),
    ("Callirrhoe", "Easy-going"),
    ("Autonoe", "Bright"),
    ("Enceladus", "Breathy"),
    ("Iapetus", "Clear"),
    ("Umbriel", "Easy-going"),
    ("Algieba", "Smooth"),
    ("Despina", "Smooth"),
    ("Erinome", "Clear"),
    ("Algenib", "Gravelly"),
    ("Rasalgethi", "Informative"),
    ("Laomedeia", "Upbeat"),
    ("Achernar", "Soft"),
    ("Alnilam", "Firm"),
    ("Schedar", "Even"),
    ("Gacrux", "Mature"),
    ("Pulcherrima", "Forward"),
    ("Achird", "Friendly"),
    ("Zubenelgenubi", "Casual"),
    ("Vindemiatrix", "Gentle"),
    ("Sadachbia", "Lively"),
    ("Sadaltager", "Knowledgeable"),
    ("Sulafat", "Warm"),
)
GEMINI_VOICES_PUBLISHED_AT: Final = "2026-09-18"
GEMINI_VOICES_SOURCE: Final = "https://ai.google.dev/gemini-api/docs/speech-generation"
_VOICE_NAMES: Final[frozenset[str]] = frozenset(name for name, _ in GEMINI_VOICES)
#: What each model family can do, from the documentation read on 2026-09-19
#: (models/gemini-3.8-live, models/gemini-3.8-live-extended-thinking,
#: live-api/thinking, live-api/tools): async function calling is unsupported
#: on 3.1 Flash Live (« the model will not start responding until you've sent
#: the tool response »), ``scheduling`` is refused and ``interactionStatus``
#: reported on Extended Thinking. ``thinking`` is NOT written here: it is the
#: ADR-245 ladder, one authority. Longest prefix wins; an unknown live model
#: gets the conservative row.
_CAPABILITY_RULES: Final[tuple[tuple[str, LiveModelCapabilities], ...]] = (
    (
        "gemini-3.8-live-extended-thinking",
        LiveModelCapabilities(
            async_delegation=True,
            delivery_scheduling=False,
            reports_idle=True,
            cancels_on_interruption=True,
            configurable_vad=True,
            resumes=True,
            thinking=True,
        ),
    ),
    (
        "gemini-3.8-live",
        LiveModelCapabilities(
            async_delegation=True,
            delivery_scheduling=True,
            reports_idle=False,
            cancels_on_interruption=True,
            configurable_vad=True,
            resumes=True,
            thinking=False,
        ),
    ),
    (
        "gemini-2.5-flash-native-audio",
        LiveModelCapabilities(
            async_delegation=True,
            delivery_scheduling=True,
            reports_idle=False,
            cancels_on_interruption=True,
            configurable_vad=True,
            resumes=True,
            thinking=False,
        ),
    ),
)
#: Longest prefix first, computed once: ``gemini-3.8-live`` is a prefix of the
#: extended-thinking name.
_RULES_LONGEST_FIRST: Final = tuple(sorted(_CAPABILITY_RULES, key=lambda r: -len(r[0])))
_UNKNOWN_CAPABILITIES: Final = LiveModelCapabilities(
    async_delegation=False,
    delivery_scheduling=False,
    reports_idle=False,
    cancels_on_interruption=True,
    configurable_vad=True,
    resumes=True,
    thinking=False,
)
#: End-of-speech presets → (sensitivity enum, silence ms) — the documented range.
_END_OF_SPEECH: Final[dict[str, tuple[str | None, int]]] = {
    "calm": ("END_SENSITIVITY_LOW", 800),
    "normal": (None, 650),
    "lively": ("END_SENSITIVITY_HIGH", 500),
}


def _declarations(inputs: LiveSetupInputs) -> list[dict[str, Any]]:
    """The function declarations of a setup: the delegation one, or the direct tools."""
    if inputs.tool_declaration is not None:
        return [inputs.tool_declaration]
    return list(inputs.direct_tools)


class GeminiLiveProvider:
    """Gemini Live API through ephemeral tokens (client → provider)."""

    provider_id = "gemini"
    connector_type = ConnectorType.GEMINI_LIVE
    connection: LiveConnection = "token"
    delegation_wire: LiveDelegationWire = "tool"
    default_model = GEMINI_LIVE_DEFAULT_MODEL
    #: The models are what the tariff table names.
    billing: LiveBilling = "tariff"

    async def list_models(self, api_key: str) -> list[LiveModel]:
        """Live-capable models, each with its thinking ladder and its capabilities."""
        return [
            LiveModel(
                provider=self.provider_id,
                name=name,
                thinking_levels=list(self.thinking_levels_of(name)),
                capabilities=LiveModelCapabilitiesResponse(**asdict(self.capabilities_of(name))),
            )
            for name in await list_live_model_names(api_key)
        ]

    async def list_voices(self, _api_key: str) -> LiveVoicesResponse:
        """The published list, with its provenance said out loud."""
        return LiveVoicesResponse(
            provider=self.provider_id,
            voices=[LiveVoice(name=n, characteristic=c) for n, c in GEMINI_VOICES],
            provenance="published",
            published_at=GEMINI_VOICES_PUBLISHED_AT,
            source=GEMINI_VOICES_SOURCE,
        )

    def knows_voice(self, name: str) -> bool:
        """Whether the name is on the published list — the only check that exists."""
        return name in _VOICE_NAMES

    @property
    def sample_rate(self) -> int:
        """The provider's TTS output rate (16-bit mono PCM)."""
        return GEMINI_TTS_SAMPLE_RATE

    async def sample_voice(self, api_key: str, voice: str, text: str) -> bytes:
        """One sentence in ``voice`` through the TTS model, on the person's key.

        The live models offer no listing of their voices and refuse no name;
        the TTS model speaks the SAME published voices, so a person hears
        what they choose before a session ever opens.
        """
        from google.genai import types

        client = gemini_client_of(api_key)
        response = await client.aio.models.generate_content(
            model=settings.live_voice_sample_model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )
        for candidate in response.candidates or []:
            for part in (candidate.content.parts if candidate.content else None) or []:
                data = part.inline_data.data if part.inline_data else None
                if data:
                    return bytes(data)
        # A blocked prompt comes back with NO candidate: say why, never « no audio »
        # (measured 2026-09-19: the 3.1 TTS preview blocks the sample sentence).
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None) if feedback else None
        if reason:
            raise ValueError(f"blocked: {getattr(reason, 'name', reason)}")
        raise ValueError("the provider returned no audio")

    def thinking_levels_of(self, model: str) -> tuple[str, ...]:
        """The ladder the reasoning profile declares for the model (ADR-245)."""
        return tuple(resolve_reasoning_profile(_REASONING_PROVIDER, model).levels)

    def capabilities_of(self, model: str) -> LiveModelCapabilities:
        """The documented row of the model's family; ``thinking`` is the ladder's word."""
        row = _UNKNOWN_CAPABILITIES
        for prefix, candidate in _RULES_LONGEST_FIRST:
            if model.startswith(prefix):
                row = candidate
                break
        # Every Gemini live model reads function declarations: the direct
        # session (ADR-300 wave 4) runs on any of them.
        return replace(row, thinking=bool(self.thinking_levels_of(model)), direct_tools=True)

    def build_setup(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The ``setup`` message the browser sends first, as documented JSON.

        No ``enableAffectiveDialog`` here, on purpose. MEASURED 2026-09-19 on the
        browser's own path (token-constrained socket, gemini-3.8-live): the flag
        earns a ``setupComplete`` and then closes the socket (1007 « invalid
        argument ») at the FIRST thing the model must answer — a text turn, a
        realtime text, a spoken question alike; only silence survives it, on
        v1beta and v1alpha, with or without the flag in the token constraint.
        The emotion of the voice comes from the mandate (LIA's inner state) and
        from the delivery note beside each result, both measured to pass.
        """
        generation: dict[str, Any] = {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": inputs.voice}}},
        }
        if inputs.thinking_level:
            # The documented JSON enum is upper-case; the ladder is stored lower-case.
            generation["thinkingConfig"] = {"thinkingLevel": inputs.thinking_level.upper()}
        return {
            "model": f"models/{inputs.model}",
            "generationConfig": generation,
            "systemInstruction": {"parts": [{"text": inputs.system_instruction}]},
            # A delegated session declares the one delegation function; a
            # direct one declares LIA's read-only tools instead.
            "tools": [{"functionDeclarations": _declarations(inputs)}],
            "realtimeInputConfig": _realtime_input(inputs.preferences),
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "sessionResumption": {},
            "contextWindowCompression": {
                "triggerTokens": inputs.trigger_tokens,
                "slidingWindow": {"targetTokens": inputs.target_tokens},
            },
        }

    async def mint(
        self,
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        expires_at: datetime,
        connect_deadline_at: datetime,
    ) -> LiveCredential:
        """An ephemeral token for ONE connection, constrained to the model and the setup.

        Measured 2026-09-18: the constraint does not refuse a session opened
        with another instruction, and a ``uses: 1`` token cannot reopen its
        session — so the server renders the setup the browser replays, and a
        reconnection mints again for the same session record.
        """
        from google.genai import types

        config = types.CreateAuthTokenConfig(
            uses=1,
            expire_time=expires_at,
            new_session_expire_time=connect_deadline_at,
            live_connect_constraints=types.LiveConnectConstraints(
                model=inputs.model, config=_sdk_config(inputs)
            ),
            lock_additional_fields=[],
            http_options=types.HttpOptions(api_version="v1alpha"),
        )
        # Bound to a name for the call's whole life: a temporary client is
        # collected mid-request and its session closes (see gemini_live_listing).
        client = gemini_client_of(api_key)
        token = await client.aio.auth_tokens.create(config=config)
        return LiveCredential(
            name=str(token.name), expires_at=expires_at, connect_deadline_at=connect_deadline_at
        )

    async def probe(
        self, api_key: str, inputs: LiveSetupInputs, *, timeout: float
    ) -> tuple[bool, str]:
        """Open a session on the REAL setup and close it: the provider judges the pair.

        Measured 2026-09-18 on the owner's activation: a probe sent with the
        response modality alone was refused on Extended Thinking with 1007
        « Thinking level must be specified for this model » — the level the
        person had chosen never reached the provider.
        """
        config = _sdk_config(inputs)
        client = gemini_client_of(api_key)

        async def _open_and_close() -> None:
            async with client.aio.live.connect(model=inputs.model, config=config):
                return None

        try:
            await asyncio.wait_for(_open_and_close(), timeout=timeout)
        except TimeoutError:
            return False, "the provider did not answer in time"
        except Exception as exc:  # noqa: BLE001 - the refusal is the answer we report
            return False, f"{type(exc).__name__}: {exc}"
        return True, "ok"


def _realtime_input(prefs: LivePreferences) -> dict[str, Any]:
    """The VAD and interruption block, from the person's reflexes."""
    sensitivity, silence_ms = _END_OF_SPEECH[prefs.end_of_speech]
    detection: dict[str, Any] = {"silenceDurationMs": silence_ms}
    if sensitivity:
        detection["endOfSpeechSensitivity"] = sensitivity
    return {
        "automaticActivityDetection": detection,
        "activityHandling": (
            "START_OF_ACTIVITY_INTERRUPTS" if prefs.interruptions else "NO_INTERRUPTION"
        ),
    }


def _sdk_config(inputs: LiveSetupInputs) -> Any:
    """The same setup, in the SDK's typed shape, for the token constraint."""
    from google.genai import types

    # The delegation declaration carries its own ``behavior`` (NON_BLOCKING);
    # a direct tool carries none and is awaited, like on the phone.
    declarations = [
        types.FunctionDeclaration(
            name=declaration["name"],
            description=declaration["description"],
            parameters=declaration["parameters"],
            behavior=(
                types.Behavior(declaration["behavior"]) if "behavior" in declaration else None
            ),
        )
        for declaration in _declarations(inputs)
    ]
    thinking = (
        types.ThinkingConfig(thinking_level=types.ThinkingLevel(inputs.thinking_level.upper()))
        if inputs.thinking_level
        else None
    )
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=inputs.system_instruction,
        tools=[types.Tool(function_declarations=declarations)],
        session_resumption=types.SessionResumptionConfig(),
        thinking_config=thinking,
    )


__all__ = [
    "GEMINI_VOICES",
    "GEMINI_VOICES_PUBLISHED_AT",
    "GEMINI_VOICES_SOURCE",
    "GeminiLiveProvider",
]
