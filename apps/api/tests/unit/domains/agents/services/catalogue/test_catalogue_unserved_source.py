"""The planner is told which source holds nothing for the person (ADR-390 qualification).

A category tool stays offered without a provider: « no provider is connected » is
the honest answer when the person asks for that source. Measured 2026-11-15 on the
proof account, whose tasks and calendar connectors are broken: for « what day must
I return the books » and « when must I take care of the car », the analyzer named
the reminder domain beside the tasks, and the planner planned the tasks alone — a
call that could only say nothing was connected, while the reminder held the answer.
The planner could not know: what the turn knows about its sources reaches its
catalogue entry, and the prompt says what that entry means.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.registry.catalogue import (
    CostProfile,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.services.smart_catalogue_service import (
    UNSERVED_SOURCE_KEY,
    get_smart_catalogue_service,
)

pytestmark = pytest.mark.unit


def _manifest() -> ToolManifest:
    return ToolManifest(
        name="get_tasks_tool",
        agent="task_agent",
        description="Read the person's tasks.",
        parameters=[],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
    )


def test_a_source_the_turn_found_unserved_says_so_in_its_entry() -> None:
    entry = get_smart_catalogue_service()._manifest_to_dict(
        replace(_manifest(), unserved_category="tasks")
    )

    assert entry[UNSERVED_SOURCE_KEY] is False


def test_a_source_nobody_judged_carries_no_claim() -> None:
    entry = get_smart_catalogue_service()._manifest_to_dict(_manifest())

    assert UNSERVED_SOURCE_KEY not in entry


def test_the_planner_prompt_says_what_the_entry_means() -> None:
    """A field the planner reads with no sentence saying what it means is noise."""
    assert f"`{UNSERVED_SOURCE_KEY}: false`" in load_prompt("smart_planner_prompt", version="v1")
