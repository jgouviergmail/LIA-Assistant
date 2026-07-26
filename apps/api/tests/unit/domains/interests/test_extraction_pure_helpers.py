"""Interest extraction — the pure surfaces around the LLM call.

Interests drive the proactive engine: what LIA brings up on its own comes from
what this extractor decided the user cares about. Four pure pieces frame the
LLM call, and every one of them fails without raising:

* ``_compute_analysis_cache_key`` decides whether an analysis is re-run or
  replayed. A key that collides across users would serve one user's analysis to
  another; a key that never repeats makes the cache a pure cost.
* ``InterestAnalysisResult.to_cache_dict`` / ``from_cache_dict`` is a
  serialization PAIR — the systemic rule requires a round-trip test over every
  serialized field, because adding a field on one side only is silent.
* ``_format_messages_for_extraction`` decides what the LLM reads.
* ``_parse_extraction_result`` applies the confidence floor: below it, an
  interest is dropped and never proposed again.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.constants import (
    INTEREST_EXTRACTION_MIN_CONFIDENCE,
    INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH,
)
from src.domains.interests.models import InterestCategory
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services.extraction_service import (
    InterestAnalysisResult,
    _compute_analysis_cache_key,
    _format_messages_for_extraction,
    _parse_extraction_result,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Cache key
# =============================================================================


class TestAnalysisCacheKey:
    def test_the_same_user_and_message_replay_the_same_analysis(self) -> None:
        first = _compute_analysis_cache_key("user-1", "je fais du vélo")
        second = _compute_analysis_cache_key("user-1", "je fais du vélo")

        assert first == second

    def test_two_users_never_share_a_key(self) -> None:
        # A collision here would hand one user's extracted interests to another.
        assert _compute_analysis_cache_key("user-1", "même message") != _compute_analysis_cache_key(
            "user-2", "même message"
        )

    def test_a_different_message_gets_its_own_key(self) -> None:
        assert _compute_analysis_cache_key("user-1", "vélo") != _compute_analysis_cache_key(
            "user-1", "escalade"
        )

    def test_the_key_carries_the_user_id_in_clear_but_never_the_message(self) -> None:
        key = _compute_analysis_cache_key("user-42", "je pars à Lisbonne avec Marie")

        assert "user-42" in key
        assert "Lisbonne" not in key
        assert "Marie" not in key

    def test_the_key_is_bounded_whatever_the_message_length(self) -> None:
        short = _compute_analysis_cache_key("u", "a")
        long = _compute_analysis_cache_key("u", "a" * 100_000)

        assert len(short) == len(long)

    def test_non_ascii_content_does_not_break_the_hash(self) -> None:
        assert _compute_analysis_cache_key("u", "escalade à Fontainebleau 🧗")


# =============================================================================
# Cache round-trip
# =============================================================================


def make_result(**overrides: Any) -> InterestAnalysisResult:
    defaults: dict[str, Any] = {
        "analyzed": True,
        "analysis_skipped_reason": None,
        "extracted_interests": [
            ExtractedInterest(
                action="create",
                topic="escalade en salle",
                category=InterestCategory.SPORTS,
                confidence=0.82,
            )
        ],
        "llm_model": "gpt-x",
        "llm_input_tokens": 1234,
        "llm_output_tokens": 56,
        "llm_cached_tokens": 78,
        "llm_temperature": 0.3,
        "analyzed_message": "je me suis mis à l'escalade",
        "context_messages_count": 4,
    }
    defaults.update(overrides)
    return InterestAnalysisResult(**defaults)


class TestCacheRoundTrip:
    """The systemic rule: every serialized field survives the round trip."""

    # Deliberately NOT cached — asserted below so the exclusion stays a choice.
    NOT_CACHED = {"llm_duration_ms", "_raw_result"}

    def test_every_field_is_either_cached_or_explicitly_excluded(self) -> None:
        declared = {field.name for field in fields(InterestAnalysisResult)}
        cached = set(make_result().to_cache_dict())

        assert declared - cached == self.NOT_CACHED, (
            "a field was added to InterestAnalysisResult without deciding whether "
            "it belongs in the Redis cache"
        )

    def test_the_round_trip_preserves_every_cached_field(self) -> None:
        original = make_result()

        restored = InterestAnalysisResult.from_cache_dict(original.to_cache_dict())

        assert restored.to_cache_dict() == original.to_cache_dict()

    def test_the_fixture_moves_every_field_off_its_default(self) -> None:
        # Without this, the round-trip identity above would be vacuous for any
        # field left at its default value.
        default = InterestAnalysisResult().to_cache_dict()
        moved = make_result().to_cache_dict()

        unchanged = [key for key in moved if moved[key] == default[key]]
        assert unchanged == ["analysis_skipped_reason"], unchanged

    def test_the_extracted_interests_survive_field_by_field(self) -> None:
        restored = InterestAnalysisResult.from_cache_dict(make_result().to_cache_dict())

        interest = restored.extracted_interests[0]
        assert interest.action == "create"
        assert interest.topic == "escalade en salle"
        assert interest.category == InterestCategory.SPORTS
        assert interest.confidence == pytest.approx(0.82)

    def test_the_llm_duration_is_not_replayed_from_the_cache(self) -> None:
        # A cache hit made no LLM call, so reporting the original duration in the
        # debug panel would be a fabricated measurement.
        restored = InterestAnalysisResult.from_cache_dict(
            make_result(llm_duration_ms=1500.0).to_cache_dict()
        )

        assert restored.llm_duration_ms == 0.0

    def test_the_raw_message_is_never_written_to_redis(self) -> None:
        result = make_result()
        result._raw_result = AIMessage(content="raw")

        assert "_raw_result" not in result.to_cache_dict()

    def test_the_payload_is_json_serialisable(self) -> None:
        # It goes to Redis as JSON — a non-serialisable value would only fail
        # in production, on the write.
        assert json.loads(json.dumps(make_result().to_cache_dict()))

    def test_a_truncated_cache_payload_degrades_to_defaults(self) -> None:
        restored = InterestAnalysisResult.from_cache_dict({})

        assert restored.analyzed is False
        assert restored.extracted_interests == []
        assert restored.llm_input_tokens == 0

    def test_an_unparseable_interest_is_dropped_not_fatal(self) -> None:
        payload = make_result().to_cache_dict()
        payload["extracted_interests"].insert(0, {"action": "create", "confidence": "not-a-float"})

        restored = InterestAnalysisResult.from_cache_dict(payload)

        assert [i.topic for i in restored.extracted_interests] == ["escalade en salle"]

    def test_an_empty_topic_is_serialised_as_an_empty_string_not_null(self) -> None:
        # `ExtractedInterest(**item)` would reject a null topic on the way back.
        result = make_result(
            extracted_interests=[ExtractedInterest(action="delete", interest_id="x")]
        )

        payload = result.to_cache_dict()

        assert payload["extracted_interests"][0]["topic"] == ""
        assert payload["extracted_interests"][0]["category"] == "other"


# =============================================================================
# Conversation formatting
# =============================================================================


class TestFormatMessagesForExtraction:
    def test_labels_the_user_and_assistant_turns(self) -> None:
        text = _format_messages_for_extraction(
            [HumanMessage(content="je fais du vélo"), AIMessage(content="Depuis longtemps ?")]
        )

        assert text == "USER: je fais du vélo\nASSISTANT: Depuis longtemps ?"

    def test_drops_the_assistants_own_proactive_notifications(self) -> None:
        # A proactive push is not user-generated content: extracting an interest
        # from it would make LIA reinforce its own suggestions in a loop.
        messages = [
            AIMessage(
                content="Un article sur le trail",
                additional_kwargs={"proactive_notification": True},
            ),
            HumanMessage(content="merci"),
        ]

        text = _format_messages_for_extraction(messages)

        assert "trail" not in text
        assert text == "USER: merci"

    def test_a_long_message_is_truncated(self) -> None:
        long_text = "a" * (INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH + 100)

        text = _format_messages_for_extraction([HumanMessage(content=long_text)])

        assert text.endswith("...")
        assert len(text) == len("USER: ") + INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH + 3

    def test_a_tool_result_never_reaches_the_prompt(self) -> None:
        # It used to, under a SYSTEM label. The context window is the four
        # messages before the new user message, so right after a tool call it
        # carried a raw payload — contact rows, message bodies — into a prompt
        # whose only question is what the USER cares about. Now aligned with the
        # journals extractor, which has always skipped tool and system turns.
        text = _format_messages_for_extraction(
            [ToolMessage(content='{"emails": ["a@b.c"]}', tool_call_id="c1")]
        )

        assert text == ""

    def test_a_system_turn_never_reaches_the_prompt(self) -> None:
        assert _format_messages_for_extraction([SystemMessage(content="ctx")]) == ""

    def test_a_tool_turn_does_not_break_the_surrounding_conversation(self) -> None:
        # The real shape after a tool call: user → assistant(tool_calls) → tool
        # → user. Only the two human/assistant turns are kept, in order.
        text = _format_messages_for_extraction(
            [
                HumanMessage(content="mes mails de Marie ?"),
                AIMessage(content="", additional_kwargs={}),
                ToolMessage(content='{"emails": ["marie@ex.com"]}', tool_call_id="c1"),
                HumanMessage(content="et le vélo, tu en penses quoi ?"),
            ]
        )

        assert text == (
            "USER: mes mails de Marie ?\nASSISTANT: \nUSER: et le vélo, tu en penses quoi ?"
        )
        assert "marie@ex.com" not in text

    def test_the_two_extractors_now_agree_on_what_a_conversation_is(self) -> None:
        # One divergence between siblings is one silent behaviour difference.
        from src.domains.journals.extraction_service import (
            _format_messages_for_extraction as journals_format,
        )

        window = [
            HumanMessage(content="salut"),
            ToolMessage(content="secret", tool_call_id="c1"),
            SystemMessage(content="scaffolding"),
            AIMessage(content="bonjour"),
        ]

        assert _format_messages_for_extraction(window) == journals_format(window)

    def test_an_empty_window_yields_an_empty_block(self) -> None:
        assert _format_messages_for_extraction([]) == ""


# =============================================================================
# LLM answer parsing
# =============================================================================


def create_item(confidence: float, topic: str = "escalade") -> dict[str, Any]:
    return {
        "action": "create",
        "topic": topic,
        "category": "sports",
        "confidence": confidence,
    }


class TestParseExtractionResult:
    def test_a_confident_creation_is_kept(self) -> None:
        interests = _parse_extraction_result(json.dumps([create_item(0.9)]))

        assert [i.topic for i in interests] == ["escalade"]

    def test_the_confidence_floor_is_inclusive(self) -> None:
        # `< MIN` is the rejection test, so exactly MIN passes.
        at_floor = _parse_extraction_result(
            json.dumps([create_item(INTEREST_EXTRACTION_MIN_CONFIDENCE)])
        )

        assert len(at_floor) == 1

    def test_an_interest_just_under_the_floor_is_dropped(self) -> None:
        # Dropped silently and for good: nothing retries this extraction.
        under = _parse_extraction_result(
            json.dumps([create_item(INTEREST_EXTRACTION_MIN_CONFIDENCE - 0.01)])
        )

        assert under == []

    def test_a_creation_without_confidence_is_dropped(self) -> None:
        # `item.get("confidence", 0)` → 0 → under the floor.
        assert _parse_extraction_result(json.dumps([{"action": "create", "topic": "x"}])) == []

    @pytest.mark.parametrize("action", ["update", "delete"])
    def test_the_floor_does_not_apply_to_update_and_delete(self, action: str) -> None:
        # Maintenance actions carry no confidence; gating them would freeze the
        # interest list forever.
        payload = [
            {
                "action": action,
                "interest_id": "3f1e8c9a-1b2c-4d5e-8f90-a1b2c3d4e5f6",
                "topic": "escalade",
            }
        ]

        assert len(_parse_extraction_result(json.dumps(payload))) == 1

    def test_a_missing_action_defaults_to_create_and_is_gated(self) -> None:
        assert _parse_extraction_result(json.dumps([{"topic": "x", "confidence": 0.1}])) == []
        assert len(_parse_extraction_result(json.dumps([{"topic": "xy", "confidence": 0.9}]))) == 1

    def test_an_invalid_item_never_takes_the_valid_ones_with_it(self) -> None:
        payload = [
            {"action": "create", "topic": "a", "confidence": 0.9},  # topic too short
            create_item(0.9, "escalade en salle"),
        ]

        interests = _parse_extraction_result(json.dumps(payload))

        assert [i.topic for i in interests] == ["escalade en salle"]

    def test_a_fenced_answer_is_unwrapped(self) -> None:
        fenced = f"```json\n{json.dumps([create_item(0.9)])}\n```"

        assert len(_parse_extraction_result(fenced)) == 1

    @pytest.mark.parametrize(
        "garbage", ["", "not json", "null", '{"actions": []}', '{"topic": "x"}']
    )
    def test_anything_that_is_not_a_list_extracts_nothing(self, garbage: str) -> None:
        # This parser only accepts a bare array — unlike the journals one, which
        # also accepts {actions: [...]}.
        assert _parse_extraction_result(garbage) == []

    def test_an_empty_array_extracts_nothing(self) -> None:
        assert _parse_extraction_result("[]") == []
