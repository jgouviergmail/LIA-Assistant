"""Where each module's model spend is recorded — declared, never inferred.

Accounting in this codebase is **ambient**: a node inside a turn spends through
a ``TrackingContext`` an ancestor published, so the node's own file mentions no
tracker at all. Reading a file therefore proves nothing in either direction,
and an audit conducted that way produced nine wrong conclusions in a single
session before this module existed.

What proved things was production. Joining ``token_usage_logs`` to the
registers on 2026-09-07 showed a clean line: everything travelling through the
agent graph was recorded, everything calling the model directly was not. And
one family was recorded nowhere at all — 84 personality translations ran
between 2025-12-11 and 2026-02-05 while the ledger was demonstrably working,
recording 5 976 rows across 17 other surfaces over the same window.

So the road is written down, and :mod:`tests.unit.infrastructure.llm.
test_llm_spend_road_completeness` refuses both an omission and a stale entry.
Four roads, and the fourth is not an escape hatch:

- :attr:`SpendRoad.TURN` — inside an agent turn; the ambient tracker records it.
- :attr:`SpendRoad.ACCOUNTED` — out of turn, opening its own accounting against
  the account (``track_proactive_tokens``, or its own ``TrackingContext``).
- :attr:`SpendRoad.CALLER` — spends through a caller that is itself on a road,
  which :data:`CALLER_ROAD_ACCOUNTANTS` must NAME, so the graph terminates.
- :attr:`SpendRoad.INSTANCE` — nobody owns this euro; only the instance's daily
  ledger receives it, and :data:`INSTANCE_ROAD_REASONS` says why.
"""

from __future__ import annotations

from enum import Enum


class SpendRoad(str, Enum):
    """Which ledger receives what a module spends on a model."""

    TURN = "turn"
    ACCOUNTED = "accounted"
    CALLER = "caller"
    INSTANCE = "instance"


#: Every module of ``src`` that calls ``get_llm``, and the road its euros take.
#: Keys are posix paths relative to ``src``. Adding a spend site without adding
#: it here fails the build; leaving one here after deleting the call fails too.
LLM_SPEND_ROADS: dict[str, SpendRoad] = {
    # --- Inside the agent turn: the ambient TrackingContext records these ----
    "domains/agents/graphs/base_agent_builder.py": SpendRoad.TURN,
    "domains/agents/nodes/initiative_node.py": SpendRoad.TURN,
    "domains/agents/nodes/react_nodes.py": SpendRoad.TURN,
    "domains/agents/nodes/response_node.py": SpendRoad.TURN,
    "domains/agents/orchestration/semantic_validator.py": SpendRoad.TURN,
    "domains/agents/services/analysis/memory_resolver.py": SpendRoad.TURN,
    "domains/agents/services/compaction_service.py": SpendRoad.TURN,
    "domains/agents/services/fallback_response.py": SpendRoad.TURN,
    "domains/agents/services/hitl/draft_modifier.py": SpendRoad.TURN,
    "domains/agents/services/hitl/item_filter.py": SpendRoad.TURN,
    "domains/agents/services/hitl/question_generator.py": SpendRoad.TURN,
    "domains/agents/services/hitl_classifier.py": SpendRoad.TURN,
    "domains/agents/services/memory_extractor.py": SpendRoad.TURN,
    "domains/agents/services/memory_reference_resolution_service.py": SpendRoad.TURN,
    "domains/agents/services/planner/strategies/multi_domain.py": SpendRoad.TURN,
    "domains/agents/services/planner/strategies/single_domain.py": SpendRoad.TURN,
    "domains/agents/services/query_analyzer_service.py": SpendRoad.TURN,
    "domains/agents/services/semantic_pivot_service.py": SpendRoad.TURN,
    "domains/agents/services/smart_planner_service.py": SpendRoad.TURN,
    "domains/agents/tools/emails_tools.py": SpendRoad.TURN,
    "domains/agents/tools/react_runner.py": SpendRoad.TURN,
    "domains/document_generation/service.py": SpendRoad.TURN,
    "domains/interests/services/extraction_service.py": SpendRoad.TURN,
    "domains/journals/extraction_service.py": SpendRoad.TURN,
    "domains/voice/service.py": SpendRoad.TURN,
    # --- Out of turn, billed to the account that benefits ------------------
    "domains/agents/services/open_loop_extractor.py": SpendRoad.ACCOUNTED,
    "domains/briefing/llm.py": SpendRoad.ACCOUNTED,
    "domains/interests/services/content_sources/llm_reflection_source.py": SpendRoad.ACCOUNTED,
    "domains/psyche/service.py": SpendRoad.ACCOUNTED,
    "domains/telephony/return_synthesis.py": SpendRoad.ACCOUNTED,
    "domains/user_mcp/description_generation.py": SpendRoad.ACCOUNTED,
    "infrastructure/scheduler/interest_subject_clustering.py": SpendRoad.ACCOUNTED,
    "infrastructure/scheduler/peer_message_delivery.py": SpendRoad.ACCOUNTED,
    "infrastructure/scheduler/reminder_notification.py": SpendRoad.ACCOUNTED,
    # --- Spends through a caller that accounts for it ----------------------
    "domains/heartbeat/prompts.py": SpendRoad.CALLER,
    "domains/interests/proactive_task.py": SpendRoad.CALLER,
    "domains/journals/consolidation_service.py": SpendRoad.CALLER,
    "domains/meetings/synthesis.py": SpendRoad.CALLER,
    "domains/meetings/template_resolution.py": SpendRoad.CALLER,
    "domains/meetings/transcript_rewrite.py": SpendRoad.CALLER,
    "domains/relations/debrief/llm.py": SpendRoad.CALLER,
    # --- The instance pays; no account may be charged for it ---------------
    "domains/diagnostics/diagnosis.py": SpendRoad.INSTANCE,
    "domains/notifications/broadcast_service.py": SpendRoad.INSTANCE,
    "domains/personalities/translation_service.py": SpendRoad.INSTANCE,
    "domains/skills/description_translation.py": SpendRoad.INSTANCE,
    "infrastructure/llm/evaluation_pipeline.py": SpendRoad.INSTANCE,
}

#: Why each instance-road module has no account to bill. Choosing this road
#: skips per-account accounting entirely, so it must be argued rather than
#: defaulted to: a module placed here by mistake spends a person's quota
#: allowance without ever touching their counters.
INSTANCE_ROAD_REASONS: dict[str, str] = {
    "domains/diagnostics/diagnosis.py": (
        "Self-diagnosis reads the instance's own incidents from a scheduler "
        "tick. It serves the operator, runs for no account, and would bill an "
        "arbitrary user if it were attached to one."
    ),
    "domains/notifications/broadcast_service.py": (
        "A broadcast is translated ONCE for a message sent to everyone. "
        "Charging the translation to a recipient would pick a payer at random "
        "among people who did not ask for it."
    ),
    "domains/personalities/translation_service.py": (
        "Personalities are instance-wide catalogue content an administrator "
        "edits; their translations belong to the deployment, not to whoever "
        "happens to select one afterwards."
    ),
    "domains/skills/description_translation.py": (
        "A skill description is translated when the skill is created or "
        "edited, for every future reader in every language — the same "
        "catalogue argument as personalities."
    ),
    "infrastructure/llm/evaluation_pipeline.py": (
        "The retrieval-evaluation harness measures the deployment's own "
        "quality on demand; its runs answer an operator's question and belong "
        "to no account's usage."
    ),
}

#: ``INSTANCE`` modules that record their spend but do NOT ask the ceiling
#: first, and the reason. Four of the five ask (``is_instance_spend_blocked``);
#: the fifth was simply an omission until this table made the asymmetry
#: visible — a road that records without asking spends past an exhausted
#: ceiling, which is half a ledger.
#:
#: An entry here is an argument, never a convenience: it must say why the
#: caller cannot skip its call.
INSTANCE_GATE_EXEMPT: dict[str, str] = {
    "infrastructure/llm/evaluation_pipeline.py": (
        "An evaluator must produce a measurement or fail; it has no empty "
        "answer to return. Skipping the call would hand back a fabricated "
        "score an operator would then read as real — worse than the spend it "
        "saves. It records what it costs, so the ledger stays exact and the "
        "next run is refused by whoever reads it."
    ),
}

#: For each ``CALLER`` module, the module that actually accounts for its spend.
#: Named rather than implied, so the road graph terminates on a real road: a
#: caller nobody names is indistinguishable from a spend nobody records.
CALLER_ROAD_ACCOUNTANTS: dict[str, str] = {
    "domains/heartbeat/prompts.py": "domains/heartbeat/proactive_task.py",
    "domains/interests/proactive_task.py": "infrastructure/proactive/runner.py",
    "domains/journals/consolidation_service.py": "domains/journals/extraction_service.py",
    "domains/meetings/synthesis.py": "domains/meetings/processing.py",
    "domains/meetings/template_resolution.py": "domains/meetings/processing.py",
    "domains/meetings/transcript_rewrite.py": "domains/meetings/processing.py",
    "domains/relations/debrief/llm.py": "domains/relations/debrief/service.py",
}


__all__ = [
    "CALLER_ROAD_ACCOUNTANTS",
    "INSTANCE_GATE_EXEMPT",
    "INSTANCE_ROAD_REASONS",
    "LLM_SPEND_ROADS",
    "SpendRoad",
]
