"""Telephony agent tools — ``place_phone_call`` (spec P3.3/P3.4).

``place_phone_call`` is a draft-producing tool: it verifies the user's
per-user ``ELEVENLABS_TELEPHONY`` connector is active, resolves the callee to an
E.164 number (a raw number is used as-is; a name is resolved against the active
contacts provider), and returns a ``PHONE_CALL`` draft that requires HITL
confirmation. The call is only dialed after the user confirms, via
``execute_phone_call_draft`` (registered in the draft executor).

The caller-facing failure/clarification strings live in ``core.i18n_telephony``
(all 6 languages).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.i18n_telephony import get_tool_phrases
from src.domains.agents.drafts import PhoneCallDraftInput
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import connector_tool, with_user_preferences
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import parse_user_id, validate_runtime_config

logger = structlog.get_logger(__name__)

# A callee looks like a phone number when it is a '+'-prefixed / digit run with
# only phone punctuation — a contact name never matches this.
_PHONE_RE = re.compile(r"^\+?\d[\d\s().\-]{6,}$")

# Non-placed initiate outcomes → the locale key that explains them. Module level
# so the completeness test can IMPORT it: this lookup is unguarded, and a status
# added without its phrase would raise KeyError right after the user confirmed
# the call — the least forgiving moment there is.
_STATUS_TO_PHRASE: dict[str, str] = {
    "already_active": "already_active",
    "not_configured": "not_configured",
    # Transient (network, vendor 5xx): "try again in a moment" is true.
    "failed": "call_failed",
    # The vendor DECLINED on configuration grounds (observed: a source number
    # not verified on the Twilio account). Telling the user to retry would be
    # a lie — nothing changes until the provider side is fixed.
    "rejected": "call_rejected",
}


def _looks_like_phone(value: str) -> bool:
    """True when the raw callee is already a dialable number (skip resolution)."""
    return bool(_PHONE_RE.match(value.strip()))


def _normalize_phone(value: str) -> str:
    """Collapse a raw number to a compact E.164-ish form (keep leading '+').

    When ``TELEPHONY_DEFAULT_COUNTRY_CODE`` is configured, a national number
    (single leading 0, e.g. ``0682511639``) is converted to E.164 by replacing
    the trunk 0 (``+33682511639``). ``00``-prefixed international numbers and
    numbers already carrying ``+`` are left untouched.
    """
    stripped = value.strip()
    if stripped.startswith("+"):
        return f"+{re.sub(r'[^0-9]', '', stripped)}"
    digits = re.sub(r"[^0-9]", "", stripped)
    country_code = get_settings().telephony_default_country_code
    if country_code and len(digits) >= 6 and digits.startswith("0") and not digits.startswith("00"):
        return f"{country_code}{digits[1:]}"
    return digits


def _strip_trailing_annotations(contact: str) -> str:
    """Drop trailing parenthetical annotations an LLM may append to a name.

    ``"Hua Gouvier (my wife)"`` -> ``"Hua Gouvier"``. Only TRAILING groups are
    stripped, and only as a retry fallback — contacts legitimately named with a
    parenthetical (e.g. ``"Jean Dupont (plombier)"``) still match exact-first.
    """
    return re.sub(r"(?:\s*\([^)]*\))+\s*$", "", contact).strip()


def _person_display_name(person: dict) -> str:
    """First display name of a Google People person, or '?' when absent."""
    names = person.get("names") or []
    return names[0].get("displayName", "?") if names else "?"


def _person_first_phone(person: dict) -> str:
    """First dialable phone of a Google People person, or '' when absent.

    Prefers ``canonicalForm`` (E.164, e.g. ``+33682511639``) over ``value``
    (display formatting, e.g. ``"06 82 51 16 39"``); the value fallback is
    normalized so the dial never receives spaces/dots.
    """
    phones = person.get("phoneNumbers") or []
    if not phones:
        return ""
    canonical = phones[0].get("canonicalForm", "")
    if canonical:
        return canonical
    value = phones[0].get("value", "")
    return _normalize_phone(value) if value else ""


@dataclass(frozen=True)
class _CalleeResolution:
    """Outcome of resolving a callee reference to a name + number."""

    kind: Literal["resolved", "not_found", "no_phone", "ambiguous"]
    name: str = ""
    phone: str = ""
    candidates: list[tuple[str, str]] = field(default_factory=list)


async def _search_contacts_with_phones(
    user_id: UUID, query: str, max_results: int = 5
) -> tuple[list[tuple[str, str]], str | None]:
    """Search the active contacts provider for candidates carrying a phone.

    Returns ``(candidates, first_match_name)`` where ``candidates`` is
    ``[(display_name, phone), ...]`` limited to matches that have a number, and
    ``first_match_name`` is the display name of the first match overall (used to
    distinguish "no match" from "matched but no phone"), or ``None`` if nothing
    matched. Requests only ``names``/``phoneNumbers`` — no other contact detail.
    """
    from src.domains.connectors.clients.registry import ClientRegistry
    from src.domains.connectors.provider_resolver import resolve_active_connector
    from src.domains.connectors.service import ConnectorService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(user_id, "contacts", connector_service)
        if resolved_type is None:
            return [], None

        credentials = (
            await connector_service.get_apple_credentials(user_id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user_id, resolved_type)
        )
        if not credentials:
            return [], None

        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return [], None
        client = client_class(user_id, credentials, connector_service)
        result = await client.search_contacts(
            query, max_results=max_results, fields=["names", "phoneNumbers"]
        )

    return _extract_candidates(result)


def _extract_candidates(result: dict) -> tuple[list[tuple[str, str]], str | None]:
    """Parse a provider search payload into ``(candidates, first_match_name)``.

    Every provider wraps search hits as ``{"person": {...}}`` (Google natively,
    Microsoft/Apple by parity — see their ``search_contacts``); an unwrapped
    person is tolerated defensively.
    """
    persons = [
        (r.get("person") or r) for r in (result.get("results", []) or []) if isinstance(r, dict)
    ]
    if not persons:
        return [], None
    candidates = [
        (_person_display_name(p), _person_first_phone(p)) for p in persons if _person_first_phone(p)
    ]
    return candidates, _person_display_name(persons[0])


async def _resolve_callee(user_id: UUID, contact: str) -> _CalleeResolution:
    """Resolve a callee reference (raw number or contact name) to name + phone."""
    if _looks_like_phone(contact):
        number = _normalize_phone(contact)
        return _CalleeResolution(kind="resolved", name=number, phone=number)

    candidates, first_match_name = await _search_contacts_with_phones(user_id, contact)
    if first_match_name is None:
        # Exact-first, sanitized retry: planners occasionally annotate the name
        # ("Hua Gouvier (my wife)") which the providers' exact search rejects.
        cleaned = _strip_trailing_annotations(contact)
        if cleaned and cleaned != contact:
            candidates, first_match_name = await _search_contacts_with_phones(user_id, cleaned)
    if first_match_name is None:
        return _CalleeResolution(kind="not_found")
    if not candidates:
        return _CalleeResolution(kind="no_phone", name=first_match_name)
    if len(candidates) > 1:
        return _CalleeResolution(kind="ambiguous", candidates=candidates)
    name, phone = candidates[0]
    return _CalleeResolution(kind="resolved", name=name, phone=phone)


async def _telephony_connector_active(user_id: UUID) -> bool:
    """Whether the user's ELEVENLABS_TELEPHONY connector is active (the guard)."""
    from src.domains.telephony.connector import TelephonyConnectorService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await TelephonyConnectorService(db).get_active(user_id) is not None


def _create_phone_call_draft(
    *,
    callee_name: str,
    callee_phone: str,
    objective: str,
    date_window: str | None,
    user_language: str,
) -> UnifiedToolOutput:
    """Build the PHONE_CALL draft (requires_confirmation=True).

    Kept in the telephony bounded context rather than the shared ``drafts.service``
    convenience layer — the shared service file is frozen by the file-size ratchet,
    and telephony owns its own draft shape.
    """
    draft_input = PhoneCallDraftInput(
        callee_name=callee_name,
        callee_phone=callee_phone,
        objective=objective,
        date_window=date_window,
        user_language=user_language,
    )
    return DraftService().create_draft(
        draft_type=DraftType.PHONE_CALL,
        content=draft_input.model_dump(),
        related_registry_ids=draft_input.related_registry_ids,
        source_tool="place_phone_call_tool",
        user_language=user_language,
    )


async def _build_place_phone_call_output(
    *,
    user_id: UUID,
    locale: str,
    contact: str,
    objective: str,
    date_window: str | None,
) -> UnifiedToolOutput:
    """Guard → resolve callee → build the PHONE_CALL draft (or a friendly failure)."""
    phrases = get_tool_phrases(locale)

    if not await _telephony_connector_active(user_id):
        return UnifiedToolOutput.failure(
            message=phrases["not_configured"], error_code="telephony_not_configured"
        )

    resolution = await _resolve_callee(user_id, contact)
    if resolution.kind == "not_found":
        return UnifiedToolOutput.failure(
            message=phrases["not_found"].format(name=contact), error_code="contact_not_found"
        )
    if resolution.kind == "no_phone":
        return UnifiedToolOutput.failure(
            message=phrases["no_phone"].format(name=resolution.name),
            error_code="contact_no_phone",
        )
    if resolution.kind == "ambiguous":
        listed = ", ".join(name for name, _ in resolution.candidates)
        return UnifiedToolOutput.failure(
            message=phrases["ambiguous"].format(name=contact, candidates=listed),
            error_code="contact_ambiguous",
        )

    logger.info(
        "place_phone_call_draft_prepared",
        user_id=str(user_id),
        has_date_window=date_window is not None,
    )
    return _create_phone_call_draft(
        callee_name=resolution.name,
        callee_phone=resolution.phone,
        objective=objective,
        date_window=date_window,
        user_language=locale,
    )


@connector_tool(
    name="place_phone_call",
    agent_name="telephony_agent",
    category="write",
    # Per-user hourly cap from settings (paid external calls) — not the write default.
    rate_limit_max_calls=lambda: get_settings().telephony_rate_limit_per_hour,
    rate_limit_window_seconds=3600,
)
@with_user_preferences
async def place_phone_call_tool(
    contact: Annotated[
        str,
        "Who to call: a contact name ('Marie', 'my brother') or a raw phone number in "
        "international format (+33...). A name is resolved against the active contacts provider.",
    ],
    objective: Annotated[
        str,
        "What LIA must accomplish on the call, in the user's words "
        "(e.g. 'ask if she is free for dinner on Tuesday').",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    date_window: str | None = None,
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Place an outbound phone call on the user's behalf (creates a draft for confirmation).

    Resolves the callee to a phone number and returns a phone-call draft that the
    user must confirm via HITL before LIA dials. Requires the user's ElevenLabs
    telephony connector to be active.

    Args:
        contact: Contact name to resolve, or a raw international phone number.
        objective: Goal LIA pursues during the call.
        runtime: LangChain tool runtime.
        date_window: Optional free-text availability window (e.g. 'this week').
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput with a PHONE_CALL draft (requires_confirmation=True), or
        a friendly failure guiding activation / clarifying the callee.
    """
    config = validate_runtime_config(runtime, "place_phone_call_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    user_id = parse_user_id(config.user_id)
    return await _build_place_phone_call_output(
        user_id=user_id,
        locale=locale,
        contact=contact,
        objective=objective,
        date_window=date_window,
    )


async def execute_phone_call_draft(
    draft_content: dict,
    user_id: UUID,
    deps: object,
) -> dict:
    """Execute a confirmed PHONE_CALL draft: actually place the call.

    Registered in ``draft_executor.ensure_executors_registered()``. On success
    it returns ``{"name", "call_id"}`` so the framework renders the async-safe
    ``phone_call`` success message ("I'm calling {name} now …"). Non-placed
    outcomes raise :class:`TelephonyExecutionError` with a localized message —
    caught by the executor framework (no crash), shown to the user.

    Args:
        draft_content: PHONE_CALL draft content (callee_name/phone, objective, …).
        user_id: User UUID.
        deps: ToolDependencies (unused — the call runs on its own DB session).

    Returns:
        Result dict ``{"success", "name", "call_id"}`` on a placed call.

    Raises:
        TelephonyExecutionError: on already-active / not-configured / failed —
            rendered as the localized message, never a traceback.
    """
    from src.domains.telephony.service import TelephonyExecutionError, TelephonyService
    from src.infrastructure.database.session import get_db_context

    lang = draft_content.get("user_language", "fr")
    callee_name = draft_content.get("callee_name", "")
    phrases = get_tool_phrases(lang)

    async with get_db_context() as db:
        result = await TelephonyService(db).initiate_call(
            user_id=user_id,
            callee_display=callee_name,
            callee_phone=draft_content["callee_phone"],
            objective=draft_content.get("objective", ""),
            date_window=draft_content.get("date_window"),
            user_language=lang,
        )

    if result.status == "placed":
        # 'name' drives the phone_call success template (async-safe, not past tense).
        return {"success": True, "name": callee_name, "call_id": str(result.call_id)}

    raise TelephonyExecutionError(phrases[_STATUS_TO_PHRASE[result.status]])
