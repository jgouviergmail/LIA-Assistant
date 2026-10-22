"""A durable hold bounds the whole run; missing tariffs and hidden extra calls fail closed."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from src.core.config import settings
from src.core.llm_usage import LLMBillingRecord
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.proactive_discussions.finance_permit import (
    DiscretionaryBudgetRefused,
    NativeSpendPermit,
    context_call_budget,
    upper_model_cost,
)
from src.domains.proactive_discussions.finance_repository import SpendReservation
from src.infrastructure.cache.pricing_cache import CachedModelPrice

pytestmark = pytest.mark.unit


def permit(amount="1", *, issue=None):
    return NativeSpendPermit(
        SpendReservation(
            owner_id=UUID(int=1),
            run_id=UUID(int=2),
            day=datetime.now(UTC).date(),
            amount=Decimal(amount),
        ),
        issue=issue or _allowed,
    )


def priced(monkeypatch):
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.enforce_usage_limit", _allowed
    )
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: CachedModelPrice(
            input_unit_price=1, output_unit_price=1, cached_input_unit_price=1
        ),
    )


def bill(cost: Decimal) -> LLMBillingRecord:
    return LLMBillingRecord(
        model_name="fictional",
        started_at=0.0,
        tokens_in=1,
        tokens_out=1,
        tokens_cache=0,
        cost_usd=float(cost),
        cost_eur=float(cost),
        usd_to_eur_rate=1.0,
    )


async def test_unknown_tariff_and_no_room_refuse_before_model_admission(monkeypatch):
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.enforce_usage_limit", _allowed
    )
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: None,
    )
    with pytest.raises(DiscretionaryBudgetRefused):
        await permit().admit("decision", LLM_DEFAULTS["discussion_decision"], 500)
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: CachedModelPrice(
            input_unit_price=10, output_unit_price=10, cached_input_unit_price=10
        ),
    )
    with pytest.raises(DiscretionaryBudgetRefused):
        await permit("0.00001").admit("decision", LLM_DEFAULTS["discussion_decision"], 500)


async def _allowed(*args, **kwargs):
    return None


async def test_one_decision_and_unknown_usage_cannot_buy_another_call(monkeypatch):
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.enforce_usage_limit", _allowed
    )
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: CachedModelPrice(
            input_unit_price=1, output_unit_price=1, cached_input_unit_price=1
        ),
    )
    current = permit()
    await current.admit("decision", LLM_DEFAULTS["discussion_decision"], 500)
    with pytest.raises(DiscretionaryBudgetRefused):
        await current.admit("decision", LLM_DEFAULTS["discussion_decision"], 500)
    current.record((), uncertain=True)
    with pytest.raises(DiscretionaryBudgetRefused):
        await current.admit("message", LLM_DEFAULTS["discussion_message"], 500)
    assert not current.may_publish


async def test_a_finished_call_commits_its_bill_never_its_bound(monkeypatch):
    # Before 2026-10-21 every admitted bound stayed committed, so three context calls
    # needed three bounds of room though each cost a fraction of its own.
    priced(monkeypatch)
    config = LLM_DEFAULTS["discussion_context"]
    bound = upper_model_cost(config, 500)
    calls = settings.discussion_context_calls_per_run
    spent = bound / 100
    issued: list[tuple[Decimal, Decimal]] = []

    async def issue(amount, committed):
        issued.append((amount, committed))

    current = permit(str(bound + spent * calls), issue=issue)
    for _ in range(calls):
        await current.admit("context", config, 500)
        current.record((bill(spent),), uncertain=False)
    # Each bound was issued with what the run had really committed before it.
    assert issued == [(bound, spent * index) for index in range(calls)]
    with pytest.raises(DiscretionaryBudgetRefused) as refused:
        await current.admit("context", config, 500)
    assert refused.value.reason == "phase_exhausted"
    assert current.may_publish


async def test_a_billed_request_stays_held_until_its_receipt(monkeypatch):
    priced(monkeypatch)
    config = LLM_DEFAULTS["discussion_decision"]
    bound = upper_model_cost(config, 500)
    current = permit(str(bound * Decimal("1.5")))
    await current.reserve_external(bound)
    assert current.committed_usd == bound
    with pytest.raises(DiscretionaryBudgetRefused) as refused:
        await current.admit("decision", config, 500)
    assert refused.value.reason == "allowance_exhausted"
    current.external_receipt(Decimal(0), uncertain=False)
    assert current.committed_usd == 0
    await current.admit("decision", config, 500)


async def test_a_refusal_names_its_cause(monkeypatch):
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.enforce_usage_limit", _allowed
    )
    monkeypatch.setattr(
        "src.domains.proactive_discussions.finance_permit.get_cached_model_price",
        lambda model: None,
    )
    with pytest.raises(DiscretionaryBudgetRefused) as refused:
        await permit().admit("decision", LLM_DEFAULTS["discussion_decision"], 500)
    assert refused.value.reason == "tariff_unavailable"


def test_a_rebuild_has_its_own_context_call_budget():
    assert context_call_budget(context_only=True) == settings.discussion_rebuild_context_calls
    assert context_call_budget(context_only=False) == settings.discussion_context_calls_per_run
    assert permit().context_calls == settings.discussion_context_calls_per_run


async def test_the_permit_admits_exactly_its_context_call_budget(monkeypatch):
    priced(monkeypatch)
    config = LLM_DEFAULTS["discussion_context"]
    budget = settings.discussion_rebuild_context_calls
    current = NativeSpendPermit(
        SpendReservation(
            owner_id=UUID(int=1),
            run_id=UUID(int=2),
            day=datetime.now(UTC).date(),
            amount=upper_model_cost(config, 500) * (budget + 1),
        ),
        issue=_allowed,
        context_calls=budget,
    )
    for _ in range(budget):
        await current.admit("context", config, 500)
    with pytest.raises(DiscretionaryBudgetRefused) as refused:
        await current.admit("context", config, 500)
    assert refused.value.reason == "phase_exhausted"
