"""Direct unit tests for the pure helpers extracted from ``response_node``.

The response_node decomposition turned ~20 inline responsibilities into named,
individually-testable module-level helpers. These tests lock each unit's
behavior directly (not only indirectly through the whole node), covering the
branches — skip reasons, error fallbacks, protected-item preservation — that
the end-to-end characterization suite exercises only partially.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from asyncpg.exceptions import TooManyConnectionsError
from langchain_core.messages import AIMessage, HumanMessage
from prometheus_client import REGISTRY
from sqlalchemy.exc import OperationalError

from src.core.constants import RESPONSE_DISPLAY_MODE_CARDS
from src.core.context import current_tracker
from src.domains.agents.constants import DATA_FILTERING_GENERATION_ERROR_MARKER, TURN_TYPE_ACTION
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.response_node import (
    _apply_relevant_ids_filtering,
    _await_knowledge_enrichment,
    _build_data_for_filtering,
    _extract_qi_response_hints,
    _instrument_business_metrics,
    _launch_knowledge_enrichment,
    _normalize_agent_results,
    _parse_psyche_appraisal,
    _prepare_turn_registry,
    _record_plan_pattern_learning,
    _render_response_html,
)
from src.domains.agents.services.business_metrics import ConversationMetrics
from tests.helpers.runtime_context import installed_runtime_context

_RESP = "src.domains.agents.nodes.response_node"
_BMS = "src.domains.agents.services.business_metrics"


# --- _normalize_agent_results -------------------------------------------------


def test_normalize_agent_results_passthrough_when_present():
    ar = {"0:contacts_agent": {"status": "success"}}
    state = {"agent_results": ar}
    assert _normalize_agent_results(state, "r") == ar


def test_normalize_agent_results_falls_back_to_tool_results():
    state = {
        "agent_results": {},
        "tool_results": [{"tool": "x"}],
        "current_turn_id": 0,
        "registry": {"id1": {"type": "EVENT"}},
    }
    out = _normalize_agent_results(state, "r")
    assert "0:semantic_tools" in out
    assert out["0:semantic_tools"]["data"] == [{"tool": "x"}]
    assert out["0:semantic_tools"]["registry_updates"] == {"id1": {"type": "EVENT"}}


def test_normalize_agent_results_empty_when_no_tools():
    assert _normalize_agent_results({"agent_results": {}, "tool_results": []}, "r") == {}


# --- _build_data_for_filtering ------------------------------------------------


def test_build_data_for_filtering_empty_when_no_registry():
    assert _build_data_for_filtering(None, "r") == ""
    assert _build_data_for_filtering({}, "r") == ""


def test_build_data_for_filtering_error_returns_marker():
    # generate_data_for_filtering raising is caught and yields the fallback marker
    # (English, LLM-facing prompt content — see DATA_FILTERING_GENERATION_ERROR_MARKER).
    with patch(f"{_RESP}.generate_data_for_filtering", side_effect=ValueError("boom")):
        out = _build_data_for_filtering({"id1": {"type": "EVENT"}}, "r")
    assert out == DATA_FILTERING_GENERATION_ERROR_MARKER


# --- _launch_knowledge_enrichment --------------------------------------------


def test_launch_knowledge_enrichment_skips_without_query_intelligence():
    with installed_runtime_context():
        task, result = _launch_knowledge_enrichment({"query_intelligence": None}, "r", "fr")
    assert task is None
    assert isinstance(result, dict) and "skip_reason" in result


# --- _await_knowledge_enrichment ---------------------------------------------


@pytest.mark.asyncio
async def test_await_knowledge_enrichment_no_task_preserves_input():
    incoming = {"skip_reason": "no_keywords"}
    ctx, result = await _await_knowledge_enrichment(None, incoming, "r")
    assert ctx == ""
    assert result is incoming


# --- _extract_qi_response_hints ----------------------------------------------


def test_extract_qi_response_hints_reads_mappings_and_qi_fields():
    state = {
        "resolved_references": {"mappings": {"ma femme": "jean dupond"}},
        "query_intelligence": {
            "english_enriched_query": "get contact details for the dupond family",
            "anticipated_needs": ["may want reminder"],
        },
    }
    resolved, enriched, anticipated = _extract_qi_response_hints(state, "r")
    assert resolved == {"ma femme": "jean dupond"}
    assert enriched == "get contact details for the dupond family"
    assert anticipated == ["may want reminder"]


def test_extract_qi_response_hints_all_none_when_absent():
    resolved, enriched, anticipated = _extract_qi_response_hints({}, "r")
    assert resolved is None
    assert enriched is None
    assert anticipated is None


# --- _apply_relevant_ids_filtering -------------------------------------------


def _filter(final_content, registry, *, original=None, domains=None):
    return _apply_relevant_ids_filtering(
        final_content=final_content,
        original_content=original if original is not None else final_content,
        current_turn_registry=registry,
        state={},
        result_domains=domains if domains is not None else set(),
        last_user_message="q",
        run_id="r",
    )


def test_relevant_ids_no_tag_leaves_everything_unchanged():
    registry = {"a": {"type": "EVENT"}, "b": {"type": "EVENT"}}
    content, out_reg = _filter("Plain answer", registry)
    assert content == "Plain answer"
    assert out_reg == registry


def test_relevant_ids_tag_filters_registry_and_strips_content():
    registry = {"a": {"type": "EVENT"}, "b": {"type": "EVENT"}}
    content, out_reg = _filter("Answer <relevant_ids>a</relevant_ids>", registry)
    assert content == "Answer"
    assert set(out_reg.keys()) == {"a"}


def test_relevant_ids_preserves_protected_draft_item():
    # A DRAFT item is unfilterable and survives even when not in relevant_ids.
    registry = {"a": {"type": "EVENT"}, "d": {"type": "DRAFT"}}
    _content, out_reg = _filter("Answer <relevant_ids>a</relevant_ids>", registry)
    assert set(out_reg.keys()) == {"a", "d"}


# --- _prepare_turn_registry --------------------------------------------------


def test_prepare_turn_registry_derives_override_action_and_personality():
    state = {
        "registry": {},
        "current_turn_id": 0,
        "detected_intent": "search",
        "personality_instruction": "Be concise",
    }
    with patch(f"{_RESP}._filter_registry_by_current_turn", Mock(return_value={"x": 1})):
        (
            full_registry,
            current_turn_id,
            resolved_context,
            current_turn_registry,
            override_action,
            personality_instruction,
        ) = _prepare_turn_registry(state, "r", {})
    assert full_registry == {}
    assert current_turn_id == 0
    assert resolved_context is None
    assert current_turn_registry == {"x": 1}
    assert override_action == "search"
    assert personality_instruction == "Be concise"


def test_prepare_turn_registry_override_none_for_non_search_intent():
    state = {"registry": {}, "detected_intent": "other"}
    with patch(f"{_RESP}._filter_registry_by_current_turn", Mock(return_value={})):
        result = _prepare_turn_registry(state, "r", {})
    assert result[4] is None  # override_action


# --- _launch_knowledge_enrichment (all skip branches + full path) ------------


def _launch(state, **context_overrides):
    """Run the helper inside a run context, the only place ``deps``/``user_id`` live now."""
    with installed_runtime_context(**context_overrides):
        return _launch_knowledge_enrichment(state, "r", "fr")


def test_launch_ke_feature_disabled():
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", False):
        task, res = _launch({"query_intelligence": {}})
    assert task is None and res == {"skip_reason": "feature_disabled"}


def test_launch_ke_no_query_intelligence():
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch({"query_intelligence": None}, deps=object())
    assert task is None and res == {"skip_reason": "no_query_intelligence"}


def test_launch_ke_no_tool_deps():
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch({"query_intelligence": {"a": 1}})
    assert task is None and res == {"skip_reason": "no_tool_deps"}


def test_launch_ke_outside_a_run_skips_on_dependencies():
    """No context at all is the only remaining way to have no acting user.

    ``LiaRuntimeContext.user_id`` is mandatory and typed, so a run can no longer
    carry dependencies while missing its user — the ambiguity ADR-231 removed.
    Outside a run, the dependency guard fires first and says so.
    """
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch_knowledge_enrichment({"query_intelligence": {"a": 1}}, "r", "fr")
    assert task is None and res == {"skip_reason": "no_tool_deps"}


def test_launch_ke_skip_domain_web_search():
    qi = {"encyclopedia_keywords": ["x"], "primary_domain": "web_search"}
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch({"query_intelligence": qi}, deps=object())
    assert task is None and res == {"skip_reason": "web_search_domain"}


def test_launch_ke_mcp_domain():
    qi = {"encyclopedia_keywords": ["x"], "primary_domain": "mcp_gmail"}
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch({"query_intelligence": qi}, deps=object())
    assert task is None and res == {"skip_reason": "mcp_domain"}


def test_launch_ke_no_keywords():
    qi = {"encyclopedia_keywords": [], "primary_domain": None}
    with patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True):
        task, res = _launch({"query_intelligence": qi}, deps=object())
    assert task is None and res == {"skip_reason": "no_keywords"}


@pytest.mark.asyncio
async def test_launch_ke_full_path_creates_task():
    qi = {"encyclopedia_keywords": ["paris"], "primary_domain": None}
    fake_service = Mock(enrich=AsyncMock(return_value=None))
    with (
        patch(f"{_RESP}.settings.knowledge_enrichment_enabled", True),
        patch(
            "src.domains.agents.services.get_knowledge_enrichment_service",
            Mock(return_value=fake_service),
        ),
    ):
        task, res = _launch({"query_intelligence": qi}, deps=object())
        assert task is not None
        assert res is None  # not set when a task is launched
        await task  # drain the task so it is not garbage-collected pending
    fake_service.enrich.assert_awaited_once()


# --- _await_knowledge_enrichment (success / no-result / timeout / error) -----


@pytest.mark.asyncio
async def test_await_ke_success_builds_debug_payload():
    ctx = SimpleNamespace(
        to_prompt_context=lambda: "CTX",
        endpoint="web",
        keyword="paris",
        results=[1, 2],
        from_cache=True,
    )

    async def _ok():
        return ctx

    context, res = await _await_knowledge_enrichment(_ok(), None, "r")
    assert context == "CTX"
    assert res["endpoint"] == "web"
    assert res["keyword_used"] == "paris"
    assert res["results_count"] == 2
    assert res["from_cache"] is True
    assert res["prompt_context"] == "CTX"


@pytest.mark.asyncio
async def test_await_ke_none_result_marks_no_result():
    async def _none():
        return None

    context, res = await _await_knowledge_enrichment(_none(), {"skip_reason": "x"}, "r")
    assert context == ""
    assert res == {"skip_reason": "no_result"}


@pytest.mark.asyncio
async def test_await_ke_timeout_records_error():
    async def _timeout():
        raise TimeoutError()

    context, res = await _await_knowledge_enrichment(_timeout(), None, "r")
    assert context == ""
    assert res["error"] == "timeout"


@pytest.mark.asyncio
async def test_await_ke_generic_error_records_message():
    async def _boom():
        raise ValueError("boom")

    context, res = await _await_knowledge_enrichment(_boom(), None, "r")
    assert context == ""
    assert res == {"error": "boom"}


# --- _parse_psyche_appraisal -------------------------------------------------


def test_parse_psyche_disabled_returns_content_unchanged():
    appraisal, content = _parse_psyche_appraisal("hello", user_psyche_enabled=False, run_id="r")
    assert appraisal is None
    assert content == "hello"


def test_parse_psyche_enabled_parses_and_strips():
    fake = SimpleNamespace(
        valence=1,
        arousal=1,
        dominance=1,
        dominant_emotion="joy",
        dominant_intensity=1,
        emotions=[],
        quality="q",
    )
    with (
        patch(f"{_RESP}.settings.psyche_enabled", True),
        patch(
            "src.domains.psyche.engine.PsycheEngine.parse_psyche_eval",
            Mock(return_value=(fake, "stripped")),
        ),
    ):
        appraisal, content = _parse_psyche_appraisal(
            "raw<eval>", user_psyche_enabled=True, run_id="r"
        )
    assert appraisal is fake
    assert content == "stripped"


# --- _record_plan_pattern_learning -------------------------------------------


def _patch_pattern_learning():
    return (
        patch(
            "src.domains.agents.analysis.query_intelligence_helpers.get_query_intelligence_from_state",
            Mock(return_value=Mock()),
        ),
        patch("src.domains.agents.services.plan_pattern_learner.record_plan_success"),
        patch("src.domains.agents.services.plan_pattern_learner.record_plan_failure"),
    )


def test_pattern_learning_records_success_on_action_turn():
    p_qi, p_ok, p_fail = _patch_pattern_learning()
    with p_qi, p_ok as ok, p_fail as fail:
        _record_plan_pattern_learning({"execution_plan": object()}, "r", TURN_TYPE_ACTION)
    ok.assert_called_once()
    fail.assert_not_called()


def test_pattern_learning_records_failure_on_rejected_plan():
    p_qi, p_ok, p_fail = _patch_pattern_learning()
    state = {"execution_plan": object(), "plan_rejection_reason": "refused"}
    with p_qi, p_ok as ok, p_fail as fail:
        _record_plan_pattern_learning(state, "r", TURN_TYPE_ACTION)
    fail.assert_called_once()
    ok.assert_not_called()


def test_pattern_learning_skips_without_plan():
    p_qi, p_ok, p_fail = _patch_pattern_learning()
    with p_qi, p_ok as ok, p_fail as fail:
        _record_plan_pattern_learning({}, "r", TURN_TYPE_ACTION)
    ok.assert_not_called()
    fail.assert_not_called()


# --- _instrument_business_metrics (graceful degradation) ---------------------


def _state() -> MessagesState:
    """A turn's state as the graph builds it."""
    return create_initial_state(uuid4(), session_id="s", run_id="r")


def _successful(agent_type: str) -> ConversationMetrics:
    """What the calculation says of a successful turn."""
    return ConversationMetrics(
        agent_type=agent_type,
        cost_usd=0.5,
        tokens_total=3,
        turns=1,
        outcome="success",
        message_count=2,
    )


@contextmanager
def _tracked_run() -> Iterator[None]:
    """A run whose tracker has nothing pending: its cost is its ledger row."""
    tracker = Mock(run_id="run-1")
    tracker.get_summary.return_value = {"cost_eur": 0.0}
    token = current_tracker.set(tracker)
    try:
        yield
    finally:
        current_tracker.reset(token)


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("no db"),
        TimeoutError("connect"),
        ConnectionRefusedError(),
        TooManyConnectionsError("sorry, too many clients already"),
        OperationalError("COMMIT", None, ConnectionResetError()),
    ],
)
async def test_a_ledger_the_database_refuses_costs_the_turn_no_other_sample(
    failure: BaseException,
) -> None:
    """A connection that cannot open, a driver's own refusal, a commit the
    database refused: through the REAL ledger read, the node neither raises —
    on the draft fast path, after the act, the answer was lost — nor loses the
    turn's other samples (read first, they were dropped with the cost)."""
    agent_type = f"test_ledger_{type(failure).__name__}"
    counter = {"agent_type": agent_type, "outcome": "success"}
    turns = {"agent_type": agent_type}
    cost = {"agent_type": agent_type}
    counted_before = _sample("agent_success_rate_total", counter)
    turns_before = _sample("conversation_turns_total_count", turns)
    cost_before = _sample("cost_per_successful_conversation_usd_count", cost)
    with (
        _tracked_run(),
        patch(
            f"{_BMS}.calculate_conversation_metrics",
            Mock(return_value=_successful(agent_type)),
        ),
        patch(f"{_BMS}.get_db_context", Mock(side_effect=failure)),
    ):
        await _instrument_business_metrics(_state(), {"configurable": {}}, "r", None)

    assert _sample("agent_success_rate_total", counter) - counted_before == 1.0
    assert _sample("conversation_turns_total_count", turns) - turns_before == 1.0
    assert _sample("cost_per_successful_conversation_usd_count", cost) == cost_before


@pytest.mark.asyncio
async def test_business_metrics_let_a_cancellation_through() -> None:
    """Best-effort is not a swallowed cancellation: through the real ledger
    read, the turn stays cancelled."""
    with (
        _tracked_run(),
        patch(
            f"{_BMS}.calculate_conversation_metrics",
            Mock(return_value=_successful("test_cancelled")),
        ),
        patch(f"{_BMS}.get_db_context", Mock(side_effect=asyncio.CancelledError())),
        pytest.raises(asyncio.CancelledError),
    ):
        await _instrument_business_metrics(_state(), {"configurable": {}}, "r", None)


@pytest.mark.asyncio
async def test_the_run_s_cost_is_read_after_every_other_sample() -> None:
    """Read last: whatever crosses the read — a cancellation, the one thing it
    lets through — the turn's other samples are already taken."""
    agent_type = "test_cost_read_last"
    counter = {"agent_type": agent_type, "outcome": "success"}
    turns = {"agent_type": agent_type}
    counted_before = _sample("agent_success_rate_total", counter)
    turns_before = _sample("conversation_turns_total_count", turns)
    with (
        patch(
            f"{_BMS}.calculate_conversation_metrics",
            Mock(return_value=_successful(agent_type)),
        ),
        patch(f"{_BMS}.current_turn_cost_usd", AsyncMock(side_effect=asyncio.CancelledError())),
        pytest.raises(asyncio.CancelledError),
    ):
        await _instrument_business_metrics(_state(), {"configurable": {}}, "r", None)

    assert _sample("agent_success_rate_total", counter) - counted_before == 1.0
    assert _sample("conversation_turns_total_count", turns) - turns_before == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent_result", "sessions"), [("success", 1), ("error", 0)])
async def test_the_metrics_are_computed_with_no_session_open(
    agent_result: str, sessions: int
) -> None:
    """Priced by the pricing cache, the calculation opens no session: the one
    this path opens is the successful turn's ledger read — a transaction held
    across the currency lookup's network call (ADR-304) is gone by construction."""
    state = _state()
    state["messages"] = [
        HumanMessage(content="question"),
        AIMessage(
            content="answer",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            response_metadata={"model_name": "model-a"},
        ),
    ]
    state["execution_mode"] = "test_sessions"
    state["current_turn_id"] = 1
    state["agent_results"] = {"1:contacts_agent": {"status": agent_result}}
    opened = Mock(side_effect=ConnectionRefusedError())
    with (
        _tracked_run(),
        patch(f"{_BMS}.quote_cached_cost_usd", return_value=0.001) as priced,
        patch(f"{_BMS}.get_db_context", opened),
    ):
        await _instrument_business_metrics(state, {"configurable": {}}, "r", None)

    priced.assert_called_once()
    assert opened.call_count == sessions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "counted", "cost_observed"),
    [("success", 1.0, 0.25), ("failure", 1.0, 0.0), ("no_agent", 0.0, 0.0)],
)
async def test_a_turn_is_counted_under_its_outcome_and_a_chat_is_not(
    outcome: str, counted: float, cost_observed: float
) -> None:
    """The composition « outcome → counter » is what read ``failure`` for a
    year: pinned on the counter's own samples, and a successful turn records
    its RUN's cost."""
    agent_type = f"test_{outcome}"
    metrics = ConversationMetrics(
        agent_type=agent_type,
        cost_usd=9.0,
        tokens_total=0,
        turns=1,
        outcome=outcome,
        message_count=2,
    )
    counter = {"agent_type": agent_type, "outcome": outcome}
    cost = {"agent_type": agent_type}
    counted_before = _sample("agent_success_rate_total", counter)
    cost_before = _sample("cost_per_successful_conversation_usd_sum", cost)
    with (
        patch(f"{_BMS}.calculate_conversation_metrics", Mock(return_value=metrics)),
        patch(f"{_BMS}.current_turn_cost_usd", AsyncMock(return_value=0.25)),
    ):
        await _instrument_business_metrics(_state(), {"configurable": {}}, "r", None)

    assert _sample("agent_success_rate_total", counter) - counted_before == counted
    assert _sample("cost_per_successful_conversation_usd_sum", cost) - cost_before == (
        cost_observed
    )


@pytest.mark.asyncio
async def test_the_calculated_figures_are_the_observed_ones() -> None:
    """What the calculation priced and counted is what the histograms
    receive: the thread's cost, its tokens, its turns."""
    agent_type = "test_observed_figures"
    metrics = ConversationMetrics(
        agent_type=agent_type,
        cost_usd=0.125,
        tokens_total=1234,
        turns=3,
        outcome="no_agent",
        message_count=6,
    )
    labels = {"agent_type": agent_type}
    names = (
        "conversation_cost_usd_sum",
        "conversation_tokens_total_sum",
        "conversation_turns_total_sum",
    )
    state = _state()
    before = [_sample(name, labels) for name in names]
    with patch(f"{_BMS}.calculate_conversation_metrics", Mock(return_value=metrics)):
        await _instrument_business_metrics(state, {"configurable": {}}, "r", None)

    observed = [_sample(name, labels) - base for name, base in zip(names, before, strict=True)]
    assert observed == [0.125, 1234.0, 3.0]


# --- _extract_qi_response_hints (english_query fallback) ----------------------


def test_extract_qi_hints_enriched_falls_back_to_english_query():
    state = {"query_intelligence": {"english_query": "fallback query"}}
    _resolved, enriched, _anticipated = _extract_qi_response_hints(state, "r")
    assert enriched == "fallback query"


# --- _render_response_html (widgets / cards / resolved-context / no-op) -------


def _render(**kw):
    base = {
        "final_content": "base",
        "current_turn_registry": None,
        "resolved_context_for_html": None,
        "user_display_mode": "markdown",
        "user_viewport": "desktop",
        "user_language": "fr",
        "user_timezone": "UTC",
        "run_id": "r",
    }
    base.update(kw)
    return _render_response_html(**base)


def test_render_html_appends_interactive_widget_regardless_of_mode():
    with patch(f"{_RESP}.generate_html_for_interactive_widgets", Mock(return_value="<W>")):
        out = _render(
            current_turn_registry={"a": {"type": "MCP_APP"}}, user_display_mode="markdown"
        )
    assert out == "base\n\n<W>"


def test_render_html_data_cards_in_cards_mode():
    with (
        patch(f"{_RESP}.generate_html_for_interactive_widgets", Mock(return_value="")),
        patch(f"{_RESP}._filter_registry_by_types", Mock(return_value={"a": {"type": "EVENT"}})),
        patch(f"{_RESP}.generate_html_for_registry", Mock(return_value="<C>")),
    ):
        out = _render(
            current_turn_registry={"a": {"type": "EVENT"}},
            user_display_mode=RESPONSE_DISPLAY_MODE_CARDS,
        )
    assert out == "base\n\n<C>"


def test_render_html_resolved_context_fallback_in_cards_mode():
    with (
        patch(f"{_RESP}.generate_html_for_interactive_widgets", Mock(return_value="")),
        patch(f"{_RESP}.generate_html_for_resolved_context", Mock(return_value="<R>")),
    ):
        out = _render(
            current_turn_registry=None,
            resolved_context_for_html={"items": [1]},
            user_display_mode=RESPONSE_DISPLAY_MODE_CARDS,
        )
    assert out == "base\n\n<R>"


def test_render_html_noop_when_nothing_to_render():
    assert _render() == "base"
