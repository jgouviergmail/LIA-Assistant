"""A run starts only with room for its first call, priced on the configured context slot."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.proactive_discussions.finance_permit import upper_model_cost
from src.domains.proactive_discussions.llm_contracts import PromptBudgetExceeded
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import SourceKey
from src.infrastructure.cache.pricing_cache import CachedModelPrice
from src.infrastructure.proactive import discussion_run_setup
from src.infrastructure.proactive.discussion_llm import prepare_call

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)
POLICY = DiscussionPolicy(enabled=True, sources=(SourceKey.CALENDAR,), revision=1)


def _slot(monkeypatch, window: int) -> None:
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_llm_config_for_agent",
        lambda *args: LLM_DEFAULTS["discussion_context"],
    )
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_effective_context_window_for_slot",
        lambda slot: window,
    )


def _price(monkeypatch, price: CachedModelPrice | None) -> None:
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: price,
    )


def test_the_first_call_is_priced_like_the_permit_will_admit_it(monkeypatch):
    _slot(monkeypatch, 1_000_000)
    _price(
        monkeypatch,
        CachedModelPrice(input_unit_price=2, output_unit_price=8, cached_input_unit_price=1),
    )
    bound = discussion_run_setup.first_call_bound("Fictional rule.", POLICY, "en", now=NOW)
    assert bound > 0
    # The same call the run will make first: the context call on the rules alone.
    payload = discussion_run_setup.context_payload(
        now=NOW,
        rules="Fictional rule.",
        policy=POLICY,
        facts=(),
        knowledge=(),
        snapshots=(),
        language="en",
        research_waves=max(0, discussion_run_setup.settings.discussion_context_calls_per_run - 1),
    )
    call = prepare_call("context", payload, discussion_run_setup.ContextInterpretation)
    assert bound == upper_model_cost(call.config, call.input_tokens)


def test_an_unpriced_model_lets_the_run_state_its_own_refusal(monkeypatch):
    # Zero, so the run starts and its first admission refuses as « tariff_unavailable »
    # rather than being reported as a day without room.
    _slot(monkeypatch, 1_000_000)
    _price(monkeypatch, None)
    assert discussion_run_setup.first_call_bound("Rule.", POLICY, "en", now=NOW) == Decimal(0)


def test_rules_that_cannot_fit_the_slot_report_no_bound(monkeypatch):
    def refused(*args, **kwargs):
        raise PromptBudgetExceeded("the rules alone do not fit")

    monkeypatch.setattr(discussion_run_setup, "prepare_call", refused)
    assert discussion_run_setup.first_call_bound("Rule.", POLICY, "en", now=NOW) == Decimal(0)
