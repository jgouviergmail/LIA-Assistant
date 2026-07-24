"""Characterization tests for granular intent mapping (drives the tool strategy).

``_map_llm_intent_to_internal`` turns the LLM's coarse verdict ("action" /
"conversation") into a granular intent — search, create, update, delete, send,
chat — which selects the **tool strategy**, i.e. which tool categories are
loaded for the turn (``agent_registry``: "delete" → delete tools, "update" →
update tools, …). ``_determine_turn_type`` then classifies the turn for
reference resolution.

Neither had any test, yet a wrong intent over-provisions mutation tools on a
read query, or withholds them from a genuine action.

Detection is a bare-word SUBSTRING match over the pivoted English query. That is
imprecise by construction, and the false positives below are pinned
DELIBERATELY: they are characterization, not endorsement. There is no
authoritative oracle for user intent here, and tightening the match (word
boundaries) would trade these false positives for false NEGATIVES on inflected
forms ("removing", "scheduling") — i.e. a genuine action silently losing its
tools. Any future change must therefore be measured against these pins rather
than made blind.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.config.agents import V3RoutingConfig
from src.domains.agents.services.query_analyzer_service import QueryAnalyzerService

pytestmark = pytest.mark.unit


@pytest.fixture
def service() -> QueryAnalyzerService:
    return QueryAnalyzerService(
        memory_resolver=MagicMock(),
        context_resolver=MagicMock(),
        goal_inferrer=MagicMock(),
        routing_decider=MagicMock(),
        thresholds=V3RoutingConfig(
            chat_semantic_threshold=0.3,
            high_semantic_threshold=0.7,
            min_confidence=0.5,
            chat_override_threshold=0.8,
            cross_domain_threshold=0.5,
        ),
    )


def _intent(service: QueryAnalyzerService, query: str, domains: list[str] | None = None) -> str:
    return service._map_llm_intent_to_internal("action", query, domains or [])


# ============================================================================
# Conversation short-circuit
# ============================================================================


class TestConversationShortCircuit:
    def test_conversation_always_maps_to_chat(self, service: QueryAnalyzerService) -> None:
        """The pattern matching must never run for a conversational verdict —
        otherwise "can you create a poem?" would load create tools."""
        assert (
            service._map_llm_intent_to_internal("conversation", "delete everything", []) == "chat"
        )


# ============================================================================
# True positives per intent
# ============================================================================


class TestGranularIntents:
    @pytest.mark.parametrize(
        "query", ["send an email to john", "reply to this", "forward it", "compose a mail"]
    )
    def test_send_requires_the_email_domain(
        self, service: QueryAnalyzerService, query: str
    ) -> None:
        assert _intent(service, query, ["email"]) == "send"

    def test_send_pattern_without_email_domain_falls_through(
        self, service: QueryAnalyzerService
    ) -> None:
        """ "send" only means "send an email" when the email domain is in play;
        otherwise the query keeps flowing through the other patterns."""
        assert _intent(service, "send the meeting invite", ["event"]) != "send"

    @pytest.mark.parametrize("query", ["delete this email", "remove the label", "erase it"])
    def test_delete_intent(self, service: QueryAnalyzerService, query: str) -> None:
        assert _intent(service, query) == "delete"

    @pytest.mark.parametrize("query", ["create an event", "schedule a meeting", "remind me at 8"])
    def test_create_intent(self, service: QueryAnalyzerService, query: str) -> None:
        assert _intent(service, query) == "create"

    @pytest.mark.parametrize("query", ["update the task", "change the title", "reschedule it"])
    def test_update_intent(self, service: QueryAnalyzerService, query: str) -> None:
        assert _intent(service, query) == "update"

    @pytest.mark.parametrize(
        "query", ["show me my emails", "what is the weather", "find john's phone number"]
    )
    def test_plain_queries_default_to_search(
        self, service: QueryAnalyzerService, query: str
    ) -> None:
        assert _intent(service, query) == "search"


# ============================================================================
# Priority order between competing patterns
# ============================================================================


class TestPriorityOrder:
    def test_delete_wins_over_create(self, service: QueryAnalyzerService) -> None:
        """Checked before create: the destructive reading is the safer default
        when both verbs appear."""
        assert _intent(service, "delete the event i created") == "delete"

    def test_create_wins_over_update(self, service: QueryAnalyzerService) -> None:
        assert _intent(service, "create a task and update the list") == "create"

    def test_send_wins_over_delete_in_email_domain(self, service: QueryAnalyzerService) -> None:
        assert _intent(service, "reply then delete it", ["email"]) == "send"

    @pytest.mark.parametrize(
        "query",
        [
            "reschedule my 3pm meeting to 5pm",
            "reschedule the dentist appointment",
            "can you reschedule it",
        ],
    )
    def test_reschedule_is_an_update_not_a_create(
        self, service: QueryAnalyzerService, query: str
    ) -> None:
        """Regression: "reschedule" strictly contains the create pattern
        "schedule", and create is checked first — so the declared "reschedule"
        UPDATE pattern was unreachable and the turn loaded create tools instead
        of update_event_tool, duplicating the event instead of moving it.
        """
        assert _intent(service, query, ["event"]) == "update"


# ============================================================================
# KNOWN IMPRECISION — pinned, not endorsed
# ============================================================================


class TestSubstringFalsePositives:
    """Bare words are matched as SUBSTRINGS of the query, so content words that
    merely CONTAIN a verb flip the intent. Pinned so the imprecision is visible
    and any future tightening is a measured change, never an accident."""

    @pytest.mark.parametrize(
        ("query", "leaked_intent", "why"),
        [
            ("what is the address of the restaurant", "create", "'add' inside 'address'"),
            ("find emails about the cancelled meeting", "delete", "'cancel' inside 'cancelled'"),
            ("show me the latest updates", "update", "'update' inside 'updates'"),
            ("what is the news today", "create", "'new' inside 'news'"),
        ],
    )
    def test_content_word_leaks_into_a_mutation_intent(
        self, service: QueryAnalyzerService, query: str, leaked_intent: str, why: str
    ) -> None:
        assert _intent(service, query) == leaked_intent, why


# ============================================================================
# _determine_turn_type
# ============================================================================


class TestTurnType:
    def test_no_context_is_a_plain_action(self, service: QueryAnalyzerService) -> None:
        assert service._determine_turn_type(None, "search") == "ACTION"

    def test_empty_context_items_is_a_plain_action(self, service: QueryAnalyzerService) -> None:
        context = MagicMock()
        context.items = []
        assert service._determine_turn_type(context, "delete") == "ACTION"

    @pytest.mark.parametrize("intent", ["send", "create", "update", "delete"])
    def test_mutation_intent_with_context_is_a_reference_action(
        self, service: QueryAnalyzerService, intent: str
    ) -> None:
        """ "delete the second one" — acting on a resolved reference."""
        context = MagicMock()
        context.items = [{"id": "1"}]
        assert service._determine_turn_type(context, intent) == "REFERENCE_ACTION"

    @pytest.mark.parametrize("intent", ["search", "list", "chat"])
    def test_read_intent_with_context_is_a_pure_reference(
        self, service: QueryAnalyzerService, intent: str
    ) -> None:
        context = MagicMock()
        context.items = [{"id": "1"}]
        assert service._determine_turn_type(context, intent) == "REFERENCE_PURE"
