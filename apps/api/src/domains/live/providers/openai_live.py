"""GPT-Live as a live provider: what the key discovers, what LIA sends, what it mints.

The second provider of ADR-299 (wave 2 spec A9), the same shape as Gemini's
and a different wire on every count, which is what the protocol is for:

- **the browser speaks WebRTC** and the SDP offer is exchanged HERE, on the
  person's key (``POST /v1/live/sessions``, documented: no ephemeral token
  exists for GPT-Live). What LIA mints is therefore its OWN single-use nonce —
  the ``credential`` the browser hands back with its offer — so « one
  credential opens one connection » holds for both providers;
- **delegation is native**: the model delegates by itself (``delegation:
  {type: client}``) and the browser reads ``session.delegation.created``,
  which carries an id and no text — the request is composed from the input
  transcript (documented, 2026-09-19). No function declaration is sent, and
  the mandate says « delegate to LIA » where Gemini's says « call send_to_lia »;
- **the voices are the live model's own** — none of the twelve is served by
  the speech endpoint (measured) — so the sample is a short live session on
  the person's key, and the provider REFUSES an unknown voice itself
  (``forbidden``, measured), which the probe therefore checks too;
- **no VAD configuration, no resumption**: the provider decides the turns,
  and a dropped connection is a new session (a fork is a new id).
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, replace
from datetime import datetime
from typing import Any, Final

from src.core.config import settings
from src.core.constants import (
    OPENAI_LIVE_DEFAULT_MODEL,
    OPENAI_LIVE_SAMPLE_MAX_SECONDS,
    OPENAI_LIVE_SAMPLE_RATE,
)
from src.core.reasoning_profiles import resolve_reasoning_profile
from src.domains.connectors.models import ConnectorType
from src.domains.live.mandate import live_lines, sample_greeting
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers.openai_live_socket import (
    OpenAiLiveRefused,
    OpenAiLiveSocket,
    sample_utterance,
)
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
from src.infrastructure.llm.providers.openai_live_listing import (
    auth_header,
    http_client,
    list_live_model_names,
)
from src.infrastructure.media.pcm import trim_silence

#: The reasoning-profile provider id (no rule today: GPT-Live has no thinking level).
_REASONING_PROVIDER: Final = "openai_live"
#: The twelve voices the documentation lists for GPT-Live, with the character
#: it gives each (language, regional influence, presentation). Vendored: no
#: listing endpoint exists, and the speech endpoint does not serve them.
OPENAI_LIVE_VOICES: Final[tuple[tuple[str, str], ...]] = (
    ("quartz", "Australian English, feminine"),
    ("ripple", "Australian English, masculine"),
    ("vesper", "British English, masculine"),
    ("willow", "Irish English, feminine"),
    ("stone", "Irish English, masculine"),
    ("gleam", "North American English, feminine"),
    ("meridian", "North American English, masculine"),
    ("bossa", "Brazilian Portuguese, feminine"),
    ("tempo", "Brazilian Portuguese, masculine"),
    ("beacon", "Filipino English, masculine"),
    ("delta", "Southern U.S. English, feminine"),
    ("cinder", "Southern U.S. English, masculine"),
)
OPENAI_LIVE_VOICES_PUBLISHED_AT: Final = "2026-09-19"
OPENAI_LIVE_VOICES_SOURCE: Final = (
    "https://developers.openai.com/api/docs/guides/live-conversations"
)
_VOICE_NAMES: Final[frozenset[str]] = frozenset(name for name, _ in OPENAI_LIVE_VOICES)
#: One row for the whole family (documented 2026-09-19: full duplex with
#: delegation running in the background, no delivery mode on a result, no
#: idle signal, no cancellation on interruption — «your application must
#: decide», no VAD settings, no resumption). ``thinking`` is the ladder's word.
_CAPABILITIES: Final = LiveModelCapabilities(
    async_delegation=True,
    delivery_scheduling=False,
    reports_idle=False,
    cancels_on_interruption=False,
    configurable_vad=False,
    resumes=False,
    thinking=False,
)


class OpenAiLiveProvider:
    """GPT-Live through WebRTC (browser) and a server-side offer exchange."""

    provider_id = "openai"
    connector_type = ConnectorType.GPT_LIVE
    connection: LiveConnection = "offer"
    delegation_wire: LiveDelegationWire = "native"
    default_model = OPENAI_LIVE_DEFAULT_MODEL
    #: The models are what the tariff table names.
    billing: LiveBilling = "tariff"

    async def list_models(self, api_key: str) -> list[LiveModel]:
        """Live-capable models the key lists, each with its (empty) ladder and capabilities."""
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
            voices=[LiveVoice(name=n, characteristic=c) for n, c in OPENAI_LIVE_VOICES],
            provenance="published",
            published_at=OPENAI_LIVE_VOICES_PUBLISHED_AT,
            source=OPENAI_LIVE_VOICES_SOURCE,
        )

    def knows_voice(self, name: str) -> bool:
        """Whether the name is on the published list (the provider refuses the rest too)."""
        return name in _VOICE_NAMES

    @property
    def sample_rate(self) -> int:
        """The rate the sample session is asked for (16-bit mono PCM)."""
        return OPENAI_LIVE_SAMPLE_RATE

    def thinking_levels_of(self, model: str) -> tuple[str, ...]:
        """The ladder the reasoning profile declares for the model (ADR-245): none today."""
        return tuple(resolve_reasoning_profile(_REASONING_PROVIDER, model).levels)

    def capabilities_of(self, model: str) -> LiveModelCapabilities:
        """The documented row of the family; ``thinking`` is the ladder's word."""
        return replace(_CAPABILITIES, thinking=bool(self.thinking_levels_of(model)))

    def build_setup(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The ``session`` object of the offer exchange — the browser replays nothing.

        No ``audio.format``: over WebRTC the format is negotiated in the SDP
        (documented). No function declaration: the delegation is the model's
        own act under ``delegation.type = client``.
        """
        return {
            "model": inputs.model,
            "instructions": inputs.system_instruction,
            "delegation": {"type": "client"},
            "audio": {"output": {"voice": inputs.voice}},
        }

    def _socket_config(self, inputs: LiveSetupInputs) -> dict[str, Any]:
        """The same session, for a server-side socket: the PCM format made explicit."""
        return {
            **self.build_setup(inputs),
            "audio": {
                "format": {"type": "audio/pcm", "rate": OPENAI_LIVE_SAMPLE_RATE},
                "output": {"voice": inputs.voice},
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
        """LIA's own single-use nonce: the provider mints nothing for a WebRTC session.

        The nonce is what the browser hands back with its SDP offer; the
        session record keeps it and consumes it on the exchange.
        """
        return LiveCredential(
            name=secrets.token_urlsafe(32),
            expires_at=expires_at,
            connect_deadline_at=connect_deadline_at,
        )

    async def exchange_offer(
        self, api_key: str, inputs: LiveSetupInputs, offer_sdp: str, *, timeout: float
    ) -> str:
        """The provider's SDP answer for the browser's offer, on the person's key.

        Args:
            api_key: The person's provider key.
            inputs: The session's setup inputs (the record's).
            offer_sdp: The browser's SDP offer.
            timeout: The bound of the HTTP exchange.

        Returns:
            The SDP answer the browser sets as its remote description.

        Raises:
            OpenAiLiveRefused: The provider refused the session (its code and words).
        """
        async with http_client(timeout=timeout) as client:
            response = await client.post(
                "/live/sessions",
                headers=auth_header(api_key),
                json={
                    "session": self.build_setup(inputs),
                    "transport": {"type": "webrtc", "sdp": offer_sdp},
                },
            )
            if response.is_error:
                raise OpenAiLiveRefused(*_http_refusal(response))
            body = response.json()
        transport = body.get("transport") if isinstance(body, dict) else None
        answer = transport.get("sdp") if isinstance(transport, dict) else None
        if not isinstance(answer, str) or not answer:
            raise OpenAiLiveRefused("no_answer", "the provider returned no SDP answer")
        return answer

    async def sample_voice(self, api_key: str, voice: str, text: str) -> bytes:
        """One sentence in ``voice`` from a short live session on the person's key.

        The speech endpoint does not serve these voices (measured): the live
        model speaks the sentence itself, for a few seconds billed to the
        person's own account, never to LIA's ledger.
        """
        inputs = LiveSetupInputs(
            model=self.default_model,
            voice=voice,
            thinking_level=None,
            system_instruction=live_lines()["sample_instructions"],
            tool_declaration={},
            # The reflexes play no part in a sample (the provider decides the turns).
            preferences=LivePreferences(),
            trigger_tokens=0,
            target_tokens=0,
        )
        greeting = sample_greeting(text)
        async with OpenAiLiveSocket(api_key, timeout=settings.live_probe_timeout_seconds) as socket:
            await socket.start(self._socket_config(inputs))
            pcm = await sample_utterance(
                socket, greeting, max_seconds=OPENAI_LIVE_SAMPLE_MAX_SECONDS
            )
            await socket.close()
        trimmed = trim_silence(pcm, sample_rate=OPENAI_LIVE_SAMPLE_RATE)
        if not trimmed:
            raise ValueError("the provider returned no audio")
        return trimmed

    async def probe(
        self, api_key: str, inputs: LiveSetupInputs, *, timeout: float
    ) -> tuple[bool, str]:
        """Open a session on the REAL setup and close it: the provider judges model AND voice."""
        try:
            async with OpenAiLiveSocket(api_key, timeout=timeout) as socket:
                await socket.start(self._socket_config(inputs))
                await socket.close()
        except OpenAiLiveRefused as exc:
            return False, f"{exc.code}: {exc.message}"
        except TimeoutError:
            return False, "the provider did not answer in time"
        except Exception as exc:  # noqa: BLE001 - the refusal is the answer we report
            return False, f"{type(exc).__name__}: {exc}"
        return True, "ok"


def _http_refusal(response: Any) -> tuple[str, str]:
    """The provider's own code and words from an error body, else the HTTP status."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        error = {}
    code = str(error.get("code") or f"http_{response.status_code}")
    message = str(error.get("message") or response.reason_phrase or "")
    return code, message


__all__ = [
    "OPENAI_LIVE_VOICES",
    "OPENAI_LIVE_VOICES_PUBLISHED_AT",
    "OPENAI_LIVE_VOICES_SOURCE",
    "OpenAiLiveProvider",
]
