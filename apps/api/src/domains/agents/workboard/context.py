"""The ticket as the context system sees it (ADR-276, lot 3).

Two declarations the chat needs to point at a ticket AFTER the turn that
listed it — « passe le deuxième en cours », « celui-là » — and both live here
rather than in the tool module, because they are the CONTEXT's business, not
the tools': every reader of ``CONTEXT_DOMAIN_TICKETS`` finds them in one place.

- The CONTEXT TYPE, registered at import like every domain's
  (``tasks_tools`` is the model): ``list_tickets`` saves its page under
  ``tickets`` — the domain's ``result_key``, so a ``$steps.<step>.tickets``
  reference and the store agree — and a confirmed deletion takes the row back
  out (``draft_executor._DRAFT_TYPE_TO_TCM_DOMAIN``).
- The REGISTRY ITEMS a read tool emits, one per ticket, keyed by the ticket's
  own id: the response and the frontend resolve a ticket by it, the
  ``FOR_EACH`` filter matches the key against the payload's ``id``
  (``ITEMS_KEY_TO_REGISTRY_CONFIG``), and the trust layer marks the text as
  another person's where it can be (``TRUST_BY_REGISTRY_TYPE``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.domains.agents.constants import AGENT_TICKET, CONTEXT_DOMAIN_TICKETS
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)


class TicketItem(BaseModel):
    """What a ticket looks like in the context store: enough to be pointed at.

    The bounded view ``_ticket_summary`` hands back, never the row — a
    description can run to thousands of characters the model would pay for
    on every reference.
    """

    id: str
    title: str
    status: str
    priority: str
    assignee_kind: str
    start_at: str | None = None
    due_at: str | None = None


ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_TICKETS,
        agent_name=AGENT_TICKET,
        item_schema=TicketItem,
        primary_id_field="id",
        display_name_field="title",
        reference_fields=["title", "status", "priority"],
        icon="🗂️",
    )
)


def ticket_registry_items(
    tickets: list[dict[str, Any]], *, tool_name: str
) -> dict[str, RegistryItem]:
    """One registry item per ticket, keyed by the ticket's own id.

    The key IS the payload's ``id``: that is what the ``FOR_EACH`` filter
    compares (``ITEMS_KEY_TO_REGISTRY_CONFIG["tickets"]``), and a prefixed
    key — the reminder tools' habit — is one the filter never matches.

    Args:
        tickets: Bounded ticket views (``_ticket_summary`` shape).
        tool_name: The tool that read them, for tracing.

    Returns:
        The registry updates, in the order the tickets were given.
    """
    return {
        ticket["id"]: RegistryItem(
            id=ticket["id"],
            type=RegistryItemType.TICKET,
            payload=ticket,
            meta=RegistryItemMeta(
                source=CONTEXT_DOMAIN_TICKETS, domain=CONTEXT_DOMAIN_TICKETS, tool_name=tool_name
            ),
        )
        for ticket in tickets
    }


__all__ = ["TicketItem", "ticket_registry_items"]
