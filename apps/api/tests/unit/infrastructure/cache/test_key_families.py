"""Redis key families declare their scope (ADR-260).

The conversation reset used to delete every key matching ``*:{user_id}*`` —
which is how the recurrence ledger, the Gmail delta anchor and the adaptive
thresholds were wiped 161 times in 56 days on the primary account. A family
now declares what it is; an undeclared family is never purged by a reset.
"""

from __future__ import annotations

import pytest

from src.infrastructure.cache.key_families import (
    BARE_PREFIX_FAMILIES,
    KEY_FAMILIES,
    KeyScope,
    assert_key_families_complete,
    family_of,
    is_reset_purgeable,
    is_user_scoped,
    scope_of,
)

pytestmark = pytest.mark.unit

UID = "08dfb351-5336-42c8-92a9-ee46c6e7f0d0"


@pytest.mark.parametrize(
    "key",
    [
        f"recurrence:{UID}:email",
        f"gmail_history_anchor:{UID}",
        f"adaptive:thr:journal_injection:{UID}",
        f"briefing:v2:lastgood:{UID}:mails",
        f"presence:{UID}:2026-09-03:14",
        f"psyche:state:{UID}",
        f"sse:connection:{UID}",
        f"user:{UID}:sessions",
        f"user:{UID}:contacts_search",
        f"oauth_lock:{UID}:GOOGLE_GMAIL",
        f"apikey:user:{UID}:abc",
    ],
)
def test_learning_and_runtime_keys_survive_a_reset(key: str) -> None:
    assert is_reset_purgeable(key) is False
    assert is_user_scoped(key) is True


@pytest.mark.parametrize(
    "key",
    [
        f"hitl_pending:{UID}",
        f"chat:active_run:{UID}",
        f"contacts_search:{UID}:jean",
        f"gmail:search:{UID}:abc",
        f"gmail:labels:{UID}",
        f"briefing:v2:{UID}:mails",
        f"heartbeat:departure:{UID}:digest",
        f"usage_limit:{UID}",
        f"rag:{UID}",
    ],
)
def test_conversation_and_cache_keys_are_purged(key: str) -> None:
    assert is_reset_purgeable(key) is True
    assert is_user_scoped(key) is True


@pytest.mark.parametrize(
    "key",
    [
        "llm_cache:_call_router_llm:abc",
        "push:debounce:chan",
        "scheduler:leader",
        "heartbeat:geocode:48.8:2.3",
    ],
)
def test_global_keys_are_neither_purged_nor_user_scoped(key: str) -> None:
    assert is_reset_purgeable(key) is False
    assert is_user_scoped(key) is False


def test_undeclared_family_is_never_purged() -> None:
    assert family_of(f"brand_new_family:{UID}") is None
    assert scope_of(f"brand_new_family:{UID}") is None
    assert is_reset_purgeable(f"brand_new_family:{UID}") is False
    assert is_user_scoped(f"brand_new_family:{UID}") is False


def test_longest_prefix_wins() -> None:
    assert family_of(f"briefing:v2:lastgood:{UID}:mails") == "briefing:v2:lastgood"
    assert family_of(f"briefing:v2:{UID}:mails") == "briefing:v2"
    assert KEY_FAMILIES["briefing:v2:lastgood"] is KeyScope.USER_LEARNING
    assert KEY_FAMILIES["briefing:v2"] is KeyScope.USER_CACHE


def test_bare_prefix_families_match_by_startswith() -> None:
    assert family_of("async_model_price_gpt-4o") == "async_model_price_"
    assert scope_of("async_model_price_gpt-4o") is KeyScope.GLOBAL
    assert set(BARE_PREFIX_FAMILIES).isdisjoint(KEY_FAMILIES)


def test_bytes_keys_are_accepted() -> None:
    assert family_of(f"recurrence:{UID}:email".encode()) == "recurrence"


def test_registry_is_complete() -> None:
    """Every Redis prefix constant of core.constants names a declared family."""
    assert_key_families_complete()


def test_registry_refuses_an_undeclared_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core import constants as c

    monkeypatch.setattr(c, "REDIS_KEY_BRAND_NEW_PREFIX", "brand_new_family:", raising=False)
    with pytest.raises(RuntimeError, match="brand_new_family"):
        assert_key_families_complete()
