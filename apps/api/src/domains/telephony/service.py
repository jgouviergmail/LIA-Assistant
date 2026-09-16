"""Telephony call orchestration — ``TelephonyService.initiate_call`` (spec P3.4).

Called by ``execute_phone_call_draft`` once the user confirms the PHONE_CALL
draft. It re-checks the capability (connector active), enforces one active call
per user (F12 partial unique index, atomic), pre-fetches free/busy, creates the
``dialing`` row with the callee number encrypted, then dials via the user's
ElevenLabs agent and persists the conversation id for webhook reconciliation.

Vendor call costs are the user's own (D-9): nothing here is metered to money.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
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
from src.domains.personalities.service import PersonalityService
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config
from src.domains.telephony.availability import AvailabilityRead, build_availability
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.live_tools import (
    LiveToolBinding,
    attach_live_tools,
    live_tools_attached,
)
from src.domains.telephony.mandates import MandateInputs, build_override, mandate_for
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository
from src.domains.users.models import User

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = structlog.get_logger(__name__)

# "failed"   → transient (network, vendor 5xx): retrying can work.
# "rejected" → the vendor DECLINED for a configuration reason (unverified
#              source number, exhausted credit). Retrying changes nothing, so
#              the two must not share a message that says "try again".
# "agent_sync_failed" → an owner or verification mandate could not be
#              installed on the vendor agent (the PATCH failed). Dialling
#              anyway would serve the owner the stranger's rules, so the
#              call is refused; retrying can work once the vendor answers.
_InitiateStatus = Literal[
    "placed",
    "already_active",
    "not_configured",
    "failed",
    "rejected",
    "auth_failed",
    "agent_sync_failed",
]

#: The consultation surface the dial path records on (ADR-263): the calendar
#: is opened from here, not from a tool, so the gate never sees it.
_SURFACE = "phone_call"
_AVAILABILITY_SECTION = "availability"

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


@dataclass(frozen=True)
class _ActiveConnector:
    """The provisioned agent, its number and its key — what a dial needs."""

    connector: Connector
    agent_id: str
    agent_phone_number_id: str
    api_key: str


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
    ) -> bool:
        """PATCH the vendor agent in place when the local config drifted.

        Compares the current config fingerprint (prompt file + greeting + data
        contract + the override permission — nothing the portal administers)
        against the one stored at activation. Best-effort for the THIRD-PARTY
        mandate: a vendor failure
        logs a warning and the call proceeds on the old config — a sync must
        never block a call. The owner and verification mandates read the
        verdict instead: without the permission the vendor refuses their
        override, and dialling would serve the owner the stranger's rules.
        On success the new fingerprint is committed (short transaction, before
        the dialing-row one).

        Returns:
            True when the agent is in sync (already, or after this PATCH).
        """
        cfg = build_agent_config(user_language, user_name)
        current = agent_config_fingerprint(cfg)
        metadata = connector.connector_metadata or {}
        if metadata.get("agent_config_hash") == current:
            return True

        try:
            await self._client_factory(api_key).update_agent(
                agent_id,
                name=cfg.name,
                system_prompt=cfg.system_prompt,
                first_message=cfg.first_message,
                data_collection=cfg.data_collection,
            )
        except ElevenLabsAgentsError as exc:
            logger.warning(
                "telephony_agent_sync_failed",
                agent_id=agent_id,
                status_code=exc.status_code,
            )
            return False

        # JSONB rule: always assign a NEW dict (in-place mutation is silently
        # dropped by SQLAlchemy). Committed now — the dialing row opens its own
        # transaction right after.
        connector.connector_metadata = {**metadata, "agent_config_hash": current}
        await self.db.commit()
        logger.info("telephony_agent_synced", agent_id=agent_id)
        return True

    async def _arm_live_tools(
        self,
        active: _ActiveConnector,
        kind: CallKind,
        live_tools: Sequence[LiveToolBinding],
    ) -> tuple[LiveToolBinding, ...]:
        """Put the agent in the tool state THIS call needs (lot 7).

        The live tools serve the owner's call only, and the vendor refuses
        them per call (measured 2026-09-16: « Tool IDs not attached to this
        agent », the call dies at pickup), so they live on the AGENT between
        the dial and the end of the owner call. Before an owner call with
        tools they are attached; before any other call, an agent still
        carrying them (a webhook that never came) is detached first — a
        stranger is never phoned by an agent holding the owner's lookups.
        Vendor HTTP outside any transaction; the connector's new state is
        committed before the dialing row opens its own.

        Args:
            active: The provisioned agent and its key.
            kind: The mandate of the call about to leave.
            live_tools: The bindings an owner call was handed.

        Returns:
            The bindings the prompt may name: what was attached, or nothing
            when the attach was refused (a call without lookups beats a
            prompt promising lookups the agent cannot make).
        """
        wanted = tuple(live_tools) if kind is CallKind.SELF else ()
        if not wanted and not live_tools_attached(active.connector):
            return ()
        client = self._client_factory(active.api_key)
        ids = [binding.vendor_id for binding in wanted]
        if not await attach_live_tools(client, active.connector, ids):
            return ()
        await self.db.commit()
        return wanted

    async def _personality_for(self, user_id: UUID) -> str:
        """The instruction the person configured for LIA's personality (lot 9).

        The same door the chat and the voice flow read; best-effort, because
        a voice with the default manner beats no call at all.
        """
        try:
            return str(await PersonalityService(self.db).get_prompt_instruction_for_user(user_id))
        except Exception as exc:  # noqa: BLE001 — a personality is colour, never a gate
            logger.warning(
                "telephony_personality_unreadable",
                user_id=str(user_id),
                error_type=type(exc).__name__,
            )
            return ""

    async def _read_availability(
        self,
        *,
        user_id: UUID,
        window_start: datetime,
        window_end: datetime,
        user_tz: str,
        user_language: str,
    ) -> AvailabilityRead:
        """Read the free/busy projection and RECORD that the calendar was opened.

        The read happens on the dial path, through a client, so the tool gate
        never sees it: the service files the consultation itself (ADR-263). A
        calendar that could not be read files ``failed``; no calendar at all
        opened nothing and files nothing.
        """
        started = time.monotonic()
        read = await build_availability(
            user_id, window_start, window_end, ConnectorService(self.db), user_tz, user_language
        )
        if read.opened:
            record_surface_consultations(
                surface=_SURFACE,
                user_id=user_id,
                opened=[_AVAILABILITY_SECTION],
                failed=[_AVAILABILITY_SECTION] if read.failed else [],
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return read

    async def initiate_call(
        self,
        *,
        user_id: UUID,
        callee_display: str,
        callee_phone: str,
        objective: str,
        date_window: str | None,
        user_language: str,
        kind: CallKind = CallKind.THIRD_PARTY,
        user_context: str = "",
        verification_code: str = "",
        live_tools: Sequence[LiveToolBinding] = (),
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
            kind: Which mandate the call runs under (lot 2). The baked agent
                serves ``THIRD_PARTY``; ``SELF`` and ``VERIFICATION`` send a
                per-call override the agent must have been synced to allow.
            user_context: The rendered context block of an owner call (lot 4);
                "" when the person switched it off or none was built.
            verification_code: The digits a ``VERIFICATION`` call reads aloud.
            live_tools: The webhook tools an owner call may use (lot 7),
                already provisioned vendor-side by the caller and attached
                to the agent here for the call; empty when the flag is off
                or nothing is available.

        Returns:
            InitiateCallResult with the terminal status and the call id.
        """
        mandate = mandate_for(kind)
        active = await self._active_connector(user_id)
        if active is None:
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
            cleared = await self._resolve_zombie_call(existing, repo, active.api_key)
            if not cleared:
                return InitiateCallResult(status="already_active", call_id=existing.id)

        now = datetime.now(UTC)
        window_start = now
        window_end = now + timedelta(days=settings.telephony_prefetch_window_days)

        user = await self.db.get(User, user_id)
        user_name = resolve_user_display_name(user.full_name, user.email) if user else ""
        user_tz = user.timezone if user and user.timezone else DEFAULT_USER_DISPLAY_TIMEZONE

        # Lazy agent re-sync (vendor HTTP outside any transaction): prompt and
        # settings changes reach the provisioned agent on the next call instead
        # of requiring a connector deactivate/reactivate cycle. Best-effort for
        # the baked mandate; MANDATORY for an override, whose permission travels
        # in this very sync.
        synced = await self._sync_agent_config(
            connector=active.connector,
            api_key=active.api_key,
            agent_id=active.agent_id,
            user_language=user_language,
            user_name=user_name,
        )
        if mandate.overrides_agent and not synced:
            logger.warning(
                "telephony_override_refused_unsynced_agent",
                user_id=str(user_id),
                kind=kind.value,
            )
            return InitiateCallResult(status="agent_sync_failed")
        live_tools = await self._arm_live_tools(active, kind, live_tools)

        personality = await self._personality_for(user_id)
        availability_summary = ""
        if mandate.prefetch_availability:
            read = await self._read_availability(
                user_id=user_id,
                window_start=window_start,
                window_end=window_end,
                user_tz=user_tz,
                user_language=user_language,
            )
            availability_summary = read.summary

        override = build_override(
            kind,
            MandateInputs(
                language=user_language,
                user_name=user_name,
                objective=objective,
                user_context=user_context if mandate.rich_context else "",
                availability_summary=availability_summary,
                now=now,
                timezone=user_tz,
                verification_code=verification_code,
                live_tool_domains=tuple(sorted({binding.domain for binding in live_tools})),
                personality=personality,
            ),
        )

        created = await self._create_dialing_row(
            repo,
            {
                "user_id": user_id,
                "callee_display": callee_display,
                "callee_phone": encrypt_data(callee_phone),  # PII encrypted at rest
                "objective": objective,
                "call_kind": kind,
                "objective_window_start": window_start,
                "objective_window_end": window_end,
                "status": PhoneCallStatus.DIALING,
                "initiated_at": now,
                "expires_at": now + timedelta(days=settings.telephony_call_retention_days),
            },
        )
        if isinstance(created, InitiateCallResult):
            return created
        call_id = created

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
            # Lot 9: the baked third-party agent reads the person's configured
            # personality per call — a variable, so no re-sync on a change.
            "personality_profile": personality,
        }

        # Vendor HTTP call — OUTSIDE any DB transaction.
        return await self._dial_and_interpret(
            api_key=active.api_key,
            repo=repo,
            user_id=user_id,
            call_id=call_id,
            agent_id=active.agent_id,
            agent_phone_number_id=active.agent_phone_number_id,
            callee_phone=callee_phone,
            dynamic_variables=dynamic_variables,
            conversation_config_override=override,
        )

    async def _active_connector(self, user_id: UUID) -> _ActiveConnector | None:
        """The user's active telephony connector with everything a dial needs.

        Returns:
            None when the connector is absent, incomplete, or without a key —
            the three ``not_configured`` cases, one answer.
        """
        connector = await TelephonyConnectorService(self.db).get_active(user_id)
        if connector is None:
            return None
        metadata = connector.connector_metadata or {}
        agent_id = metadata.get("agent_id")
        agent_phone_number_id = metadata.get("agent_phone_number_id")
        creds = await ConnectorService(self.db).get_api_key_credentials(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if not agent_id or not agent_phone_number_id or creds is None:
            return None
        return _ActiveConnector(
            connector=connector,
            agent_id=str(agent_id),
            agent_phone_number_id=str(agent_phone_number_id),
            api_key=creds.api_key,
        )

    async def _create_dialing_row(
        self, repo: TelephonyRepository, data: dict[str, Any]
    ) -> UUID | InitiateCallResult:
        """Persist the DIALING row and COMMIT it BEFORE dialing.

        Two reasons:
         1. Crash-safety / reconciliation: the call_id is sent to the vendor as
            a dynamic variable, so the row MUST exist before the call is placed
            — a crash after dialing still leaves a row for the post-call
            webhook (or the stale reaper). Committing after the vendor call
            would risk an orphan call whose webhook can never reconcile.
         2. The vendor HTTP call is then never held inside a DB transaction
            (no connection nor uncommitted F12 row locked across external I/O).
        The F12 partial unique index keeps "one active call per user" atomic.

        Returns:
            The committed call id, or the ``already_active`` result when the
            index refused a concurrent second call.
        """
        try:
            call = await repo.create(data)
            call_id = call.id  # capture before commit (may expire the ORM object)
            await self.db.commit()
            return call_id
        except IntegrityError:
            await self.db.rollback()
            racing = await repo.get_active_for_user(data["user_id"])
            return InitiateCallResult(
                status="already_active", call_id=racing.id if racing else None
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
        conversation_config_override: dict[str, Any] | None = None,
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
            conversation_config_override: The rendered mandate of an owner or
                verification call; None for the baked third-party agent.

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
                conversation_config_override=conversation_config_override,
            )
        except ElevenLabsAgentsError as exc:
            # A credential rejection is NOT transient: "try again in a moment"
            # is a lie until the connector key is replaced (prod 2026-08-15:
            # the vendor stopped accepting the stored legacy credential and
            # every call died behind the generic retry message).
            if exc.is_auth_error:
                await repo.mark_dial_failed(
                    call_id, error=f"initiate_auth_failed:{exc.status_code}"
                )
                logger.warning(
                    "telephony_initiate_call_auth_failed",
                    user_id=str(user_id),
                    call_id=str(call_id),
                    status_code=exc.status_code,
                )
                return InitiateCallResult(status="auth_failed", call_id=call_id)
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
