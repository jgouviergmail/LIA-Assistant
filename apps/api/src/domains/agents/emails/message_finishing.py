"""The last touch a whole message gets before a tool hands it on (ADR-287, ADR-344).

Label ids are named from the mailbox's own listing, and the body and the
attachments are flattened to the top level the cards and the model read. Shared
by the reading of e-mails and the listing of the person's drafts, which read
whole messages the same way; ``emails_tools.py`` is frozen at its audited size.
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


class LabelListingClient(Protocol):
    """A mailbox client that names its labels."""

    async def list_labels(self, use_cache: bool = True) -> dict[str, str]: ...


def enrich_message(message: dict[str, Any]) -> None:
    """Flatten the body and the attachments of a whole message, in place.

    For Gmail the text body is read from the MIME tree; Apple and Microsoft
    hand it top-level already (ADR-287). The WHOLE body: a detail level
    paginates it under a token budget, and the cards truncate for display on
    their own.

    Args:
        message: A whole message, as its client returned it.
    """
    try:
        from src.domains.agents.tools.formatters import GmailFormatter

        body = GmailFormatter._extract_body(message)
        if body:
            message["body"] = body
        if message.get("attachments") is None:
            message["attachments"] = GmailFormatter._extract_attachments(message) or []
    except Exception as error:
        logger.warning(
            "get_emails_enrich_failed",
            message_id=message.get("id", ""),
            error_type=type(error).__name__,
        )


async def finish_messages(
    client: LabelListingClient, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Name the labels and flatten body + attachments of whole messages.

    Args:
        client: The mailbox client (its label listing is read once).
        messages: Whole messages, as the client returned them.

    Returns:
        The same messages, enriched in place.
    """
    if not messages:
        return messages
    labels_mapping = await client.list_labels(use_cache=True)
    for message in messages:
        if "labelIds" in message:
            message["labelIds"] = [
                labels_mapping.get(label_id, label_id) for label_id in message["labelIds"]
            ]
        enrich_message(message)
    return messages


__all__ = ["LabelListingClient", "enrich_message", "finish_messages"]
