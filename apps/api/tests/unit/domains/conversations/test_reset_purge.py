"""The conversation reset purges Redis by declared key family (ADR-260).

Measured 2026-09-03 on the primary production account: 161 resets in 56
days, each deleting the recurrence ledger (20/20 keys), the Gmail delta
anchor, the adaptive thresholds and the briefing's last-known-good values —
none of which is the conversation. The scan patterns are unchanged; the
registry now decides, and what is kept is counted.
"""

from __future__ import annotations

import fnmatch
from typing import Any

import pytest

from src.domains.conversations.reset_purge import purge_conversation_keys, reset_scan_patterns
from src.infrastructure.observability.metrics_key_families import (
    conversation_reset_keys_deleted_total,
    conversation_reset_keys_kept_total,
    reset_undeclared_family_total,
)

pytestmark = pytest.mark.unit

UID = "08dfb351-5336-42c8-92a9-ee46c6e7f0d0"
OTHER = "dea7604e-84b6-45f9-9f6e-000000000000"


class _FakeRedis:
    """SCAN/DELETE-faithful in-memory double (glob match, cursor always 0)."""

    def __init__(self, keys: list[str]) -> None:
        self.data: dict[str, str] = dict.fromkeys(keys, "1")
        self.deleted: list[str] = []

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[bytes]]:
        return 0, [k.encode() for k in self.data if fnmatch.fnmatchcase(k, match)]

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                self.deleted.append(key)
                removed += 1
        return removed


LEARNING_AND_RUNTIME = [
    f"recurrence:{UID}:email",
    f"recurrence:{UID}:web_search",
    f"gmail_history_anchor:{UID}",
    f"adaptive:thr:journal_injection:{UID}",
    f"briefing:v2:lastgood:{UID}:mails",
    f"sse:connection:{UID}",
    f"sse:streams:{UID}",
    f"user:{UID}:sessions",
    f"user:{UID}:contacts_search",
    f"oauth_lock:{UID}:GOOGLE_GMAIL",
]
PURGEABLE = [
    f"hitl_pending:{UID}",
    f"chat:active_run:{UID}",
    f"contacts_search:{UID}:jean",
    f"contacts_list:{UID}",
    f"gmail:search:{UID}:abc",
    f"gmail:labels:{UID}",
    f"briefing:v2:{UID}:mails",
    f"heartbeat:birthdays:{UID}",
]
OTHER_USER = [f"recurrence:{OTHER}:event", f"contacts_list:{OTHER}"]
GLOBAL = ["llm_cache:_call_router_llm:abc", "scheduler:leader"]
UNDECLARED = [f"brand_new_family:{UID}"]


def _counter_value(counter: Any, **labels: str) -> float:
    return float(counter.labels(**labels)._value.get())


async def test_learning_and_runtime_keys_survive_a_reset() -> None:
    redis = _FakeRedis(LEARNING_AND_RUNTIME + PURGEABLE + OTHER_USER + GLOBAL + UNDECLARED)

    deleted = await purge_conversation_keys(redis, user_id=UID, conversation_id=UID)

    for key in LEARNING_AND_RUNTIME + OTHER_USER + GLOBAL + UNDECLARED:
        assert key in redis.data, key
    for key in PURGEABLE:
        assert key not in redis.data, key
    assert deleted == {
        "hitl_pending": 1,
        "chat:active_run": 1,
        "contacts_search": 1,
        "contacts_list": 1,
        "gmail:search": 1,
        "gmail:labels": 1,
        "briefing:v2": 1,
        "heartbeat:birthdays": 1,
    }


async def test_undeclared_family_is_kept_and_counted() -> None:
    before = _counter_value(reset_undeclared_family_total, family="brand_new_family")
    redis = _FakeRedis(UNDECLARED)

    await purge_conversation_keys(redis, user_id=UID, conversation_id=UID)

    assert redis.data == {UNDECLARED[0]: "1"}
    assert _counter_value(reset_undeclared_family_total, family="brand_new_family") == before + 1


async def test_kept_and_deleted_counters_move_by_family_and_scope() -> None:
    deleted_before = _counter_value(conversation_reset_keys_deleted_total, family="contacts_list")
    kept_before = _counter_value(conversation_reset_keys_kept_total, scope="user_learning")
    redis = _FakeRedis([f"contacts_list:{UID}", f"recurrence:{UID}:email"])

    await purge_conversation_keys(redis, user_id=UID, conversation_id=UID)

    assert (
        _counter_value(conversation_reset_keys_deleted_total, family="contacts_list")
        == deleted_before + 1
    )
    assert (
        _counter_value(conversation_reset_keys_kept_total, scope="user_learning") == kept_before + 1
    )


async def test_a_key_matched_by_several_patterns_is_deleted_once() -> None:
    redis = _FakeRedis([f"contacts_search:{UID}:jean"])

    deleted = await purge_conversation_keys(redis, user_id=UID, conversation_id=UID)

    assert deleted == {"contacts_search": 1}
    assert redis.deleted == [f"contacts_search:{UID}:jean"]


async def test_distinct_conversation_id_still_purges_conversation_keys() -> None:
    conv = "11111111-2222-3333-4444-555555555555"
    redis = _FakeRedis([f"hitl_pending:{conv}", f"recurrence:{UID}:email"])

    await purge_conversation_keys(redis, user_id=UID, conversation_id=conv)

    assert f"hitl_pending:{conv}" not in redis.data
    assert f"recurrence:{UID}:email" in redis.data


def test_scan_patterns_are_the_historical_six_deduplicated() -> None:
    assert reset_scan_patterns("u", "c") == ["*:u:*", "*:u", "u:*", "*:c:*", "*:c", "c:*"]
    assert reset_scan_patterns("u", "u") == ["*:u:*", "*:u", "u:*"]


async def test_undeclared_key_prefixed_by_the_id_never_leaks_the_id_into_a_label() -> None:
    before = _counter_value(reset_undeclared_family_total, family="id_prefixed")
    redis = _FakeRedis([f"{UID}:something"])

    await purge_conversation_keys(redis, user_id=UID, conversation_id=UID)

    assert f"{UID}:something" in redis.data
    assert _counter_value(reset_undeclared_family_total, family="id_prefixed") == before + 1


def test_an_id_shaped_head_never_becomes_a_metric_label() -> None:
    """Label cardinality is bounded BY CONSTRUCTION, not by today's key names.

    A key whose first segment is some OTHER entity's id (not the user's, not
    the conversation's) would otherwise publish that id as a Prometheus label
    value — one series per row, forever.
    """
    from src.domains.conversations.reset_purge import _undeclared_label

    ids = {"08dfb351-5336-42c8-92a9-ee46c6e7f0d0"}
    assert _undeclared_label("08dfb351-5336-42c8-92a9-ee46c6e7f0d0:x", ids) == "id_prefixed"
    # Another entity's uuid — not in `ids`, still an id.
    assert _undeclared_label("3f2504e0-4f89-11d3-9a0c-0305e82c3301:x", ids) == "id_prefixed"
    # A hex digest and a long number are ids too.
    assert _undeclared_label("9f8e7d6c5b4a39281706:y", ids) == "id_prefixed"
    assert _undeclared_label("175678901234:y", ids) == "id_prefixed"
    # A real family name stays itself.
    assert _undeclared_label("recurrence:abc:email", ids) == "recurrence"
    assert _undeclared_label("bm25", ids) == "bm25"
