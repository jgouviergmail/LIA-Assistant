"""What a confirmed e-mail draft does (ADR-369, LOT 5.4).

The tools of ``emails_tools`` prepare a card; these functions act once the person has
confirmed it. Each is the ``execute_fn`` of its draft type: it leaves with what the card
showed, the person's files read as it leaves, and a file gone since stops the message.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.tools.email_files import files_to_send

logger = structlog.get_logger(__name__)


async def execute_email_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email draft: actually send the email.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    This is the execute_fn passed to DraftService.process_draft_action().
    It retrieves the Gmail client and sends the email.

    Args:
        draft_content: Dict with email content from draft
            {to, subject, body, cc, bcc, is_html}
        user_id: User UUID
        deps: ToolDependencies for getting Gmail client

    Returns:
        Dict with send result:
            {success, message_id, thread_id, to, subject, message}

    Raises:
        Exception: If email send fails
    """
    # Get email client via dynamic provider resolution
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("email", user_id, deps)

    # Send email
    result = await client.send_email(
        to=draft_content["to"],
        subject=draft_content["subject"],
        body=draft_content["body"],
        cc=draft_content.get("cc"),
        bcc=draft_content.get("bcc"),
        is_html=draft_content.get("is_html", False),
        attachments=await files_to_send(draft_content, user_id, client),
    )

    logger.info(
        "email_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content["to"],
        "subject": draft_content["subject"],
        "message": APIMessages.email_sent_successfully(draft_content["to"]),
    }


async def execute_email_reply_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email reply draft: actually send the reply.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.agents.services.card_composition_service import draft_composition_scope
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    async with draft_composition_scope(draft_content, user_id, deps, "reply"):
        client, _resolved_type = await resolve_client_for_category("email", user_id, deps)
        result = await client.reply_email(
            message_id=draft_content["message_id"],
            body=draft_content["body"],
            reply_all=draft_content.get("reply_all", False),
            # Whom the card showed (the clients' own rule, ADR-344), or whom the
            # person put instead: Graph would otherwise address it by ITS rule.
            to=draft_content.get("to"),
            cc=draft_content.get("cc"),
            attachments=await files_to_send(draft_content, user_id, client),
        )

    logger.info(
        "email_reply_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
        original_message_id=draft_content["message_id"],
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content.get("to"),
        "subject": draft_content.get("subject"),
        "message": APIMessages.reply_sent_successfully(),
    }


async def execute_email_forward_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email forward draft: actually send the forwarded email.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.agents.services.card_composition_service import draft_composition_scope
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    async with draft_composition_scope(draft_content, user_id, deps, "forward"):
        client, _resolved_type = await resolve_client_for_category("email", user_id, deps)
        result = await client.forward_email(
            message_id=draft_content["message_id"],
            to=draft_content["to"],
            body=draft_content.get("body"),
            cc=draft_content.get("cc"),
            attachments=await files_to_send(draft_content, user_id, client),
        )

    logger.info(
        "email_forward_draft_executed",
        user_id=str(user_id),
        message_id=result.get("id"),
        original_message_id=draft_content["message_id"],
    )

    return {
        "success": True,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "to": draft_content["to"],
        "subject": draft_content.get("subject"),
        "message": APIMessages.email_forwarded_successfully(draft_content["to"]),
    }


async def execute_email_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute an email delete draft: actually move email to trash.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.agents.services.card_composition_service import draft_composition_scope
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    async with draft_composition_scope(draft_content, user_id, deps, "delete_email"):
        client, _resolved_type = await resolve_client_for_category("email", user_id, deps)
        await client.trash_email(draft_content["message_id"])

    # Falsy subject → APIMessages renders its localized subject-less variant.
    subject = draft_content.get("subject") or None

    logger.info(
        "email_delete_draft_executed",
        user_id=str(user_id),
        message_id=draft_content["message_id"],
    )

    return {
        "success": True,
        "message_id": draft_content["message_id"],
        "message": APIMessages.email_moved_to_trash(subject),
    }
