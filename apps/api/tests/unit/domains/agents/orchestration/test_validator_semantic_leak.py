"""Regression tests for the semantic-leak detection in PlanValidator.

These tests guard the "INDEXABLE vs SEMANTIC CRITERIA" principle enforced
by the planner prompt and the validator:

  - Indexable criteria (dates, IDs, sender, status...) -> tool parameters.
  - Semantic criteria (medical, urgent, important, best...) -> handled by
    the Response LLM downstream; NEVER passed as text-search query to a
    literal-search tool, otherwise the store returns 0 hits or false
    positives.

The validator runs in one of three modes (gated by
`settings.planner_semantic_leak_mode`):

  - "off":         no-op kill switch
  - "observe":     log + Prometheus counter, plan untouched (default)
  - "autocorrect": NULL the leaky param and bump `max_results`

These tests cover the 10-row regression matrix defined when the feature
was designed. They MUST pass before and after every change to the leak
detector to guarantee no regression on legitimate plans.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationContext,
    ValidationResult,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

pytestmark = [pytest.mark.unit]

# ============================================================================
# Helpers
# ============================================================================


def _make_manifest(
    name: str,
    *,
    text_search_mode: Literal["literal", "semantic", "hybrid"] = "literal",
    has_query_param: bool = True,
) -> ToolManifest:
    """Build a minimal ToolManifest for a search-style tool."""
    params: list[ParameterSchema] = []
    if has_query_param:
        params.append(
            ParameterSchema(
                name="query",
                type="string",
                required=False,
                description="Free-text search",
            )
        )
        params.append(
            ParameterSchema(
                name="max_results",
                type="integer",
                required=False,
                description="Page size",
            )
        )
    return ToolManifest(
        name=name,
        agent="test_agent",
        description="A search-style tool for regression tests",
        parameters=params,
        outputs=[OutputFieldSchema(path="items[]", type="array", description="Items")],
        cost=CostProfile(est_tokens_in=100, est_tokens_out=200),
        permissions=PermissionProfile(required_scopes=[]),
        text_search_mode=text_search_mode,
    )


def _make_validator(*manifests: ToolManifest) -> PlanValidator:
    """Build a PlanValidator with an in-memory registry holding the given tools."""
    registry = AgentRegistry()
    for m in manifests:
        registry.register_tool_manifest(m, override=True)
    return PlanValidator(registry)


def _make_step(
    step_id: str,
    tool_name: str,
    parameters: dict[str, Any],
) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="test_agent",
        tool_name=tool_name,
        parameters=parameters,
    )


def _make_plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="test_plan",
        user_id="test_user",
        session_id="test_session",
        steps=list(steps),
    )


def _make_context(
    *,
    semantic_filter_terms: tuple[str, ...] = (),
) -> ValidationContext:
    return ValidationContext(
        user_id="test_user",
        session_id="test_session",
        semantic_filter_terms=semantic_filter_terms,
    )


def _count_leak_warnings(result: ValidationResult) -> int:
    return sum(1 for w in result.warnings if w.context and "matched_terms" in w.context)


@pytest.fixture
def observe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default rollout mode: log + metrics only, plan untouched."""
    from src.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "planner_semantic_leak_mode", "observe", raising=False)
    monkeypatch.setattr(s, "planner_semantic_broad_batch", 25, raising=False)


@pytest.fixture
def autocorrect_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase-2 mode: actively rewrite leaky steps."""
    from src.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "planner_semantic_leak_mode", "autocorrect", raising=False)
    monkeypatch.setattr(s, "planner_semantic_broad_batch", 25, raising=False)


@pytest.fixture
def off_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kill switch — detector disabled entirely."""
    from src.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "planner_semantic_leak_mode", "off", raising=False)


# ============================================================================
# Regression matrix (10 scenarios from the design doc)
# ============================================================================


class TestSemanticLeakRegressionMatrix:
    """The 10 scenarios that MUST hold before and after every change."""

    # ------------------------------------------------------------------
    # Row 1 — Generic listing, no semantic filter
    # ------------------------------------------------------------------
    def test_row1_events_tomorrow_no_leak(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step(
                "s1",
                "get_events_tool",
                {"query": None, "time_min": "2026-05-16", "time_max": "2026-05-17"},
            )
        )
        # _check_semantic_leak returns None; the assertion is on plan state,
        # not on a return value — no semantic_filter_terms means an early
        # return and no plan mutation.
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=()), ValidationResult(is_valid=True)
        )
        assert plan.steps[0].parameters["query"] is None

    # ------------------------------------------------------------------
    # Row 2 — Indexable filter (sender)
    # ------------------------------------------------------------------
    def test_row2_emails_from_sender_no_leak(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_emails_tool"))
        plan = _make_plan(_make_step("s1", "get_emails_tool", {"query": "from:marc"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan,
            _make_context(semantic_filter_terms=("medical", "urgent")),
            result,
        )
        # "from:marc" contains no semantic term -> no warning, no autocorrect.
        assert _count_leak_warnings(result) == 0
        assert plan.steps[0].parameters["query"] == "from:marc"

    # ------------------------------------------------------------------
    # Row 3 — Exception #1: user explicitly quoted the literal term
    # ------------------------------------------------------------------
    def test_row3_quoted_literal_term_no_leak(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": '"urgent"'}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        assert _count_leak_warnings(result) == 0
        assert plan.steps[0].parameters["query"] == '"urgent"'

    def test_row3_french_apostrophe_does_not_skip_detection(self, observe_mode: None) -> None:
        """A French linguistic apostrophe must NOT be treated as a citation
        signal — only the double-quote skips the leak check. Otherwise common
        francophone phrases ("d'urgence", "l'hôpital", "rendez-vous d'équipe")
        would silently disable detection on legitimate semantic leaks.
        """
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": "urgent d'équipe"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        # The single-quote in "d'équipe" must NOT inhibit detection of "urgent".
        assert _count_leak_warnings(result) == 1

    # ------------------------------------------------------------------
    # Row 4 — Exception #2: tool exposes semantic/vector search
    # ------------------------------------------------------------------
    def test_row4_semantic_search_tool_no_leak(self, observe_mode: None) -> None:
        validator = _make_validator(
            _make_manifest("search_notion_tool", text_search_mode="semantic")
        )
        plan = _make_plan(_make_step("s1", "search_notion_tool", {"query": "medical"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        assert _count_leak_warnings(result) == 0
        assert plan.steps[0].parameters["query"] == "medical"

    # ------------------------------------------------------------------
    # Row 5 — Target case: "mes deux prochains rdv médicaux"
    # ------------------------------------------------------------------
    def test_row5_target_case_medical_appointments_observe(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"query": "medical", "max_results": 2})
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        # observe mode: warn but do NOT touch the plan
        assert _count_leak_warnings(result) == 1
        assert plan.steps[0].parameters["query"] == "medical"
        assert plan.steps[0].parameters["max_results"] == 2

    def test_row5_target_case_medical_appointments_autocorrect(
        self, autocorrect_mode: None
    ) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"query": "medical", "max_results": 2})
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        # autocorrect: NULL the param and bump max_results to broad batch (25)
        assert _count_leak_warnings(result) == 1
        assert plan.steps[0].parameters["query"] is None
        assert plan.steps[0].parameters["max_results"] == 25

    # ------------------------------------------------------------------
    # Row 6 — Cardinality x Semantic: "the 3 most important emails from boss"
    # The leak is on "important"; "boss" is indexable and goes elsewhere.
    # ------------------------------------------------------------------
    def test_row6_cardinality_times_semantic(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_emails_tool"))
        plan = _make_plan(
            _make_step(
                "s1",
                "get_emails_tool",
                {"query": "important from:boss", "max_results": 3},
            )
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("important",)), result
        )
        assert _count_leak_warnings(result) == 1

    # ------------------------------------------------------------------
    # Row 7 — Mixed: indexable (sender + date) + semantic (urgent) in one query
    # ------------------------------------------------------------------
    def test_row7_mixed_indexable_and_semantic(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_emails_tool"))
        plan = _make_plan(
            _make_step(
                "s1",
                "get_emails_tool",
                {"query": "urgent from:marc after:2026-05-01"},
            )
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        assert _count_leak_warnings(result) == 1

    # ------------------------------------------------------------------
    # Row 8 — Multi-step plan: leak must be detected per step independently
    # ------------------------------------------------------------------
    def test_row8_multi_step_per_step_detection(self, observe_mode: None) -> None:
        validator = _make_validator(
            _make_manifest("get_emails_tool"),
            _make_manifest("get_events_tool"),
        )
        plan = _make_plan(
            _make_step("s1", "get_emails_tool", {"query": "important"}),
            _make_step("s2", "get_events_tool", {"query": "medical"}),
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan,
            _make_context(semantic_filter_terms=("important", "medical")),
            result,
        )
        assert _count_leak_warnings(result) == 2

    # ------------------------------------------------------------------
    # Row 9 — Conservatism: no hint -> no autocorrect, even if the query
    # looks semantic. Avoid overreach.
    # ------------------------------------------------------------------
    def test_row9_no_hint_no_autocorrect(self, autocorrect_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": "medical"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(plan, _make_context(semantic_filter_terms=()), result)
        assert _count_leak_warnings(result) == 0
        assert plan.steps[0].parameters["query"] == "medical"

    # ------------------------------------------------------------------
    # Row 10 — Word-boundary match: "medical" in "medical clinic Paris"
    # detected; "medical" as substring of "medicalign" NOT detected.
    # ------------------------------------------------------------------
    def test_row10_word_boundary_true_positive(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": "medical clinic Paris"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        assert _count_leak_warnings(result) == 1

    def test_row10_word_boundary_no_false_positive(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": "medicalign software"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        assert _count_leak_warnings(result) == 0


# ============================================================================
# Mode gating
# ============================================================================


class TestSemanticLeakModeGating:
    """The mode flag must control behavior end-to-end."""

    def test_off_mode_is_a_noop(self, off_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(_make_step("s1", "get_events_tool", {"query": "medical"}))
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("medical",)), result
        )
        assert _count_leak_warnings(result) == 0
        assert plan.steps[0].parameters["query"] == "medical"

    def test_observe_mode_does_not_mutate_plan(self, observe_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"query": "urgent", "max_results": 5})
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        # Warning emitted; plan UNCHANGED (key guarantee for safe rollout).
        assert _count_leak_warnings(result) == 1
        assert plan.steps[0].parameters["query"] == "urgent"
        assert plan.steps[0].parameters["max_results"] == 5

    def test_autocorrect_preserves_already_broad_max_results(self, autocorrect_mode: None) -> None:
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"query": "urgent", "max_results": 40})
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        # max_results was already broad enough — keep user's value, only NULL the query.
        assert plan.steps[0].parameters["query"] is None
        assert plan.steps[0].parameters["max_results"] == 40

    def test_autocorrect_skips_when_param_is_required(self, autocorrect_mode: None) -> None:
        """If the tool declares the leaky param as required=True, autocorrect
        must NOT NULL it (would produce a plan that fails at execution with
        a missing-parameter error, since the validator does not re-run after
        the mutation). The detection warning is still emitted.
        """
        # Build a manifest where `query` is required.
        manifest = ToolManifest(
            name="search_required_query_tool",
            agent="test_agent",
            description="Search tool that requires query",
            parameters=[
                ParameterSchema(
                    name="query",
                    type="string",
                    required=True,
                    description="Required free-text",
                ),
                ParameterSchema(
                    name="max_results",
                    type="integer",
                    required=False,
                    description="Page size",
                ),
            ],
            outputs=[OutputFieldSchema(path="items[]", type="array", description="Items")],
            cost=CostProfile(est_tokens_in=100, est_tokens_out=200),
            permissions=PermissionProfile(required_scopes=[]),
        )
        validator = _make_validator(manifest)
        plan = _make_plan(
            _make_step(
                "s1",
                "search_required_query_tool",
                {"query": "urgent", "max_results": 5},
            )
        )
        result = ValidationResult(is_valid=True)
        validator._check_semantic_leak(
            plan, _make_context(semantic_filter_terms=("urgent",)), result
        )
        # Detection warning emitted, but the required param is preserved.
        assert _count_leak_warnings(result) == 1
        assert plan.steps[0].parameters["query"] == "urgent"
        assert plan.steps[0].parameters["max_results"] == 5


# ============================================================================
# Backwards-compatibility — no-regression on legacy callers
# ============================================================================


class TestSemanticLeakBackwardsCompat:
    """The leak detector must not break existing call sites."""

    def test_validation_context_default_is_empty_tuple(self) -> None:
        """Existing call sites that don't pass semantic_filter_terms still work."""
        ctx = ValidationContext(user_id="u", session_id="s")
        assert ctx.semantic_filter_terms == ()

    def test_validator_full_pipeline_runs_without_terms(self, observe_mode: None) -> None:
        """validate_execution_plan() with no hint produces no semantic warnings."""
        validator = _make_validator(_make_manifest("get_events_tool"))
        plan = _make_plan(
            _make_step("s1", "get_events_tool", {"query": "medical", "max_results": 10})
        )
        result = validator.validate_execution_plan(plan, _make_context())
        assert _count_leak_warnings(result) == 0
