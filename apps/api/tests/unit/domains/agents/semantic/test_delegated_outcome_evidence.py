"""A real MCP task factory's opaque report never authorizes replay or success."""

from dataclasses import asdict

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.requested_outcomes import (
    GoalFieldExpectation,
    GoalRequirement,
)
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.outcome_evidence import (
    coverage_has_gap,
    observe_requested_outcome,
    requested_outcome_coverage,
)
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest
from src.infrastructure.mcp.user_context import _build_user_tool_manifest

pytestmark = pytest.mark.unit


def _goal(kind: str) -> GoalRequirement:
    return GoalRequirement.model_validate(
        {
            "domain": "mcp_issues",
            "label": "Issue",
            "source_quote": "Issue",
            "kind": kind,
            "operation": "create" if kind == "action" else None,
            "collection_key": "issues",
            "min_count": 1,
        }
    )


@pytest.mark.parametrize("name", ["mcp_issues_task", "unusual_delegator"])
@pytest.mark.parametrize("kind", ["read", "action"])
@pytest.mark.parametrize(
    "raw",
    [
        {
            "success": True,
            "structured_data": {"server_name": "Issues", "iterations": 2},
        },
        {"success": False, "error_code": "TIMEOUT"},
        {"success": True, "structured_data": {"draft_id": "pending-draft"}},
        {
            "success": True,
            "structured_data": {"issues": []},
            "metadata": {"partial": True},
        },
    ],
)
def test_real_factory_delegation_is_neutral_before_failure_draft_or_partial(name, kind, raw):
    manifest = build_mcp_react_task_manifest(
        name, "mcp_issues_agent", "Issues", "Issue tools", [], [], hitl_required=False
    )
    assert manifest.delegates_execution and asdict(manifest)["delegates_execution"] is True
    token = request_tool_manifests_ctx.set([manifest])
    try:
        goal = _goal(kind)
        observation = observe_requested_outcome(name, {}, raw, requirements=[goal])
        assert observation is not None and observation["kind"] == "unknown"
        coverage = requested_outcome_coverage([goal], [observation], timezone="UTC")[0]
        assert coverage.status == "unknown" and not coverage_has_gap(coverage)
        assert coverage.tool_names == (name,)
    finally:
        request_tool_manifests_ctx.reset(token)


def test_individual_mcp_mutation_remains_unknown_without_a_delegation_flag():
    manifest = _build_user_tool_manifest(
        adapter_name="mcp_user_00000001_create_issue",
        tool_name="create_issue",
        description="Create issue",
        input_schema={},
        output_schema=None,
        server_name="Issues",
        server_domain="mcp_issues",
        hitl_required=False,
        annotations={"read_only_hint": False, "destructive_hint": False},
    )
    assert manifest.delegates_execution is False
    token = request_tool_manifests_ctx.set([manifest])
    try:
        goal = _goal("action")
        observation = observe_requested_outcome(
            manifest.name,
            {},
            {"success": True, "structured_data": {"issues": []}},
            requirements=[goal],
        )
        assert observation["kind"] == "action" and observation["operation"] is None
        assert (
            requested_outcome_coverage([goal], [observation], timezone="UTC")[0].status == "unknown"
        )
    finally:
        request_tool_manifests_ctx.reset(token)


@pytest.mark.parametrize(
    ("tool_name", "domain", "kind", "operation", "field", "data", "expected_status"),
    [
        (
            "get_contacts_tool",
            "contact",
            "read",
            None,
            "name",
            {"name": "Ada"},
            "satisfied",
        ),
        (
            "create_reminder_tool",
            "reminder",
            "action",
            "create",
            "content",
            {"content": "Ada"},
            "pending_confirmation",
        ),
    ],
)
def test_native_result_keeps_its_proven_kind_and_current_mutation_verdict(
    tool_name, domain, kind, operation, field, data, expected_status
):
    token = request_tool_manifests_ctx.set(collect_static_manifests())
    try:
        goal = GoalRequirement(
            domain=domain,
            label="Ada",
            source_quote="Ada",
            kind=kind,
            operation=operation,
            expected_fields=(
                GoalFieldExpectation(field=field, expected_value="Ada", source_quote="Ada"),
            ),
        )
        observation = observe_requested_outcome(
            tool_name,
            {},
            {"success": True, "structured_data": data},
            requirements=[goal],
        )
        assert observation["kind"] == kind
        assert (
            requested_outcome_coverage([goal], [observation], timezone="UTC")[0].status
            == expected_status
        )
    finally:
        request_tool_manifests_ctx.reset(token)
