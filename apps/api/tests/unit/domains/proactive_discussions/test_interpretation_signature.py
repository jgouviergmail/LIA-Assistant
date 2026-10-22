"""An interpretation is reused while what its meaning depends on is unchanged.

Before 2026-10-21 the checkpoint keyed on the policy REVISION, so editing the hours or
the daily limit had every fact interpreted, and paid for, again.
"""

from datetime import UTC, datetime

import pytest

from src.domains.proactive_discussions.context_store.checkpoints import (
    interpretation_signature,
    readiness_signature,
)
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit

BASE = DiscussionPolicy(
    enabled=True,
    start_hour=9,
    end_hour=20,
    timezone="Europe/Berlin",
    daily_max=2,
    sources=(SourceKey.CALENDAR, SourceKey.MEMORIES),
    sensitive_topics=("health",),
    forbidden_topics=("Fictional topic",),
    revision=3,
)


@pytest.mark.parametrize(
    "change",
    [
        {"start_hour": 7},
        {"end_hour": 22},
        {"daily_max": None},
        {"enabled": False},
        {"paused_until": datetime(2026, 10, 22, tzinfo=UTC)},
        {"revision": 4},
        # Order and spelling carry no meaning.
        {"sources": (SourceKey.MEMORIES, SourceKey.CALENDAR)},
        {"forbidden_topics": ("  fictional TOPIC ",)},
    ],
)
def test_when_lia_may_speak_never_changes_what_a_fact_means(change):
    changed = BASE.model_copy(update=change)
    assert interpretation_signature(changed, "fr-FR") == interpretation_signature(BASE, "fr-FR")


@pytest.mark.parametrize(
    "change",
    [
        {"sources": (SourceKey.CALENDAR,)},
        {"sensitive_topics": ()},
        {"forbidden_topics": ("Another fictional topic",)},
        {"timezone": "America/New_York"},
    ],
)
def test_what_a_fact_may_be_read_as_changes_the_signature(change):
    changed = BASE.model_copy(update=change)
    assert interpretation_signature(changed, "fr-FR") != interpretation_signature(BASE, "fr-FR")


def test_the_summaries_language_changes_the_signature():
    assert interpretation_signature(BASE, "fr-FR") != interpretation_signature(BASE, "en-US")


def test_readiness_follows_its_interpretation_the_epoch_and_the_directives():
    signature = interpretation_signature(BASE, "fr-FR")
    ready = readiness_signature(signature, 2, "directives-a")
    assert ready == readiness_signature(signature, 2, "directives-a")
    assert ready != readiness_signature(signature, 3, "directives-a")
    assert ready != readiness_signature(signature, 2, "directives-b")
    other = interpretation_signature(BASE.model_copy(update={"timezone": "UTC"}), "fr-FR")
    assert ready != readiness_signature(other, 2, "directives-a")
