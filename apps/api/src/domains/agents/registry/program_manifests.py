"""Interdomain-program manifest registration (single loader entry point).

The frozen ``catalogue_loader`` is at its size cap, so the program's new
domains register through this ONE aggregator (net-zero loader cost per new
domain). One function per lot-delivered domain, fanned out below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry


def register_program_manifests(registry: AgentRegistry) -> None:
    """Register every interdomain-program agent + tool manifest.

    Args:
        registry: Global agent registry being initialized.
    """
    from src.domains.agents.automation.catalogue_registration import (
        register_automation_manifests,
    )
    from src.domains.agents.documents.catalogue_manifests import (
        DOCUMENT_AGENT_MANIFEST,
        search_user_documents_catalogue_manifest,
    )
    from src.domains.agents.google_contacts.person_overview_manifest import (
        get_person_overview_catalogue_manifest,
    )

    register_automation_manifests(registry)
    registry.register_agent_manifest(DOCUMENT_AGENT_MANIFEST)
    registry.register_tool_manifest(search_user_documents_catalogue_manifest)
    registry.register_tool_manifest(get_person_overview_catalogue_manifest)

    # Peers program: flag-gated like its router — a disabled instance must
    # not advertise tools whose REST surface is absent.
    from src.core.config import settings

    if getattr(settings, "peers_enabled", False):
        from src.domains.agents.peer.catalogue_registration import (
            register_peer_manifests,
        )

        register_peer_manifests(registry)
