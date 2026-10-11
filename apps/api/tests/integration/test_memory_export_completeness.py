"""Management exports cover every current memory, without private or superseded facts."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.domains.memories.models import Memory
from src.domains.memories.router import export_memories
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_export_is_complete_current_owned_and_does_not_expose_biometric_context(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    other = User(
        id=uuid4(),
        email=f"memory-export-other-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    rows = [
        Memory(
            user_id=test_user.id,
            content=f"Current memory {index}",
            category="personal",
            importance=0.0,
            context_biometric={"private": "biometric-secret"},
        )
        for index in range(1003)
    ]
    async_session.add_all(rows)
    async_session.add_all(
        [
            Memory(user_id=other.id, content="Foreign memory secret", category="personal"),
            Memory(
                user_id=test_user.id,
                content="Superseded historical secret",
                category="personal",
                invalidated_at=datetime.now(UTC),
            ),
        ]
    )
    await async_session.commit()
    response = await export_memories(export_format="json", user=test_user, db=async_session)
    assert isinstance(response, StreamingResponse)
    try:
        payload = json.loads(b"".join([chunk async for chunk in response.body_iterator]))
    finally:
        await response._reader.close()
    assert payload["total_memories"] == len(payload["memories"]) == 1003
    assert all(item["importance"] == 0 for item in payload["memories"])
    assert all(item["context_biometric"] is None for item in payload["memories"])
    assert "biometric-secret" not in str(payload)
    assert "Foreign memory secret" not in str(payload)
    assert "Superseded historical secret" not in str(payload)
