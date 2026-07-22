"""Registration of the automation manifests into the catalogue (ADR-140).

Kept with its owner package: ``catalogue_loader`` is frozen at its size cap,
so it delegates the per-domain registrations it cannot absorb.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.agents.automation.catalogue_manifests import (
    AUTOMATION_AGENT_MANIFEST,
    create_scheduled_action_catalogue_manifest,
    list_scheduled_actions_catalogue_manifest,
    toggle_scheduled_action_catalogue_manifest,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry


def register_automation_manifests(registry: AgentRegistry) -> None:
    """Register the automation agent + its three tool manifests.

    Args:
        registry: Global agent registry being initialized.
    """
    registry.register_agent_manifest(AUTOMATION_AGENT_MANIFEST)
    registry.register_tool_manifest(create_scheduled_action_catalogue_manifest)
    registry.register_tool_manifest(list_scheduled_actions_catalogue_manifest)
    registry.register_tool_manifest(toggle_scheduled_action_catalogue_manifest)
