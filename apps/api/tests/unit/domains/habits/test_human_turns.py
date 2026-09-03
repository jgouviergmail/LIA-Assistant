"""One predicate for a human turn, pinned to the product vocabulary.

The rhythm repository and the recurrence-ledger seed must read the SAME
definition (two wordings of "human" is how the seed came to rebuild LIA's
own scheduled routines as the user's recurrences, measured 2026-09-03).
"""

from __future__ import annotations

import pytest

from src.domains.habits.human_turns import (
    HUMAN_OUTCOME_CHANNELS,
    HUMAN_OUTCOME_PREDICATE_SQL,
    HUMAN_OUTCOME_RESULT_TYPES,
)
from src.domains.product.constants import CHANNELS, RESULT_TYPES, derive_channel, derive_result_type

pytestmark = pytest.mark.unit


def test_vocabulary_is_a_subset_of_the_product_domain() -> None:
    assert HUMAN_OUTCOME_CHANNELS <= CHANNELS
    assert HUMAN_OUTCOME_RESULT_TYPES <= RESULT_TYPES


@pytest.mark.parametrize("channel", ["scheduler", "web_showroom", "unknown"])
def test_non_human_channels_are_excluded(channel: str) -> None:
    assert channel not in HUMAN_OUTCOME_CHANNELS
    assert f"'{channel}'" not in HUMAN_OUTCOME_PREDICATE_SQL


def test_automation_runs_are_excluded() -> None:
    assert "automation_run" not in HUMAN_OUTCOME_RESULT_TYPES
    assert "'automation_run'" not in HUMAN_OUTCOME_PREDICATE_SQL


def test_scheduled_action_sessions_never_qualify() -> None:
    """The scheduler's own session prefix derives to a non-human channel and
    result type — the metronome class proven on prod 2026-08-05 and 2026-09-03."""
    channel = derive_channel("scheduled_action_abc")
    assert channel not in HUMAN_OUTCOME_CHANNELS
    assert derive_result_type("action", channel) not in HUMAN_OUTCOME_RESULT_TYPES


@pytest.mark.parametrize("session_id", ["session_abc", "channel_telegram_1", "0ad6c5be-1"])
def test_typed_sessions_qualify(session_id: str) -> None:
    channel = derive_channel(session_id)
    assert channel in HUMAN_OUTCOME_CHANNELS
    assert derive_result_type("action", channel) in HUMAN_OUTCOME_RESULT_TYPES
    assert derive_result_type("conversation", channel) in HUMAN_OUTCOME_RESULT_TYPES


def test_predicate_is_a_self_contained_sql_fragment_over_alias_po() -> None:
    assert HUMAN_OUTCOME_PREDICATE_SQL == (
        "po.channel IN ('web') AND po.result_type IN ('action', 'answer')"
    )
