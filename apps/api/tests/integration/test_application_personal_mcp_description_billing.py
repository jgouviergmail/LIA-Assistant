"""An independent account-FK write proves no actor lock spans provider accounting."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import settings
from src.domains.agents.application.personal_mcp_description import (
    execute_personal_mcp_description,
    prepare_personal_mcp_description,
)
from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionInput,
)
from src.domains.user_mcp.models import UserMCPServer
from src.domains.user_mcp.personal_description import regenerate_personal_mcp_description
from src.domains.user_mcp.personal_state import observe_personal_mcp_state, set_personal_mcp_state
from src.domains.user_mcp.service import UserMCPServerService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.mcp.personal_state_gateway import (
    PersonalMCPStateGateway,
    configure_personal_mcp_state,
)
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


async def test_provider_accounting_can_commit_on_its_own_session(async_engine, monkeypatch):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        row = UserMCPServer(
            user_id=owner,
            name="billing-safe",
            url="https://example.com",
            discovered_tools_cache=[{"name": "read", "description": "Read owned records"}],
        )
        seed.add(row)
        await seed.commit()
        server_id = row.id
    previous = configure_personal_mcp_state(
        PersonalMCPStateGateway(
            observe_personal_mcp_state,
            set_personal_mcp_state,
            describe=regenerate_personal_mcp_description,
        )
    )
    try:
        async with factory() as db:

            async def provider(*args, **kwargs):
                assert not db.in_transaction()
                # User FK insertion takes KEY SHARE; it would wait on an actor
                # FOR UPDATE lock held during a provider/accounting await.
                async with factory() as accounting:
                    accounting.add(
                        UserMCPServer(
                            user_id=owner,
                            name="billing-lock-probe",
                            url="https://accounting.example.com",
                        )
                    )
                    await asyncio.wait_for(accounting.commit(), timeout=2)
                return "Routes requests for owned records."

            monkeypatch.setattr(UserMCPServerService, "_llm_generate_description", provider)
            draft = await prepare_personal_mcp_description(
                db, owner, PersonalMCPDescriptionInput(server_id=server_id)
            )
            await db.commit()
            receipt = PreferenceWriteReceipt()
            await execute_personal_mcp_description(db, owner, draft, receipt)
            assert (
                receipt.committed
                and receipt.values is not None
                and receipt.values["personal_mcp_description"]["domain_description"]
                == "Routes requests for owned records."
            )
    finally:
        configure_personal_mcp_state(previous)
