"""A secure action hands off after exact HITL, with no mutation or proof in its receipt."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_repository import get_command, save_command
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interaction_metadata import (
    with_application_interaction_metadata,
)
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.services import draft_executor
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize(
    "intervention",
    [
        "valid",
        "unbound",
        "operator_off",
        "operator_during_claim",
        "inactive_during_claim",
        "downgraded_receipt",
    ],
)
async def test_exact_human_confirmation_creates_only_a_secure_waiting_receipt(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
    device: bool,
) -> None:
    operations = import_module("src.domains.agents.application.session_bulk_operations")
    execution = import_module("src.domains.agents.application.draft_execution")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(actor_id))
    target = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, current.session_id)
    draft_id = "secure-fleet-draft"

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.domains.agents.application.command_service.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.application.draft_execution.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.application_session_tools.get_db_context", session
    )
    monkeypatch.setattr(
        "src.domains.agents.application.interaction_metadata.get_db_context", session
    )
    # The actual ledger owns its normal transaction; only its database fixture is substituted.
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    try:
        with patch.dict(APPLICATION_OPERATIONS._operations):
            APPLICATION_OPERATIONS._operations[operations.SESSION_FLEET_OPERATION.operation_id] = (
                replace(operations.SESSION_FLEET_OPERATION, kind=OperationKind.DEVICE)
                if device
                else operations.SESSION_FLEET_OPERATION
            )
            if intervention == "valid":
                tools = import_module("src.domains.agents.tools.application_session_tools")
                with installed_runtime_context(user_id=actor_id, application_origin=origin):
                    proposal = await tools.revoke_lia_other_device_sessions_tool.coroutine(
                        runtime=make_tool_runtime(
                            user_id=actor_id, application_origin=origin, store=InMemoryStore()
                        )
                    )
                assert proposal.success and proposal.metadata["requires_confirmation"]
                item = next(iter(proposal.registry_updates.values()))
                content = ApplicationActionDraftContent.model_validate(item.payload["content"])
                draft_id = item.id
                assert current.session_id not in str(proposal) and target.session_id not in str(
                    proposal
                )
            else:
                content = await operations.prepare_other_sessions_revocation(
                    async_session, actor_id, origin=origin
                )
                await save_command(
                    async_session,
                    content,
                    draft_id,
                    origin=None if intervention == "unbound" else origin,
                )
            await async_session.commit()
            if intervention == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif intervention in {"operator_during_claim", "inactive_during_claim"}:
                actual_claim = execution.claim_command

                async def withdraw_after_claim(db: AsyncSession, command_id, user_id):
                    token = await actual_claim(db, command_id, user_id)
                    if intervention == "operator_during_claim":
                        monkeypatch.setattr(settings, "application_tools_enabled", False)
                    else:
                        test_user.is_active = False
                        await db.commit()
                    return token

                monkeypatch.setattr(execution, "claim_command", withdraw_after_claim)
            with (
                installed_runtime_context(
                    user_id=actor_id, application_origin=origin, language="fr", deps=object()
                ),
                patch.dict(draft_executor.EXECUTOR_REGISTRY),
            ):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": draft_id,
                        "draft_type": "application_action",
                        "draft_content": content.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "secure-fleet-thread"}},
                    "secure-fleet-thread",
                    "fr",
                )
            assert not result.success
            assert await redis.exists(f"session:{current.session_id}")
            assert await redis.exists(f"session:{target.session_id}")
            effects = (
                await async_session.scalars(
                    select(AgentEffect).where(AgentEffect.user_id == actor_id)
                )
            ).all()
            if intervention == "downgraded_receipt":
                row = await get_command(async_session, content.command_id, actor_id)
                assert row is not None and row.result_encrypted is not None
                receipt = ApplicationExecutionOutcome.model_validate_json(
                    decrypt_data(row.result_encrypted)
                )
                assert receipt.interaction is not None
                downgraded = receipt.model_copy(
                    update={
                        "interaction": receipt.interaction.model_copy(
                            update={"kind": "secure" if device else "device"}
                        )
                    }
                )
                row.result_encrypted = encrypt_data(downgraded.model_dump_json())
                effects[0].result_payload = encrypt_data(downgraded.model_dump_json())
                effects[0].result_digest = payload_digest(downgraded.model_dump(mode="json"))
                await async_session.commit()
                current.step_up_at = None
                await redis.set(
                    f"session:{current.session_id}", json.dumps(current.to_dict()), keepttl=True
                )
                with pytest.raises(AuthorizationError):
                    await claim_approved_waiting_interaction(
                        async_session, actor_id, content.command_id, origin
                    )
                return
            if intervention != "valid":
                if intervention in {"operator_during_claim", "inactive_during_claim"}:
                    assert len(effects) == 1 and effects[0].status == EffectStatus.FAILED
                    row = await get_command(async_session, content.command_id, actor_id)
                    assert row is not None and row.phase.value == "failed"
                else:
                    assert effects == []
                return
            assert result.error is None and result.to_agent_result()["status"] == "waiting"
            assert result.result_data["interaction"]["kind"] == ("device" if device else "secure")
            assert len(effects) == 1 and effects[0].status == EffectStatus.WAITING
            row = await get_command(async_session, content.command_id, actor_id)
            assert row is not None and row.phase.value == "waiting"
            public = result.to_agent_result()
            assert current.session_id not in str(public) and target.session_id not in str(public)
            assert "step_up_at" not in str(public)
            assert await with_application_interaction_metadata(
                {}, effects[0].run_id, str(actor_id)
            ) == {
                "application_interactions": [{"command_id": str(content.command_id)}],
            }
            assert (
                await with_application_interaction_metadata({}, effects[0].run_id, str(uuid4()))
                == {}
            )
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            assert (
                await with_application_interaction_metadata({}, effects[0].run_id, str(actor_id))
                == {}
            )
    finally:
        for item in (current, target):
            await store.delete_session(item.session_id)
