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
from src.core.time_utils import format_datetime_for_display
from src.core.user_display import resolve_user_display_name
from src.domains.connectors.models import Connector, ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config
from src.domains.telephony.availability import build_availability_summary
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.users.models import User

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger(__name__)

# "failed"   → transient (network, vendor 5xx): retrying can work.
# "rejected" → the vendor DECLINED for a configuration reason (unverified
#              source number, exhausted credit). Retrying changes nothing, so
#              the two must not share a message that says "try again".
_InitiateStatus = Literal["placed", "already_active", "not_configured", "failed", "rejected"]

# Vendor conversation statuses meaning the call itself is over ("processing" =
# ended, transcript still being prepared). spike: values per the conversations
# API — used by the self-healing one-active-call guard.
_VENDOR_TERMINAL_CONVERSATION_STATUSES = frozenset({"done", "failed", "processing"})


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
        self._client_factory = client_factory or ElevenLabsAgentsClient

    async def _resolve_zombie_call(
        self,
        existing: PhoneCall,
        repo: TelephonyRepository,
        api_key: str,
    ) -> bool:
        """Try to close an active-looking row that is actually over (two tiers).

        Tier 1 — vendor probe: when the row carries a conversation id, ask
        ElevenLabs for the conversation status; a terminal status means the call
        ended but the webhook never arrived (no public webhook in dev, webhook
        lost in prod) → close the row and let the new call proceed immediately.
        Tier 2 — stale threshold: same rule as the reaper, applied inline so the
        guard never depends on the reaper's 5-minute tick.

        Best-effort: any vendor error falls through to the threshold. Returns
        True when the row was closed (``close_zombie`` is the atomic transition
        and keeps refusing RECEIVED rows — their return is in flight).
        """
        conversation_id = existing.elevenlabs_conversation_id
        if conversation_id:
            try:
                status = await self._client_factory(api_key).get_conversation_status(
                    conversation_id
                )
            except ElevenLabsAgentsError as exc:
                if exc.status_code == 404:
                    # The conversation document is GONE vendor-side (observed:
                    # a mid-call connector deactivation deleted the agent and
                    # its conversation — the end-of-call webhook can never
                    # arrive, and the row blocked calls until the stale
                    # threshold). A missing conversation is terminal by
                    # definition — but only past a short grace window, in case
                    # a freshly dialed conversation is not readable yet
                    # (closing a LIVE call would allow a concurrent second one).
                    initiated_at = existing.initiated_at
                    grace = timedelta(seconds=settings.telephony_probe_not_found_grace_seconds)
                    if initiated_at is not None and datetime.now(UTC) - initiated_at >= grace:
                        closed = await repo.close_zombie(existing.id, error="conversation_gone")
                        if closed:
                            logger.info(
                                "telephony_zombie_closed_conversation_gone",
                                call_id=str(existing.id),
                            )
                            return True
                logger.debug(
                    "telephony_zombie_probe_failed",
                    call_id=str(existing.id),
                    status_code=exc.status_code,
                )
            else:
                if status in _VENDOR_TERMINAL_CONVERSATION_STATUSES:
                    closed = await repo.close_zombie(existing.id, error="ended_no_webhook")
                    if closed:
                        logger.info(
                            "telephony_zombie_closed_vendor_terminal",
                            call_id=str(existing.id),
                            vendor_status=status,
                        )
                        return True

        initiated_at = existing.initiated_at
        stale_after = timedelta(minutes=settings.telephony_stale_call_timeout_minutes)
        if initiated_at is not None and datetime.now(UTC) - initiated_at >= stale_after:
            closed = await repo.close_zombie(existing.id, error="stale_no_webhook")
            if closed:
                logger.info("telephony_zombie_closed_stale", call_id=str(existing.id))
                return True
        return False

    async def _sync_agent_config(
        self,
        *,
        connector: Connector,
        api_key: str,
        agent_id: str,
        user_language: str,
        user_name: str,
    ) -> None:
        """PATCH the vendor agent in place when the local config drifted.

        Compares the current config fingerprint (prompt file + voice/TTS/format/
        duration settings) against the one stored at activation. Best-effort: a
        vendor failure logs a warning and the call proceeds on the old config —
        a sync must never block a call. On success the new fingerprint is
        committed (short transaction, before the dialing-row one).
        """
        cfg = build_agent_config(user_language, user_name)
        current = agent_config_fingerprint(
            cfg,
            llm_model=settings.telephony_agent_llm_model or None,
            tts_model_id=settings.telephony_agent_tts_model_id,
            voice_id=settings.telephony_agent_voice_id or None,
            audio_format=settings.telephony_agent_audio_format or None,
            max_duration_seconds=settings.telephony_max_call_duration_seconds,
        )
        metadata = connector.connector_metadata or {}
        if metadata.get("agent_config_hash") == current:
            return

        try:
            await self._client_factory(api_key).update_agent(
                agent_id,
                name=cfg.name,
                system_prompt=cfg.system_prompt,
                first_message=cfg.first_message,
                language=cfg.language,
                llm_model=settings.telephony_agent_llm_model or None,
                tts_model_id=settings.telephony_agent_tts_model_id,
                voice_id=settings.telephony_agent_voice_id or None,
                audio_format=settings.telephony_agent_audio_format or None,
                max_duration_seconds=settings.telephony_max_call_duration_seconds,
                data_collection=cfg.data_collection,
            )
        except ElevenLabsAgentsError as exc:
            logger.warning(
                "telephony_agent_sync_failed",
                agent_id=agent_id,
                status_code=exc.status_code,
            )
            return

        # JSONB rule: always assign a NEW dict (in-place mutation is silently
        # dropped by SQLAlchemy). Committed now — the dialing row opens its own
        # transaction right after.
        connector.connector_metadata = {**metadata, "agent_config_hash": current}
        await self.db.commit()
        logger.info("telephony_agent_synced", agent_id=agent_id)

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

        metadata = connector.connector_metadata or {}
        agent_id = metadata.get("agent_id")
        agent_phone_number_id = metadata.get("agent_phone_number_id")
        creds = await ConnectorService(self.db).get_api_key_credentials(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if not agent_id or not agent_phone_number_id or creds is None:
            return InitiateCallResult(status="not_configured")

        # One-active-call guard with SELF-HEALING: a row stuck DIALING because
        # its webhook never arrived used to block the next call until the stale
        # reaper's 5-minute tick happened to sweep it (observed: a call refused
        # 5 seconds BEFORE the sweep, then the retry passed). The guard now
        # closes the zombie itself when the vendor says the conversation ended
        # or the stale threshold elapsed.
        repo = TelephonyRepository(self.db)
        existing = await repo.get_active_for_user(user_id)
        if existing is not None:
            cleared = await self._resolve_zombie_call(existing, repo, creds.api_key)
            if not cleared:
                return InitiateCallResult(status="already_active", call_id=existing.id)

        now = datetime.now(UTC)
        window_start = now
        window_end = now + timedelta(days=settings.telephony_prefetch_window_days)

        user = await self.db.get(User, user_id)
        user_name = resolve_user_display_name(user.full_name, user.email) if user else ""
        user_tz = user.timezone if user and user.timezone else DEFAULT_USER_DISPLAY_TIMEZONE

        # Lazy agent re-sync (best-effort, vendor HTTP outside any transaction):
        # prompt/settings changes reach the provisioned agent on the next call
        # instead of requiring a connector deactivate/reactivate cycle.
        await self._sync_agent_config(
            connector=connector,
            api_key=creds.api_key,
            agent_id=agent_id,
            user_language=user_language,
            user_name=user_name,
        )

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
            # Temporal anchor — the voice agent has no clock of its own: without
            # "today" a callee's "tomorrow at 10" is unresolvable (observed on a
            # real call: "tomorrow"=Saturday spoken back as Sunday). Same
            # formatter as the availability summary (user tz + language).
            "current_datetime": format_datetime_for_display(now, user_tz, user_language),
            "recording_disclosure": "",  # D-8: recording disabled → no disclosure
            "call_id": str(call_id),  # webhook reconciliation key
        }

        # Vendor HTTP call — OUTSIDE any DB transaction.
        return await self._dial_and_interpret(
            api_key=creds.api_key,
            repo=repo,
            user_id=user_id,
            call_id=call_id,
            agent_id=agent_id,
            agent_phone_number_id=agent_phone_number_id,
            callee_phone=callee_phone,
            dynamic_variables=dynamic_variables,
        )

    async def _dial_and_interpret(
        self,
        *,
        api_key: str,
        repo: TelephonyRepository,
        user_id: UUID,
        call_id: UUID,
        agent_id: str,
        agent_phone_number_id: str,
        callee_phone: str,
        dynamic_variables: dict[str, str],
    ) -> InitiateCallResult:
        """Place the call and turn the vendor's answer into a terminal status.

        Extracted from :meth:`initiate_call` because reading that answer is a
        subject of its own — the vendor has three ways of saying something other
        than "placed", and only one of them is an HTTP error. Keeping the four
        branches here also keeps the caller under the complexity ratchet.

        The DIALING row already exists and is committed; this method owns its
        transition. It runs entirely outside any DB transaction.

        Args:
            api_key: Vendor credential of the user's connector.
            repo: Repository bound to the caller's session.
            user_id: Owner of the call (logging only).
            call_id: The committed DIALING row to transition.
            agent_id: Provisioned vendor agent.
            agent_phone_number_id: Vendor-side source number.
            callee_phone: Plaintext E.164 number sent to the vendor.
            dynamic_variables: Per-call variables, ``call_id`` included.

        Returns:
            ``placed``, ``failed`` (transient) or ``rejected`` (configuration).
        """
        try:
            result = await self._client_factory(api_key).initiate_outbound_call(
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

        # The vendor answers 200 even when it REFUSES to dial (unverified number,
        # exhausted credit, bad phone id): the rejection lives in the body, as
        # `success: false`. Ignoring it left a DIALING row that no call would
        # ever end — and, having no conversation id, one the self-healing probe
        # cannot even ask about, so it blocked every further call until the
        # 15-minute stale threshold. Observed in dev: a user unable to place a
        # call for a quarter of an hour after a silent refusal.
        if not result.success:
            await repo.mark_dial_failed(call_id, error=f"initiate_rejected:{result.message or '?'}")
            logger.warning(
                "telephony_initiate_call_rejected",
                user_id=str(user_id),
                call_id=str(call_id),
                vendor_message=result.message,
            )
            return InitiateCallResult(status="rejected", call_id=call_id)

        await repo.set_conversation_id(call_id, result.conversation_id)
        if not result.conversation_id:
            # Accepted but unidentifiable: the call may well be ringing, so the
            # row STAYS active (closing it would allow a concurrent second
            # call). It is simply unprobeable — the stale threshold is then the
            # only way out, and that is worth saying out loud.
            logger.warning(
                "telephony_call_initiated_without_conversation_id",
                user_id=str(user_id),
                call_id=str(call_id),
            )
        logger.info("telephony_call_initiated", user_id=str(user_id), call_id=str(call_id))
        return InitiateCallResult(status="placed", call_id=call_id)
