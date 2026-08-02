"""Fixtures shared by the manifest-truthfulness suites.

The catalogue is loaded once per module rather than per test: building it walks
every domain's manifests, and both suites read it dozens of times.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.catalogue_loader import initialize_catalogue


@pytest.fixture(scope="module")
def manifests() -> dict[str, ToolManifest]:
    """The catalogue as the planner receives it, keyed by tool name."""
    registry = AgentRegistry()
    initialize_catalogue(registry)
    return {manifest.name: manifest for manifest in registry.list_tool_manifests()}
