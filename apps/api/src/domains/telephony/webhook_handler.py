"""ElevenLabs post-call webhook: foreign-filter → per-user HMAC → reconcile.

The webhook is unauthenticated (no session) and the HMAC secret is per-user, so
we cannot verify a signature until we know *which* call it is. The order is
therefore deliberate and security-critical:

1. Parse the untrusted body; extract our injected ``call_id``.
2. Resolve ``call_id → PhoneCall`` (unknown ⇒ ignore — could be another
   workspace's webhook; never reveal existence).
3. Check the payload ``agent_id`` matches the call's connector agent (mismatch
   ⇒ ignore).
4. Only now, with the resolved connector's ``api_secret``, verify the HMAC over
   ``"{timestamp}.{body}"`` with a strict replay window (bad ⇒ reject 4xx — a
   known call with a forged signature is a genuine security event).

spike (P2.0): confirm the exact signature header name + payload field paths
against a real ElevenLabs account before go-live. Paths are read defensively so
a shape drift degrades to "ignored", never a crash.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.models import PhoneCall
from src.domains.telephony.repository import TelephonyRepository

logger = structlog.get_logger(__name__)

# spike: ElevenLabs post-call webhook signature header ("t=<ts>,v0=<hex>").
SIGNATURE_HEADER = "ElevenLabs-Signature"


class WebhookOutcome(str, Enum):
    """Result of authenticating a post-call webhook."""

    OK = "ok"
    IGNORED_MALFORMED = "malformed"
    IGNORED_UNKNOWN = "unknown_call"
    IGNORED_AGENT_MISMATCH = "agent_mismatch"
    BAD_SIGNATURE = "bad_signature"


@dataclass(frozen=True)
class WebhookAuth:
    """Authentication outcome + the reconciled call/payload on success."""

    outcome: WebhookOutcome
    call: PhoneCall | None = None
    payload: dict[str, Any] | None = None


def _nested(payload: dict[str, Any], *path: str) -> Any:
    """Walk a dotted path through nested dicts, returning None if any hop misses."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_call_id(payload: dict[str, Any]) -> str | None:
    """Extract our injected ``call_id`` (echoed back in dynamic_variables)."""
    value = _nested(
        payload, "data", "conversation_initiation_client_data", "dynamic_variables", "call_id"
    )
    return value if isinstance(value, str) and value else None


def extract_agent_id(payload: dict[str, Any]) -> str | None:
    """Extract the ElevenLabs ``agent_id`` that handled the conversation."""
    value = _nested(payload, "data", "agent_id")
    return value if isinstance(value, str) and value else None


def verify_signature(body: bytes, sig_header: str, secret: str, tolerance_seconds: int) -> bool:
    """Verify an ``ElevenLabs-Signature`` HMAC header, Stripe-style.

    The header is ``t=<unix_ts>,v0=<hex_hmac>``; the signed payload is
    ``f"{t}.{body}"`` and the digest is HMAC-SHA256 with the workspace secret.
    Rejects a timestamp outside ``tolerance_seconds`` (replay protection) and
    compares digests in constant time.
    """
    if not sig_header or not secret:
        return False

    timestamp: str | None = None
    provided: str | None = None
    for part in sig_header.split(","):
        key, _, val = part.strip().partition("=")
        if key == "t":
            timestamp = val
        elif key == "v0":
            provided = val
    if not timestamp or not provided:
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False
    now = int(datetime.now(UTC).timestamp())
    if abs(now - ts) > tolerance_seconds:
        return False

    signed = f"{timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


async def authenticate_and_reconcile(
    body: bytes,
    sig_header: str,
    db: AsyncSession,
    *,
    tolerance_seconds: int,
) -> WebhookAuth:
    """Foreign-filter → resolve → agent match → per-user HMAC verify.

    Returns a :class:`WebhookAuth` whose ``outcome`` tells the router whether to
    process (``OK``), silently drop with a 200 (any ``IGNORED_*``), or reject
    with a 4xx (``BAD_SIGNATURE``). No PII is logged on any path.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError, ValueError:
        return WebhookAuth(WebhookOutcome.IGNORED_MALFORMED)
    if not isinstance(payload, dict):
        return WebhookAuth(WebhookOutcome.IGNORED_MALFORMED)

    call_id_raw = extract_call_id(payload)
    if not call_id_raw:
        return WebhookAuth(WebhookOutcome.IGNORED_MALFORMED)
    try:
        call_id = UUID(call_id_raw)
    except ValueError:
        return WebhookAuth(WebhookOutcome.IGNORED_MALFORMED)

    call = await TelephonyRepository(db).get_by_call_id(call_id)
    if call is None:
        return WebhookAuth(WebhookOutcome.IGNORED_UNKNOWN)

    connector_service = ConnectorService(db)
    connector = await connector_service.repository.get_by_user_and_type(
        call.user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    connector_agent_id = (connector.connector_metadata or {}).get("agent_id") if connector else None
    if not connector_agent_id or extract_agent_id(payload) != connector_agent_id:
        return WebhookAuth(WebhookOutcome.IGNORED_AGENT_MISMATCH)

    creds = await connector_service.get_api_key_credentials(
        call.user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    secret = creds.api_secret if creds else None
    if not secret or not verify_signature(body, sig_header, secret, tolerance_seconds):
        return WebhookAuth(WebhookOutcome.BAD_SIGNATURE, call=call)

    return WebhookAuth(WebhookOutcome.OK, call=call, payload=payload)
