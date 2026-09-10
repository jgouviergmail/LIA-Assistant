"""What the debug panel is told about each model call (B8, lot 7.1).

`TokenUsageRecord` has carried the parameters LIA actually SENT since ADR-263
lot 7 — the provider, the sampling settings, the output cap, the reasoning
intent and a digest of the lot — and it carries the call's VERDICT (`status`,
`failure_kind`) and the configured SLOT it ran for (`llm_type`).

`get_llm_calls_breakdown` published none of them, so the panel showed a model
name and a price and nothing about the request behind them. Three questions a
person debugging a live exchange asks, and could not answer:

- **which provider actually served this?** A model name does not say: the same
  tag runs on Ollama locally and in the cloud;
- **did this call SUCCEED?** A failed call and a successful one rendered
  identically, both with their tokens billed;
- **what was asked of it?** A turn that answers differently from yesterday is
  usually a parameter, and the parameter was invisible.

Nothing new is collected here: the fields exist, they are read.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from src.domains.chat.service import TrackingContext
from src.domains.chat.tracking_records import TokenUsageRecord

BASE = {
    "node_name": "router",
    "model_name": "gpt-5-mini",
    "prompt_tokens": 100,
    "completion_tokens": 20,
    "cached_tokens": 0,
    "cost_usd": 0.01,
    "cost_eur": 0.009,
    "usd_to_eur_rate": Decimal("0.92"),
}


def _context(records: list[TokenUsageRecord]) -> TrackingContext:
    """A context whose run records are exactly what the test handed it."""
    ctx = TrackingContext(
        run_id=str(uuid4()),
        user_id=uuid4(),
        session_id="s",
        conversation_id=uuid4(),
        auto_commit=False,
    )
    ctx._context_token = None
    ctx._get_all_run_records = lambda: records  # type: ignore[method-assign]
    return ctx


class TestTheBreakdownCarriesWhatWasActuallySent:
    def test_it_names_the_provider_behind_the_model(self) -> None:
        # A model name does not say who served it: the same tag runs locally
        # and in the cloud, and they do not behave the same.
        call = _context([TokenUsageRecord(**BASE, provider="ollama")]).get_llm_calls_breakdown()[0]

        assert call["provider"] == "ollama"

    def test_it_names_the_configured_slot(self) -> None:
        # `node_name` is the GRAPH node; `llm_type` is the slot an operator
        # configured. Reading one for the other sent people to the wrong row of
        # the admin screen.
        call = _context(
            [TokenUsageRecord(**BASE, llm_type="router_classification")]
        ).get_llm_calls_breakdown()[0]

        assert call["llm_type"] == "router_classification"

    def test_it_carries_the_sampling_settings(self) -> None:
        call = _context(
            [TokenUsageRecord(**BASE, temperature=0.2, top_p=0.9, max_output_tokens=512)]
        ).get_llm_calls_breakdown()[0]

        assert call["temperature"] == 0.2
        assert call["top_p"] == 0.9
        assert call["max_output_tokens"] == 512

    def test_it_carries_the_reasoning_intent(self) -> None:
        call = _context(
            [TokenUsageRecord(**BASE, reasoning_level="high", reasoning_budget_tokens=4096)]
        ).get_llm_calls_breakdown()[0]

        assert call["reasoning_level"] == "high"
        assert call["reasoning_budget_tokens"] == 4096

    def test_it_carries_the_digest_that_correlates_two_calls(self) -> None:
        # The handle that says « these two calls were made the same way » — and
        # the one to quote when reporting a behaviour change.
        call = _context(
            [TokenUsageRecord(**BASE, params_digest="ab12cd34")]
        ).get_llm_calls_breakdown()[0]

        assert call["params_digest"] == "ab12cd34"


class TestTheBreakdownCarriesTheVerdict:
    def test_a_failed_call_says_so(self) -> None:
        call = _context(
            [TokenUsageRecord(**BASE, status="error", failure_kind="rate_limit")]
        ).get_llm_calls_breakdown()[0]

        assert call["status"] == "error"
        assert call["failure_kind"] == "rate_limit"

    def test_a_successful_call_carries_no_failure(self) -> None:
        call = _context([TokenUsageRecord(**BASE, status="success")]).get_llm_calls_breakdown()[0]

        assert call["status"] == "success"
        assert call["failure_kind"] is None


class TestNothingIsInvented:
    def test_an_unobserved_field_stays_absent_rather_than_defaulted(self) -> None:
        # A default temperature printed on a call that never carried one is a
        # fact nobody measured — the panel would name a value the provider
        # never saw.
        call = _context([TokenUsageRecord(**BASE)]).get_llm_calls_breakdown()[0]

        for key in (
            "provider",
            "llm_type",
            "temperature",
            "top_p",
            "max_output_tokens",
            "reasoning_level",
            "reasoning_budget_tokens",
            "params_digest",
            "status",
            "failure_kind",
        ):
            assert call[key] is None, key

    def test_the_figures_the_panel_already_showed_are_unchanged(self) -> None:
        # This enrichment ADDS keys; a characterization guard on the ones the
        # panel already reads.
        call = _context(
            [TokenUsageRecord(**BASE, duration_ms=120.5, call_type="chat", sequence=3)]
        ).get_llm_calls_breakdown()[0]

        assert call["node_name"] == "router"
        assert call["model_name"] == "gpt-5-mini"
        assert call["tokens_in"] == 100
        assert call["tokens_out"] == 20
        assert call["tokens_cache"] == 0
        assert call["cost_eur"] == 0.009
        assert call["duration_ms"] == 120.5
        assert call["call_type"] == "chat"
        assert call["sequence"] == 3

    def test_every_call_of_the_run_is_described_the_same_way(self) -> None:
        # A key present on one call and absent on another makes the panel's
        # rows disagree about what a row IS.
        calls = _context(
            [
                TokenUsageRecord(**BASE, provider="openai"),
                TokenUsageRecord(**{**BASE, "node_name": "response"}),
            ]
        ).get_llm_calls_breakdown()

        assert set(calls[0]) == set(calls[1])
