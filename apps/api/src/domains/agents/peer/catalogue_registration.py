"""Registration of the peer manifests into the catalogue (peers program).

Kept with its owner package (automation precedent): ``catalogue_loader`` is
frozen at its size cap, so it delegates the per-domain registrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.agents.peer.catalogue_manifests import (
    PEER_AGENT_MANIFEST,
    get_peer_availability_catalogue_manifest,
    get_peer_tasks_catalogue_manifest,
    list_peer_connections_catalogue_manifest,
    send_peer_message_catalogue_manifest,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry


def register_peer_manifests(registry: AgentRegistry) -> None:
    """Register the peer agent + its four tool manifests.

    Args:
        registry: Global agent registry being initialized.
    """
    registry.register_agent_manifest(PEER_AGENT_MANIFEST)
    registry.register_tool_manifest(send_peer_message_catalogue_manifest)
    registry.register_tool_manifest(list_peer_connections_catalogue_manifest)
    registry.register_tool_manifest(get_peer_availability_catalogue_manifest)
    registry.register_tool_manifest(get_peer_tasks_catalogue_manifest)
