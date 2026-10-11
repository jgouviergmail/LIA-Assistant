"""Original UI/native creations share one serial quota/name decision per owner."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import settings
from src.core.exceptions import ValidationError
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.domains.user_mcp.service import UserMCPServerService
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("same_name", [False, True])
async def test_parallel_creations_refuse_excess_slots_or_duplicate_names(
    async_engine, monkeypatch, same_name, committed_user_ids: list[UUID]
):
    monkeypatch.setattr(settings, "mcp_user_max_servers_per_user", 3 if same_name else 1)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        committed_user_ids.append(owner)
        await seed.commit()
    arrived = 0
    ready = asyncio.Event()

    async def validate(url):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=3)
        return True, None

    monkeypatch.setattr("src.domains.user_mcp.service.validate_http_endpoint", validate)

    async def create(index):
        async with factory() as db:
            try:
                await UserMCPServerService(db).create_server(
                    owner,
                    UserMCPServerCreate(
                        name="same" if same_name else f"server-{index}",
                        url="https://example.org/mcp",
                    ),
                )
                await db.commit()
                return True
            except ValidationError:
                await db.rollback()
                return False

    outcomes = await asyncio.wait_for(
        asyncio.gather(create(1), create(2), return_exceptions=True), timeout=6
    )
    assert outcomes.count(True) == 1 and outcomes.count(False) == 1, [
        type(item).__name__ for item in outcomes
    ]
    async with factory() as observed:
        count = await observed.scalar(
            select(func.count()).select_from(UserMCPServer).where(UserMCPServer.user_id == owner)
        )
        assert count == 1
