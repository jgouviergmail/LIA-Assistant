"""Telephony agent tool — ``call_me`` (phone-as-a-channel, lot 3).

LIA phones the ACCOUNT HOLDER on the number they declared and verified, under
the owner mandate: the chat's context on the line, a conversation rather than
an errand, and whatever the person asks for relayed into the chat as their own
message once the call ends (lot 4).

No confirmation card, by construction and not by exception: the person who
would confirm is the person who picks up, and hanging up undoes it — which is
what ``mutation_policy="reversible"`` says on the manifest. That policy is
also what lets the tool run UNATTENDED: a routine « call me every morning at
eight » plans this tool, and the effect gate ledgers it instead of refusing
it as it would a draft (ADR-276). The exception rests on the ONE seam the
identity service exposes, :func:`_verified_number`: anything short of a
verified line is a localized refusal pointing at the settings.

The third-party tool stays in ``telephony_tools.py``; this module is the
owner's, so neither grows past its cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.i18n_telephony import get_tool_phrases
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.telephony.live_tools import ensure_vendor_live_tools
from src.domains.agents.tools.decorators import connector_tool, with_user_preferences
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import parse_user_id, validate_runtime_config
from src.domains.agents.tools.telephony_tools import (
    _STATUS_TO_PHRASE,
    _owner_identity,
    _telephony_connector_active,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.delegation_tool import ensure_vendor_delegation_tool
from src.domains.telephony.live_tools import LiveToolBinding
from src.domains.telephony.models import CallKind
from src.domains.telephony.self_call_context import MEMORY_LINES_MAX, SectionFetcher
from src.domains.telephony.service import InitiateCallResult

if TYPE_CHECKING:
    # A type-only edge: ``agents`` must not import ``voice_sessions`` at
    # runtime (the projection there reads the display package back).
    from src.domains.voice_sessions.session import VoiceSessionMode

logger = structlog.get_logger(__name__)


def memory_fetcher_for(user_id: UUID, *, objective: str) -> SectionFetcher:
    """The memories section of an owner call — the chat's own profile builder.

    Handed to the telephony context builder from HERE because that builder
    lives in ``agents``, which ``telephony`` must not import (the T2 cycle).
    The objective is a LOOKUP, embedded before the search: handed no vector,
    the chat's builder served the most recent memories instead (ADR-313).

    Args:
        user_id: Whose memories.
        objective: The purpose of the call, the query the search ranks on.

    Returns:
        A fetcher yielding the profile lines the chat would inject.
    """
    from src.domains.agents.middleware.memory_injection import build_profile_for_lookup

    async def fetch() -> list[str]:
        profile, _state, _debug = await build_profile_for_lookup(
            str(user_id), objective or "catch-up call"
        )
        return [line for line in (profile or "").splitlines() if line.strip()][:MEMORY_LINES_MAX]

    return fetch


async def _owner_context(
    user_id: UUID, *, language: str, timezone: str, objective: str, rich_context_enabled: bool
) -> str:
    """The context block an owner call carries, or "" when the switch is off.

    Args:
        user_id: Whose context.
        language: Backend-canonical language of the rendering.
        timezone: The person's IANA zone.
        objective: The purpose of the call, used to pick relevant memories.
        rich_context_enabled: The person's own switch.

    Returns:
        The rendered block (lot 4), empty when switched off.
    """
    from src.domains.telephony.self_call_context import build_owner_context, default_fetchers

    return await build_owner_context(
        user_id,
        language=language,
        rich_context_enabled=rich_context_enabled,
        fetchers=default_fetchers(
            user_id,
            language=language,
            timezone=timezone,
            memory_fetcher=memory_fetcher_for(user_id, objective=objective),
            flatten=spoken_text,
        ),
    )


def spoken_text(text: str) -> str:
    """A stored message as prose a voice can read: no card markup, no Markdown.

    Args:
        text: The message as archived (an HTML ``lia-card``, Markdown, or plain).

    Returns:
        The words alone.
    """
    from src.domains.agents.display.plain_text import markdown_to_plain_text

    return markdown_to_plain_text(text)


async def _live_tools_for(
    db: Any, user_id: UUID, *, disabled_domains: frozenset[str] = frozenset()
) -> tuple[LiveToolBinding, ...]:
    """The webhook tools an owner call may attach (lot 7), provisioned if needed.

    Read the flag first so nothing is looked up when the feature is off; then
    the active connector and its secret, which the call-back token derives
    from. A missing piece means a call WITHOUT tools, never a refused call.
    Every offered tool is provisioned once per connector; the person's own
    switches decide what THIS call attaches (lot 8).

    Args:
        db: The session the connector metadata is committed on.
        user_id: The person being called.
        disabled_domains: The domains the person switched off.

    Returns:
        The bindings to hand to the dial; empty when none apply.
    """
    if not get_settings().telephony_live_tools_enabled:
        return ()
    connector = await TelephonyConnectorService(db).get_active(user_id)
    if connector is None:
        return ()
    creds = await ConnectorService(db).get_api_key_credentials(
        user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    if creds is None or not creds.api_secret:
        return ()
    # The reads end before the vendor is asked (ADR-304).
    await db.commit()
    bindings = await ensure_vendor_live_tools(
        db, connector=connector, api_key=creds.api_key, api_secret=creds.api_secret
    )
    return tuple(b for b in bindings if b.domain not in disabled_domains)


async def _delegation_tool_for(db: Any, user_id: UUID, *, user_name: str) -> str | None:
    """The delegation tool of a Live owner call (ADR-301), provisioned if needed.

    The same three pieces a live tool needs — the active connector, its key,
    its secret — and the same rule: a missing piece or a vendor refusal means
    a call WITHOUT the tool (the dial then runs direct and says so), never a
    refused call.
    """
    connector = await TelephonyConnectorService(db).get_active(user_id)
    if connector is None:
        return None
    creds = await ConnectorService(db).get_api_key_credentials(
        user_id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    if creds is None or not creds.api_secret:
        return None
    # The reads end before the vendor is asked (ADR-304).
    await db.commit()
    return await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        user_name=user_name,
    )


async def _initiate_owner_call(
    *,
    user_id: UUID,
    callee_phone: str,
    objective: str,
    user_language: str,
    timezone: str,
    call_mode: VoiceSessionMode,
    rich_context_enabled: bool,
    disabled_domains: frozenset[str] = frozenset(),
) -> InitiateCallResult:
    """Dial the person under the owner mandate, on a session of its own.

    The mode is settled HERE, before anything is built for it (ADR-301): a
    LIVE call (``delegated``) is handed the one delegation tool and nothing
    else — no lookup, no context: the voice knows nothing, LIA does — and a
    DIRECT call is handed its lookups and the context block. A Live call
    whose delegation tool cannot be provisioned runs DIRECT, with what a
    direct call needs (review 2026-09-20: it used to degrade AFTER the
    lookups and the context had been skipped — a voice that could answer
    nothing). A vendor refusal at the attach itself, inside the dial, still
    degrades without them — the same envelope as a direct call whose attach
    was refused.

    Args:
        user_id: The person being called.
        callee_phone: Their verified number.
        objective: The purpose of the call, in their words.
        user_language: Backend-canonical language.
        timezone: Their IANA zone.
        call_mode: The EFFECTIVE mode the identity resolved.
        rich_context_enabled: The person's own switch on a direct call's context.
        disabled_domains: The domains the person switched off for their voice.

    Returns:
        The dial's result.
    """
    from src.core.user_display import resolve_user_display_name
    from src.domains.telephony.service import TelephonyService
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        user = await db.get(User, user_id)
        display = resolve_user_display_name(user.full_name, user.email) if user else ""
        # This session is the dial's own; no read of it may stay open while
        # the context below is built or a vendor answers (ADR-304).
        await db.commit()
        delegation_tool_id: str | None = None
        if call_mode == "delegated":
            delegation_tool_id = await _delegation_tool_for(db, user_id, user_name=display)
            if delegation_tool_id is None:
                # A Live mandate with no way to delegate would promise what the
                # voice cannot do (ADR-184): the call runs direct, and is
                # handed what a direct call needs below.
                logger.warning(
                    "telephony_live_call_degraded_to_direct",
                    user_id=str(user_id),
                    reason="delegation_tool_unavailable",
                )
                call_mode = "direct"
        live_tools: tuple[LiveToolBinding, ...] = ()
        context = ""
        if call_mode == "direct":
            live_tools = await _live_tools_for(db, user_id, disabled_domains=disabled_domains)
            context = await _owner_context(
                user_id,
                language=user_language,
                timezone=timezone,
                objective=objective,
                rich_context_enabled=rich_context_enabled,
            )
        return await TelephonyService(db).initiate_call(
            user_id=user_id,
            callee_display=display,
            callee_phone=callee_phone,
            objective=objective,
            date_window=None,
            user_language=user_language,
            kind=CallKind.SELF,
            user_context=context,
            live_tools=live_tools,
            call_mode=call_mode,
            delegation_tool_id=delegation_tool_id,
        )


async def _build_call_me_output(
    *, user_id: UUID, locale: str, timezone: str, objective: str
) -> UnifiedToolOutput:
    """Guard → verified number → context → dial, or a localized refusal."""
    phrases = get_tool_phrases(locale)

    if not await _telephony_connector_active(user_id):
        return UnifiedToolOutput.failure(
            message=phrases["not_configured"], error_code="telephony_not_configured"
        )

    identity = await _owner_identity(user_id)
    if not identity.verified or identity.phone_number is None:
        return UnifiedToolOutput.failure(
            message=phrases["number_not_verified"], error_code="phone_number_not_verified"
        )

    purpose = objective.strip()
    # The EFFECTIVE mode (ADR-301): the person's choice, or direct when this
    # instance cannot be called back. The dial builds what the mode needs
    # once the mode is settled — a Live call opens none of the sources.
    result = await _initiate_owner_call(
        user_id=user_id,
        callee_phone=identity.phone_number,
        objective=purpose,
        user_language=locale,
        timezone=timezone,
        call_mode=identity.call_mode_effective,
        rich_context_enabled=identity.rich_context_enabled,
        disabled_domains=frozenset(identity.disabled_domains),
    )
    if result.status != "placed":
        return UnifiedToolOutput.failure(
            message=phrases[_STATUS_TO_PHRASE[result.status]],
            error_code=f"telephony_{result.status}",
        )

    logger.info("call_me_placed", user_id=str(user_id), call_id=str(result.call_id))
    return UnifiedToolOutput.action_success(
        message=phrases["calling_you"],
        structured_data={"call_id": str(result.call_id)},
    )


@connector_tool(
    name="call_me",
    agent_name="telephony_agent",
    category="write",
    # Per-user hourly cap from settings (paid external calls) — shared with the
    # third-party tool: it is the same line and the same bill.
    rate_limit_max_calls=lambda: get_settings().telephony_rate_limit_per_hour,
    rate_limit_window_seconds=3600,
)
@with_user_preferences
async def call_me_tool(
    objective: Annotated[
        str,
        "What the call is about, in the user's words (e.g. 'go over tomorrow's meetings', "
        "'take my shopping list'). Express dates absolutely. Empty means a catch-up call.",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Call the user on their own verified phone number (no confirmation needed).

    LIA phones the account holder and talks with them about the objective;
    what they ask for reaches their chat — during the call (Live) or relayed
    as their own message once it ends (Live direct), as they chose in the
    settings. Requires the telephony connector and a verified number.

    Args:
        objective: The purpose of the call.
        runtime: LangChain tool runtime.
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput saying the call is ringing, or a localized refusal.
    """
    config = validate_runtime_config(runtime, "call_me_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    return await _build_call_me_output(
        user_id=parse_user_id(config.user_id),
        locale=locale,
        timezone=user_timezone,
        objective=objective,
    )


__all__ = ["call_me_tool"]
