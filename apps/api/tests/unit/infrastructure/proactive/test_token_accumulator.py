"""Adding up what several model calls cost, for one out-of-turn task.

``TokenAccumulator`` is the pattern four guides tell the author of a proactive
task to use when their task calls a model more than once
(``GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS``, ``HEARTBEAT_AUTONOME``,
``BRIEFING_DOMAIN``, ``ARCHITECTURE``). Measured 2026-09-07: it had no test at
all — a documented API whose arithmetic nobody checked, in the one module whose
whole job is arithmetic.

Its ``add_from_usage_metadata`` now delegates to
:mod:`src.infrastructure.llm.usage_metadata`, the single implementation that
replaced eight disagreeing copies. Only ONE of those eight read Anthropic's
``cache_read_input_tokens`` and clamped the subtraction at zero; the other
seven billed cached prompts at full price and could reach a negative count.
That the accumulator now inherits the right one is exactly what the tests
below pin.
"""

from __future__ import annotations

import pytest

from src.infrastructure.proactive.tracking import TokenAccumulator

pytestmark = pytest.mark.unit


class TestAddingUpSeveralCalls:
    """One task, several calls, one total."""

    def test_a_fresh_accumulator_has_nothing_to_declare(self) -> None:
        accumulator = TokenAccumulator()
        assert accumulator.get_totals() == (0, 0, 0)
        assert accumulator.total_tokens == 0
        assert accumulator.call_count == 0

    def test_two_calls_add_up(self) -> None:
        accumulator = TokenAccumulator(model_name="gpt-test")
        accumulator.add(tokens_in=100, tokens_out=20)
        accumulator.add(tokens_in=50, tokens_out=5, tokens_cache=30)

        assert accumulator.get_totals() == (150, 25, 30)
        assert accumulator.total_tokens == 175
        assert accumulator.call_count == 2

    def test_the_call_count_counts_calls_not_tokens(self) -> None:
        """A call that consumed nothing is still a call that was made."""
        accumulator = TokenAccumulator()
        accumulator.add(tokens_in=0, tokens_out=0)
        assert accumulator.call_count == 1

    def test_the_model_is_the_last_one_actually_used(self) -> None:
        """A fallback slot may answer the second call; the row must say so."""
        accumulator = TokenAccumulator(model_name="gpt-test")
        accumulator.add(tokens_in=1, tokens_out=1, model_name="claude-test")
        assert accumulator.model_name == "claude-test"

    def test_an_absent_model_never_erases_the_known_one(self) -> None:
        accumulator = TokenAccumulator(model_name="gpt-test")
        accumulator.add(tokens_in=1, tokens_out=1)
        assert accumulator.model_name == "gpt-test"


class TestReadingAProvidersUsage:
    """Delegated to the one implementation, and the delegation is what matters."""

    def test_an_openai_shaped_answer_is_read(self) -> None:
        accumulator = TokenAccumulator()
        accumulator.add_from_usage_metadata({"input_tokens": 80, "output_tokens": 12})
        assert accumulator.get_totals() == (80, 12, 0)

    def test_a_cached_prompt_is_not_billed_twice(self) -> None:
        """The defect seven of the eight copies carried.

        ``input_tokens`` INCLUDES the cached ones, so a reader that does not
        subtract them charges the full price for a prompt the provider served
        from its cache.
        """
        accumulator = TokenAccumulator()
        accumulator.add_from_usage_metadata(
            {
                "input_tokens": 1000,
                "output_tokens": 10,
                "input_token_details": {"cache_read": 800},
            }
        )
        assert accumulator.get_totals() == (200, 10, 800)

    def test_the_subtraction_never_goes_negative(self) -> None:
        """A provider reporting more cache than input must not owe us tokens."""
        accumulator = TokenAccumulator()
        accumulator.add_from_usage_metadata(
            {
                "input_tokens": 100,
                "output_tokens": 5,
                "input_token_details": {"cache_read": 400},
            }
        )
        tokens_in, _out, _cache = accumulator.get_totals()
        assert tokens_in >= 0

    def test_no_usage_at_all_records_no_call(self) -> None:
        """An empty answer is not a call worth counting."""
        accumulator = TokenAccumulator()
        accumulator.add_from_usage_metadata(None)
        accumulator.add_from_usage_metadata({})
        assert accumulator.call_count == 0
        assert accumulator.get_totals() == (0, 0, 0)

    def test_several_answers_accumulate(self) -> None:
        accumulator = TokenAccumulator()
        accumulator.add_from_usage_metadata({"input_tokens": 10, "output_tokens": 1})
        accumulator.add_from_usage_metadata({"input_tokens": 20, "output_tokens": 2})
        assert accumulator.get_totals() == (30, 3, 0)
        assert accumulator.call_count == 2


class TestHandingTheTotalsOn:
    """The dict the task returns is what eventually reaches the ledger."""

    def test_the_result_dict_carries_every_field_the_tracker_reads(self) -> None:
        accumulator = TokenAccumulator(model_name="gpt-test")
        accumulator.add(tokens_in=7, tokens_out=3, tokens_cache=1)

        assert accumulator.to_result_dict() == {
            "tokens_in": 7,
            "tokens_out": 3,
            "tokens_cache": 1,
            "model_name": "gpt-test",
        }

    def test_an_unnamed_model_is_reported_as_unknown_not_invented(self) -> None:
        assert TokenAccumulator().to_result_dict()["model_name"] is None
