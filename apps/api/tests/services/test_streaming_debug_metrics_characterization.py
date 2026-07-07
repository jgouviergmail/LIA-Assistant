"""Characterization tests for ``StreamingService._add_debug_metrics_sections``.

This 730-line method is the target of the ``DebugMetricsBuilder`` extraction.
It is a sectioned, in-place transformation ``state -> debug_metrics`` where each
section is independently guarded by try/except (a failure in one section must
NOT prevent the others from being built). These golden-master tests pin the
CURRENT output of each section on representative inputs so the extraction into
one builder-method-per-section can be proven behavior-preserving.

Every assertion below was verified GREEN against the pre-refactoring code.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.domains.agents.services.streaming.debug_metrics_builder import DebugMetricsBuilder
from src.domains.agents.services.streaming.service import StreamingService


def _direct_builder(
    *,
    tracker=None,
    cached_tool_scores=None,
    cached_filtered_catalogue=None,
    resolver=lambda s: None,
):
    """Construct DebugMetricsBuilder directly with injected deps for section tests."""
    return DebugMetricsBuilder(
        tracker=tracker,
        cached_filtered_catalogue=cached_filtered_catalogue,
        cached_tool_scores=cached_tool_scores,
        skill_name_resolver=resolver,
    )


@pytest.fixture
def service() -> StreamingService:
    return StreamingService()


def _build(service: StreamingService, state: dict, debug_metrics: dict | None = None) -> dict:
    """Run the in-place builder and return the mutated debug_metrics dict."""
    dm = debug_metrics if debug_metrics is not None else {}
    service._add_debug_metrics_sections(dm, state, "char-run")
    return dm


def test_empty_state_builds_only_token_budget_and_knowledge_enrichment(service):
    """With an empty state and no tracker/caches, only the always-on sections appear."""
    dm = _build(service, {})

    # token_budget is always computed (TokenCounterService on the messages list).
    assert "token_budget" in dm
    assert dm["token_budget"]["current_tokens"] == 0
    assert dm["token_budget"]["zone"] == "safe"
    assert dm["token_budget"]["fallback_active"] is False
    # knowledge_enrichment is always seeded with defaults when absent.
    assert "knowledge_enrichment" in dm
    assert dm["knowledge_enrichment"]["executed"] is False

    # State-/tracker-driven sections must be absent.
    for absent in (
        "planner_intelligence",
        "execution_timeline",
        "tool_selection",
        "llm_calls",
        "memory_injection",
        "rag_injection",
        "journal_injection",
        "skills",
    ):
        assert absent not in dm


def test_planner_intelligence_section(service):
    """planner_intelligence is derived from planning_result flags + token math."""
    planning_result = SimpleNamespace(
        used_template=True,
        used_panic_mode=False,
        used_generative=False,
        tokens_used=100,
        tokens_saved=900,
        plan=None,
        success=True,
        error=None,
    )
    dm = _build(service, {"planning_result": planning_result})

    pi = dm["planner_intelligence"]
    assert pi["strategy"] == "template_bypass"
    assert pi["tokens"]["used"] == 100
    assert pi["tokens"]["saved"] == 900
    assert pi["tokens"]["full_catalogue_estimate"] == 1000
    assert pi["tokens"]["reduction_percentage"] == 90.0
    assert pi["flags"] == {
        "used_template": True,
        "used_panic_mode": False,
        "used_generative": False,
    }
    assert pi["success"] is True


def test_execution_timeline_section(service):
    """execution_timeline maps plan steps + completed_steps, deriving domain from agent."""
    step = SimpleNamespace(step_id="s1", tool_name="get_emails_tool", agent_name="emails_agent")
    execution_plan = SimpleNamespace(steps=[step])
    state = {
        "execution_plan": execution_plan,
        "completed_steps": {"s1": {"success": True, "duration_ms": 123}},
    }
    dm = _build(service, state)

    tl = dm["execution_timeline"]
    assert tl["total_steps"] == 1
    assert tl["completed_steps"] == 1
    assert tl["steps"][0]["step_id"] == "s1"
    assert tl["steps"][0]["tool_name"] == "get_emails_tool"
    assert tl["steps"][0]["domain"] == "emails"
    assert tl["steps"][0]["status"] == "completed"
    assert tl["steps"][0]["success"] is True
    assert tl["steps"][0]["duration_ms"] == 123


def test_injection_sections_pass_through_state_debug_dicts(service):
    """memory/rag/journal injection sections copy the state debug dicts verbatim."""
    state = {
        "memory_injection_debug": {"memory_count": 2, "emotional_state": "calm"},
        "rag_injection_debug": {"spaces_searched": 1, "chunks_injected": 3},
        "journal_injection_debug": {"entries_found": 4, "entries_injected": 1, "entries": []},
    }
    dm = _build(service, state)

    assert dm["memory_injection"] == {"memory_count": 2, "emotional_state": "calm"}
    assert dm["rag_injection"] == {"spaces_searched": 1, "chunks_injected": 3}
    assert dm["journal_injection"]["entries_found"] == 4


def test_knowledge_enrichment_section_marks_executed(service):
    """knowledge_enrichment merges the response_node execution result (endpoint => executed)."""
    state = {
        "knowledge_enrichment_result": {
            "endpoint": "web_search",
            "keyword_used": "paris",
            "results_count": 3,
            "from_cache": False,
            "results": [{"title": "t"}],
            "prompt_context": "ctx",
        }
    }
    dm = _build(service, state)

    ke = dm["knowledge_enrichment"]
    assert ke["executed"] is True
    assert ke["endpoint"] == "web_search"
    assert ke["keyword_used"] == "paris"
    assert ke["results_count"] == 3


def test_llm_calls_section_builds_summary_lifecycle_and_pipeline(service):
    """A tracker with get_llm_calls_breakdown drives llm_calls, llm_summary,
    token_budget enrichment, request_lifecycle and llm_pipeline together."""

    class _Tracker:
        def get_llm_calls_breakdown(self):
            return [
                {
                    "node_name": "response",
                    "tokens_in": 10,
                    "tokens_out": 5,
                    "tokens_cache": 0,
                    "cost_eur": 0.01,
                    "duration_ms": 100.0,
                    "sequence": 1,
                }
            ]

    svc = StreamingService(tracker=_Tracker())
    dm = _build(svc, {})

    assert dm["llm_summary"]["total_calls"] == 1
    assert dm["llm_summary"]["total_tokens_in"] == 10
    assert dm["llm_summary"]["total_tokens_out"] == 5
    # token_budget is enriched with the real totals from the llm calls.
    assert dm["token_budget"]["total_consumed"] == 15
    assert dm["token_budget"]["tokens_input"] == 10
    assert dm["token_budget"]["tokens_output"] == 5
    # request_lifecycle + llm_pipeline are derived from llm_calls.
    assert dm["request_lifecycle"]["total_nodes"] == 1
    assert dm["llm_pipeline"]["total_calls"] == 1
    assert dm["llm_pipeline"]["total_chat_calls"] == 1


def test_tool_selection_section_from_cached_scores(service):
    """tool_selection is built from the cached SemanticToolSelector scores."""
    service._cached_tool_scores = {
        "selected_tools": [{"tool_name": "get_emails_tool", "score": 0.5, "confidence": "high"}],
        "top_score": 0.5,
        "has_uncertainty": False,
        "all_scores": {"get_emails_tool": 0.5, "get_events_tool": 0.1},
    }
    dm = _build(service, {})

    ts = dm["tool_selection"]
    assert ts["selected_tools"] == [
        {"tool_name": "get_emails_tool", "score": 0.5, "confidence": "high"}
    ]
    assert ts["top_score"] == 0.5
    assert ts["has_uncertainty"] is False
    # all_scores is sorted descending by score.
    assert list(ts["all_scores"].keys()) == ["get_emails_tool", "get_events_tool"]


# ---------------------------------------------------------------------------
# Additional coverage: sections that require tracker/resolver injection or
# specific branches (google API, image generation, journal-planner, skills,
# planner plan-details, DB-aggregated token override, error isolation).
# ---------------------------------------------------------------------------


def test_planner_intelligence_plan_details_and_generative_strategy():
    """planner_intelligence exposes plan step/tool/cost details for a generative plan."""
    plan = SimpleNamespace(
        steps=[SimpleNamespace(tool_name="get_emails_tool")], estimated_cost=0.02
    )
    pr = SimpleNamespace(
        used_template=False,
        used_panic_mode=False,
        used_generative=True,
        tokens_used=200,
        tokens_saved=800,
        plan=plan,
        success=True,
        error=None,
    )
    dm: dict = {}
    _direct_builder().build(dm, {"planning_result": pr}, "r")

    pi = dm["planner_intelligence"]
    assert pi["strategy"] == "generative"
    assert pi["plan"]["steps_count"] == 1
    assert pi["plan"]["tools_used"] == ["get_emails_tool"]
    assert pi["plan"]["estimated_cost_usd"] == 0.02
    assert pi["tokens"]["reduction_percentage"] == 80.0


def test_google_api_calls_section_summary():
    """google_api_calls splits billable vs cached and sums billable cost."""

    class _Tracker:
        def get_google_api_calls_breakdown(self):
            return [
                {"cost_usd": 0.01, "cost_eur": 0.009, "cached": False},
                {"cost_usd": 0.0, "cost_eur": 0.0, "cached": True},
            ]

    dm: dict = {}
    _direct_builder(tracker=_Tracker()).build(dm, {}, "r")

    s = dm["google_api_summary"]
    assert s["total_calls"] == 2
    assert s["billable_calls"] == 1
    assert s["cached_calls"] == 1
    assert s["total_cost_usd"] == 0.01


def test_image_generation_calls_inject_synthetic_llm_entry():
    """image_generation is summarized AND injected into llm_calls as a synthetic entry."""

    class _Tracker:
        def get_image_generation_calls_breakdown(self):
            return [
                {
                    "model": "imagen-3",
                    "cost_eur": 0.04,
                    "cost_usd": 0.05,
                    "image_count": 2,
                    "duration_ms": 1200,
                }
            ]

    dm: dict = {}
    _direct_builder(tracker=_Tracker()).build(dm, {}, "r")

    assert dm["image_generation_summary"]["total_images"] == 2
    # Synthetic llm_calls entry (drives request_lifecycle + llm_pipeline downstream).
    synthetic = dm["llm_calls"][0]
    assert synthetic["node_name"] == "image_generation"
    assert synthetic["model_name"] == "imagen-3"
    assert synthetic["sequence"] == 9999
    assert dm["request_lifecycle"]["total_nodes"] == 1
    assert dm["llm_pipeline"]["total_calls"] == 1


def test_journal_planner_injection_section_pass_through():
    """journal_planner_injection copies the state debug dict verbatim."""
    dm: dict = {}
    _direct_builder().build(
        dm,
        {
            "journal_planner_injection_debug": {
                "entries_found": 3,
                "entries_injected": 1,
                "entries": [],
            }
        },
        "r",
    )
    assert dm["journal_planner_injection"]["entries_found"] == 3
    assert dm["journal_planner_injection"]["entries_injected"] == 1


def test_skills_section_tool_activation_mode():
    """skills reflects the resolved skill + 'tool' activation mode when no plan drove it."""
    skill_data = {
        "category": "utility",
        "priority": 10,
        "scripts": ["run.py"],
        "references": ["ref.md"],
        "scope": "admin",
    }
    dm: dict = {}
    with patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=skill_data)):
        _direct_builder(resolver=lambda s: "my_skill").build(dm, {}, "r")

    sk = dm["skills"]
    assert sk["activated"] is True
    assert sk["skill_name"] == "my_skill"
    assert sk["activation_mode"] == "tool"  # no planning_result -> Route 3
    assert sk["is_deterministic"] is False
    assert sk["has_scripts"] is True
    assert sk["has_references"] is True
    assert sk["category"] == "utility"


def test_llm_calls_db_aggregated_overrides_token_budget():
    """When the DB summary is more complete than in-memory, token_budget uses DB totals."""

    class _Tracker:
        def get_llm_calls_breakdown(self):
            return [
                {
                    "node_name": "response",
                    "tokens_in": 10,
                    "tokens_out": 5,
                    "tokens_cache": 0,
                    "cost_eur": 0.01,
                    "duration_ms": 100,
                    "sequence": 1,
                }
            ]

    db = SimpleNamespace(tokens_in=100, tokens_out=50, tokens_cache=5, cost_eur=0.5)
    dm: dict = {}
    _direct_builder(tracker=_Tracker()).build(dm, {}, "r", db)

    # DB total (150) > memory total (15) -> token_budget adopts the DB figures.
    assert dm["token_budget"]["total_consumed"] == 150
    assert dm["token_budget"]["tokens_input"] == 100
    assert dm["token_budget"]["tokens_output"] == 50


def test_section_failure_is_isolated_from_other_sections():
    """A tracker that raises in one section must NOT prevent the always-on sections."""

    class _BoomTracker:
        def get_llm_calls_breakdown(self):
            raise RuntimeError("boom")

    dm: dict = {}
    _direct_builder(tracker=_BoomTracker()).build(dm, {}, "r")

    # token_budget + knowledge_enrichment are still built despite llm_calls failing.
    assert "token_budget" in dm
    assert "knowledge_enrichment" in dm
    assert "llm_calls" not in dm


def _planning_result_with_metadata(metadata: dict) -> SimpleNamespace:
    """A fully-formed PlanningResult stand-in (planner_intelligence reads all flags)."""
    return SimpleNamespace(
        used_template=False,
        used_panic_mode=False,
        used_generative=True,
        tokens_used=0,
        tokens_saved=0,
        success=True,
        error=None,
        plan=SimpleNamespace(metadata=metadata, steps=[], estimated_cost=0.0),
    )


def test_skills_section_planner_activation_mode():
    """A plan whose metadata carries skill_name yields 'planner' activation mode."""
    planning_result = _planning_result_with_metadata({"skill_name": "s"})
    with patch(
        "src.domains.skills.cache.SkillsCache.get_by_name",
        Mock(return_value={"scripts": ["x"], "references": []}),
    ):
        dm: dict = {}
        _direct_builder(resolver=lambda s: "s").build(dm, {"planning_result": planning_result}, "r")
    assert dm["skills"]["activation_mode"] == "planner"
    assert dm["skills"]["is_deterministic"] is False


def test_skills_section_bypass_activation_mode_is_deterministic():
    """A skill_bypass plan yields 'bypass' mode flagged deterministic."""
    planning_result = _planning_result_with_metadata({"skill_bypass": True})
    with patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=None)):
        dm: dict = {}
        _direct_builder(resolver=lambda s: "s").build(dm, {"planning_result": planning_result}, "r")
    assert dm["skills"]["activation_mode"] == "bypass"
    assert dm["skills"]["is_deterministic"] is True


def test_tool_selection_fallback_builds_from_filtered_catalogue():
    """When tool_scores lack selected_tools, they are rebuilt from the filtered catalogue."""
    scores = {
        "selected_tools": [],
        "top_score": 0.5,
        "has_uncertainty": False,
        "all_scores": {"t1": 0.5, "t2": 0.1},
    }
    catalogue = SimpleNamespace(tools=[{"name": "t1"}])
    dm: dict = {}
    _direct_builder(cached_tool_scores=scores, cached_filtered_catalogue=catalogue).build(
        dm, {}, "r"
    )
    sel = dm["tool_selection"]["selected_tools"]
    assert sel == [{"tool_name": "t1", "score": 0.5, "confidence": "high"}]


def test_planner_intelligence_panic_and_filtered_strategies():
    """Strategy name reflects panic_mode / filtered_catalogue flag combinations."""
    panic = SimpleNamespace(
        used_template=False,
        used_panic_mode=True,
        used_generative=False,
        tokens_used=0,
        tokens_saved=0,
        plan=None,
        success=True,
        error=None,
    )
    dm: dict = {}
    _direct_builder().build(dm, {"planning_result": panic}, "r")
    assert dm["planner_intelligence"]["strategy"] == "panic_mode"

    filtered = SimpleNamespace(
        used_template=False,
        used_panic_mode=False,
        used_generative=False,
        tokens_used=0,
        tokens_saved=0,
        plan=None,
        success=True,
        error=None,
    )
    dm2: dict = {}
    _direct_builder().build(dm2, {"planning_result": filtered}, "r")
    assert dm2["planner_intelligence"]["strategy"] == "filtered_catalogue"


def test_execution_waves_section_from_dependency_graph():
    """execution_waves is populated from DependencyGraph.get_wave_info()."""
    graph = Mock()
    graph.get_wave_info.return_value = {"waves": [["s1"], ["s2"]]}
    with patch(
        "src.domains.agents.orchestration.dependency_graph.DependencyGraph",
        Mock(return_value=graph),
    ):
        dm: dict = {}
        _direct_builder().build(dm, {"execution_plan": SimpleNamespace(steps=[])}, "r")
    assert dm["execution_waves"] == {"waves": [["s1"], ["s2"]]}
