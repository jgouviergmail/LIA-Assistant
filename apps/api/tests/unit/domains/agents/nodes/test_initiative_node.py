"""
Unit tests for initiative_node.

Tests the post-execution proactive enrichment node.

Phase: ADR-062 — Agent Initiative Phase
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.domains.agents.nodes.initiative_node import (
    InitiativeAction,
    InitiativeDecision,
    _build_semantic_context,
    _extract_domains,
    _extract_original_query,
    _format_interests,
    _format_memory_facts,
    _manifest_domain,
)
from src.domains.agents.orchestration.plan_schemas import ParameterItem, ParameterValue


@pytest.mark.unit
class TestInitiativeDecision:
    """Tests for InitiativeDecision schema."""

    def test_no_action_decision(self) -> None:
        decision = InitiativeDecision(
            analysis="No cross-domain signals found.",
            should_act=False,
            reasoning="Results are self-contained.",
        )
        assert not decision.should_act
        assert decision.actions == []
        assert decision.suggestion is None

    def test_action_with_suggestion(self) -> None:
        decision = InitiativeDecision(
            analysis="Email mentions a meeting.",
            should_act=True,
            reasoning="Check calendar availability.",
            actions=[
                InitiativeAction(
                    tool_name="get_events_tool",
                    parameters=[
                        ParameterItem(
                            name="start_date",
                            value=ParameterValue(string_value="2026-03-26", value_type="string"),
                        )
                    ],
                    rationale="Check Thursday availability",
                )
            ],
            suggestion="Would you like me to create a calendar event?",
        )
        assert decision.should_act
        assert len(decision.actions) == 1
        assert decision.suggestion is not None


@pytest.mark.unit
class TestExtractDomains:
    """Tests for _extract_domains."""

    def test_none_qi(self) -> None:
        state: dict = {"query_intelligence": None}
        assert _extract_domains(state) == []

    def test_qi_with_domains(self) -> None:
        qi = MagicMock()
        qi.domains = ["email", "contact"]
        state: dict = {"query_intelligence": qi}
        assert _extract_domains(state) == ["email", "contact"]

    def test_qi_without_domains_attr(self) -> None:
        qi = MagicMock(spec=[])
        state: dict = {"query_intelligence": qi}
        assert _extract_domains(state) == []


@pytest.mark.unit
class TestExtractOriginalQuery:
    """Tests for _extract_original_query."""

    def test_finds_last_human_message(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        state: dict = {
            "messages": [
                HumanMessage(content="first question"),
                AIMessage(content="response"),
                HumanMessage(content="second question"),
            ]
        }
        assert _extract_original_query(state) == "second question"

    def test_empty_messages(self) -> None:
        state: dict = {"messages": []}
        assert _extract_original_query(state) == ""


@pytest.mark.unit
class TestFormatHelpers:
    """Tests for formatting helpers."""

    def test_format_memory_facts_none(self) -> None:
        assert _format_memory_facts(None) == "No relevant memories."

    def test_format_memory_facts_with_data(self) -> None:
        result = _format_memory_facts(["Fact 1", "Fact 2"])
        assert "Fact 1" in result
        assert "Fact 2" in result

    def test_format_interests_empty(self) -> None:
        assert _format_interests({"interests": []}) == "No known interests."

    def test_format_interests_with_data(self) -> None:
        profile = {
            "interests": [
                {"topic": "cycling", "category": "sports", "status": "active"},
                {"topic": "cooking", "category": "hobbies", "status": "inactive"},
            ]
        }
        result = _format_interests(profile)
        assert "cycling" in result
        assert "cooking" not in result  # inactive filtered out


def _manifest(name: str, agent: str, parameters: list | None = None) -> MagicMock:
    """Build a minimal tool manifest mock with real name/agent/parameters."""
    m = MagicMock()
    m.name = name
    m.agent = agent
    m.parameters = parameters or []
    return m


@pytest.mark.unit
class TestManifestDomain:
    """Tests for _manifest_domain."""

    def test_strips_agent_suffix(self) -> None:
        assert _manifest_domain(_manifest("get_route_tool", "routes_agent")) == "routes"

    def test_missing_agent_returns_unknown(self) -> None:
        m = MagicMock(spec=[])
        assert _manifest_domain(m) == "unknown"

    def test_empty_agent_returns_unknown(self) -> None:
        assert _manifest_domain(_manifest("t", "")) == "unknown"


@pytest.mark.unit
class TestBuildSemanticContext:
    """Tests for _build_semantic_context (S2i semantic bridges)."""

    def test_disabled_returns_fallbacks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.constants import SEMANTIC_CANDIDATES_NONE, SEMANTIC_DEPS_NO_CROSS_DOMAIN
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", False, raising=False)

        deps, candidates = _build_semantic_context(
            ["email"], [_manifest("get_contact_tool", "contact_agent")]
        )

        assert deps == SEMANTIC_DEPS_NO_CROSS_DOMAIN
        assert candidates == SEMANTIC_CANDIDATES_NONE

    def test_bridge_found_between_executed_and_adjacent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.nodes import initiative_node as mod
        from src.domains.agents.semantic import expansion_service as svc_mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        type_def = MagicMock()
        type_def.used_in_tools = ["get_contact_tool", "unavailable_tool"]
        type_def.source_domains = ["email", "contact"]

        registry = MagicMock()
        registry.get_by_domain.side_effect = lambda d: (
            {"email_address"} if d == "email" else set()
        )
        registry.get.side_effect = lambda n: type_def if n == "email_address" else None

        service = MagicMock()
        service.registry = registry
        monkeypatch.setattr(svc_mod, "get_expansion_service", lambda: service)

        deps_calls: list[tuple[list[str], bool]] = []

        def _fake_deps(domains: list[str], include_jinja2_patterns: bool = True) -> str:
            deps_calls.append((domains, include_jinja2_patterns))
            return "DEPS_SECTION"

        monkeypatch.setattr(svc_mod, "generate_semantic_dependencies_for_prompt", _fake_deps)

        deps, candidates = _build_semantic_context(
            ["email"], [_manifest("get_contact_tool", "contact_agent")]
        )

        assert deps == "DEPS_SECTION"
        # Dependencies computed over executed + adjacent domains, without Jinja2
        assert deps_calls == [(["email", "contact"], False)]
        # Directional candidate: type from executed domain → available adjacent tool
        assert "email_address" in candidates
        assert "get_contact_tool" in candidates
        assert "unavailable_tool" not in candidates
        assert "(from email results)" in candidates  # provider attribution

    def test_no_consumers_returns_candidates_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.constants import SEMANTIC_CANDIDATES_NONE
        from src.domains.agents.nodes import initiative_node as mod
        from src.domains.agents.semantic import expansion_service as svc_mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        type_def = MagicMock()
        type_def.used_in_tools = ["some_other_tool"]  # not in adjacent manifests
        type_def.source_domains = ["email"]

        registry = MagicMock()
        registry.get_by_domain.return_value = {"email_address"}
        registry.get.return_value = type_def

        service = MagicMock()
        service.registry = registry
        monkeypatch.setattr(svc_mod, "get_expansion_service", lambda: service)
        monkeypatch.setattr(
            svc_mod, "generate_semantic_dependencies_for_prompt", lambda *a, **k: "DEPS"
        )

        _deps, candidates = _build_semantic_context(
            ["email"], [_manifest("get_contact_tool", "contact_agent")]
        )

        assert candidates == SEMANTIC_CANDIDATES_NONE

    def test_registry_failure_degrades_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.constants import SEMANTIC_CANDIDATES_NONE, SEMANTIC_DEPS_NO_CROSS_DOMAIN
        from src.domains.agents.nodes import initiative_node as mod
        from src.domains.agents.semantic import expansion_service as svc_mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        def _boom() -> None:
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr(svc_mod, "get_expansion_service", _boom)
        monkeypatch.setattr(
            svc_mod,
            "generate_semantic_dependencies_for_prompt",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("deps failed")),
        )

        deps, candidates = _build_semantic_context(
            ["email"], [_manifest("get_contact_tool", "contact_agent")]
        )

        assert deps == SEMANTIC_DEPS_NO_CROSS_DOMAIN
        assert candidates == SEMANTIC_CANDIDATES_NONE

    def test_manifest_param_semantic_type_creates_bridge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tool whose PARAMETER declares the semantic_type is a consumer even
        when the ontology's used_in_tools does not list it — the live manifest
        layer wins over the static editorial layer (union semantics)."""
        from src.domains.agents.nodes import initiative_node as mod
        from src.domains.agents.semantic import expansion_service as svc_mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        type_def = MagicMock()
        type_def.used_in_tools = []  # ontology knows no consumer
        type_def.source_domains = ["contact"]

        registry = MagicMock()
        registry.get_by_domain.return_value = {"physical_address"}
        registry.get.return_value = type_def

        service = MagicMock()
        service.registry = registry
        monkeypatch.setattr(svc_mod, "get_expansion_service", lambda: service)
        monkeypatch.setattr(
            svc_mod, "generate_semantic_dependencies_for_prompt", lambda *a, **k: "DEPS"
        )

        param = MagicMock()
        param.semantic_type = "physical_address"
        manifest = _manifest("get_places_tool", "place_agent", parameters=[param])

        _deps, candidates = _build_semantic_context(["contact"], [manifest])

        assert "physical_address" in candidates
        assert "get_places_tool" in candidates

    def test_consumers_truncated_beyond_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.agents.nodes import initiative_node as mod
        from src.domains.agents.semantic import expansion_service as svc_mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        tool_names = [f"tool_{i}" for i in range(5)]
        type_def = MagicMock()
        type_def.used_in_tools = tool_names
        type_def.source_domains = ["email"]

        registry = MagicMock()
        registry.get_by_domain.return_value = {"email_address"}
        registry.get.return_value = type_def

        service = MagicMock()
        service.registry = registry
        monkeypatch.setattr(svc_mod, "get_expansion_service", lambda: service)
        monkeypatch.setattr(
            svc_mod, "generate_semantic_dependencies_for_prompt", lambda *a, **k: "DEPS"
        )

        _deps, candidates = _build_semantic_context(
            ["email"], [_manifest(n, "contact_agent") for n in tool_names]
        )

        assert "tool_0, tool_1, tool_2" in candidates
        assert "(+2 more)" in candidates
        assert "tool_4" not in candidates

    def test_real_registry_contact_to_route_bridge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The real TypeRegistry yields the canonical contact→route bridge.

        Domain vocabulary is SINGULAR ("contact", "route" — v3.2 naming, same
        as QueryIntelligence.domains and agent names): physical_address is
        provided by [contact] and consumed by get_route_tool. This pins the
        vocabulary alignment — a plural drift would silently produce the
        fallback string instead.
        """
        from src.core.constants import SEMANTIC_CANDIDATES_NONE
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "semantic_linking_enabled", True, raising=False)

        deps, candidates = _build_semantic_context(
            ["contact"], [_manifest("get_route_tool", "route_agent")]
        )

        assert isinstance(deps, str) and deps
        assert candidates != SEMANTIC_CANDIDATES_NONE
        assert "physical_address" in candidates
        assert "get_route_tool" in candidates


@pytest.mark.unit
class TestInitiativePromptPlaceholders:
    """The prompt template and the node's format() kwargs stay in sync."""

    def test_prompt_formats_with_all_node_kwargs(self) -> None:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        prompt = load_prompt("initiative_prompt", version="v1").format(
            execution_summary="summary",
            available_tools="tools",
            memory_facts="facts",
            user_interests="interests",
            semantic_dependencies="deps",
            connection_candidates="candidates",
            user_language="fr",
            user_timezone="UTC",
            original_query="query",
            current_datetime="2026-07-02",
            max_actions=2,
        )

        assert "<SemanticBridges>" in prompt
        assert "deps" in prompt
        assert "candidates" in prompt


@pytest.mark.unit
@pytest.mark.asyncio
class TestInitiativeSkippedWhenSkillActive:
    """Initiative is skipped when a skill is driving the turn.

    Skills define a deterministic output contract (plan_template + references).
    Running initiative on top would inject orthogonal domains (e.g. "nearby
    places" during a daily briefing), polluting the skill's intended output
    and confusing the response LLM that must follow the skill's formatting.
    """

    async def test_skips_when_execution_plan_carries_skill_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = {"skill_name": "briefing-quotidien"}
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        assert result.get("initiative_skipped_reason") == "skill_active"
        assert result.get("initiative_iteration") == 1

    async def test_runs_when_plan_has_no_skill_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regular (non-skill) plans still proceed past the skill check.

        Verified by letting the node reach the next early-return
        (``no_adjacent_read_only_tools``) — proof the skill check did not
        short-circuit first.
        """
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = {}  # no skill_name
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
            "query_intelligence": None,  # forces empty executed_domains
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        assert result.get("initiative_skipped_reason") != "skill_active"

    async def test_skips_when_plan_metadata_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A plan without ``metadata`` attribute does not crash the check."""
        from src.domains.agents.nodes import initiative_node as mod

        monkeypatch.setattr(mod.settings, "initiative_enabled", True, raising=False)

        plan = MagicMock()
        plan.metadata = None
        state = {
            "execution_plan": plan,
            "initiative_iteration": 0,
            "query_intelligence": None,
        }
        config = {"configurable": {"user_id": "test-user"}}

        result = await mod.initiative_node(state, config)

        # Not skipped for "skill_active" since no skill_name present
        assert result.get("initiative_skipped_reason") != "skill_active"
