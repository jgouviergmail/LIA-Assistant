"""The skills tools are ONE affordance, and every manifest says so (2026-09-20).

Replayed on dev: the ReAct selector (ADR-293) bound ``activate_skill_tool`` by
rank and dropped ``run_skill_script`` — the loop activated the skill, could not
run its script and answered in prose, the production motif on both skills.
The manifests now declare a ``binding_unit`` the selector binds whole or not at
all. A fifth skills tool added without it would be bound alone again.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.skills import catalogue_manifests
from src.domains.skills.catalogue_manifests import SKILLS_BINDING_UNIT

pytestmark = pytest.mark.unit


def _skills_manifests() -> list[ToolManifest]:
    return [
        value for value in vars(catalogue_manifests).values() if isinstance(value, ToolManifest)
    ]


def test_every_skills_tool_declares_the_one_binding_unit() -> None:
    manifests = _skills_manifests()
    assert len(manifests) >= 4, "the four skills tools are declared in this module"
    assert {m.binding_unit for m in manifests} == {SKILLS_BINDING_UNIT}


def test_the_unit_is_the_skills_tools_alone() -> None:
    """No other family may borrow the unit: it would be bound with every skill call."""
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    registry = AgentRegistry()
    initialize_catalogue(registry)
    skills_names = {m.name for m in _skills_manifests()}
    borrowed = [
        m.name
        for m in registry.list_tool_manifests()
        if m.binding_unit == SKILLS_BINDING_UNIT and m.name not in skills_names
    ]
    assert borrowed == []
