"""Admission under an already durable run reservation; invoices stay in native ledgers."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.core.config import settings
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_usage import LLMBillingRecord
from src.domains.proactive_discussions.finance_repository import SpendReservation
from src.domains.proactive_discussions.llm_contracts import DiscussionPhase
from src.domains.proactive_discussions.run_types import SpendRefusal
from src.infrastructure.cache.pricing_cache import get_cached_model_price
from src.infrastructure.llm.usage_guard import enforce_usage_limit


class DiscretionaryBudgetRefused(ValueError):
    """A voluntary initiative cannot spend without a priced, bounded allowance.

    Attributes:
        reason: Why, in the run's closed vocabulary: the run reports it as is, and
            nothing ever reads the message to classify it.
    """

    def __init__(self, reason: SpendRefusal, message: str) -> None:
        super().__init__(message)
        self.reason: SpendRefusal = reason


class TariffBound(BaseModel):
    """The two per-token prices of one tariff row or time slot, finite and non-negative."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    input_unit_price: float = Field(ge=0)
    output_unit_price: float = Field(ge=0)


def upper_model_cost(config: LLMAgentConfig, input_tokens: int) -> Decimal:
    """Return the most one call can cost on the slot's configured model.

    The bound takes the dearest published time slot, counts every input token as
    uncached and cache-written, adds the whole output budget and a 25 % framing
    margin. What the call really costs is settled from its usage afterwards.

    Args:
        config: The slot's effective model configuration.
        input_tokens: The measured prompt size.

    Returns:
        The upper bound, in USD.

    Raises:
        DiscretionaryBudgetRefused: The model has no per-token tariff, or the
            tariff or the input is invalid.
    """
    price = get_cached_model_price(config.model)
    if price is None or price.pricing_unit != "per_1m_tokens":
        raise DiscretionaryBudgetRefused("tariff_unavailable", "effective model tariff unavailable")
    rates = [
        TariffBound(
            input_unit_price=price.input_unit_price, output_unit_price=price.output_unit_price
        )
    ]
    rates.extend(TariffBound.model_validate(slot) for slot in price.time_slots or ())
    incoming = max(Decimal(str(rate.input_unit_price)) for rate in rates)
    outgoing = max(Decimal(str(rate.output_unit_price)) for rate in rates)
    write = Decimal(str(price.cache_write_multiplier))
    if not write.is_finite() or write < 1 or input_tokens < 0:
        raise DiscretionaryBudgetRefused(
            "tariff_unavailable", "invalid effective model tariff or input"
        )
    # Reserve the most expensive published time slot, all input uncached and
    # cache-written, plus tokenizer/provider framing margin. Actual usage wins.
    return (
        (incoming * Decimal(input_tokens) * write + outgoing * Decimal(config.max_tokens))
        / Decimal(1_000_000)
        * Decimal("1.25")
    )


#: Issue one call's bound durably: ``(bound, committed)``, both in USD.
SpendIssuer = Callable[[Decimal, Decimal], Awaitable[None]]


def context_call_budget(*, context_only: bool) -> int:
    """The context-phase calls one run may buy.

    Args:
        context_only: Whether the run is a requested rebuild, which interprets every
            admitted fact rather than enough to speak.

    Returns:
        The configured budget of that kind of run.
    """
    if context_only:
        return settings.discussion_rebuild_context_calls
    return settings.discussion_context_calls_per_run


class NativeSpendPermit:
    """Admit each model call and billed request of one run against its reservation.

    Every admission asks the usage ceilings first, then checks that what the run has
    committed plus the call's upper bound fits the reservation, and issues it durably
    before the call is made. A finished call commits what its billing records say it
    cost, never its bound: the bound is a promise about one call, not a debt on the
    calls after it. Billed requests that are not model calls stay held at their bound
    until their receipt arrives. An unconfirmed outcome stops every later admission.
    """

    def __init__(
        self, reservation: SpendReservation, *, issue: SpendIssuer, context_calls: int | None = None
    ) -> None:
        self.reservation = reservation
        self._issue = issue
        self.context_calls = (
            context_call_budget(context_only=False) if context_calls is None else context_calls
        )
        self._counts: dict[DiscussionPhase, int] = {}
        self._records: tuple[LLMBillingRecord, ...] = ()
        self._external = Decimal(0)
        self._external_held = Decimal(0)
        self.uncertain = False

    @property
    def committed_usd(self) -> Decimal:
        """What the run has committed: its known spend and the holds nobody billed yet."""
        return self.actual_usd + self._external_held

    def _hold(self, amount: Decimal) -> None:
        if (
            self.uncertain
            or not amount.is_finite()
            or amount < 0
            or self.committed_usd + amount > self.reservation.amount
        ):
            raise DiscretionaryBudgetRefused(
                "allowance_exhausted", "discussion run allowance exhausted or unreconciled"
            )
        if datetime.now(UTC).date() != self.reservation.day:
            raise DiscretionaryBudgetRefused(
                "day_over", "discussion reservation belongs to a previous UTC day"
            )

    async def admit(self, phase: DiscussionPhase, config: LLMAgentConfig, tokens: int) -> None:
        """Admit one model call of a phase.

        Args:
            phase: The call's phase; a run may call ``context`` as often as its
                context-call budget allows and the other phases once.
            config: The slot's effective model configuration.
            tokens: The measured prompt size.

        Raises:
            UsageLimitExceededError: The account's or the instance's usage ceiling is
                reached.
            DiscretionaryBudgetRefused: The phase's call count, the reservation or its
                UTC day is exhausted, or the tariff is unusable.
        """
        await enforce_usage_limit(self.reservation.owner_id, layer="proactive_discussions")
        if self._counts.get(phase, 0) >= (self.context_calls if phase == "context" else 1):
            raise DiscretionaryBudgetRefused(
                "phase_exhausted", "discussion model phase count exhausted"
            )
        maximum = upper_model_cost(config, tokens)
        self._hold(maximum)
        await self._issue(maximum, self.committed_usd)
        self._counts[phase] = self._counts.get(phase, 0) + 1

    async def reserve_external(self, maximum: Decimal) -> None:
        """Hold and issue the upper bound of a billed request that is not a model call.

        Args:
            maximum: The most the request can cost, in USD.

        Raises:
            UsageLimitExceededError: A usage ceiling is reached.
            DiscretionaryBudgetRefused: The reservation cannot hold the amount.
        """
        await enforce_usage_limit(self.reservation.owner_id, layer="proactive_discussions")
        self._hold(maximum)
        await self._issue(maximum, self.committed_usd)
        self._external_held += maximum

    def record(self, records: tuple[LLMBillingRecord, ...], *, uncertain: bool) -> None:
        """Keep the native billing records of one model call.

        Args:
            records: The call's billing records.
            uncertain: Whether the call's outcome was not confirmed; an uncertain
                permit never publishes.
        """
        self._records += records
        self.uncertain = self.uncertain or uncertain

    def external_receipt(self, cost: Decimal, *, uncertain: bool) -> None:
        """Record what the run's billed requests that are not model calls really cost.

        The receipt covers every such request of the run, so their holds are released.

        Args:
            cost: The requests' cost, in USD.
            uncertain: Whether a request's outcome was not confirmed.

        Raises:
            ValueError: The cost is not a finite, non-negative amount.
        """
        if not cost.is_finite() or cost < 0:
            raise ValueError("invalid external discretionary receipt")
        self._external += cost
        self._external_held = Decimal(0)
        self.uncertain = self.uncertain or uncertain

    @property
    def actual_usd(self) -> Decimal:
        """What the run really spent so far: its billing records plus its receipts, in USD."""
        return sum((Decimal(str(record.cost_usd)) for record in self._records), self._external)

    @property
    def may_publish(self) -> bool:
        """Whether the run may publish: nothing uncertain, and its spend within the hold."""
        return not self.uncertain and self.actual_usd <= self.reservation.amount
