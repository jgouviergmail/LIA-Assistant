"""Real PostgreSQL confirmation freezes resolution and preserves intervening UI writes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.location_schemas import LocationChangeRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_location_tools import update_lia_home_location_tool
from src.domains.users.models import User
from src.domains.users.schemas import HomeLocationData, HomeLocationUpdate
from src.domains.users.service import UserService
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "clear,intervention", [(False, False), (False, True), (True, False), (True, True)]
)
async def test_location_native_confirmation(
    async_session: AsyncSession,
    test_user: User,
    clear: bool,
    intervention: bool,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    old = HomeLocationData(address="Old", lat=48, lon=2)
    test_user.home_location_encrypted = encrypt_data(old.model_dump_json())
    test_user.last_known_location_encrypted = encrypt_data('{"lat":49,"lon":3,"accuracy":5}')
    test_user.last_known_location_updated_at = datetime.now(UTC)
    await async_session.commit()
    remembered = test_user.last_known_location_encrypted
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    resolver = AsyncMock(return_value=HomeLocationData(address="New", lat=0, lon=12))
    with (
        patch("src.domains.agents.tools.application_location_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch(
            "src.domains.agents.application.location_preparation.resolve_home_location", resolver
        ),
        patch(
            "src.domains.connectors.service.ConnectorService.is_places_enabled",
            AsyncMock(return_value=True),
        ),
        patch(
            "src.domains.users.geocoding.resolve_home_coordinates",
            AsyncMock(side_effect=AssertionError("no geocoding after approval")),
        ),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(user_id=test_user.id, deps=object(), language="fr"),
    ):
        output = await update_lia_home_location_tool.coroutine(
            change=(
                LocationChangeRequest(action="clear")
                if clear
                else LocationChangeRequest(action="set", address="New")
            ),
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore(), language="fr"),
        )
        assert output.success and output.metadata["requires_confirmation"]
        await async_session.refresh(test_user)
        assert test_user.home_location_encrypted is not None
        assert (await UserService(async_session).get_home_location(test_user.id)).address == "Old"
        item = next(iter(output.registry_updates.values()))
        if intervention:
            await UserService(async_session).set_home_location(
                test_user.id,
                HomeLocationUpdate(address="Manual", lat=45, lon=4),
                resolved=True,
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "location-confirmation"}},
            "location-confirmation",
            "fr",
        )
    await async_session.refresh(test_user)
    assert result.success is (not intervention)
    assert resolver.await_count == (0 if clear else 1)
    actual = await UserService(async_session).get_home_location(test_user.id)
    if intervention:
        assert actual.address == "Manual"
        assert draft_refusal_code(result) == "STALE_STATE"
    elif clear:
        assert actual is None
        assert test_user.last_known_location_encrypted is None
        assert test_user.last_known_location_updated_at is None
    else:
        assert actual.address == "New" and actual.lat == 0 and actual.lon == 12
        assert test_user.last_known_location_encrypted == remembered
