"""Telephony call orchestration — ``TelephonyService.initiate_call`` (spec P3.4).

Called by ``execute_phone_call_draft`` once the user confirms the PHONE_CALL
draft. It re-checks the capability (connector active), enforces one active call
per user (F12 partial unique index, atomic), pre-fetches free/busy, creates the
``dialing`` row with the callee number encrypted, then dials via the user's
ElevenLabs agent and persists the conversation id for webhook reconciliation.

Vendor call costs are the user's own (D-9): nothing here is metered to money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.security import encrypt_data
from src.core.user_display import resolve_user_display_name
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.availability import build_availability_summary
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.users.models import User

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger(__name__)

_InitiateStatus = Literal["placed", "already_active", "not_configured", "failed"]


class TelephonyExecutionError(Exception):
    """Raised by the draft executor to surface a localized, non-crashing failure.

    The draft-executor framework catches this and renders ``str(self)`` as the
    (already localized) user-facing message — no traceback reaches the user.
    """


@dataclass(frozen=True)
class InitiateCallResult:
    """Outcome of an initiate-call attempt (no money, ever — D-9)."""

    status: _InitiateStatus
    call_id: UUID | None = None


class TelephonyService:
    """Places outbound calls for a confirmed PHONE_CALL draft."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        client_factory: Callable[[str], ElevenLabsAgentsClient] | None = None,
    ) -> None:
        self.db = db
        self._client_factory = client_factory or (lambda api_key: ElevenLabsAgentsClient(api_key))

    async def initiate_call(
        self,
        *,
        user_id: UUID,
        callee_display: str,
        callee_phone: str,
        objective: str,
        date_window: str | None,
        user_language: str,
    ) -> InitiateCallResult:
        """Dial the callee via the user's ElevenLabs agent.

        Args:
            user_id: Owner of the telephony connector.
            callee_display: Human-readable callee name (never the raw number).
            callee_phone: Plaintext E.164 number (stored encrypted; sent to the vendor).
            objective: What the agent must accomplish on the call.
            date_window: Free-text availability window hint (currently advisory —
                the pre-fetch window is [now, now + prefetch_window_days]).
            user_language: Language for the availability summary + agent.

        Returns:
            InitiateCallResult with the terminal status and the call id.
        """
        connector = await TelephonyConnectorService(self.db).get_active(user_id)
        if connector is None:
            return InitiateCallResult(status="not_configured")

        repo = TelephonyRepository(self.db)
        existing = await repo.get_active_for_user(user_id)
        if existing is not None:
            return InitiateCallResult(status="already_active", call_id=existing.id)

        metadata = connector.connector_metadata or {}
        agent_id = metadata.get("agent_id")
        agent_phone_number_id = metadata.get("agent_phone_number_id")
        creds = await ConnectorService(self.db).get_api_key_credentials(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if not agent_id or not agent_phone_number_id or creds is None:
            return InitiateCallResult(status="not_configured")

        now = datetime.now(UTC)
        window_start = now
        window_end = now + timedelta(days=settings.telephony_prefetch_window_days)

        user = await self.db.get(User, user_id)
        user_name = resolve_user_display_name(user.full_name, user.email) if user else ""
        user_tz = user.timezone if user and user.timezone else DEFAULT_USER_DISPLAY_TIMEZONE

        availability_summary = await build_availability_summary(
            user_id,
            window_start,
            window_end,
            ConnectorService(self.db),
            user_tz,
            user_language,
        )

        # Persist the dialing row AND COMMIT it BEFORE dialing. Two reasons:
        #  1. Crash-safety / reconciliation: the call_id is sent to the vendor as a
        #     dynamic variable, so the row MUST exist before the call is placed — a
        #     crash after dialing still leaves a row for the post-call webhook (or
        #     the stale reaper). Committing after the vendor call would risk an
        #     orphan call whose webhook can never reconcile (lost return).
        #  2. The vendor HTTP call is then never held inside a DB transaction (no
        #     connection nor uncommitted F12 row locked across external I/O).
        # The F12 partial unique index keeps "one active call per user" atomic.
        try:
            call = await repo.create(
                {
                    "user_id": user_id,
                    "callee_display": callee_display,
                    "callee_phone": encrypt_data(callee_phone),  # PII encrypted at rest
                    "objective": objective,
                    "objective_window_start": window_start,
                    "objective_window_end": window_end,
                    "status": PhoneCallStatus.DIALING,
                    "initiated_at": now,
                    "expires_at": now + timedelta(days=settings.telephony_call_retention_days),
                }
            )
            call_id = call.id  # capture before commit (may expire the ORM object)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            racing = await repo.get_active_for_user(user_id)
            return InitiateCallResult(
                status="already_active", call_id=racing.id if racing else None
            )

        dynamic_variables = {
            "user_name": user_name,
            "callee_name": callee_display,
            "objective": objective,
            "availability_summary": availability_summary,
            "recording_disclosure": "",  # D-8: recording disabled → no disclosure
            "call_id": str(call_id),  # webhook reconciliation key
        }

        # Vendor HTTP call — OUTSIDE any DB transaction.
        client = self._client_factory(creds.api_key)
        try:
            result = await client.initiate_outbound_call(
                agent_id=agent_id,
                agent_phone_number_id=agent_phone_number_id,
                to_number=callee_phone,  # plaintext to the vendor; only the column is encrypted
                dynamic_variables=dynamic_variables,
                ringing_timeout_secs=settings.telephony_ringing_timeout_seconds,
            )
        except ElevenLabsAgentsError as exc:
            await repo.mark_dial_failed(call_id, error=f"initiate_failed:{exc.status_code}")
            logger.warning(
                "telephony_initiate_call_failed",
                user_id=str(user_id),
                call_id=str(call_id),
                status_code=exc.status_code,
            )
            return InitiateCallResult(status="failed", call_id=call_id)

        await repo.set_conversation_id(call_id, result.conversation_id)
        logger.info("telephony_call_initiated", user_id=str(user_id), call_id=str(call_id))
        return InitiateCallResult(status="placed", call_id=call_id)
