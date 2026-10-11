"""Only an actual native application commit closes a conditional draft operation."""

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.requested_outcomes import GoalFieldExpectation, GoalRequirement
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.outcome_evidence import (
    observe_requested_outcome,
    requested_outcome_coverage,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("tool", "changes", "extra", "expected"),
    [
        ("update_lia_preferences_tool", {}, {}, "satisfied"),
        ("update_lia_preferences_tool", {"committed": False}, {}, "pending_confirmation"),
        ("update_lia_preferences_tool", {"phase": "claimed"}, {}, "pending_confirmation"),
        ("update_lia_preferences_tool", {}, {"draft_id": "pending"}, "pending_confirmation"),
        ("update_lia_preferences_tool", {}, {"draft": {"id": "pending"}}, "pending_confirmation"),
        ("update_lia_preferences_tool", {"committed": "true"}, {}, "pending_confirmation"),
        ("create_reminder_tool", {}, {}, "pending_confirmation"),
    ],
)
def test_only_registered_committed_application_results_prove_execution(
    tool, changes, extra, expected
):
    goal = GoalRequirement(
        domain="setting" if tool == "update_lia_preferences_tool" else "reminder",
        kind="action",
        operation="update" if tool == "update_lia_preferences_tool" else "create",
        label="font size",
        source_quote="18",
        expected_fields=(
            GoalFieldExpectation(
                field="application_result.values.font_size",
                expected_value="18",
                source_quote="18",
            ),
        ),
    )
    result = {
        "success": True,
        "structured_data": {
            "application_result": {
                "success": True,
                "phase": "committed",
                "committed": True,
                "values": {"font_size": 18},
                **changes,
            },
            **extra,
        },
    }
    token = request_tool_manifests_ctx.set(collect_static_manifests())
    try:
        evidence = observe_requested_outcome(tool, {}, result)
        assert requested_outcome_coverage([goal], [evidence], timezone="UTC")[0].status == expected
    finally:
        request_tool_manifests_ctx.reset(token)
