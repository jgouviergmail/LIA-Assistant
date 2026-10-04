"""Own-account admission and idempotent browser-reported Dynamic Maps loads.

The report observes Map construction, not a Google invoice. SDK/key failures
before construction are not loads. No charge is invented at admission time.
"""

import hashlib
import hmac
import time
from uuid import UUID, uuid4

from sqlalchemy import select, text

from src.core.config import settings
from src.core.exceptions import raise_configuration_missing, raise_invalid_input
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.google_api.models import GoogleApiUsageLog
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.infrastructure.database.session import get_db_context

LOAD_TOKEN_TTL_SECONDS = 3600
MAPS_API = "maps_javascript"
MAPS_ENDPOINT = "/dynamicmap"


def _signature(payload: str, user_id: UUID) -> str:
    return hmac.new(
        settings.secret_key.encode(), f"{user_id}:{payload}".encode(), hashlib.sha256
    ).hexdigest()


def issue_load_token(user_id: UUID) -> str:
    payload = f"{uuid4()}.{int(time.time()) + LOAD_TOKEN_TTL_SECONDS}"
    return f"{payload}.{_signature(payload, user_id)}"


def verify_load_token(token: str, user_id: UUID) -> UUID:
    if len(token) > 200 or not token.isascii() or token.count(".") != 2:
        raise_invalid_input("Invalid map load token")
    nonce, expiry, signature = token.split(".")
    payload = f"{nonce}.{expiry}"
    if not hmac.compare_digest(signature, _signature(payload, user_id)):
        raise_invalid_input("Invalid map load token")
    try:
        grant_id = UUID(nonce)
        expires_at = int(expiry)
    except ValueError:
        raise_invalid_input("Invalid map load token")
    if expires_at <= time.time():
        raise_invalid_input("Expired map load token")
    return grant_id


def _configured_maps_key() -> str:
    return settings.google_maps_browser_api_key.strip() or (settings.google_api_key or "").strip()


def browser_maps_key() -> str:
    key = _configured_maps_key()
    if not key:
        raise_configuration_missing("google_maps", "api_key")
    usd, eur, _ = GoogleApiPricingService.get_cost_per_request(MAPS_API, MAPS_ENDPOINT)
    if usd <= 0 or eur <= 0:
        raise_configuration_missing("google_maps", "dynamic_maps_pricing")
    return key


async def record_map_load(grant_id: UUID, user_id: UUID) -> None:
    """Serialize reports across workers, and acknowledge only durable metering.

    Retried/lost HTTP acknowledgements reuse the grant's synthetic run. A
    PostgreSQL transaction lock serializes competing reports; the tracker owns
    a separate session and persists every ledger family in its own transaction.
    No database lock is held during SDK/network loading in the browser.
    """
    run_id = f"map_{grant_id.hex}"
    async with get_db_context() as db:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": grant_id.int % (2**63)},
        )
        existing = await db.scalar(
            select(GoogleApiUsageLog.id).where(
                GoogleApiUsageLog.run_id == run_id,
                GoogleApiUsageLog.user_id == user_id,
                GoogleApiUsageLog.api_name == MAPS_API,
                GoogleApiUsageLog.endpoint == MAPS_ENDPOINT,
            )
        )
        if existing is not None:
            return
        async with TrackingContext(
            run_id, user_id, "interactive_map", None, auto_commit=False
        ) as tracker:
            track_google_api_call("maps_javascript", "/dynamicmap")
            try:
                await tracker.commit(strict=True)
            finally:
                TrackingContext.cleanup_run_records(run_id)


def map_load_config() -> dict[str, object]:
    """Public availability/estimate only; credentials never enter /config."""
    if not _configured_maps_key():
        return {"enabled": False}
    usd, eur, _ = GoogleApiPricingService.get_cost_per_request(MAPS_API, MAPS_ENDPOINT)
    if usd <= 0 or eur <= 0:
        return {"enabled": False}
    return {"enabled": True, "estimated_cost_eur": str(eur)}
