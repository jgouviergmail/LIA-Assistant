"""Token metadata is complete across bounded pages, with no secret-bearing column projection."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.health_queries import read_health_tokens
from src.domains.agents.application.health_read_schemas import HealthTokensRead
from src.domains.health_metrics.models import HealthMetricToken

pytestmark = pytest.mark.integration


async def test_token_pages_cover_all_owned_including_revoked_without_hashes(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    rows = [
        HealthMetricToken(
            user_id=owner,
            token_hash=sha256(f"SECRET-{i}".encode()).hexdigest(),
            token_prefix="hm_public",
            label=f"Watch {i}",
        )
        for i in range(103)
    ]
    async_session.add_all(rows)
    rows[0].revoked_at = datetime.now(UTC)
    await async_session.commit()
    page = await read_health_tokens(async_session, owner, HealthTokensRead(limit=50))
    assert page.total == 103 and page.returned_count == 50 and page.truncated
    ids = {row.id for row in page.tokens}
    while page.truncated:
        page = await read_health_tokens(
            async_session,
            owner,
            HealthTokensRead(limit=50, after_id=page.next_cursor, as_of=page.as_of),
        )
        assert not ids.intersection(row.id for row in page.tokens)
        ids.update(row.id for row in page.tokens)
    assert len(ids) == 103
    assert "token_hash" not in page.model_dump_json()
    with pytest.raises(ResourceNotFoundError):
        await read_health_tokens(
            async_session, owner, HealthTokensRead(after_id=uuid4(), as_of=page.as_of)
        )
