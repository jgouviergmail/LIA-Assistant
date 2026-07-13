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


class ElevenLabsAgentsError(RuntimeError):
    """Raised when the ElevenLabs API returns a non-success response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"ElevenLabs API error {status_code}: {detail}")


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
            # Never log the api key; a short detail only.
            logger.warning(
                "elevenlabs_api_error",
                method=method,
                path=path,
                status_code=resp.status_code,
            )
            raise ElevenLabsAgentsError(resp.status_code, resp.text[:200])
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
        data_collection: list[dict[str, str]] | None = None,
    ) -> str:
        """Create a LIA-controlled agent; returns its ``agent_id``.

        ``data_collection`` declares the structured fields the agent must extract
        during the call (their identifiers are the contract with the post-call
        webhook — see ``return_synthesis._extract_structured``). Without it the
        agent collects nothing and ``structured_data`` stays empty.

        spike: confirm the exact prompt-text key (``conversation_config.agent.
        prompt.prompt``), the data-collection config path (assumed
        ``platform_settings.data_collection``) and where voicemail-detection +
        max-duration config live in the body before go-live.
        """
        body: dict[str, Any] = {
            "name": name,
            "conversation_config": {
                "agent": {
                    "prompt": {"prompt": system_prompt},
                    "first_message": first_message,
                    "language": language,
                },
            },
        }
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
        resp = await self._request("POST", "/agents/create", json=body)
        agent_id: str = resp.json()["agent_id"]
        logger.info("elevenlabs_agent_created", agent_id=agent_id)
        return agent_id

    async def delete_agent(self, agent_id: str) -> None:
        """Best-effort delete of a LIA-created agent (deactivation cleanup)."""
        try:
            await self._request("DELETE", f"/agents/{agent_id}")
        except ElevenLabsAgentsError as exc:
            # The agent lives in the user's workspace — cleanup failure is non-fatal.
            logger.warning("elevenlabs_agent_delete_failed", agent_id=agent_id, detail=exc.detail)

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
