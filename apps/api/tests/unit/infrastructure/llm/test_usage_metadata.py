"""The two spellings of one number, and the clamp six copies were missing.

Written from the seven implementations this module replaced. Each case below
is a real disagreement between them, not an invented edge: the Anthropic
spelling was read by exactly one, and the clamp by exactly the same one.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.usage_metadata import (
    UsageTokens,
    tokens_from_response,
    tokens_from_usage_metadata,
)

pytestmark = pytest.mark.unit


class TestBothProviderSpellings:
    """OpenAI nests the cache count; Anthropic publishes it at the top."""

    def test_openai_shape_subtracts_the_nested_cache(self) -> None:
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_token_details": {"cache_read": 400},
        }
        assert tokens_from_usage_metadata(usage) == UsageTokens(600, 200, 400)

    def test_anthropic_shape_subtracts_the_top_level_cache(self) -> None:
        """The case six of the seven copies got wrong.

        On an Anthropic model they read no cache at all, so 1000 prompt tokens
        were priced at full rate when 400 of them were served from cache.
        """
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 400,
        }
        assert tokens_from_usage_metadata(usage) == UsageTokens(600, 200, 400)

    def test_a_provider_reporting_neither_cache_field_is_not_a_failure(self) -> None:
        usage = {"input_tokens": 300, "output_tokens": 50}
        assert tokens_from_usage_metadata(usage) == UsageTokens(300, 50, 0)


class TestCacheWrites:
    """A prompt-cache write is counted apart; its TARIFF decides what it costs (ADR-306).

    Two shapes reach the reader for one Claude call. Through the path LIA runs,
    langchain-anthropic reports the generic ``cache_creation`` alone (measured
    on Sonnet 5 through ``get_llm``, 2026-09-23: 5,075 written tokens, no TTL
    keys); when the response carries the TTL breakdown it fills
    ``ephemeral_*_input_tokens`` and sets ``cache_creation`` to 0. Either way
    ``input_tokens`` includes the written tokens.
    """

    def test_the_shape_of_the_path_lia_runs(self) -> None:
        """Copied from the runtime probe: the generic key, and nothing else."""
        usage = {
            "input_tokens": 5147,
            "output_tokens": 5,
            "total_tokens": 5152,
            "input_token_details": {"cache_creation": 5075, "cache_read": 0},
        }
        assert tokens_from_usage_metadata(usage) == UsageTokens(5147, 5, 0, 5075)

    def test_the_anthropic_ttl_breakdown_is_the_write_count(self) -> None:
        usage = {
            "input_tokens": 6000,
            "output_tokens": 50,
            "input_token_details": {
                "cache_read": 0,
                "cache_creation": 0,
                "ephemeral_5m_input_tokens": 5074,
                "ephemeral_1h_input_tokens": 0,
            },
        }
        tokens = tokens_from_usage_metadata(usage)
        assert tokens == UsageTokens(6000, 50, 0, 5074)
        # A write is still a prompt token: its input price is inside ``prompt``.
        assert tokens.cache_write <= tokens.prompt

    def test_both_ttls_are_written_tokens(self) -> None:
        usage = {
            "input_tokens": 900,
            "output_tokens": 1,
            "input_token_details": {
                "ephemeral_5m_input_tokens": 300,
                "ephemeral_1h_input_tokens": 200,
            },
        }
        assert tokens_from_usage_metadata(usage).cache_write == 500

    def test_a_read_and_a_write_in_one_call(self) -> None:
        usage = {
            "input_tokens": 10_000,
            "output_tokens": 40,
            "input_token_details": {
                "cache_read": 8_000,
                "cache_creation": 0,
                "ephemeral_5m_input_tokens": 1_500,
                "ephemeral_1h_input_tokens": 0,
            },
        }
        assert tokens_from_usage_metadata(usage) == UsageTokens(2_000, 40, 8_000, 1_500)

    def test_the_generic_key_counts_whoever_reports_it(self) -> None:
        """langchain-openai maps OpenAI's ``cache_write_tokens`` to the same key.
        The COUNT is the same fact on every provider; whether a write costs
        more than an input token is the tariff's to say (``CachedModelPrice``)."""
        usage = {
            "input_tokens": 1000,
            "output_tokens": 10,
            "input_token_details": {"cache_read": 0, "cache_creation": 1000},
        }
        assert tokens_from_usage_metadata(usage).cache_write == 1000

    def test_the_two_shapes_never_add_up_twice(self) -> None:
        """langchain-anthropic zeroes the generic key when it fills the breakdown."""
        usage = {
            "input_tokens": 900,
            "output_tokens": 1,
            "input_token_details": {"cache_creation": 0, "ephemeral_5m_input_tokens": 600},
        }
        assert tokens_from_usage_metadata(usage).cache_write == 600

    def test_writes_are_summed_across_models_by_the_callback_reader(self) -> None:
        from src.infrastructure.llm.usage_metadata import tokens_from_callback

        class _Handler:
            usage_metadata = {
                "claude-opus-5": {
                    "input_tokens": 3000,
                    "output_tokens": 5,
                    "input_token_details": {"ephemeral_5m_input_tokens": 2500},
                },
                "claude-sonnet-5": {
                    "input_tokens": 1000,
                    "output_tokens": 5,
                    "input_token_details": {"ephemeral_5m_input_tokens": 400},
                },
            }

        assert tokens_from_callback(_Handler()).cache_write == 2900


class TestTheClamp:
    """A count that flows into a price is never negative."""

    def test_an_inconsistent_report_clamps_at_zero(self) -> None:
        """Cache larger than the reported input must not go below zero.

        Observed shape rather than a theoretical one: providers have reported
        a cache count that excludes itself from ``input_tokens``, which under
        the un-clamped copies produced a negative prompt count feeding a
        multiplication by a per-token price.
        """
        usage = {
            "input_tokens": 100,
            "output_tokens": 10,
            "input_token_details": {"cache_read": 900},
        }
        result = tokens_from_usage_metadata(usage)
        assert result.prompt == 0
        assert result.cached == 900


class TestDefensiveReading:
    """Measuring a call must never be able to break it."""

    @pytest.mark.parametrize("usage", [None, {}, {"input_tokens": None}])
    def test_nothing_usable_reads_as_no_usage(self, usage: dict | None) -> None:
        assert tokens_from_usage_metadata(usage).is_empty

    def test_a_non_numeric_count_reads_as_zero(self) -> None:
        usage = {"input_tokens": "many", "output_tokens": 5}
        assert tokens_from_usage_metadata(usage) == UsageTokens(0, 5, 0)

    def test_a_malformed_details_block_is_ignored(self) -> None:
        usage = {"input_tokens": 10, "output_tokens": 2, "input_token_details": "nope"}
        assert tokens_from_usage_metadata(usage) == UsageTokens(10, 2, 0)


class TestReadingFromAResponse:
    """The common call site takes the message, not the mapping."""

    def test_a_message_carrying_usage_is_read(self) -> None:
        class _Message:
            usage_metadata = {"input_tokens": 8, "output_tokens": 3}

        assert tokens_from_response(_Message()) == UsageTokens(8, 3, 0)

    def test_an_object_without_usage_reads_as_empty(self) -> None:
        assert tokens_from_response(object()).is_empty

    def test_a_non_mapping_usage_attribute_reads_as_empty(self) -> None:
        class _Message:
            usage_metadata = "unexpected"

        assert tokens_from_response(_Message()).is_empty


class TestReadingTheModelName:
    """One spelling question, one answer — not three fallbacks."""

    def test_model_name_attribute_wins(self) -> None:
        from src.infrastructure.llm.usage_metadata import model_name_of

        class _Client:
            model_name = "gpt-5.6-luna"
            model = "ignored"

        assert model_name_of(_Client()) == "gpt-5.6-luna"

    def test_model_attribute_is_the_fallback(self) -> None:
        from src.infrastructure.llm.usage_metadata import model_name_of

        class _Client:
            model = "claude-opus-5"

        assert model_name_of(_Client()) == "claude-opus-5"

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_an_unusable_value_reads_as_no_name(self, value: object) -> None:
        """None, never ``""`` or ``"unknown"``: a price lookup must be able to
        tell "no model was named" from "a model called unknown"."""
        from src.infrastructure.llm.usage_metadata import model_name_of

        client = type("_Client", (), {"model_name": value, "model": value})()
        assert model_name_of(client) is None


class TestReadingTheUsageCallback:
    """The handler keys by model; one call may report more than one."""

    def test_entries_are_summed_across_models(self) -> None:
        from src.infrastructure.llm.usage_metadata import UsageTokens, tokens_from_callback

        class _Handler:
            usage_metadata = {
                "gpt-5.6-luna": {"input_tokens": 100, "output_tokens": 10},
                "fallback-model": {"input_tokens": 40, "output_tokens": 4},
            }

        assert tokens_from_callback(_Handler()) == UsageTokens(140, 14, 0)

    def test_the_cache_is_subtracted_here_too(self) -> None:
        """The variant this replaced ignored the cache and over-billed."""
        from src.infrastructure.llm.usage_metadata import UsageTokens, tokens_from_callback

        class _Handler:
            usage_metadata = {
                "m": {
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "input_token_details": {"cache_read": 700},
                }
            }

        assert tokens_from_callback(_Handler()) == UsageTokens(300, 20, 700)

    def test_a_handler_that_collected_nothing_reads_as_empty(self) -> None:
        from src.infrastructure.llm.usage_metadata import tokens_from_callback

        class _Handler:
            usage_metadata: dict = {}

        assert tokens_from_callback(_Handler()).is_empty
        assert tokens_from_callback(object()).is_empty
