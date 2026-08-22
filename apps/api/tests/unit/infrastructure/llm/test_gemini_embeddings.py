"""Contract of the Gemini embedding adapter: token estimation and cost.

Two properties are load-bearing and were previously unguarded:

- **The token estimate feeds the billing counters.** ``len(text) // 4`` assumes
  a space-separated script. Measured against the real Gemini tokenizer on the
  six supported languages (2026-08-22): it under-counts Chinese by 41-57% and
  the whole corpus by 15%. A script-aware estimate lands at +1% overall while
  leaving Latin scripts bit-identical.
- **The price is administered, not hard-coded.** ``llm_model_pricing`` already
  carries every embedding model, and the DB billing has always read it. Only
  the Prometheus counter and the log lines used a frozen 0.15/1M constant,
  which went wrong the moment the configured model or the tariff changed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.infrastructure.llm import gemini_embeddings as ge

_MODULE = "src.infrastructure.llm.gemini_embeddings"


@pytest.mark.unit
class TestEstimateTokens:
    """Script-aware estimation, with Latin behaviour frozen."""

    @pytest.mark.parametrize(
        "text",
        [
            "Comment connecter mon agenda Google ?",
            "How do I add an MCP server?",
            "Wie verbinde ich meinen Kalender?",
            "¿Cómo conecto mi calendario?",
            "Come collego il mio calendario?",
        ],
        ids=["fr", "en", "de", "es", "it"],
    )
    def test_space_separated_scripts_keep_the_historic_estimate(self, text: str) -> None:
        """No CJK character means the formula must be exactly the old one."""
        assert ge._estimate_tokens([text]) == len(text) // 4 + 1

    def test_chinese_counts_about_one_token_per_character(self) -> None:
        """`len // 4` gave 3 tokens for a 12-character sentence worth ~12."""
        text = "如何连接我的谷歌日历"

        estimate = ge._estimate_tokens([text])

        assert estimate >= len(text)
        assert estimate < 2 * len(text)

    def test_mixed_script_counts_each_part_on_its_own_scale(self) -> None:
        cjk = "支持语言"
        latin = "LIA supports six languages in total"
        mixed = f"{latin} {cjk}"

        estimate = ge._estimate_tokens([mixed])

        assert estimate == pytest.approx(len(cjk) + (len(mixed) - len(cjk)) // 4 + 1, abs=1)

    @pytest.mark.parametrize(
        "text", ["カレンダー", "일정 관리", "如何连接"], ids=["kana", "hangul", "han"]
    )
    def test_every_space_less_script_is_covered(self, text: str) -> None:
        assert ge._estimate_tokens([text]) > len(text) // 4 + 1

    def test_batches_sum_over_every_text(self) -> None:
        texts = ["premier texte", "second texte", "如何连接"]

        assert ge._estimate_tokens(texts) == sum(ge._estimate_tokens([t]) for t in texts)

    def test_empty_batch_costs_nothing(self) -> None:
        assert ge._estimate_tokens([]) == 0

    def test_empty_string_never_estimates_zero(self) -> None:
        """A request was still made; charging it 0 tokens would hide the call."""
        assert ge._estimate_tokens([""]) >= 1


@pytest.mark.unit
class TestEmbeddingCost:
    """Cost comes from the administered pricing table."""

    def test_cost_is_read_from_the_pricing_cache_for_the_configured_model(self) -> None:
        with patch(f"{_MODULE}.get_cached_cost_usd_eur", return_value=(0.25, 0.23)) as priced:
            cost = ge._embedding_cost_usd("gemini-embedding-001", 1_000_000)

        assert cost == 0.25
        priced.assert_called_once_with("gemini-embedding-001", 1_000_000, 0)

    def test_a_different_model_gets_that_model_s_price(self) -> None:
        """The frozen constant made every model cost 0.15/1M forever."""
        prices = {"gemini-embedding-001": (0.15, 0.14), "gemini-embedding-2": (0.20, 0.18)}

        with patch(f"{_MODULE}.get_cached_cost_usd_eur", side_effect=lambda m, *_a: prices[m]):
            assert ge._embedding_cost_usd("gemini-embedding-001", 1) == 0.15
            assert ge._embedding_cost_usd("gemini-embedding-2", 1) == 0.20

    def test_a_cold_pricing_cache_degrades_to_zero_without_raising(self) -> None:
        """Embedding must never fail because a metric could not be priced."""
        with patch(f"{_MODULE}.get_cached_cost_usd_eur", return_value=(0.0, 0.0)):
            assert ge._embedding_cost_usd("gemini-embedding-001", 1_000) == 0.0

    def test_a_pricing_failure_is_swallowed_rather_than_breaking_the_call(self) -> None:
        with patch(f"{_MODULE}.get_cached_cost_usd_eur", side_effect=RuntimeError("cache down")):
            assert ge._embedding_cost_usd("gemini-embedding-001", 1_000) == 0.0

    def test_no_frozen_price_constant_remains(self) -> None:
        """A hard-coded tariff next to an administered one drifts silently."""
        assert not hasattr(ge, "GEMINI_EMBEDDING_COST_PER_TOKEN_USD")


@pytest.mark.unit
class TestModelName:
    """The pricing table is keyed without the ``models/`` prefix."""

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("models/gemini-embedding-001", "gemini-embedding-001"),
            ("gemini-embedding-001", "gemini-embedding-001"),
        ],
    )
    def test_prefix_is_stripped_for_metrics_and_pricing(
        self, configured: str, expected: str
    ) -> None:
        with patch(f"{_MODULE}.GoogleGenerativeAIEmbeddings"):
            client = ge.GeminiRetrievalEmbeddings(model=configured, google_api_key="k")

        assert client.model_name == expected


@pytest.mark.unit
class TestPricingHappensOncePerCall:
    """The batch is priced once, not once per consumer of the number.

    Metrics and persistence both need the cost. Computing it twice is wasted
    work on a path that runs on every chat turn, and — worse — two independent
    computations of one number is the drift risk this lot removed elsewhere.
    """

    def test_a_sync_embed_prices_the_batch_exactly_once(self) -> None:
        with patch(f"{_MODULE}.GoogleGenerativeAIEmbeddings") as client_cls:
            client_cls.return_value.embed_query.return_value = [0.1, 0.2]
            client = ge.GeminiRetrievalEmbeddings(google_api_key="k")

            with (
                patch(f"{_MODULE}.get_cached_cost_usd_eur", return_value=(0.1, 0.09)) as priced,
                patch.object(client, "_persist_cost_sync"),
            ):
                client.embed_query("bonjour")

        assert priced.call_count == 1

    def test_the_persisted_cost_is_the_one_the_metric_recorded(self) -> None:
        with patch(f"{_MODULE}.GoogleGenerativeAIEmbeddings") as client_cls:
            client_cls.return_value.embed_query.return_value = [0.1, 0.2]
            client = ge.GeminiRetrievalEmbeddings(google_api_key="k")

            with (
                patch(f"{_MODULE}.get_cached_cost_usd_eur", return_value=(0.42, 0.39)),
                patch.object(client, "_persist_cost_sync") as persisted,
            ):
                client.embed_query("bonjour")

        assert persisted.call_args.args[1] == 0.42
