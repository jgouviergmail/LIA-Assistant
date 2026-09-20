"""The live session, server side (ADR-299): the connector, the credentials, the trace.

What this service does NOT do is the point: it executes no request. A
delegated request goes through the chat's own door from the browser; this
module only frappes the credentials, keeps the session record, archives the
voice-only exchanges and closes the books at the end.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    LIVE_DELEGATION_TOOL_NAME,
    LIVE_DIRECT_TRANSCRIPT_MAX_ROWS,
    LIVE_DURATION_UNLIMITED,
    LIVE_SESSION_RECORD_GRACE_SECONDS,
    LIVE_SESSION_RUN_PREFIX,
    LIVE_TURN_TEXT_MAX_CHARS,
    REDIS_KEY_LIVE_MINT_PREFIX,
)
from src.domains.agents.api.archive_metadata import (
    build_live_turn_metadata,
)
from src.domains.connectors.models import (
    ConnectorType,
)
from src.domains.live.connector_service import LiveConnectorService
from src.domains.live.direct_mandate import build_direct_setup_inputs
from src.domains.live.errors import (
    raise_live_connector_missing,
    raise_live_credential_invalid,
    raise_live_instance_busy,
    raise_live_mint_rate_limited,
    raise_live_mode_unsupported,
    raise_live_model_unpriced,
    raise_live_provider_refused,
    raise_live_session_expired,
    raise_live_session_in_progress,
    raise_live_session_not_found,
)
from src.domains.live.pricing import rates_for
from src.domains.live.providers import (
    PROVIDERS,
    AgentSyncing,
    LiveProvider,
    LiveSetupInputs,
    OfferExchanging,
    provider_by_id,
    setup_inputs_from_dict,
    setup_inputs_to_dict,
)
from src.domains.live.schemas import (
    LiveCredentialResponse,
    LiveEndRequest,
    LiveEndResponse,
    LiveExtendResponse,
    LiveModelCapabilitiesResponse,
    LiveOfferRequest,
    LiveOfferResponse,
    LiveRates,
    LiveSessionMode,
    LiveSessionStartResponse,
    LiveToolCallRequest,
    LiveToolCallResponse,
    LiveTurnRequest,
    LiveTurnResponse,
)
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from src.domains.live.tool_door import run_session_tool
from src.domains.live.vendor_bill import fetch_vendor_bill
from src.domains.users.models import User
from src.domains.voice_sessions.session import VoiceSession, as_voice_session_mode
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_live import (
    live_mint_total,
    live_offer_exchanges_total,
    live_session_duration_seconds,
    live_session_extensions_total,
    live_sessions_active,
    live_sessions_total,
    live_turns_archived_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter
from src.infrastructure.scheduler.voice_session_closing import close_voice_session

logger = structlog.get_logger(__name__)


def live_session_run_id(session_id: str) -> str:
    """The run id every euro and every row of a session is filed under."""
    return f"{LIVE_SESSION_RUN_PREFIX}{session_id}"


class LiveService:
    """The session lifecycle: claim, credentials, offer, extension, trace, closing.

    The connectors, the catalogue, the samples and the reflexes are
    `LiveConnectorService`'s, composed here and never re-implemented.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connectors = LiveConnectorService(db)

    # -- thin doors the tests replace ------------------------------------------------

    async def _store(self) -> LiveSessionStore:
        return LiveSessionStore(await get_redis_cache())

    async def _limiter(self) -> Any:
        return await get_rate_limiter()

    async def _personality_of(self, user_id: uuid.UUID) -> str:
        from src.domains.personalities.service import PersonalityService

        try:
            return str(await PersonalityService(self.db).get_prompt_instruction_for_user(user_id))
        except Exception as exc:  # noqa: BLE001 - a personality is colour, never a gate
            logger.warning("live_personality_unreadable", error_type=type(exc).__name__)
            return ""

    async def _inner_state_of(self, user_id: uuid.UUID, timezone: str) -> str:
        """LIA's inner state for the mandate — the psyche engine's own block, or "".

        The block is the one every secondary generation point carries (the
        reminders, the proactive messages, the spoken comments); it answers
        "" when the engine is off for the instance or the person, and on any
        failure — colour, never a gate (owner question 5, 2026-09-19).
        """
        from src.domains.psyche.service import build_psyche_prompt_block

        return await build_psyche_prompt_block(user_id=user_id, user_timezone=timezone)

    async def _conversation_id(self, user_id: uuid.UUID, *, language: str) -> uuid.UUID:
        from src.domains.conversations.service import ConversationService

        conversation = await ConversationService().get_or_create_conversation(
            user_id, self.db, language=language
        )
        return conversation.id

    async def _archive(
        self, *, conversation_id: uuid.UUID, role: str, content: str, metadata: dict[str, Any]
    ) -> Any:
        from src.domains.conversations.service import ConversationService

        return await ConversationService().archive_message(
            conversation_id, role, content, metadata, self.db
        )

    # -- connector -------------------------------------------------------------------

    # -- session ---------------------------------------------------------------------

    async def _sync_agent(
        self,
        provider: LiveProvider,
        connector: Any,
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        language: str,
    ) -> None:
        """Let an agent-bound provider prepare the person's agent; keep what it holds on the connector."""
        if not isinstance(provider, AgentSyncing):
            return
        try:
            synced = await provider.sync_agent(
                api_key, dict(connector.connector_metadata or {}), inputs
            )
        except Exception as exc:
            live_mint_total.labels(provider=provider.provider_id, outcome="provider_error").inc()
            logger.warning("live_agent_sync_failed", error_type=type(exc).__name__)
            raise_live_provider_refused(language, type(exc).__name__)
        if synced != (connector.connector_metadata or {}):
            connector.connector_metadata = synced  # a NEW dict: the JSONB rule
            self.db.add(connector)
            await self.db.commit()

    async def _mint(
        self,
        provider: LiveProvider,
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        expires_at: datetime,
        language: str,
        on_failure: Any,
    ) -> LiveCredentialResponse:
        connect_deadline_at = datetime.now(UTC) + timedelta(
            seconds=settings.live_connect_window_seconds
        )
        try:
            credential = await provider.mint(
                api_key, inputs, expires_at=expires_at, connect_deadline_at=connect_deadline_at
            )
        except Exception as exc:
            await on_failure()
            live_mint_total.labels(provider=provider.provider_id, outcome="provider_error").inc()
            logger.warning("live_mint_failed", error_type=type(exc).__name__)
            raise_live_provider_refused(language, type(exc).__name__)
        live_mint_total.labels(provider=provider.provider_id, outcome="ok").inc()
        return LiveCredentialResponse(
            credential=credential.name,
            credential_expires_at=credential.expires_at,
            connect_deadline_at=credential.connect_deadline_at,
            connection=provider.connection,
            # An offer connection's setup is posted by the API in the exchange; the
            # browser replays nothing and is handed nothing.
            setup=provider.build_setup(inputs) if provider.connection == "token" else {},
        )

    @staticmethod
    async def _keep_nonce(
        store: LiveSessionStore,
        provider: LiveProvider,
        record: LiveSessionRecord,
        minted: LiveCredentialResponse,
    ) -> LiveSessionRecord | None:
        """For an ``offer`` connection, write the minted nonce on the record under its claim.

        Returns:
            The record as it now reads, or None when the claim was lost meanwhile.
        """
        if provider.connection != "offer":
            return record
        nonced = replace(record, nonce=minted.credential, nonce_until=minted.connect_deadline_at)
        if not await store.rewrite(nonced, now=datetime.now(UTC)):
            return None
        return nonced

    async def _admit(
        self, user: User, mode: LiveSessionMode, *, language: str
    ) -> tuple[Any, LiveProvider, Any, LiveRates | None]:
        """The refusals of a start, in order: no connector, rate limit, no tariff, no such mode.

        Returns:
            The connector, its provider, the chosen settings and the model's
            rates — None on a vendor-billed provider, which the platform
            prices nothing of.
        """
        connector = await self.connectors.chosen_connector(user)
        if connector is None:
            live_mint_total.labels(provider="none", outcome="connector_missing").inc()
            raise_live_connector_missing(language)
        provider = PROVIDERS[ConnectorType(connector.connector_type)]
        if await self._rate_limited(user.id):
            live_mint_total.labels(provider=provider.provider_id, outcome="rate_limited").inc()
            raise_live_mint_rate_limited(language)
        chosen = self.connectors.connector_settings(connector)
        # A tariff-billed model with no tariff is not offered and does not
        # start (owner rule 2026-09-19): the meter it feeds would have nothing
        # to multiply by. A vendor-billed provider's session (an ElevenLabs
        # agent) starts with no rates: the platform prices nothing of it, the
        # vendor states its bill at the end.
        rates = rates_for(chosen.model) if provider.billing == "tariff" else None
        if provider.billing == "tariff" and rates is None:
            live_mint_total.labels(provider=provider.provider_id, outcome="model_unpriced").inc()
            raise_live_model_unpriced(language, chosen.model)
        if mode == "direct" and not provider.capabilities_of(chosen.model).direct_tools:
            live_mint_total.labels(provider=provider.provider_id, outcome="mode_unsupported").inc()
            raise_live_mode_unsupported(language)
        return connector, provider, chosen, rates

    async def _rate_limited(self, user_id: uuid.UUID) -> bool:
        limiter = await self._limiter()
        allowed = await limiter.acquire(
            key=f"{REDIS_KEY_LIVE_MINT_PREFIX}{user_id}",
            max_calls=settings.live_mint_rate_limit_max_calls,
            window_seconds=settings.live_mint_rate_limit_window_seconds,
        )
        return not allowed

    async def start(
        self,
        user: User,
        *,
        language: str,
        timezone: str,
        display_name: str,
        mode: LiveSessionMode = "delegated",
    ) -> LiveSessionStartResponse:
        """Refuse in order, then claim, mint and hand the browser its setup.

        A DIRECT session (ADR-300 wave 4) renders the direct mandate — the
        phone's context block and LIA's read-only tools declared on the
        setup, no delegation — and is refused on a model whose wire carries
        no tool schema (``direct_tools`` false).
        """
        connector, provider, chosen, rates = await self._admit(user, mode, language=language)
        connector_type = ConnectorType(connector.connector_type)
        capabilities = provider.capabilities_of(chosen.model)
        prefs = self.connectors.preferences(user)
        now = datetime.now(UTC)
        # An unlimited cap (0) rolls by extension slices the client renews without
        # asking; a bounded one is the model's own. Either way the credential and
        # the record live to the cap, never for ever (a key with no TTL is never written).
        cap_minutes = chosen.session_max_minutes or settings.live_extension_minutes
        expires_at = now + timedelta(minutes=cap_minutes)
        session_id = uuid.uuid4().hex
        personality = await self._personality_of(user.id)
        psyche_block = await self._inner_state_of(user.id, timezone)
        if mode == "direct":
            inputs = await build_direct_setup_inputs(
                user_id=user.id,
                model=chosen.model,
                voice=chosen.voice,
                thinking_level=chosen.thinking_level,
                preferences=prefs,
                disabled_domains=frozenset(user.phone_disabled_domains or ()),
                language=language,
                timezone=timezone,
                display_name=display_name,
                now=now,
                personality=personality,
                psyche_block=psyche_block,
            )
        else:
            inputs = self.connectors.setup_inputs(
                provider,
                user,
                chosen,
                language=language,
                timezone=timezone,
                display_name=display_name,
                now=now,
                personality=personality,
                psyche_block=psyche_block,
            )
        api_key = await self.connectors.api_key_of(user.id, connector_type)
        # A provider whose sessions run on the person's AGENT prepares it for
        # THIS setup (the tools of the mode, the prompt permission) before
        # anything is claimed: a vendor refusal is a start that never happened.
        await self._sync_agent(provider, connector, api_key, inputs, language=language)
        record = LiveSessionRecord(
            session_id=session_id,
            user_id=user.id,
            provider=provider.provider_id,
            model=chosen.model,
            run_id=live_session_run_id(session_id),
            started_at=now,
            expires_at=expires_at,
            token=uuid.uuid4().hex,
            setup_inputs=setup_inputs_to_dict(inputs),
            unlimited_cap=chosen.session_max_minutes == LIVE_DURATION_UNLIMITED,
            mode=mode,
        )
        store = await self._store()
        ttl_seconds = record.remaining_life_seconds(now)
        if not await store.claim(record, ttl_seconds=ttl_seconds):
            # The claim is per ACCOUNT: whoever holds it is this same person, in
            # a tab that died without closing its books (a crash, a killed
            # page) or one still open elsewhere. A new start SUPERSEDES it —
            # its books are closed with that outcome, its slot freed — rather
            # than locking the person out until the record's TTL.
            previous = await store.get(user.id)
            superseded = previous is not None and await self._supersede(
                user, previous, language=language
            )
            if not superseded or not await store.claim(record, ttl_seconds=ttl_seconds):
                live_mint_total.labels(
                    provider=provider.provider_id, outcome="session_in_progress"
                ).inc()
                raise_live_session_in_progress(language)
        if await store.count_active(now) >= settings.live_max_concurrent_sessions:
            await store.release(user.id, record.token)
            live_mint_total.labels(provider=provider.provider_id, outcome="instance_busy").inc()
            raise_live_instance_busy(language)

        async def _undo() -> None:
            await store.release(user.id, record.token)

        credential = await self._mint(
            provider,
            api_key,
            inputs,
            expires_at=expires_at,
            language=language,
            on_failure=_undo,
        )
        # Two starts of one account in the same second: the second superseded
        # this record while the credential was being minted. The slot is the
        # other tab's now — count nothing for this one and refuse it honestly.
        current = await store.get(user.id)
        kept = (
            await self._keep_nonce(store, provider, record, credential)
            if current is not None and current.token == record.token
            else None
        )
        if kept is None:
            live_mint_total.labels(
                provider=provider.provider_id, outcome="session_in_progress"
            ).inc()
            raise_live_session_in_progress(language)
        await store.register_active(session_id, expires_at)
        live_sessions_active.set(await store.count_active(now))
        logger.info(
            "live_session_minted", session_id=session_id, provider=provider.provider_id, mode=mode
        )
        return LiveSessionStartResponse(
            **credential.model_dump(),
            session_id=session_id,
            provider=provider.provider_id,
            model=chosen.model,
            run_id=record.run_id,
            mode=mode,
            expires_at=expires_at,
            session_max_minutes=chosen.session_max_minutes,
            idle_timeout_seconds=chosen.idle_timeout_seconds,
            preferences=prefs,
            capabilities=LiveModelCapabilitiesResponse(**asdict(capabilities)),
            delegation_tool_name=LIVE_DELEGATION_TOOL_NAME,
            delegation_timeout_seconds=settings.live_delegation_timeout_seconds,
            delegation_result_max_tokens=settings.live_delegation_result_max_tokens,
            turn_text_max_chars=LIVE_TURN_TEXT_MAX_CHARS,
            rates=rates,
            session_budget_eur=chosen.session_budget_eur,
        )

    async def run_tool(
        self,
        user: User,
        session_id: str,
        payload: LiveToolCallRequest,
        *,
        language: str,
        timezone: str,
        display_name: str,
    ) -> LiveToolCallResponse:
        """Run one lookup the voice asked for on a DIRECT session (ADR-300 wave 4).

        The record must be the person's; the rest is ``tool_door.run_session_tool``.
        """
        record = await self._owned_record(user, session_id, language=language)
        return await run_session_tool(
            record,
            await self._store(),
            user,
            payload,
            language=language,
            timezone=timezone,
            display_name=display_name,
        )

    async def _owned_record(
        self, user: User, session_id: str, *, language: str
    ) -> LiveSessionRecord:
        store = await self._store()
        record = await store.get(user.id)
        if record is None or record.session_id != session_id:
            raise_live_session_not_found(language)
        return record

    async def renew_credential(
        self, user: User, session_id: str, *, language: str
    ) -> LiveCredentialResponse:
        """A fresh credential for a RECONNECTION of the same session (same setup).

        Measured 2026-09-18: a ``uses: 1`` credential cannot reopen its session;
        a fresh one with the resumption handle can. The session's expiry does
        not move — the credential expires with the session it belongs to.
        """
        record = await self._owned_record(user, session_id, language=language)
        if await self._rate_limited(user.id):
            live_mint_total.labels(provider=record.provider, outcome="rate_limited").inc()
            raise_live_mint_rate_limited(language)
        return await self._remint(user, record, language=language)

    async def _remint(
        self, user: User, record: LiveSessionRecord, *, language: str
    ) -> LiveCredentialResponse:
        """A fresh credential for the SAME record, minted to the record's own expiry.

        On the SESSION's provider (the record's), never the account's current
        choice: a switch made mid-session must not reconnect elsewhere.
        """
        connector = await self.connectors.connector_of(user, record.provider, language=language)
        connector_type = ConnectorType(connector.connector_type)
        provider = PROVIDERS[connector_type]

        async def _nothing() -> None:
            return None

        minted = await self._mint(
            provider,
            await self.connectors.api_key_of(user.id, connector_type),
            setup_inputs_from_dict(record.setup_inputs),
            expires_at=record.expires_at,
            language=language,
            on_failure=_nothing,
        )
        if await self._keep_nonce(await self._store(), provider, record, minted) is None:
            # The claim went to a successor while the credential was minted.
            raise_live_session_not_found(language)
        return minted

    async def exchange_offer(
        self, user: User, session_id: str, payload: LiveOfferRequest, *, language: str
    ) -> LiveOfferResponse:
        """Exchange the browser's SDP offer on the person's key — once per credential.

        The nonce is consumed BEFORE the exchange: a refused exchange burns it,
        and the browser asks for a fresh credential to try again (« one
        credential opens one connection », on both providers).
        """
        record = await self._owned_record(user, session_id, language=language)
        connector = await self.connectors.connector_of(user, record.provider, language=language)
        provider = PROVIDERS[ConnectorType(connector.connector_type)]
        if provider.connection != "offer" or not isinstance(provider, OfferExchanging):
            live_offer_exchanges_total.labels(provider=record.provider, outcome="refused").inc()
            raise_live_provider_refused(language, "not an offer connection")
        now = datetime.now(UTC)
        if (
            record.nonce is None
            or not hmac.compare_digest(record.nonce, payload.credential)
            or record.nonce_until is None
            or now >= record.nonce_until
        ):
            live_offer_exchanges_total.labels(provider=record.provider, outcome="refused").inc()
            raise_live_credential_invalid(language)
        consumed = replace(record, nonce=None, nonce_until=None)
        if not await (await self._store()).rewrite(consumed, now=now):
            raise_live_session_not_found(language)
        try:
            answer = await provider.exchange_offer(
                await self.connectors.api_key_of(user.id, ConnectorType(connector.connector_type)),
                setup_inputs_from_dict(record.setup_inputs),
                payload.sdp,
                timeout=settings.live_probe_timeout_seconds,
            )
        except Exception as exc:
            live_offer_exchanges_total.labels(
                provider=record.provider, outcome="provider_error"
            ).inc()
            logger.warning(
                "live_offer_exchange_failed", error_type=type(exc).__name__, detail=str(exc)[:200]
            )
            raise_live_provider_refused(language, str(exc)[:200])
        live_offer_exchanges_total.labels(provider=record.provider, outcome="ok").inc()
        logger.info("live_offer_exchanged", session_id=session_id, provider=record.provider)
        return LiveOfferResponse(sdp=answer)

    async def extend(self, user: User, session_id: str, *, language: str) -> LiveExtendResponse:
        """Prolong the session by the published extension, on the person's explicit word.

        The cap moves from its CURRENT value (« ten more minutes » means ten),
        unlimited times, each explicit (owner decision 2026-09-19) — except on
        a model whose cap is « no limit », where the client renews the slice
        in silence and the renewal is counted as ROLLING, never as the
        person's extension. Measured
        the same day: Gemini closes an OPEN connection at its credential's
        expiry (1011 « auth token has expired »), so on a ``token`` connection
        a fresh credential is minted to the new cap and handed back for an
        immediate reconnection on the resumption handle. An ``offer``
        connection (GPT-Live) holds no expiring credential — the WebRTC
        session outlives the cap on its own — so nothing is minted and the
        browser keeps its connection (measured 2026-09-19: a reconnection
        there would be a NEW provider session, its context lost).
        """
        record = await self._owned_record(user, session_id, language=language)
        provider = provider_by_id(record.provider)
        reconnects = provider is not None and provider.connection == "token"
        now = datetime.now(UTC)
        if now >= record.expires_at:
            raise_live_session_expired(language)
        if reconnects and await self._rate_limited(user.id):
            live_mint_total.labels(provider=record.provider, outcome="rate_limited").inc()
            raise_live_mint_rate_limited(language)
        extended = replace(
            record,
            expires_at=record.expires_at + timedelta(minutes=settings.live_extension_minutes),
            extensions=record.extensions + (0 if record.unlimited_cap else 1),
        )
        ttl_seconds = (
            int((extended.expires_at - now).total_seconds()) + LIVE_SESSION_RECORD_GRACE_SECONDS
        )
        store = await self._store()
        if not await store.extend(extended, ttl_seconds=ttl_seconds):
            # The claim is a successor's: this session is over for this tab.
            raise_live_session_not_found(language)
        await store.register_active(session_id, extended.expires_at)
        credential = await self._remint(user, extended, language=language) if reconnects else None
        live_session_extensions_total.labels(
            provider=record.provider, kind="rolling" if record.unlimited_cap else "explicit"
        ).inc()
        logger.info(
            "live_session_extended",
            session_id=session_id,
            extensions=extended.extensions,
            expires_at=extended.expires_at.isoformat(),
        )
        return LiveExtendResponse(
            expires_at=extended.expires_at, extensions=extended.extensions, credential=credential
        )

    # -- trace -----------------------------------------------------------------------

    async def archive_turn(
        self, user: User, session_id: str, payload: LiveTurnRequest, *, language: str
    ) -> LiveTurnResponse:
        """Archive a voice-only exchange, one row per role, at once (spec A7).

        A DIRECT session archives nothing turn by turn (ADR-300 wave 4): its
        exchanges are KEPT in its record and become, at its end, the message
        the person would have typed (ADR-301) — so the same door accumulates
        them, and answers no row ids.
        """
        record = await self._owned_record(user, session_id, language=language)
        if record.mode == "direct":
            # ADR-301: kept in the record until the end, when the exchanges
            # become the person's own turn — never archived one by one.
            kept = await (await self._store()).append_turns(
                user.id,
                [
                    (role, text.strip()[:LIVE_TURN_TEXT_MAX_CHARS])
                    for role, text in (
                        ("user", payload.user_text),
                        ("assistant", payload.assistant_text),
                    )
                    if text and text.strip()
                ],
                ttl_seconds=record.remaining_life_seconds(datetime.now(UTC)),
                max_rows=LIVE_DIRECT_TRANSCRIPT_MAX_ROWS,
            )
            logger.debug("live_direct_turn_kept", session_id=session_id, rows=kept)
            return LiveTurnResponse(user_message_id=None, assistant_message_id=None)
        conversation_id = await self._conversation_id(user.id, language=language)
        ids: dict[str, uuid.UUID | None] = {"user": None, "assistant": None}
        for role, text in (("user", payload.user_text), ("assistant", payload.assistant_text)):
            if not text or not text.strip():
                continue
            row = await self._archive(
                conversation_id=conversation_id,
                role=role,
                content=text.strip()[:LIVE_TURN_TEXT_MAX_CHARS],
                metadata=build_live_turn_metadata(
                    run_id=record.run_id,
                    live_session_id=session_id,
                    started_at=payload.started_at,
                    ended_at=payload.ended_at,
                ),
            )
            ids[role] = row.id
            live_turns_archived_total.labels(role=role).inc()
        await self.db.commit()
        return LiveTurnResponse(user_message_id=ids["user"], assistant_message_id=ids["assistant"])

    async def _supersede(self, user: User, previous: LiveSessionRecord, *, language: str) -> bool:
        """Close a same-account session a new start replaces; False when it could not."""
        try:
            await self.end(
                user, previous.session_id, LiveEndRequest(outcome="superseded"), language=language
            )
        except Exception as exc:  # noqa: BLE001 - the new session is then refused honestly
            logger.warning("live_session_supersede_failed", error_type=type(exc).__name__)
            return False
        logger.info("live_session_superseded", session_id=previous.session_id)
        return True

    async def end(
        self, user: User, session_id: str, payload: LiveEndRequest, *, language: str
    ) -> LiveEndResponse:
        """Close the books through the voice session's own policy, then free the slot.

        Everything a session owes at its end — the card with EXACT figures,
        the decision row, the learning of the voice-only rows — is the
        carrier-neutral closing (ADR-301, ``voice_session_closing``): the
        phone's post-call path calls the same function. What stays here is
        the browser's own: the record, the claim, the metrics.
        """
        record = await self._owned_record(user, session_id, language=language)
        store = await self._store()
        now = datetime.now(UTC)
        duration = int((now - record.started_at).total_seconds())
        conversation_id = await self._conversation_id(user.id, language=language)
        session = VoiceSession.browser(
            session_id=session_id,
            run_id=record.run_id,
            mode=as_voice_session_mode(record.mode),
            user_id=user.id,
            conversation_id=conversation_id,
            language=language,
            timezone=str(user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE),
        )
        transcript = (
            VoiceTranscript.from_rows(await store.turns(user.id))
            if record.mode == "direct"
            else None
        )
        closed = await close_voice_session(
            self.db,
            session=session,
            memory_enabled=bool(user.memory_enabled),
            outcome=payload.outcome,
            duration_seconds=duration,
            extensions=record.extensions,
            transcript=transcript,
        )
        await store.release(user.id, record.token)
        await store.unregister_active(session_id)
        live_sessions_active.set(await store.count_active(now))
        live_sessions_total.labels(provider=record.provider, outcome=payload.outcome).inc()
        live_session_duration_seconds.observe(duration)
        # The vendor's own bill, read on the person's key and SHOWN — after the
        # books are closed and the slot freed, so a slow vendor delays nothing
        # that matters; never written anywhere (the platform re-bills none of it).
        vendor_bill = await fetch_vendor_bill(
            self.connectors, user, record, payload.provider_conversation_id
        )
        logger.info(
            "live_session_ended",
            session_id=session_id,
            outcome=payload.outcome,
            detail=payload.detail,
            duration_seconds=duration,
            delegations=closed.delegations,
            voice_turns=closed.voice_turns,
        )
        return LiveEndResponse(
            summary_message_id=closed.summary_message_id,
            duration_seconds=duration,
            delegations=closed.delegations,
            voice_turns=closed.voice_turns,
            relay=closed.relay,
            extensions=record.extensions,
            usage=closed.usage,
            vendor_bill=vendor_bill,
        )


__all__ = ["LiveService", "live_session_run_id"]
