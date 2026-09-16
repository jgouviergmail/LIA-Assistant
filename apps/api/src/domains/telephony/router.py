"""Telephony connector router — the per-user activation wizard (spec §4.2).

Endpoints are mounted only when ``TELEPHONY_ENABLED`` is set (see
``api/v1/routes.py``). The post-call ``/telephony/webhook`` + ``/telephony/calls``
endpoints are added in Phase 4.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_webhook_signature
from src.core.security.utils import encrypt_data
from src.core.session_dependencies import get_current_active_session
from src.core.user_display import resolve_user_display_name
from src.domains.chat.repository import ChatRepository
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.shared.phone_domains import PHONE_DOMAINS
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.identity import PhoneIdentity, TelephonyIdentityService
from src.domains.telephony.repository import TelephonyRepository
from src.domains.telephony.schemas import (
    TelephonyActivateRequest,
    TelephonyCallSummary,
    TelephonyCallUsage,
    TelephonyConnectorResponse,
    TelephonyIdentityConfirmRequest,
    TelephonyIdentityNumberRequest,
    TelephonyIdentityResponse,
    TelephonyIdentityUpdateRequest,
    TelephonyIdentityVerifyResponse,
    TelephonyKeyValidateRequest,
    TelephonyKeyValidateResponse,
)
from src.domains.telephony.spend import phone_call_run_id
from src.domains.telephony.verification import TelephonyVerificationService
from src.domains.telephony.webhook_handler import (
    SIGNATURE_HEADER,
    WebhookOutcome,
    authenticate_and_reconcile,
)
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_telephony import telephony_webhook_ignored_total

logger = get_logger(__name__)

router = APIRouter(
    prefix="/telephony",
    tags=["Telephony"],
    # Administrable capability: a switched-off feature refuses at the
    # door, not only in the planner catalogue.
    dependencies=capability_dependencies(PlatformCapability.TELEPHONY),
)


@router.post(
    "/connector/validate-key",
    response_model=TelephonyKeyValidateResponse,
    summary="Validate an ElevenLabs API key + list workspace numbers",
)
async def validate_key(
    body: TelephonyKeyValidateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyKeyValidateResponse:
    """Step 1 of the wizard: confirm the key and surface importable numbers."""
    service = TelephonyConnectorService(db)
    result = await service.validate_key(body.api_key)
    numbers = await service.list_numbers(body.api_key) if result.is_valid else []
    return TelephonyKeyValidateResponse(
        is_valid=result.is_valid, message=result.message, numbers=numbers
    )


@router.post(
    "/connector/activate",
    response_model=TelephonyConnectorResponse,
    summary="Provision the LIA agent and activate the telephony connector",
)
async def activate(
    body: TelephonyActivateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyConnectorResponse:
    """Steps 3–5 of the wizard: create the guardrailed agent + store the connector."""
    service = TelephonyConnectorService(db)
    user_name = resolve_user_display_name(user.full_name, user.email)
    connector = await service.activate(
        user_id=user.id,
        api_key=body.api_key,
        agent_phone_number_id=body.agent_phone_number_id,
        webhook_secret=body.webhook_secret,
        user_language=(user.language or settings.default_language),
        user_name=user_name,
        caller_number_display=body.caller_number_display,
    )
    metadata = connector.connector_metadata or {}
    logger.info("telephony_connector_activated_api", user_id=str(user.id))
    return TelephonyConnectorResponse(
        status="active",
        agent_id=str(metadata.get("agent_id", "")),
        agent_phone_number_id=str(metadata.get("agent_phone_number_id", "")),
    )


@router.delete(
    "/connector",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate telephony (delete the LIA agent + remove the connector)",
)
async def deactivate(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unlink telephony for the current user."""
    await TelephonyConnectorService(db).deactivate(user.id)
    logger.info("telephony_connector_deactivated_api", user_id=str(user.id))


@router.post(
    "/webhook",
    include_in_schema=False,
    summary="ElevenLabs post-call webhook",
)
async def telephony_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive the ElevenLabs post-call webhook (unauthenticated — per-user HMAC).

    Foreign-filter → resolve → agent match → per-user HMAC verify (see
    ``webhook_handler``). Returns 200 immediately and reconciles in the
    background; a forged signature on a known call is rejected (4xx). No PII is
    logged on any path.
    """
    body = await request.body()
    sig = request.headers.get(SIGNATURE_HEADER, "")
    auth = await authenticate_and_reconcile(
        body, sig, db, tolerance_seconds=settings.telephony_webhook_tolerance_seconds
    )

    if auth.outcome is WebhookOutcome.OK and auth.call is not None and auth.payload is not None:
        # Deferred import: keep the LLM/notification stack out of router import.
        from src.domains.telephony.return_synthesis import deliver_return_with_retry

        # T1 approach A: persist the ENCRYPTED webhook (it carries the transcript) as
        # a RECEIVED inbox row and COMMIT before responding 200. The vendor delivers
        # the webhook only once, so if the fire-and-forget synthesis below crashes,
        # the return reaper replays it from this durable, encrypted payload. The
        # transcript is purged the instant synthesis succeeds (mark_completed) — it
        # only rests on disk, encrypted, for the synthesis window (D-8).
        await TelephonyRepository(db).persist_return_inbox(
            auth.call.id,
            encrypted_payload=encrypt_data(json.dumps(auth.payload)),
            received_at=datetime.now(UTC),
        )
        safe_fire_and_forget(
            deliver_return_with_retry(auth.call.id, auth.payload), name="telephony_return"
        )
        return {"ok": True}

    telephony_webhook_ignored_total.labels(reason=auth.outcome.value).inc()
    if auth.outcome is WebhookOutcome.BAD_SIGNATURE:
        raise_invalid_webhook_signature("telephony")
    return {"ok": True}  # foreign / unknown / malformed → 200, silently dropped


@router.get(
    "/calls",
    response_model=list[TelephonyCallSummary],
    summary="List the current user's recent outbound calls",
)
async def list_calls(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TelephonyCallSummary]:
    """Return the user's recent calls (newest first) — status/summary only.

    The response model omits the encrypted ``callee_phone``; nothing sensitive is
    logged here (only a count at INFO).
    """
    calls = await TelephonyRepository(db).list_recent_for_user(user.id, limit=limit)
    logger.info("telephony_calls_listed", user_id=str(user.id), count=len(calls))
    # Lot 8: the bill of a call is the per-run summary under its own run id —
    # one batch read for the page, the meter's own vocabulary.
    summaries = await ChatRepository(db).get_token_summaries_by_run_ids(
        [phone_call_run_id(call.id) for call in calls]
    )
    listed: list[TelephonyCallSummary] = []
    for call in calls:
        summary = TelephonyCallSummary.model_validate(call)
        row = summaries.get(phone_call_run_id(call.id))
        if row is not None:
            summary = summary.model_copy(
                update={
                    "usage": TelephonyCallUsage(
                        tokens_in=row.total_prompt_tokens,
                        tokens_out=row.total_completion_tokens,
                        tokens_cache=row.total_cached_tokens,
                        cost_eur=float(row.total_cost_eur),
                        google_api_requests=row.google_api_requests,
                    )
                }
            )
        listed.append(summary)
    return listed


# ---------------------------------------------------------------------------
# The person's own number (lot 1 of the phone-as-a-channel programme)
# ---------------------------------------------------------------------------


def _identity_response(
    identity: PhoneIdentity, *, verification_pending: bool = False
) -> TelephonyIdentityResponse:
    """Project the service's identity onto the public schema."""
    return TelephonyIdentityResponse(
        phone_number=identity.phone_number,
        verified=identity.verified,
        verified_at=identity.verified_at,
        rich_context_enabled=identity.rich_context_enabled,
        disabled_domains=list(identity.disabled_domains),
        available_domains=list(PHONE_DOMAINS),
        verification_pending=verification_pending,
    )


async def _verification(db: AsyncSession) -> TelephonyVerificationService:
    return TelephonyVerificationService(db, redis=await get_redis_cache())


@router.get(
    "/identity",
    response_model=TelephonyIdentityResponse,
    summary="The current user's own phone number and its verification state",
)
async def get_identity(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyIdentityResponse:
    """Read the declared number, whether it was verified, and the context switch."""
    identity = await TelephonyIdentityService(db).get_identity(user.id)
    pending = await (await _verification(db)).pending(user.id)
    return _identity_response(identity, verification_pending=pending)


@router.post(
    "/identity/verify",
    response_model=TelephonyIdentityVerifyResponse,
    summary="Call the declared number and read a verification code aloud",
)
async def start_identity_verification(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyIdentityVerifyResponse:
    """Place the verification call; the code is kept server-side for its TTL."""
    started = await (await _verification(db)).start(
        user.id,
        language=user.language or settings.default_language,
        display_name=resolve_user_display_name(user.full_name, user.email),
    )
    return TelephonyIdentityVerifyResponse(
        call_id=started.call_id, expires_in_seconds=started.expires_in_seconds
    )


@router.post(
    "/identity/confirm",
    response_model=TelephonyIdentityResponse,
    summary="Type the spoken code back; the number is verified on a match",
)
async def confirm_identity_verification(
    body: TelephonyIdentityConfirmRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyIdentityResponse:
    """Judge the typed code (bounded attempts, constant-time compare)."""
    identity = await (await _verification(db)).confirm(
        user.id, body.code, language=user.language or settings.default_language
    )
    return _identity_response(identity)


@router.put(
    "/identity/number",
    response_model=TelephonyIdentityResponse,
    summary="Declare the current user's own phone number (stored encrypted, unverified)",
)
async def set_identity_number(
    body: TelephonyIdentityNumberRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyIdentityResponse:
    """Store the number in E.164; a changed number loses its verification."""
    identity = await TelephonyIdentityService(db).set_number(
        user.id, body.phone_number, language=user.language or settings.default_language
    )
    return _identity_response(identity)


@router.delete(
    "/identity/number",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget the current user's own phone number",
)
async def clear_identity_number(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Drop the number and its verification."""
    await TelephonyIdentityService(db).clear_number(user.id)


@router.patch(
    "/identity",
    response_model=TelephonyIdentityResponse,
    summary="Switch the rich context or the domains of owner calls",
)
async def update_identity(
    body: TelephonyIdentityUpdateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TelephonyIdentityResponse:
    """Persist the switches the body carries."""
    service = TelephonyIdentityService(db)
    identity = await service.get_identity(user.id)
    if body.rich_context_enabled is not None:
        identity = await service.set_rich_context(user.id, body.rich_context_enabled)
    if body.disabled_domains is not None:
        identity = await service.set_disabled_domains(
            user.id, body.disabled_domains, language=user.language or settings.default_language
        )
    return _identity_response(identity)
