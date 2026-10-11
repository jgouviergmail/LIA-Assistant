"""Independent sessions prove probe/billing lock lifetime and late DNS edit refusal."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.personal_mcp_connection import (
    execute_personal_mcp_connection,
    prepare_personal_mcp_connection,
)
from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionInput,
)
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_connection import test_personal_mcp_connection as probe_owner
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.llm.embedding_context import get_embedding_context
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stage", ["network", "description", "embedding", "dns_edit"])
async def test_probe_external_work_has_no_actor_lock_and_late_endpoint_edits_refuse_contact(
    async_engine, monkeypatch, stage
):
    for name in ["application_tools_enabled", "mcp_enabled", "mcp_user_enabled"]:
        monkeypatch.setattr(settings, name, True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        row = UserMCPServer(user_id=owner, name="lifetime", url="https://example.org/mcp")
        seed.add(row)
        await seed.commit()
        server_id = row.id
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            connect=probe_owner,
        )
    )
    try:
        async with factory() as db:
            calls = []

            async def independent_write(phase):
                assert not db.in_transaction()
                calls.append(phase)
                async with factory() as accounting:
                    accounting.add(
                        UserMCPServer(
                            user_id=owner,
                            name=f"accounting-{phase}",
                            url="https://accounting.example.org",
                        )
                    )
                    await asyncio.wait_for(accounting.commit(), timeout=2)

            async def dns(url):
                if stage == "dns_edit":
                    async with factory() as other:
                        await other.execute(
                            update(UserMCPServer)
                            .where(UserMCPServer.id == server_id)
                            .values(url="https://changed.example.org/private")
                        )
                        await other.commit()
                return True, None

            async def connect(**kwargs):
                if stage == "network":
                    await independent_write("network")
                return SimpleNamespace(
                    tools=[{"name": "read", "description": "Read owned records"}]
                )

            async def description(**kwargs):
                if stage == "description":
                    await independent_write("description")
                return "Routes owned requests."

            async def embed(**kwargs):
                if stage == "embedding":
                    context = get_embedding_context()
                    assert context is not None and context.user_id == str(owner)
                    await independent_write("embedding")
                return {}

            network = AsyncMock(side_effect=connect)
            generator = AsyncMock(side_effect=description)
            embeddings = AsyncMock(side_effect=embed)
            pool = SimpleNamespace(get_or_connect=network, disconnect=AsyncMock())
            monkeypatch.setattr("src.infrastructure.mcp.user_pool.get_user_mcp_pool", lambda: pool)
            monkeypatch.setattr(
                "src.domains.user_mcp.personal_connection.validate_http_endpoint", dns
            )
            monkeypatch.setattr(UserMCPServerService, "_llm_generate_description", generator)
            monkeypatch.setattr(
                "src.domains.agents.services.tool_selector.compute_tool_embeddings", embeddings
            )
            monkeypatch.setattr(
                "src.domains.user_mcp.connection_embeddings.spend_blocked",
                AsyncMock(return_value=False),
            )
            monkeypatch.setattr(
                "src.domains.user_mcp.connection_embeddings.enforce_usage_limit", AsyncMock()
            )
            draft = await prepare_personal_mcp_connection(
                db, owner, PersonalMCPConnectionInput(server_id=server_id)
            )
            await db.commit()
            receipt = PreferenceWriteReceipt()
            if stage == "dns_edit":
                with pytest.raises(ResourceConflictError):
                    await execute_personal_mcp_connection(db, owner, draft, receipt)
                assert (
                    not receipt.committed
                    and not network.called
                    and not generator.called
                    and not embeddings.called
                )
            else:
                await execute_personal_mcp_connection(db, owner, draft, receipt)
                assert receipt.committed and receipt.values is not None
                assert receipt.values["personal_mcp_connection"]["connection_success"] is True
                assert calls == [stage]
            await db.rollback()
    finally:
        configure_personal_mcp_state(previous)
