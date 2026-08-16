"""Async client for the ElevenLabs ElevenAgents API (per-user API key).

Endpoints verified against the current ElevenAgents docs (2026 rebrand). Exact
request-body field paths marked "spike" are to be confirmed by the P2.0 vertical
slice against a real account before go-live.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.domains.telephony.schemas import OutboundCallResult, PhoneNumberInfo

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.elevenlabs.io/v1/convai"
# ElevenLabs authenticates via this header (not a bearer token).
_AUTH_HEADER = "xi-api-key"


def _agent_config_body(
    *,
    name: str,
    system_prompt: str,
    first_message: str,
    language: str,
    llm_model: str | None,
    tts_model_id: str | None,
    voice_id: str | None,
    audio_format: str | None,
    max_duration_seconds: int | None,
    data_collection: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Build the agent config body shared by create_agent and update_agent.

    One source of truth: whatever is covered by the config fingerprint
    (``agent_prompt.agent_config_fingerprint``) is exactly what gets sent.
    """
    prompt_config: dict[str, Any] = {
        "prompt": system_prompt,
        # System tools: each entry REQUIRES its "name" field (real vendor 400
        # observed on an empty object: "Field required — built_in_tools.
        # end_call.name"). Without end_call the agent can NEVER hang up.
        "built_in_tools": {
            "end_call": {"name": "end_call"},
            "voicemail_detection": {"name": "voicemail_detection"},
        },
    }
    if llm_model:
        # Pin the agent's LLM: the platform default (gemini-2.5-flash, a
        # thinking model — verified on a fresh agent) was observed reciting
        # its English reasoning ALOUD on a real French call. PATCH contract
        # verified on a throwaway agent (200, stored, echoed by GET).
        prompt_config["llm"] = llm_model
    body: dict[str, Any] = {
        "name": name,
        "conversation_config": {
            "agent": {
                "prompt": prompt_config,
                "first_message": first_message,
                "language": language,
            },
        },
    }
    tts: dict[str, Any] = {}
    if tts_model_id:
        tts["model_id"] = tts_model_id
    if voice_id:
        tts["voice_id"] = voice_id
    if audio_format:
        # Telephony is 8 kHz mu-law end to end: Twilio requires ulaw_8000 and a
        # format mismatch is the vendor's documented cause of garbled/poor call
        # audio. Set BOTH directions (TTS out + ASR in).
        # spike: field paths per the agent config schema
        # (tts.agent_output_audio_format / asr.user_input_audio_format).
        tts["agent_output_audio_format"] = audio_format
        body["conversation_config"]["asr"] = {"user_input_audio_format": audio_format}
    if tts:
        body["conversation_config"]["tts"] = tts
    if max_duration_seconds:
        body["conversation_config"]["conversation"] = {"max_duration_seconds": max_duration_seconds}
    if data_collection:
        body["platform_settings"] = {
            "data_collection": {
                field["identifier"]: {
                    "type": field["type"],
                    "description": field["description"],
                }
                for field in data_collection
            }
        }
    return body


class ElevenLabsAgentsError(RuntimeError):
    """Raised when the ElevenLabs API returns a non-success response.

    ``is_auth_error`` distinguishes a credential rejection (the stored key no
    longer authenticates — retrying is pointless, the connector key must be
    replaced) from transient/configuration failures. HTTP 401 always counts;
    a 4xx flagged by the vendor's structured taxonomy counts too.
    """

    def __init__(self, status_code: int, detail: str, *, auth_error: bool = False) -> None:
        self.status_code = status_code
        self.detail = detail
        self.is_auth_error = auth_error or status_code == 401
        super().__init__(f"ElevenLabs API error {status_code}: {detail}")


def _is_auth_response(resp: httpx.Response) -> bool:
    """Vendor-declared authentication failure, classified STRUCTURALLY.

    Reads ``detail.type`` from the JSON body (the vendor's error taxonomy) —
    never a message substring (same doctrine as ToolErrorCode). Observed in
    prod 2026-08-15: 400 ``{"detail": {"type": "authentication_error", "code":
    "invalid_api_key", ...}}`` when ElevenLabs stopped accepting a legacy
    key-ID-shaped credential.
    """
    if resp.status_code == 401:
        return True
    try:
        payload = resp.json()
    except ValueError:
        return False
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return isinstance(detail, dict) and detail.get("type") == "authentication_error"


class ElevenLabsAgentsClient:
    """Thin async wrapper over the ElevenAgents REST API.

    ``transport`` is injectable so tests can drive it with ``httpx.MockTransport``
    (no network, no monkeypatching of httpx internals).
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._headers = {_AUTH_HEADER: api_key}
        self._timeout = timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE_URL,
            headers=self._headers,
            timeout=self._timeout,
            transport=self._transport,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with self._client() as client:
            resp = await client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            # Never log the api key. The truncated vendor detail IS logged: it
            # names the offending field (e.g. "built_in_tools.end_call.name:
            # Field required") and carries no user data — without it a prod 4xx
            # (observed: agent-sync PATCH 400) is undiagnosable.
            detail = resp.text[:200]
            # Classified on the FULL body before truncation: the structured
            # taxonomy field can sit past the 200-char cut (observed in prod).
            auth_error = _is_auth_response(resp)
            logger.warning(
                "elevenlabs_api_error",
                method=method,
                path=path,
                status_code=resp.status_code,
                auth_error=auth_error,
                detail=detail,
            )
            raise ElevenLabsAgentsError(resp.status_code, detail, auth_error=auth_error)
        return resp

    async def validate_key(self) -> bool:
        """Return True if the API key authenticates (lists agents => 200)."""
        async with self._client() as client:
            resp = await client.get("/agents")
        return resp.status_code == 200

    async def list_phone_numbers(self) -> list[PhoneNumberInfo]:
        """List phone numbers imported in the user's workspace."""
        resp = await self._request("GET", "/phone-numbers")
        payload = resp.json()
        # The endpoint returns a list; tolerate a {"phone_numbers": [...]} envelope.
        rows = payload if isinstance(payload, list) else payload.get("phone_numbers", [])
        return [PhoneNumberInfo.model_validate(row) for row in rows]

    async def create_agent(
        self,
        *,
        name: str,
        system_prompt: str,
        first_message: str,
        language: str,
        llm_model: str | None = None,
        tts_model_id: str | None = None,
        voice_id: str | None = None,
        audio_format: str | None = None,
        max_duration_seconds: int | None = None,
        data_collection: list[dict[str, str]] | None = None,
    ) -> str:
        """Create a LIA-controlled agent; returns its ``agent_id``.

        ``tts_model_id`` selects the agent's voice model. ElevenLabs REJECTS
        non-English agents without a turbo/flash v2.5 model (real 400 observed:
        "Non-english Agents must use turbo or flash v2_5"), so callers must pass
        one whenever ``language`` is not English. ``voice_id`` overrides the
        vendor default voice (an ENGLISH voice — garbled speech observed on
        French calls with it).

        The ``end_call`` system tool is always enabled — without it the agent
        can NEVER hang up and the line stays open after the goodbyes (observed).
        ``voicemail_detection`` supports the prompt's voicemail behavior, and
        ``max_duration_seconds`` caps runaway calls at the vendor level.

        ``data_collection`` declares the structured fields the agent must extract
        during the call (their identifiers are the contract with the post-call
        webhook — see ``return_synthesis._extract_structured``). Without it the
        agent collects nothing and ``structured_data`` stays empty.

        spike: confirm the exact prompt-text key (``conversation_config.agent.
        prompt.prompt``), the data-collection config path (assumed
        ``platform_settings.data_collection``) and the ``built_in_tools`` shape
        (docs: ``agent.prompt.built_in_tools`` object keyed by tool name).
        """
        body = _agent_config_body(
            name=name,
            system_prompt=system_prompt,
            first_message=first_message,
            language=language,
            llm_model=llm_model,
            tts_model_id=tts_model_id,
            voice_id=voice_id,
            audio_format=audio_format,
            max_duration_seconds=max_duration_seconds,
            data_collection=data_collection,
        )
        resp = await self._request("POST", "/agents/create", json=body)
        agent_id: str = resp.json()["agent_id"]
        logger.info("elevenlabs_agent_created", agent_id=agent_id)
        return agent_id

    async def update_agent(
        self,
        agent_id: str,
        *,
        name: str,
        system_prompt: str,
        first_message: str,
        language: str,
        llm_model: str | None = None,
        tts_model_id: str | None = None,
        voice_id: str | None = None,
        audio_format: str | None = None,
        max_duration_seconds: int | None = None,
        data_collection: list[dict[str, str]] | None = None,
    ) -> None:
        """Update an existing agent in place with the SAME config body as create.

        Powers the lazy config re-sync: prompt/voice/format changes reach the
        provisioned agent on the next call, without deactivating the connector.
        spike: PATCH semantics per the agents API (config fields replaced).
        """
        body = _agent_config_body(
            name=name,
            system_prompt=system_prompt,
            first_message=first_message,
            language=language,
            llm_model=llm_model,
            tts_model_id=tts_model_id,
            voice_id=voice_id,
            audio_format=audio_format,
            max_duration_seconds=max_duration_seconds,
            data_collection=data_collection,
        )
        await self._request("PATCH", f"/agents/{agent_id}", json=body)
        logger.info("elevenlabs_agent_updated", agent_id=agent_id)

    async def delete_agent(self, agent_id: str) -> None:
        """Best-effort delete of a LIA-created agent (deactivation cleanup)."""
        try:
            await self._request("DELETE", f"/agents/{agent_id}")
        except ElevenLabsAgentsError as exc:
            # The agent lives in the user's workspace — cleanup failure is non-fatal.
            logger.warning("elevenlabs_agent_delete_failed", agent_id=agent_id, detail=exc.detail)

    async def get_conversation_status(self, conversation_id: str) -> str:
        """Return the vendor-side status of a conversation (empty if absent).

        Powers the self-healing one-active-call guard: a row stuck DIALING
        because its post-call webhook never arrived can be closed as soon as
        the vendor reports the conversation terminal. spike: status values per
        the conversations API (initiated / in-progress / processing / done /
        failed).
        """
        resp = await self._request("GET", f"/conversations/{conversation_id}")
        status: str = resp.json().get("status", "")
        return status

    async def initiate_outbound_call(
        self,
        *,
        agent_id: str,
        agent_phone_number_id: str,
        to_number: str,
        dynamic_variables: dict[str, Any],
        ringing_timeout_secs: int,
    ) -> OutboundCallResult:
        """Place an outbound call. Recording is disabled at the API level (D-8)."""
        body = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "to_number": to_number,
            "call_recording_enabled": False,  # D-8: no recording, ever
            "telephony_call_config": {"ringing_timeout_secs": ringing_timeout_secs},
            "conversation_initiation_client_data": {"dynamic_variables": dynamic_variables},
        }
        resp = await self._request("POST", "/twilio/outbound-call", json=body)
        payload = resp.json()
        return OutboundCallResult(
            success=payload.get("success", False),
            conversation_id=payload.get("conversation_id"),
            call_sid=payload.get("callSid"),
            message=payload.get("message"),
        )
