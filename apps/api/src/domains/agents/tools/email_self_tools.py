"""Email tool — ``send_email_to_me`` (ADR-314).

An e-mail the person sends to THEMSELVES needs no confirmation card: the one who
would confirm is the one who receives it, and deleting it undoes it — the
``call_me`` precedent (ADR-290), for the same reason and with the same effect: a
``reversible`` policy that the effect gate LEDGERS, including in a routine,
where a draft would be refused (« every morning, e-mail me the weather »).

The recipient is never a parameter, so the tool cannot write to anyone else:

- a connected mailbox sends to ITS OWN address, as its provider states it
  (``get_own_address``, the three email clients alike);
- without one, LIA's own mail relay sends to the account's e-mail address —
  only when that address is VERIFIED, or an account opened with someone else's
  address would turn LIA into a relay aimed at that someone (owner decision
  2026-09-24, arbitration Q1);
- a mailbox that is connected but broken is not usable: the relay delivers,
  and the « Reconnect » notice says why the message did not come from it.

A failure is returned, never raised (ADR-303), and nothing reaches the model as
« sent » unless a provider or the relay accepted it.
"""

from __future__ import annotations

import html
from typing import Annotated, Any, Final, Literal
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.constants import AGENT_EMAIL
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.emails.content_generation import (
    NOTE_TO_SELF_RECIPIENT,
    EmailContent,
    resolve_email_content,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    parse_user_id,
    validate_runtime_config,
)

logger = structlog.get_logger(__name__)

_TOOL_NAME: Final = "send_email_to_me_tool"
_EMAIL_CATEGORY: Final = "email"

#: Where the message went: the connected mailbox, or the account's address.
SelfRoute = Literal["mailbox", "account_email"]


def _refusal(message: str, code: ToolErrorCode) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(message=message, error_code=code.value)


def _sent(route: SelfRoute, *, message_id: str | None = None, note: str = "") -> UnifiedToolOutput:
    where = (
        "to the user's own mailbox"
        if route == "mailbox"
        else "by LIA's mail relay to the user's account address"
    )
    logger.info("email_to_self_sent", route=route)
    return UnifiedToolOutput.action_success(
        message=f"The e-mail was sent {where}.{note}",
        structured_data={"sent_to": route, "message_id": message_id or None},
    )


def relay_bodies(content: EmailContent, *, is_html: bool) -> tuple[str, str]:
    """The HTML and plain parts LIA's relay sends.

    A plain body is ESCAPED into its HTML part — model-written text never
    becomes markup — and an HTML body gets a readable plain part.

    Args:
        content: The settled subject and body.
        is_html: Whether the body is HTML.

    Returns:
        ``(html_body, text_body)``.
    """
    from src.domains.agents.display.plain_text import strip_html_if_markup

    if is_html:
        return content.body, strip_html_if_markup(content.body)
    escaped = html.escape(content.body)
    return f'<pre style="white-space:pre-wrap;font-family:inherit">{escaped}</pre>', content.body


async def _send_from_mailbox(
    runtime: ToolRuntime[LiaRuntimeContext, Any],
    user_id: UUID,
    content: EmailContent,
    *,
    is_html: bool,
) -> UnifiedToolOutput | None:
    """Send through the connected mailbox, to its own address.

    Returns:
        The outcome, or None when no mailbox is ACTIVE (the relay takes over).
    """
    from src.domains.agents.dependencies import get_dependencies
    from src.domains.connectors.provider_resolver import (
        resolve_active_connector,
        resolve_client_for_category,
    )

    deps = get_dependencies(runtime)
    connector_service = await deps.get_connector_service()
    if await resolve_active_connector(user_id, _EMAIL_CATEGORY, connector_service) is None:
        return None
    client, _connector_type = await resolve_client_for_category(_EMAIL_CATEGORY, user_id, deps)
    own_address = await client.get_own_address()
    if not own_address:
        return _refusal(
            "The connected mailbox did not state its own address: nothing was sent.",
            ToolErrorCode.CONFIGURATION_ERROR,
        )
    result = await client.send_email(
        to=own_address, subject=content.subject, body=content.body, is_html=is_html
    )
    return _sent("mailbox", message_id=str(result.get("id") or ""))


async def _mailbox_needs_reconnecting(
    runtime: ToolRuntime[LiaRuntimeContext, Any], user_id: UUID
) -> bool:
    """Whether the email category holds a connector stuck in ERROR — and say so."""
    from src.domains.agents.dependencies import get_dependencies
    from src.domains.agents.services.connector_error_notice import emit_connector_notice
    from src.domains.connectors.provider_resolver import find_error_connector_type

    connector_service = await get_dependencies(runtime).get_connector_service()
    broken = await find_error_connector_type(user_id, _EMAIL_CATEGORY, connector_service)
    if broken:
        emit_connector_notice(broken, "reconnect", _TOOL_NAME)
    return bool(broken)


async def _send_from_lia(
    user_id: UUID, content: EmailContent, *, is_html: bool, note: str = ""
) -> UnifiedToolOutput:
    """Send through LIA's own relay to the account's VERIFIED address."""
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.email.email_service import get_email_service

    async with get_db_context() as db:
        user = await db.get(User, user_id)
        address = user.email if user is not None and user.is_verified else None
    if not address:
        return _refusal(
            "No mailbox is connected and the account's e-mail address is not verified: "
            "nothing was sent. A mailbox can be connected in Settings > Connectors.",
            ToolErrorCode.CONFIGURATION_ERROR,
        )
    html_body, text_body = relay_bodies(content, is_html=is_html)
    if not await get_email_service().send_email(address, content.subject, html_body, text_body):
        return _refusal(
            "LIA's mail relay did not accept the message: nothing was sent.",
            ToolErrorCode.EXTERNAL_API_ERROR,
        )
    return _sent("account_email", note=note)


@connector_tool(name="send_email_to_me", agent_name=AGENT_EMAIL, category="write")
async def send_email_to_me_tool(
    subject: Annotated[str | None, "Subject (optional if content_instruction is given)"] = None,
    body: Annotated[str | None, "Body (optional if content_instruction is given)"] = None,
    content_instruction: Annotated[
        str | None,
        "What the e-mail should contain, for generation (a summary, a note, a digest). "
        "Use instead of subject/body.",
    ] = None,
    is_html: Annotated[bool, "True if body is HTML (default False)"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Send an e-mail to the user THEMSELVES — no confirmation, routines included.

    Args:
        subject: Subject, unless generated.
        body: Body, unless generated.
        content_instruction: What to write, for generation.
        is_html: Whether ``body`` is HTML.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying where the message went, or a typed failure.
    """
    config = validate_runtime_config(runtime, _TOOL_NAME)
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    content = await resolve_email_content(
        runtime=runtime,
        recipient=NOTE_TO_SELF_RECIPIENT,
        subject=subject,
        body=body,
        content_instruction=content_instruction,
    )
    if isinstance(content, UnifiedToolOutput):
        return content

    try:
        sent = await _send_from_mailbox(runtime, user_id, content, is_html=is_html)
        if sent is not None:
            return sent
        broken = await _mailbox_needs_reconnecting(runtime, user_id)
    except Exception as e:  # noqa: BLE001 — classified and returned, never raised (ADR-303)
        return handle_tool_exception(e, _TOOL_NAME, {"route": "mailbox"})

    note = (
        " The connected mailbox needs to be reconnected, so it did not come from it."
        if broken
        else ""
    )
    try:
        return await _send_from_lia(user_id, content, is_html=is_html, note=note)
    except Exception as e:  # noqa: BLE001 — classified and returned, never raised (ADR-303)
        return handle_tool_exception(e, _TOOL_NAME, {"route": "relay"})


__all__ = ["relay_bodies", "send_email_to_me_tool"]
