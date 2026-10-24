"""Read restrictions are resolved before opening any personal source."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS
from src.domains.proactive_discussions.rule_controls import (
    ControlSupport,
    RuleCache,
    RuleCompilation,
    RuleCompilationRefused,
    cache_compilation,
    refusal_wait,
    refused_rule_cache,
    restricted_sources,
)
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit

FIRST_WAIT = timedelta(minutes=30)
CEILING = timedelta(hours=24)


def test_owned_exact_rule_can_only_remove_an_authorized_source():
    support = ControlSupport(id=f"memory:{uuid4()}", text="Do not consult my calendar anymore.")
    result = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [
                {
                    "source": "calendar",
                    "support_id": support.id,
                    "quote": "Do not consult my calendar",
                }
            ],
        }
    )
    assert restricted_sources(result, (support,), (SourceKey.CALENDAR, SourceKey.SMS)) == (
        SourceKey.SMS,
    )


@pytest.mark.parametrize(
    "change", [{"support_id": "foreign"}, {"quote": "an invented restriction"}]
)
def test_invented_rule_proof_refuses_the_whole_run(change):
    support = ControlSupport(id=f"reply:{uuid4()}", text="Never read my SMS.")
    result = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [
                {"source": "sms", "support_id": support.id, "quote": support.text, **change}
            ],
        }
    )
    with pytest.raises(RuleCompilationRefused, match="owned exact"):
        restricted_sources(result, (support,), (SourceKey.SMS,))


def test_uncertain_rule_abstains_before_private_read():
    result = RuleCompilation(abstain=True, denied=())
    assert restricted_sources(result, (), (SourceKey.CALENDAR,)) == ()


@pytest.mark.parametrize(
    ("refusals", "wait"),
    [
        (1, FIRST_WAIT),
        (2, 2 * FIRST_WAIT),
        (3, 4 * FIRST_WAIT),
        (6, 32 * FIRST_WAIT),  # 16 h, still under the ceiling
        (7, CEILING),  # 32 h, held to the ceiling
        (10_000, CEILING),  # counted for months: never an overflow
    ],
)
def test_each_refusal_of_the_same_inputs_waits_twice_as_long_up_to_the_ceiling(refusals, wait):
    assert refusal_wait(refusals, first=FIRST_WAIT, ceiling=CEILING) == wait


def test_a_refused_compilation_is_cached_as_a_refusal_that_reads_nothing():
    """Nothing is readable under a refusal, whichever of its fields a reader trusts."""
    now = datetime.now(UTC)

    cache = refused_rule_cache("inputs", None, now=now, first=FIRST_WAIT, ceiling=CEILING)

    assert (cache.refused, cache.refusals, cache.expires_at) == (True, 1, now + FIRST_WAIT)
    assert cache.abstain is True and cache.denied == ()


def test_the_same_inputs_refused_again_wait_longer_even_once_the_wait_ended():
    first_at = datetime.now(UTC)
    first = refused_rule_cache("inputs", None, now=first_at, first=FIRST_WAIT, ceiling=CEILING)
    again_at = first.expires_at  # the wait is over: the compiler was asked again

    again = refused_rule_cache("inputs", first, now=again_at, first=FIRST_WAIT, ceiling=CEILING)

    assert (again.refusals, again.expires_at) == (2, again_at + 2 * FIRST_WAIT)


@pytest.mark.parametrize(
    "previous",
    [
        # The person's rules or sources changed: new inputs, a first refusal.
        {"signature": "former inputs", "refused": True, "refusals": 5},
        # The same inputs compiled once, then refused: nothing was refused before.
        {"signature": "inputs", "refused": False, "refusals": 0},
    ],
)
def test_a_first_refusal_of_these_inputs_waits_the_first_wait(previous):
    now = datetime.now(UTC)
    stored = RuleCache(expires_at=now, denied=(), abstain=False, **previous)

    cache = refused_rule_cache("inputs", stored, now=now, first=FIRST_WAIT, ceiling=CEILING)

    assert (cache.refusals, cache.expires_at) == (1, now + FIRST_WAIT)


def test_a_compilation_is_cached_with_the_sources_it_denies_for_the_cache_lifetime():
    support = ControlSupport(id=f"memory:{uuid4()}", text="Never read my SMS.")
    compiled = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [{"source": "sms", "support_id": support.id, "quote": "read my SMS"}],
        }
    )
    now = datetime.now(UTC)

    cache = cache_compilation(
        compiled,
        (support,),
        (SourceKey.CALENDAR, SourceKey.SMS),
        signature="inputs",
        previous=None,
        now=now,
    )

    assert (cache.refused, cache.denied, cache.abstain) == (False, (SourceKey.SMS,), False)
    assert cache.expires_at == now + timedelta(hours=settings.discussion_rule_cache_hours)


def test_a_refused_compilation_first_waits_the_declared_tick_intervals():
    support = ControlSupport(id=f"memory:{uuid4()}", text="Never read my SMS.")
    invented = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [{"source": "sms", "support_id": support.id, "quote": "invented"}],
        }
    )
    now = datetime.now(UTC)

    cache = cache_compilation(
        invented, (support,), (SourceKey.SMS,), signature="inputs", previous=None, now=now
    )

    intervals = DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS
    assert cache.refused and cache.refusals == 1
    assert cache.expires_at == now + timedelta(
        minutes=intervals * settings.discussion_interval_minutes
    )


def test_a_compilation_is_stored_in_the_shape_a_previous_release_reads():
    """The values forbid unknown fields: a stored ``refused: false`` would have made a
    rolled-back release refuse every account's cache, so a compilation omits both."""
    cache = RuleCache(
        signature="inputs", expires_at=datetime.now(UTC), denied=(SourceKey.SMS,), abstain=False
    )

    assert set(cache.stored()) == {"signature", "expires_at", "denied", "abstain"}
    assert RuleCache.model_validate(cache.stored()) == cache


def test_a_refusal_is_stored_with_its_count_and_reads_back_whole():
    refusal = refused_rule_cache(
        "inputs", None, now=datetime.now(UTC), first=FIRST_WAIT, ceiling=CEILING
    )

    stored = refusal.stored()

    assert (stored["refused"], stored["refusals"]) == (True, 1)
    assert RuleCache.model_validate(stored) == refusal


def test_a_cache_stored_before_refusals_were_kept_still_reads_as_a_compilation():
    stored = {
        "signature": "inputs",
        "expires_at": datetime.now(UTC).isoformat(),
        "denied": ["sms"],
        "abstain": False,
    }

    cache = RuleCache.model_validate(stored)

    assert (cache.refused, cache.refusals, cache.denied) == (False, 0, (SourceKey.SMS,))
