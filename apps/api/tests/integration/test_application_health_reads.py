"""Native management reads preserve health consent, source projection and complete pagination."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.health_queries import read_health_samples, read_health_tokens
from src.domains.agents.application.health_read_schemas import HealthSamplesRead
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["page", "consent_off", "native_off", "deployment_off", "foreign_cursor", "late_withdrawal"],
)
async def test_health_samples_are_owned_consented_and_paged(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = True
    foreign = User(id=uuid4(), email=f"health-foreign-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    foreign_id = foreign.id
    start = datetime.now(UTC) - timedelta(days=2)
    rows = [
        HealthSample(
            user_id=owner,
            kind="steps",
            date_start=start,
            date_end=start + timedelta(minutes=i + 1),
            value=10 + i,
            source="watch",
        )
        for i in range(103)
    ]
    other = HealthSample(
        user_id=foreign_id,
        kind="steps",
        date_start=start,
        date_end=start + timedelta(minutes=1),
        value=99999,
        source="private",
    )
    heart = HealthSample(
        user_id=owner,
        kind="heart_rate",
        date_start=start,
        date_end=start + timedelta(minutes=1),
        value=80,
        source="watch",
    )
    async_session.add_all([*rows, other, heart])
    await async_session.commit()
    cursor = other.id if scenario == "foreign_cursor" else None
    if scenario == "consent_off":
        await async_session.execute(
            update(User).where(User.id == owner).values(health_metrics_agents_enabled=False)
        )
        await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "deployment_off":
        monkeypatch.setattr(settings, "health_metrics_enabled", False)
    if scenario == "late_withdrawal":
        from src.domains.health_metrics import management_read

        original = management_read.read_health_sample_page

        async def disable(*args, **kwargs):
            result = await original(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(management_read, "read_health_sample_page", disable)
    query = HealthSamplesRead(
        limit=50, kind="steps", after_id=cursor, as_of=datetime.now(UTC) if cursor else None
    )
    if scenario != "page":
        with pytest.raises(
            ResourceNotFoundError if scenario == "foreign_cursor" else AuthorizationError
        ):
            await read_health_samples(async_session, owner, query)
        return
    first = await read_health_samples(async_session, owner, query)
    assert first.total == 103 and first.returned_count == 50 and first.truncated
    assert "user_id" not in first.model_dump_json() and "99999" not in first.model_dump_json()
    ids = {row.id for row in first.samples}
    while first.truncated:
        first = await read_health_samples(
            async_session,
            owner,
            query.model_copy(update={"after_id": first.next_cursor, "as_of": first.as_of}),
        )
        assert not ids.intersection(row.id for row in first.samples)
        ids.update(row.id for row in first.samples)
    assert len(ids) == 103


async def test_health_token_inventory_is_metadata_only_even_without_data_consent(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    secret = "hm_private-secret"
    token = HealthMetricToken(
        user_id=test_user.id,
        token_hash=sha256(secret.encode()).hexdigest(),
        token_prefix="hm_public",
        label="Watch",
    )
    async_session.add(token)
    await async_session.commit()
    result = await read_health_tokens(async_session, test_user.id)
    assert len(result.tokens) == 1 and result.tokens[0].label == "Watch"
    assert (
        secret not in result.model_dump_json() and token.token_hash not in result.model_dump_json()
    )
