"""A browser continuation spends the exact persisted HITL once, not a fabricated handoff."""

from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    save_command,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.agents.effects.chain_verify import verify_chain
from src.domains.agents.effects.digest import args_digest, draft_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.notary import notarise_account
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "corruption",
    [
        "none",
        "missing",
        "approval_kind",
        "approval_ref",
        "draft_digest",
        "args_digest",
        "policy",
        "status",
        "truncated",
        "result_digest",
        "receipt",
        "schema",
        "duplicate",
        "tool_name",
        "closed_at",
        "error_code",
        "malformed",
    ],
)
async def test_continuation_requires_the_exact_immutable_waiting_effect(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    module = import_module("src.domains.agents.application.continuation_approval")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, session.session_id)
    assert origin is not None
    try:
        draft = await prepare_preference_content(
            async_session, actor_id, PreferencePatch(font_size=17)
        )
        draft_id = f"draft-{uuid4()}"
        await save_command(async_session, draft, draft_id, origin=origin)
        await async_session.commit()
        original_token = await claim_command(async_session, draft.command_id, actor_id)
        assert original_token is not None
        waiting = ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.WAITING,
            interaction=PendingApplicationInteraction(
                interaction_id=draft.command_id, kind="device", expires_at=draft.expires_at
            ),
        )
        assert await close_command(
            async_session, draft.command_id, actor_id, original_token, waiting
        )
        content = draft.model_dump(mode="json")
        request = ClaimRequest(
            user_id=actor_id,
            thread_id=f"continue-{uuid4()}",
            run_id="original-run",
            source="user",
            execution_mode="react",
            tool_name="draft:application_action",
            mutation_policy="draft",
            idempotency_key=f"draft:{draft_id}",
            args_digest=args_digest("draft:application_action", {"draft": content}),
            approval_kind="draft_critique",
            approval_ref=draft_id,
            draft_digest=draft_digest(content),
        )
        repository = EffectLedgerRepository(async_session)
        original = None
        if corruption != "missing":
            ticket = await repository.claim(request)
            assert ticket.claim_token is not None
            assert await repository.close_waiting(
                ticket.effect.id, ticket.claim_token, result_payload=waiting.model_dump(mode="json")
            )
            await async_session.flush()
            await async_session.refresh(ticket.effect)
            original = ticket.effect
            replacements = {
                "approval_kind": "policy",
                "approval_ref": "another-draft",
                "draft_digest": "0" * 64,
                "args_digest": "0" * 64,
                "policy": "none",
                "status": EffectStatus.SUCCEEDED,
                "truncated": True,
                "result_digest": "0" * 64,
                "receipt": encrypt_data(
                    waiting.model_copy(update={"values": {"fabricated": True}}).model_dump_json()
                ),
                "schema": original.schema_version + 1,
                "tool_name": "draft:email",
                "closed_at": None,
                "error_code": "EXECUTION_FAILED",
                "malformed": encrypt_data("not-json"),
            }
            columns = {
                "policy": "mutation_policy",
                "truncated": "result_truncated",
                "receipt": "result_payload",
                "schema": "schema_version",
                "malformed": "result_payload",
            }
            if corruption in replacements:
                setattr(original, columns.get(corruption, corruption), replacements[corruption])
            elif corruption == "duplicate":
                duplicate = request.model_copy(update={"thread_id": f"duplicate-{uuid4()}"})
                other = await repository.claim(duplicate)
                assert other.claim_token is not None
                assert await repository.close_waiting(
                    other.effect.id,
                    other.claim_token,
                    result_payload=waiting.model_dump(mode="json"),
                )
        await async_session.commit()
        if corruption != "none":
            with pytest.raises(AuthorizationError):
                await module.claim_approved_waiting_interaction(
                    async_session, actor_id, draft.command_id, origin
                )
            await async_session.rollback()
            row = await get_command(async_session, draft.command_id, actor_id)
            assert row is not None and row.phase == ApplicationPhase.WAITING
            assert row.claim_token == original_token
            return
        assert original is not None
        original_id = original.id
        original_result = original.result_payload
        await notarise_account(async_session, actor_id, limit=20)
        await async_session.commit()
        claimed = await module.claim_approved_waiting_interaction(
            async_session, actor_id, draft.command_id, origin
        )
        assert claimed is not None
        assert claimed.command.draft == draft and claimed.command.previous_outcome == waiting
        assert claimed.effect_id != original_id and claimed.effect_token is not None
        continuation = await async_session.get(AgentEffect, claimed.effect_id)
        assert continuation is not None and continuation.status == EffectStatus.CLAIMED
        assert (
            continuation.approval_ref == draft_id
            and continuation.draft_digest == request.draft_digest
        )
        assert continuation.run_id == request.run_id and continuation.thread_id == request.thread_id
        assert str(original_id) in continuation.idempotency_key
        assert continuation.retry_of is None
        assert (
            await module.claim_approved_waiting_interaction(
                async_session, actor_id, draft.command_id, origin
            )
            is None
        )
        await async_session.refresh(original)
        assert (
            original.status == EffectStatus.WAITING and original.result_payload == original_result
        )
        rows = (
            await async_session.scalars(
                select(AgentEffect).where(AgentEffect.thread_id == request.thread_id)
            )
        ).all()
        assert len(rows) == 2
        completed = ApplicationExecutionOutcome(
            success=True, phase=ApplicationPhase.COMMITTED, committed=True
        )
        assert await repository.close_success(
            claimed.effect_id,
            claimed.effect_token,
            result_payload=completed.model_dump(mode="json"),
        )
        assert await close_command(
            async_session, draft.command_id, actor_id, claimed.command.token, completed
        )
        await notarise_account(async_session, actor_id, limit=20)
        await async_session.flush()
        audit = await verify_chain(async_session, actor_id, deep=True)
        assert audit.ok and audit.payloads_checked == 4
    finally:
        await store.delete_session(session.session_id)
