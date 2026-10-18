"""Cache partitions credentials, occurrence, evidence, model, policy and reference time."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.domains.agents.services.qualification.cache import classification_cache_key
from tests.unit.domains.agents.services.test_classification_batches import observed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changed",
    [
        "owner",
        "provider",
        "grant",
        "container",
        "item",
        "occurrence",
        "revision",
        "scope",
        "evidence",
        "model",
        "policy",
        "clock",
        "timezone",
    ],
)
def test_every_semantic_or_authorization_dimension_changes_the_key(
    changed: str,
) -> None:
    owner = uuid4()
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    value = observed(1)
    base = {
        "user_id": owner,
        "provider": "google_gmail",
        "source_scope": "grant-1",
        "model": "jev-pinned",
        "policy": "policy-v1",
        "now": now,
        "timezone": "UTC",
    }
    first = classification_cache_key(value, **base)
    changes = {
        "owner": {"user_id": uuid4()},
        "provider": {"provider": "microsoft_outlook"},
        "grant": {"source_scope": "grant-2"},
        "model": {"model": "another-model"},
        "policy": {"policy": "policy-v2"},
        "clock": {"now": now + timedelta(hours=1)},
        "timezone": {"timezone": "Europe/Paris"},
    }
    fields = {
        "container": {"container_id": "other"},
        "item": {"item_id": "another"},
        "occurrence": {"occurrence": "another"},
        "revision": {"revision": "another"},
        "scope": {"evidence_scope": "body"},
        "evidence": {"evidence": {"subject": "changed"}},
    }
    second = classification_cache_key(
        value.model_copy(update=fields.get(changed, {})), **{**base, **changes.get(changed, {})}
    )
    assert first != second
    assert str(owner) in first
    assert "grant-1" not in first and "private-" not in first and "Please" not in first


def test_dictionary_order_does_not_cost_another_native_call() -> None:
    value = observed(1)
    kwargs = {
        "user_id": uuid4(),
        "provider": "google_gmail",
        "source_scope": "grant-1",
        "model": "jev-pinned",
        "policy": "policy-v1",
        "now": datetime.now(UTC),
        "timezone": "UTC",
    }
    reversed_fields = dict(reversed(list(value.evidence.items())))
    assert classification_cache_key(value, **kwargs) == classification_cache_key(
        value.model_copy(update={"evidence": reversed_fields}), **kwargs
    )
