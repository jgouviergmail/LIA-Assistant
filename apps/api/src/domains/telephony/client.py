"""Async client for the ElevenLabs ElevenAgents API (per-user API key).

Endpoints verified against the current ElevenAgents docs (2026 rebrand). Exact
request-body field paths marked "spike" are to be confirmed by the P2.0 vertical
slice against a real account before go-live.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    data_collection: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Build the agent config body shared by create_agent and update_agent.

    One source of truth: whatever is covered by the config fingerprint
    (``agent_prompt.agent_config_fingerprint``) is exactly what gets sent.

    The body carries what is LIA's and nothing the portal administers (owner
    decision, 2026-09-16): the model and its reasoning effort, the language,
    the voice, the audio format and the duration cap are configured on the
    ElevenLabs portal, for the agent, and changed there without restarting
    the application. Sent from here they would overwrite the portal on every
    sync — and the vendor MERGES a PATCH with what the agent stores, then
    validates the pair: measured on production 2026-09-16, a pinned ``llm``
    collided with the portal's ``reasoning_effort`` (« Not supported
    reasoning effort ») and every verification and owner call was refused.
    What LIA sends is its own: the name, the prompt, the greeting, the system
    tools the prompt relies on, the data-collection contract and the override
    permission for the two fields a mandate renders per call.
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
    body: dict[str, Any] = {
        "name": name,
        "conversation_config": {
            "agent": {"prompt": prompt_config, "first_message": first_message},
        },
    }
    # The per-call override permission (lot 2). The owner's own call and the
    # verification call replace the prompt and the greeting of the ONE
    # provisioned agent through
    # ``conversation_initiation_client_data.conversation_config_override``;
    # the vendor refuses the override unless the agent allows each field.
    # Measured 2026-09-16: a PATCH carrying this block REPLACES the omitted
    # booleans with false, so the whole block is sent every time — and only
    # what a mandate uses is opened (a permission nobody uses is a surface
    # nobody watches).
    body["platform_settings"] = {"overrides": override_permissions()}
    if data_collection:
        body["platform_settings"]["data_collection"] = {
            field["identifier"]: {
                "type": field["type"],
                "description": field["description"],
            }
            for field in data_collection
        }
    return body


def override_permissions() -> dict[str, Any]:
    """What a per-call override may replace on the provisioned agent.

    One function read by the body AND the fingerprint, so they cannot
    disagree. Exactly the two fields a mandate renders per call — the prompt
    and the greeting. The language and the duration cap are the portal's
    (owner decision, 2026-09-16), and the live tools are attached to the
    AGENT rather than named per call: measured on a real owner call
    2026-09-16, the vendor refuses ``tool_ids`` inside an override (« Tool
    IDs not attached to this agent ») and the call dies at pickup.

    Returns:
        The ``platform_settings.overrides`` block, complete — the vendor
        replaces every omitted boolean with false on PATCH.
    """
    return {
        "conversation_config_override": {
            "agent": {"prompt": {"prompt": True}, "first_message": True},
        },
        "custom_llm_extra_body": False,
        "enable_conversation_initiation_client_data_from_webhook": False,
    }


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
        data_collection: list[dict[str, str]] | None = None,
    ) -> str:
        """Create a LIA-controlled agent; returns its ``agent_id``.

        The agent is created in the vendor's default language with the
        vendor's default voice and audio format: those, the model and the
        duration cap are administered on the ElevenLabs portal afterwards
        (owner decision, 2026-09-16 — see ``docs/technical/TELEPHONY.md``,
        activation runbook). A sync never touches them.

        The ``end_call`` system tool is always enabled — without it the agent
        can NEVER hang up and the line stays open after the goodbyes (observed).
        ``voicemail_detection`` supports the prompt's voicemail behavior.

        ``data_collection`` declares the structured fields the agent must extract
        during the call (their identifiers are the contract with the post-call
        webhook — see ``return_synthesis._extract_structured``). Without it the
        agent collects nothing and ``structured_data`` stays empty.

        Field paths measured against a real account (2026-09-16): the prompt
        text under ``conversation_config.agent.prompt.prompt``, the
        data-collection contract under ``platform_settings.data_collection``,
        ``built_in_tools`` an object keyed by tool name.
        """
        body = _agent_config_body(
            name=name,
            system_prompt=system_prompt,
            first_message=first_message,
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
        data_collection: list[dict[str, str]] | None = None,
    ) -> None:
        """Update an existing agent in place with the SAME config body as create.

        Powers the lazy config re-sync: a prompt or greeting change reaches the
        provisioned agent on the next call, without deactivating the connector.
        Measured 2026-09-16: a PATCH is MERGED with the stored config, so what
        the portal administers survives a sync untouched.
        """
        body = _agent_config_body(
            name=name,
            system_prompt=system_prompt,
            first_message=first_message,
            data_collection=data_collection,
        )
        await self._request("PATCH", f"/agents/{agent_id}", json=body)
        logger.info("elevenlabs_agent_updated", agent_id=agent_id)

    async def set_agent_tool_ids(self, agent_id: str, tool_ids: Sequence[str]) -> None:
        """Attach exactly ``tool_ids`` to the agent (lot 7, an empty list detaches).

        The live tools serve the OWNER's call only, so they are attached to
        the agent before that call and detached after it, as one small PATCH
        of the prompt's ``tool_ids`` — the rest of the config is untouched
        (the vendor merges a PATCH). Measured 2026-09-16: the PATCH answers
        200 and reads back; naming the ids per call in the override instead is
        refused on a real call (« Tool IDs not attached to this agent »).

        Args:
            agent_id: The provisioned agent.
            tool_ids: The vendor tool ids the agent may call, or nothing.

        Raises:
            ElevenLabsAgentsError: On a vendor refusal.
        """
        body = {"conversation_config": {"agent": {"prompt": {"tool_ids": list(tool_ids)}}}}
        await self._request("PATCH", f"/agents/{agent_id}", json=body)
        logger.info("elevenlabs_agent_tools_set", agent_id=agent_id, tool_count=len(tool_ids))

    async def delete_agent(self, agent_id: str) -> None:
        """Best-effort delete of a LIA-created agent (deactivation cleanup)."""
        try:
            await self._request("DELETE", f"/agents/{agent_id}")
        except ElevenLabsAgentsError as exc:
            # The agent lives in the user's workspace — cleanup failure is non-fatal.
            logger.warning("elevenlabs_agent_delete_failed", agent_id=agent_id, detail=exc.detail)

    async def create_tool(self, body: dict[str, Any]) -> str:
        """Create a workspace webhook tool (lot 7); returns the vendor id.

        Measured 2026-09-16: ``POST /convai/tools`` answers 200 with the id
        under ``id``.

        Args:
            body: The ``tool_config`` envelope (``live_tools.webhook_tool_body``).

        Returns:
            The vendor's tool id.
        """
        resp = await self._request("POST", "/tools", json=body)
        tool_id: str = resp.json()["id"]
        logger.info("elevenlabs_tool_created", tool_id=tool_id)
        return tool_id

    async def delete_tool(self, tool_id: str) -> None:
        """Best-effort delete of a workspace tool, forced.

        Measured 2026-09-16: a tool still referenced by an agent — even a
        deleted one — answers 409 until ``?force=true``.

        Args:
            tool_id: The vendor's tool id.
        """
        try:
            await self._request("DELETE", f"/tools/{tool_id}", params={"force": "true"})
        except ElevenLabsAgentsError as exc:
            logger.warning("elevenlabs_tool_delete_failed", tool_id=tool_id, detail=exc.detail)

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
        conversation_config_override: dict[str, Any] | None = None,
    ) -> OutboundCallResult:
        """Place an outbound call. Recording is disabled at the API level (D-8).

        ``conversation_config_override`` replaces the agent's prompt and
        greeting for THIS call only (lot 2, owner and verification mandates);
        the agent must allow each field (``override_permissions``). None keeps
        the baked third-party mandate.
        """
        initiation: dict[str, Any] = {"dynamic_variables": dynamic_variables}
        if conversation_config_override is not None:
            initiation["conversation_config_override"] = conversation_config_override
        body = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "to_number": to_number,
            "call_recording_enabled": False,  # D-8: no recording, ever
            "telephony_call_config": {"ringing_timeout_secs": ringing_timeout_secs},
            "conversation_initiation_client_data": initiation,
        }
        resp = await self._request("POST", "/twilio/outbound-call", json=body)
        payload = resp.json()
        return OutboundCallResult(
            success=payload.get("success", False),
            conversation_id=payload.get("conversation_id"),
            call_sid=payload.get("callSid"),
            message=payload.get("message"),
        )
