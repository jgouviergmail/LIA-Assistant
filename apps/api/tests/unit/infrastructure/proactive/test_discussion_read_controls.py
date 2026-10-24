"""A refused read restriction reads nothing, and is not paid for again before its wait (A16).

The compiler's denials must quote the person's own words; one that does not is refused
and the run reads nothing. Before this, the refusal failed the run without a deferral,
so every tick — every fifteen minutes — paid the compiler again for the same inputs and
was refused again. A refusal is now cached under the inputs' signature, waits twice the
tick interval, then twice as long at each new refusal up to the cache's own lifetime,
and the run says why it read nothing (owner decision Q4, 2026-10-22).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS
from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.contextualization.outcome import NOTHING_INTERPRETED
from src.domains.proactive_discussions.finance_permit import NativeSpendPermit
from src.domains.proactive_discussions.finance_repository import SpendReservation
from src.domains.proactive_discussions.rule_controls import (
    ControlSupport,
    RuleCache,
    RuleCompilation,
)
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import SourceKey
from src.infrastructure.proactive import discussion_context
from src.infrastructure.proactive.discussion_attention import DiscussionAuthority
from src.infrastructure.proactive.discussion_context import NativeContextStore
from src.infrastructure.proactive.discussion_control import ControlSnapshot
from src.infrastructure.proactive.discussion_llm import DiscussionLLM
from src.infrastructure.proactive.discussion_run_setup import DiscussionRunSetup
from src.infrastructure.proactive.discussion_runner import DiscussionAct, rule_cache_signature

pytestmark = pytest.mark.unit

SUPPORT = ControlSupport(id=f"memory:{uuid4()}", text="Never read my SMS.")
#: A denial quoting words the person never wrote: the compilation is refused.
INVENTED = RuleCompilation.model_validate(
    {
        "abstain": False,
        "denied": [{"source": "sms", "support_id": SUPPORT.id, "quote": "an invented rule"}],
    }
)
#: A denial quoting the person's own words.
QUOTED = RuleCompilation.model_validate(
    {
        "abstain": False,
        "denied": [{"source": "sms", "support_id": SUPPORT.id, "quote": "Never read my SMS"}],
    }
)


def _setup() -> DiscussionRunSetup:
    """A claimed, funded run on the calendar and the SMS, under one rule about the SMS."""
    claim = RunClaim(
        owner_id=uuid4(),
        run_id=uuid4(),
        fence=1,
        policy_revision=0,
        context_epoch=0,
        lease_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    return DiscussionRunSetup(
        claim=claim,
        policy=DiscussionPolicy(sources=(SourceKey.CALENDAR, SourceKey.SMS)),
        controls=ControlSnapshot(revision="r1", text="Never read my SMS.", supports=(SUPPORT,)),
        reservation=SpendReservation(
            owner_id=claim.owner_id,
            run_id=claim.run_id,
            day=datetime.now(UTC).date(),
            amount=Decimal("1"),
        ),
        language="en",
        personality="",
    )


class _Store(NativeContextStore):
    """The account's rule cache, held in memory (the claim fence is the integration suite's)."""

    def __init__(self, cache: RuleCache | None = None) -> None:
        setup = _setup()
        super().__init__(setup.claim, setup.policy, setup.controls.revision, setup.language)
        self.cache = cache

    async def read_rule_cache(self) -> RuleCache | None:
        return self.cache

    async def save_rule_cache(self, cache: RuleCache) -> None:
        self.cache = cache


class _Compiler(DiscussionLLM):
    """The context slot's rules compiler, answering one compilation; it counts its calls."""

    def __init__(self, act: DiscussionAct, compiled: RuleCompilation) -> None:
        super().__init__(
            act.setup.claim.owner_id,
            act.setup.claim.run_id,
            act.permit,
            authorize=act.authority.check,
            source="proactive",
        )
        self.compiled, self.calls = compiled, 0

    async def compile_rules(self, content: str) -> RuleCompilation:
        self.calls += 1
        return self.compiled


class _Granted(DiscussionAuthority):
    """The run's authority, granted: what it checks is the integration suite's."""

    async def check(self, *, lease_owner: str | None = None) -> None:
        return None


async def _never_issued(_amount: Decimal, _committed: Decimal) -> None:
    raise AssertionError("these runs make no paid call")


def _act(compiled: RuleCompilation, store: _Store) -> tuple[DiscussionAct, _Compiler]:
    """A run whose only stand-ins are the account's rule cache and the paid compiler."""
    setup = _setup()
    act = DiscussionAct(
        setup, NativeSpendPermit(setup.reservation, issue=_never_issued, context_calls=3)
    )
    compiler = _Compiler(act, compiled)
    act.store, act.model = store, compiler
    return act, compiler


def _first_wait() -> timedelta:
    return timedelta(
        minutes=DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS * settings.discussion_interval_minutes
    )


async def test_a_refused_compilation_reads_nothing_and_is_cached_as_a_refusal() -> None:
    store = _Store()
    act, _ = _act(INVENTED, store)
    before = datetime.now(UTC)

    assert await act.apply_read_controls() is False

    assert act.policy.sources == ()
    assert store.cache is not None and store.cache.refused and store.cache.refusals == 1
    assert store.cache.expires_at >= before + _first_wait()
    # The refused call still spent one of the run's context passes.
    assert act.context_passes == 2


async def test_the_same_refused_inputs_are_not_compiled_again_before_their_wait_ends() -> None:
    store = _Store()
    first, _ = _act(INVENTED, store)
    await first.apply_read_controls()
    again, compiler = _act(INVENTED, store)

    assert await again.apply_read_controls() is False

    assert compiler.calls == 0
    assert again.policy.sources == ()
    assert store.cache is not None and store.cache.refusals == 1


async def test_refused_again_once_the_wait_ended_the_inputs_wait_twice_as_long() -> None:
    store = _Store()
    act, compiler = _act(INVENTED, store)
    store.cache = RuleCache(
        signature=rule_cache_signature(act.setup.controls, act.policy),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        denied=(),
        abstain=True,
        refused=True,
        refusals=1,
    )
    before = datetime.now(UTC)

    assert await act.apply_read_controls() is False

    assert compiler.calls == 1
    assert store.cache.refusals == 2
    assert store.cache.expires_at >= before + 2 * _first_wait()


async def test_a_valid_compilation_after_a_refusal_reads_what_it_leaves() -> None:
    store = _Store()
    act, _ = _act(QUOTED, store)
    store.cache = RuleCache(
        signature=rule_cache_signature(act.setup.controls, act.policy),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        denied=(),
        abstain=True,
        refused=True,
        refusals=4,
    )

    assert await act.apply_read_controls() is True

    assert act.policy.sources == (SourceKey.CALENDAR,)
    assert store.cache.refused is False and store.cache.refusals == 0


async def test_the_build_says_the_rules_were_refused_and_never_starts_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    act, _ = _act(INVENTED, _Store())
    act.authority = _Granted(act.setup.claim, act.setup.controls.revision)
    monkeypatch.setattr(
        act, "_loop", AsyncMock(side_effect=AssertionError("a refused run started reading"))
    )

    result = await act.build()

    assert (result.ready, result.outcome) == (False, "rules_refused")


async def test_the_store_writes_the_shape_a_previous_release_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What reaches the JSONB column for a compilation is the pre-refusal shape."""
    setup = _setup()
    state = ContextStateRecord(user_id=setup.claim.owner_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    async def fenced(_repository: object) -> ContextStateRecord:
        return state

    monkeypatch.setattr(discussion_context, "get_db_context", session)
    monkeypatch.setattr(discussion_context, "ContextRepository", lambda _db: object())
    store = NativeContextStore(setup.claim, setup.policy, setup.controls.revision, setup.language)
    # The claim fence is the integration suite's.
    monkeypatch.setattr(store, "_fenced_state", fenced)

    await store.save_rule_cache(
        RuleCache(
            signature="inputs",
            expires_at=datetime.now(UTC),
            denied=(SourceKey.SMS,),
            abstain=False,
        )
    )

    assert state.rule_cache is not None
    assert set(state.rule_cache) == {"signature", "expires_at", "denied", "abstain"}


def test_a_rebuild_whose_rules_were_refused_interpreted_nothing() -> None:
    """A rebuild ending on it is no completed rebuild, and says why."""
    assert "rules_refused" in NOTHING_INTERPRETED
