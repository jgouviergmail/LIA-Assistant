"""Proactive discussion settings: every bound adjustable, contradictory ones refused at boot."""

from decimal import Decimal
from typing import get_args

import pytest
from pydantic import ValidationError

from src.core.config.proactive_discussions import ProactiveDiscussionSettings
from src.core.constants import (
    DISCUSSION_ATTENTION_ALERT_GAP_MINUTES_DEFAULT,
    DISCUSSION_SENSITIVE_TOPICS,
)
from src.domains.proactive_discussions.llm_contracts import ContextInterpretation
from src.domains.shared.discussion_sources import SensitiveTopic, SourceReadRequest

pytestmark = pytest.mark.unit


def test_the_topic_vocabulary_has_one_declaration():
    # The settings module may not import the domain, so it reads the constant; the
    # domain's Literal must name exactly the same topics, in the same order.
    assert get_args(SensitiveTopic) == DISCUSSION_SENSITIVE_TOPICS


def test_a_new_account_consents_to_every_sensitive_topic_by_default():
    # Owner decision 2026-10-21: consented by default, withdrawn one by one.
    assert ProactiveDiscussionSettings().discussion_default_sensitive_topics == list(
        DISCUSSION_SENSITIVE_TOPICS
    )


def test_an_alert_no_longer_holds_an_opening_back_by_default():
    # Owner decision 2026-10-21: « no alert in the last 30 minutes » was too restrictive.
    assert DISCUSSION_ATTENTION_ALERT_GAP_MINUTES_DEFAULT == 0
    assert ProactiveDiscussionSettings().discussion_attention_alert_gap_minutes == 0


@pytest.mark.parametrize(
    "spelling,topics",
    [
        (" Grief ,health,,health", ["health", "grief"]),
        ("", []),
        (["finances", "relationships"], ["relationships", "finances"]),
    ],
)
def test_topics_are_read_in_vocabulary_order_without_duplicates(spelling, topics):
    settings = ProactiveDiscussionSettings(discussion_default_sensitive_topics=spelling)
    assert settings.discussion_default_sensitive_topics == topics


def test_an_unknown_topic_refuses_the_boot():
    with pytest.raises(ValidationError, match="DISCUSSION_DEFAULT_SENSITIVE_TOPICS"):
        ProactiveDiscussionSettings(discussion_default_sensitive_topics="health,politics")


@pytest.mark.parametrize(
    "values,named",
    [
        (
            {"discussion_run_deadline_seconds": 300, "discussion_run_lease_seconds": 300},
            "DISCUSSION_RUN_DEADLINE_SECONDS",
        ),
        (
            {"discussion_read_call_limit": 40, "discussion_run_read_calls_max": 20},
            "DISCUSSION_READ_CALL_LIMIT",
        ),
        (
            {"discussion_rebuild_deadline_seconds": 100, "discussion_run_deadline_seconds": 200},
            "DISCUSSION_REBUILD_DEADLINE_SECONDS",
        ),
        (
            {
                "discussion_run_budget_usd": Decimal("2"),
                "discussion_owner_daily_budget_usd": Decimal("1"),
            },
            "DISCUSSION_OWNER_DAILY_BUDGET_USD",
        ),
        (
            {
                "discussion_run_budget_usd": Decimal("2"),
                "discussion_instance_daily_budget_usd": Decimal("1"),
            },
            "DISCUSSION_INSTANCE_DAILY_BUDGET_USD",
        ),
        # The batch is drawn from the candidates a tick examines: fewer of them than
        # owners served leaves places no tick can ever fill.
        (
            {"discussion_tick_candidates": 3, "discussion_tick_owners": 4},
            "DISCUSSION_TICK_CANDIDATES",
        ),
    ],
)
def test_contradictory_bounds_refuse_the_boot_naming_the_setting(values, named):
    with pytest.raises(ValidationError, match=named):
        ProactiveDiscussionSettings(**values)


def test_equal_run_and_day_ceilings_are_coherent():
    # A run's reservation is the smaller of its ceiling and the day's room, so a run
    # ceiling equal to the day is legitimate (production: 5/5/5).
    settings = ProactiveDiscussionSettings(
        discussion_run_budget_usd=Decimal("5"),
        discussion_owner_daily_budget_usd=Decimal("5"),
        discussion_instance_daily_budget_usd=Decimal("5"),
    )
    assert settings.discussion_run_budget_usd == Decimal("5")


@pytest.mark.parametrize("spelling,topics", [("health,grief", ["health", "grief"]), ("", [])])
def test_the_env_file_spelling_of_the_topics_is_read(monkeypatch, spelling, topics):
    # The .env files write the list comma-separated; an empty value consents to none.
    monkeypatch.setenv("DISCUSSION_DEFAULT_SENSITIVE_TOPICS", spelling)
    assert ProactiveDiscussionSettings().discussion_default_sensitive_topics == topics


def test_a_ceiling_finer_than_the_ledger_refuses_the_boot():
    # Reservations are held to eight decimals: a finer ceiling would make every run
    # reserve a rounded amount above its own ceiling.
    with pytest.raises(ValidationError):
        ProactiveDiscussionSettings(discussion_run_budget_usd=Decimal("0.123456789"))
    assert ProactiveDiscussionSettings(
        discussion_run_budget_usd=Decimal("0.12345678")
    ).discussion_run_budget_usd == Decimal("0.12345678")


def _bounds(field: object) -> tuple[float | None, float | None]:
    """The inclusive lower and upper bound a field's metadata declares, as numbers."""
    low = high = None
    for item in getattr(field, "metadata", ()):
        low = getattr(item, "ge", None) if getattr(item, "ge", None) is not None else low
        low = getattr(item, "gt", None) if getattr(item, "gt", None) is not None else low
        high = getattr(item, "le", None) if getattr(item, "le", None) is not None else high
        high = (
            getattr(item, "max_length", None)
            if getattr(item, "max_length", None) is not None
            else high
        )
    return low, high


@pytest.mark.parametrize(
    ("setting", "contract", "field"),
    [
        ("discussion_read_call_limit", SourceReadRequest, "call_limit"),
        ("discussion_read_timeout_seconds", SourceReadRequest, "timeout_seconds"),
        ("discussion_research_item_limit", SourceReadRequest, "item_limit"),
        ("discussion_research_item_max_chars", SourceReadRequest, "item_max_chars"),
        # One classification per offered fact, so a pass never offers more than an
        # answer may classify.
        ("discussion_context_facts_per_pass", ContextInterpretation, "classifications"),
    ],
)
def test_every_value_a_setting_accepts_the_contract_it_feeds_accepts(setting, contract, field):
    # Measured 2026-10-21: DISCUSSION_READ_CALL_LIMIT accepted 20 at boot while every
    # read refused anything past 16, so every run failed before reading anything.
    low, high = _bounds(ProactiveDiscussionSettings.model_fields[setting])
    floor, ceiling = _bounds(contract.model_fields[field])
    assert low is not None and high is not None and ceiling is not None
    assert floor is None or low >= floor
    assert high <= ceiling


def test_a_rebuild_may_outlast_the_lease_that_every_step_renews():
    # Measured 2026-10-21: a 69-fact rebuild took 237 s against an opening's 240.
    settings = ProactiveDiscussionSettings(
        discussion_run_lease_seconds=300,
        discussion_run_deadline_seconds=240,
        discussion_rebuild_deadline_seconds=900,
    )
    assert settings.discussion_rebuild_deadline_seconds > settings.discussion_run_lease_seconds
