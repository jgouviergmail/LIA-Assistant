"""Guard: a system skill's deterministic plan runs tools that exist, under their own agent.

A plan template is text. The skill bypass (ADR-160) turns it into a plan with no
model call, for every account the skill is detected for: a step naming a tool
that was renamed, the wrong agent, a parameter the tool does not take or a step
type a template cannot run fails at RUN time, never at boot. Every system skill's
template is read here against the catalogue loaded with every feature flag on
(a manifest gated off in CI would otherwise read as missing) and against the
registered tools' own argument schemas — the plan's parameters reach the tool
function, which accepts some the planner is never shown (``days_ahead``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifestNotFound
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.services.planner.strategies.skill_bypass import TEMPLATE_STEP_TYPES
from src.domains.skills.loader import scan_skills_directory
from tests._repo_paths import repo_root_or_skip
from tests.unit.domains.agents.registry.catalogue_flags import CATALOGUE_FEATURE_FLAGS

pytestmark = pytest.mark.unit

SKILLS_DIR = repo_root_or_skip() / "data" / "skills" / "system"


def _deterministic_templates() -> list[tuple[str, dict[str, Any]]]:
    """Every system skill whose plan template the bypass turns into a plan as is."""
    found: list[tuple[str, dict[str, Any]]] = []
    for skill in scan_skills_directory(SKILLS_DIR, scope="admin"):
        template = skill.get("plan_template") or {}
        if template.get("deterministic"):
            found.append((skill["name"], template))
    return found


@pytest.fixture(scope="module")
def runnable() -> Iterator[tuple[AgentRegistry, dict[str, BaseTool]]]:
    """The full catalogue and the registered tools, every catalogue flag on."""
    from src.core.config import settings
    from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

    with pytest.MonkeyPatch.context() as patch:
        for flag in CATALOGUE_FEATURE_FLAGS:
            if hasattr(settings, flag):
                patch.setattr(settings, flag, True, raising=False)
        previous = registry_module._global_registry
        registry = AgentRegistry()
        initialize_catalogue(registry)
        registry_module._global_registry = registry
        try:
            ensure_tools_loaded()
            yield registry, get_all_tools()
        finally:
            registry_module._global_registry = previous


def template_problems(
    template: dict[str, Any], registry: AgentRegistry, tools: dict[str, BaseTool]
) -> list[str]:
    """What in a template the bypass would turn into a plan that cannot run.

    Args:
        template: The skill's ``plan_template``.
        registry: The full catalogue.
        tools: The registered tools by name.

    Returns:
        One sentence per defect, empty when every step can run.
    """
    problems: list[str] = []
    for step in template.get("steps") or []:
        step_id = step.get("step_id", "?")
        step_type = step.get("step_type", "TOOL")
        if step_type not in {kind.value for kind in TEMPLATE_STEP_TYPES}:
            problems.append(f"{step_id}: a template runs no {step_type} step")
            continue
        name = step.get("tool_name", "")
        try:
            manifest = registry.get_tool_manifest(name)
        except ToolManifestNotFound:
            problems.append(f"{step_id}: no tool named {name!r}")
            continue
        if manifest.agent != step.get("agent_name"):
            problems.append(
                f"{step_id}: {name} belongs to {manifest.agent}, not {step.get('agent_name')}"
            )
        tool = tools.get(name)
        accepted = set(tool.args) if tool is not None else set()
        unknown = sorted(set(step.get("parameters") or {}) - accepted)
        if unknown:
            problems.append(f"{step_id}: {name} takes no {', '.join(unknown)}")
    return problems


def test_the_system_skills_carry_deterministic_templates() -> None:
    """Anti-vacuity: the parametrized guard below runs over real templates."""
    assert len(_deterministic_templates()) >= 1


@pytest.mark.parametrize(
    ("skill_name", "template"),
    _deterministic_templates(),
    ids=[name for name, _ in _deterministic_templates()],
)
def test_every_step_runs_a_real_tool_under_its_own_agent(
    skill_name: str,
    template: dict[str, Any],
    runnable: tuple[AgentRegistry, dict[str, BaseTool]],
) -> None:
    assert template_problems(template, *runnable) == [], skill_name


def test_the_guard_refuses_what_cannot_run(
    runnable: tuple[AgentRegistry, dict[str, BaseTool]],
) -> None:
    """Proven on a failing fixture: one defect of each kind, each one named."""
    broken = {
        "deterministic": True,
        "steps": [
            {"step_id": "gone", "agent_name": "event_agent", "tool_name": "no_such_tool"},
            {"step_id": "agent", "agent_name": "task_agent", "tool_name": "get_events_tool"},
            {
                "step_id": "param",
                "agent_name": "event_agent",
                "tool_name": "get_events_tool",
                "parameters": {"no_such_parameter": 1},
            },
            {"step_id": "kind", "step_type": "CONDITIONAL", "tool_name": "get_events_tool"},
        ],
    }

    problems = template_problems(broken, *runnable)

    assert [problem.split(":")[0] for problem in problems] == ["gone", "agent", "param", "kind"]
