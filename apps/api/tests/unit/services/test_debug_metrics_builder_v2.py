"""Unit tests for DebugMetricsBuilder v2 chronological ordering.

``request_lifecycle`` used to order nodes by the hardcoded
``DEBUG_PIPELINE_NODE_ORDER`` list and append every unknown node (react_*,
compaction, extractions…) AFTER ``response`` — a false chronology. And
``llm_pipeline`` sorted by ``sequence``, a PER-CONTEXT counter that
collides across the TrackingContexts sharing a run (a background
extraction's call #1 tied with the router's call #1).

v2 orders both by the run-anchored ``started_offset_ms`` (falling back to
``sequence`` for legacy records), so the panel shows what actually
happened, in the order it happened.
"""

from src.domains.agents.services.streaming.service import StreamingService


def _call(
    node_name: str,
    sequence: int,
    started_offset_ms: float | None = None,
    duration_ms: float = 50.0,
    call_type: str = "chat",
) -> dict:
    call = {
        "node_name": node_name,
        "model_name": "m",
        "tokens_in": 10,
        "tokens_out": 5,
        "tokens_cache": 0,
        "cost_eur": 0.001,
        "duration_ms": duration_ms,
        "call_type": call_type,
        "sequence": sequence,
    }
    if started_offset_ms is not None:
        call["started_offset_ms"] = started_offset_ms
    return call


def _build_with_calls(calls: list[dict]) -> dict:
    class _Tracker:
        def get_llm_calls_breakdown(self) -> list[dict]:
            return calls

    svc = StreamingService(tracker=_Tracker())
    dm: dict = {}
    svc._add_debug_metrics_sections(dm, {}, "v2-run")
    return dm


def test_request_lifecycle_orders_nodes_chronologically_not_by_static_list() -> None:
    """react_* nodes appear at their true position, not appended after response."""
    dm = _build_with_calls(
        [
            _call("router", 1, 0.0),
            _call("react_call_model", 2, 100.0),
            _call("embedding_embed_query", 3, 150.0, call_type="embedding"),
            _call("react_call_model", 4, 700.0),
            _call("response", 5, 900.0),
        ]
    )

    names = [node["name"] for node in dm["request_lifecycle"]["nodes"]]
    assert names == ["router", "react_call_model", "embedding_embed_query", "response"]


def test_llm_pipeline_sorts_across_contexts_by_started_offset() -> None:
    """A background extraction (its own context, sequence restarts at 1) must
    not tie with the router — the run-anchored offset breaks the collision."""
    dm = _build_with_calls(
        [
            _call("journal_extraction", 1, 5000.0),
            _call("router", 1, 0.0),
        ]
    )

    ordered = [c["node_name"] for c in dm["llm_pipeline"]["calls"]]
    assert ordered == ["router", "journal_extraction"]


def test_ordering_falls_back_to_sequence_for_legacy_records() -> None:
    """Records without started_offset_ms (old history entries) order by sequence."""
    dm = _build_with_calls(
        [
            _call("router", 2),
            _call("planner", 1),
        ]
    )

    assert [c["node_name"] for c in dm["llm_pipeline"]["calls"]] == ["planner", "router"]
    assert [n["name"] for n in dm["request_lifecycle"]["nodes"]] == ["planner", "router"]


def test_llm_pipeline_calls_carry_started_offset_ms() -> None:
    """The waterfall needs each call's start position in the payload."""
    dm = _build_with_calls([_call("router", 1, 42.5)])

    assert dm["llm_pipeline"]["calls"][0]["started_offset_ms"] == 42.5


# ---------------------------------------------------------------------------
# v2 sections: execution_mode, semantic_validation, react_execution, hitl,
# compaction — every stage of the run must be visible in the panel.
# ---------------------------------------------------------------------------


def _build_state(state: dict, service: StreamingService | None = None) -> dict:
    svc = service or StreamingService()
    dm: dict = {}
    svc._add_debug_metrics_sections(dm, state, "v2-run")
    return dm


def test_execution_mode_defaults_to_pipeline() -> None:
    assert _build_state({})["execution_mode"] == "pipeline"
    assert _build_state({"execution_mode": None})["execution_mode"] == "pipeline"


def test_execution_mode_react_is_surfaced() -> None:
    assert _build_state({"execution_mode": "react"})["execution_mode"] == "react"


def test_semantic_validation_section_serializes_the_verdict() -> None:
    from src.domains.agents.orchestration.validation_models import (
        CriticalityLevel,
        SemanticIssue,
        SemanticIssueType,
        SemanticValidationResult,
    )

    result = SemanticValidationResult(
        is_valid=False,
        issues=[
            SemanticIssue(
                issue_type=SemanticIssueType.SCOPE_UNDERFLOW,
                description="Plan ignores the date constraint",
                step_index=1,
                severity="high",
                suggested_fix="Add the date filter",
            )
        ],
        confidence=0.55,
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=1.2,
        criticality=CriticalityLevel.MEDIUM,
        used_fallback=False,
        fallback_reason=None,
    )

    dm = _build_state({"semantic_validation": result})

    sv = dm["semantic_validation"]
    assert sv["is_valid"] is False
    assert sv["confidence"] == 0.55
    assert sv["criticality"] == "MEDIUM"
    assert sv["requires_clarification"] is False
    assert sv["used_fallback"] is False
    assert sv["validation_duration_seconds"] == 1.2
    issue = sv["issues"][0]
    assert issue["issue_type"] == "scope_underflow"
    assert issue["description"] == "Plan ignores the date constraint"
    assert issue["severity"] == "high"
    assert issue["step_index"] == 1
    assert issue["suggested_fix"] == "Add the date filter"


def test_semantic_validation_absent_without_state() -> None:
    assert "semantic_validation" not in _build_state({})


def test_react_execution_section_from_state() -> None:
    from src.core.config import get_settings

    dm = _build_state(
        {
            "execution_mode": "react",
            "react_iteration": 3,
            "react_tool_names": ["get_emails_tool", "get_events_tool"],
            "react_elapsed_seconds": 12.5,
            "react_call_digests": {"a": 1, "b": 2},
        }
    )

    react = dm["react_execution"]
    assert react["iterations"] == 3
    # Published bound (ADR-184 doctrine): the enforced limit travels with the
    # value it constrains — read from settings, never hardcoded.
    assert react["max_iterations"] == get_settings().react_agent_max_iterations
    assert react["elapsed_seconds"] == 12.5
    assert react["tool_names"] == ["get_emails_tool", "get_events_tool"]
    assert react["executed_tool_calls"] == 2


def test_react_execution_surfaces_the_delegated_half() -> None:
    """ADR-256: the panel read `elapsed` as the turn's total while it counted
    only the model's reasoning, so a delegated sub-agent loop showed as zero.
    The bound travels with the value it constrains (ADR-184)."""
    from src.core.config import get_settings

    dm = _build_state(
        {
            "execution_mode": "react",
            "react_iteration": 2,
            "react_tool_names": [],
            "react_elapsed_seconds": 8.0,
            "react_tool_seconds": 245.5,
            "react_call_digests": {},
        }
    )

    react = dm["react_execution"]
    assert react["elapsed_seconds"] == 8.0
    assert react["tool_seconds"] == 245.5
    assert react["tool_budget_seconds"] == get_settings().react_tool_budget_seconds


def test_react_execution_reports_zero_tool_time_when_none_was_spent() -> None:
    """A turn that called no tool is not the same as a turn we did not measure —
    the key is always present so the panel can tell them apart."""
    dm = _build_state(
        {
            "execution_mode": "react",
            "react_iteration": 1,
            "react_tool_names": [],
            "react_elapsed_seconds": 3.0,
            "react_call_digests": {},
        }
    )

    assert dm["react_execution"]["tool_seconds"] == 0.0


def test_react_execution_absent_in_pipeline_mode() -> None:
    assert "react_execution" not in _build_state({"execution_mode": "pipeline"})


def test_hitl_section_from_state_flags_and_interrupt_info() -> None:
    svc = StreamingService()
    svc.hitl_interrupt_info = {"action_type": "draft_critique", "tool_name": "send_email_tool"}

    dm = _build_state(
        {
            "plan_approved": True,
            "clarification_response": "oui, envoie",
            "clarification_field": "subject",
        },
        service=svc,
    )

    hitl = dm["hitl"]
    assert hitl["interrupted"] is True
    assert hitl["interrupt_action_type"] == "draft_critique"
    assert hitl["interrupt_tool_name"] == "send_email_tool"
    assert hitl["plan_approved"] is True
    assert hitl["clarification_response"] == "oui, envoie"
    assert hitl["clarification_field"] == "subject"


def test_hitl_section_for_each_cancellation() -> None:
    dm = _build_state({"for_each_cancelled": True, "cancellation_reason": "user_declined"})

    hitl = dm["hitl"]
    assert hitl["interrupted"] is False
    assert hitl["for_each_cancelled"] is True
    assert hitl["cancellation_reason"] == "user_declined"


def test_hitl_section_absent_without_any_signal() -> None:
    assert "hitl" not in _build_state({})


def test_compaction_section_from_state() -> None:
    dm = _build_state(
        {
            "compaction_count": 2,
            "compaction_summary": "x" * 500,
            "compaction_debug": {
                "strategy": "llm_summary",
                "tokens_saved": 1200,
                "messages_removed": 14,
            },
        }
    )

    compaction = dm["compaction"]
    assert compaction["count"] == 2
    assert compaction["strategy"] == "llm_summary"
    assert compaction["tokens_saved"] == 1200
    assert compaction["messages_removed"] == 14
    # The summary is conversation-derived content: preview only, bounded.
    assert len(compaction["summary_preview"]) <= 400


def test_compaction_section_absent_when_never_compacted() -> None:
    assert "compaction" not in _build_state({"compaction_count": 0})
