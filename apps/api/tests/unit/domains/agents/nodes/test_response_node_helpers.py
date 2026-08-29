"""Direct unit tests for the pure helpers extracted from ``response_node``.

The response_node decomposition turned ~20 inline responsibilities into named,
individually-testable module-level helpers. These tests lock each unit's
behavior directly (not only indirectly through the whole node), covering the
branches — skip reasons, error fallbacks, protected-item preservation — that
the end-to-end characterization suite exercises only partially.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.constants import RESPONSE_DISPLAY_MODE_CARDS
from src.domains.agents.constants import DATA_FILTERING_GENERATION_ERROR_MARKER, TURN_TYPE_ACTION
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
from tests.helpers.runtime_context import installed_runtime_context

_RESP = "src.domains.agents.nodes.response_node"


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
    assert _build_data_for_filtering(None, "fr", "r") == ""
    assert _build_data_for_filtering({}, "fr", "r") == ""


def test_build_data_for_filtering_error_returns_marker():
    # generate_data_for_filtering raising is caught and yields the fallback marker
    # (English, LLM-facing prompt content — see DATA_FILTERING_GENERATION_ERROR_MARKER).
    with patch(f"{_RESP}.generate_data_for_filtering", side_effect=ValueError("boom")):
        out = _build_data_for_filtering({"id1": {"type": "EVENT"}}, "fr", "r")
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


@pytest.mark.asyncio
async def test_business_metrics_never_raises_on_db_failure():
    with patch(
        "src.infrastructure.database.get_db_context", Mock(side_effect=RuntimeError("no db"))
    ):
        # Must return None without propagating the failure.
        assert await _instrument_business_metrics({}, {"configurable": {}}, "r") is None


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
