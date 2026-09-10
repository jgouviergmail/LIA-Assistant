"""Registration of the workboard manifests into the catalogue (ADR-276).

Kept with its owner package (the automation and peers precedent):
``catalogue_loader`` is frozen at its size cap, so it delegates the per-domain
registrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.agents.workboard.catalogue_manifests import (
    TICKET_AGENT_MANIFEST,
    comment_ticket_catalogue_manifest,
    create_ticket_catalogue_manifest,
    delete_ticket_catalogue_manifest,
    get_ticket_catalogue_manifest,
    list_tickets_catalogue_manifest,
    update_ticket_catalogue_manifest,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry


def register_workboard_manifests(registry: AgentRegistry) -> None:
    """Register the ticket agent and its six tool manifests.

    Args:
        registry: Global agent registry being initialized.
    """
    registry.register_agent_manifest(TICKET_AGENT_MANIFEST)
    registry.register_tool_manifest(create_ticket_catalogue_manifest)
    registry.register_tool_manifest(update_ticket_catalogue_manifest)
    registry.register_tool_manifest(comment_ticket_catalogue_manifest)
    registry.register_tool_manifest(list_tickets_catalogue_manifest)
    registry.register_tool_manifest(get_ticket_catalogue_manifest)
    registry.register_tool_manifest(delete_ticket_catalogue_manifest)
