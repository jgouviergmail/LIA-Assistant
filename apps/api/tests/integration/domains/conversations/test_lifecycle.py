"""A discussion transition is atomic, owner-bound and safe to replay after a lost reply."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.conversation_execution import ExecutionKind
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import BaseAPIException
from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import turn_decision
from src.domains.agents.effects.models import AgentDecision, DecisionOutcome
from src.domains.bookmarks.models import MessageBookmark
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations import cleanup_port, legacy_reset
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextObservationRecord,
    ContextStateRecord,
)
from src.domains.proactive_discussions.models import DiscussionPreference
from src.infrastructure.observability.metrics_agents import conversation_resets_total
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


class NativeCleanupResult:
    """Native boundaries are separately proven against real Store/checkpoint/Redis."""

    def __init__(self, *, succeeds: bool) -> None:
        self.succeeds = succeeds

    async def prepare_owner(self, owner: UUID) -> None:
        """This fixture has no Live provider or Redis record to bind."""

    async def purge_checkpoint(self, target: ConversationRef) -> bool:
        return self.succeeds

    async def purge_tool_context(self, target: ConversationRef) -> bool:
        return self.succeeds

    async def purge_pending(self, target: ConversationRef) -> bool:
        return self.succeeds


@dataclass(frozen=True)
class Scenario:
    owner: UUID
    main: ConversationRef
    annex: ConversationRef
    other: ConversationRef


@pytest.fixture
async def scenario(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> Scenario:
    owner = await commit_owner(async_engine, committed_user_ids)
    targets = (
        ConversationRef(owner, owner, ConversationKind.MAIN, 0, owner),
        ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 3, uuid4()),
        ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 0, uuid4()),
    )
    async with AsyncSession(async_engine) as db:
        for index, target in enumerate(targets):
            db.add(
                Conversation(
                    id=target.id,
                    user_id=owner,
                    kind=target.kind,
                    revision=target.revision,
                    runtime_id=target.runtime_id,
                    title=f"Topic {index}",
                    message_count=1,
                    total_tokens=11,
                )
            )
        await db.flush()
        for target in targets:
            db.add(
                ConversationMessage(conversation_id=target.id, role="user", content="Keep scope")
            )
        await db.commit()
    return Scenario(owner, *targets)


async def test_reset_rotates_only_its_runtime_and_preserves_title_and_billed_history(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    target = scenario.annex
    run_id = str(uuid4())
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        question = await db.scalar(
            select(ConversationMessage.id).where(ConversationMessage.conversation_id == target.id)
        )
        assert question is not None
        answer = ConversationMessage(
            conversation_id=target.id, role="assistant", content="Kept answer"
        )
        db.add(answer)
        await db.flush()
        turn = turn_decision(
            run_id=run_id,
            user_id=scenario.owner,
            thread_id=str(target.id),
            execution_mode="pipeline",
            automated=False,
        )
        turn.request_message_id = question
        turn.response_message_id = answer.id
        turn.outcome = DecisionOutcome.ANSWERED
        await DecisionRepository(db).record(turn, ended_at=datetime.now(UTC))
        bookmark = MessageBookmark(
            user_id=scenario.owner,
            message_id=answer.id,
            conversation_id=target.id,
            content=answer.content,
            answered_at=answer.created_at,
        )
        billed = MessageTokenSummary(
            user_id=scenario.owner,
            session_id="fixture",
            run_id=run_id,
            conversation_id=target.id,
            total_prompt_tokens=7,
            total_completion_tokens=4,
        )
        db.add_all([billed, bookmark])
        await db.commit()
        result = await ConversationLifecycle(db).request_reset(
            scenario.owner, target.id, operation_id=uuid4(), expected_revision=target.revision
        )
        assert result.logical_applied and not result.cleanup_complete
        assert result.new_revision == target.revision + 1
        row = await db.get(Conversation, target.id, populate_existing=True)
        assert row is not None and row.runtime_id != target.runtime_id
        assert (row.title, row.message_count, row.total_tokens) == ("Topic 1", 0, 0)
        remaining = set(await db.scalars(select(ConversationMessage.conversation_id)))
        assert {scenario.main.id, scenario.other.id} <= remaining and target.id not in remaining
        await db.refresh(billed)
        assert billed.conversation_id is None and billed.total_prompt_tokens == 7
        await db.refresh(bookmark)
        assert bookmark.message_id is None and bookmark.content == "Kept answer"
        decisions = list(
            await db.scalars(select(AgentDecision).where(AgentDecision.user_id == scenario.owner))
        )
        assert len(decisions) == 1
        saved = decisions[0]
        assert saved.run_id == run_id and saved.outcome == DecisionOutcome.ANSWERED
        assert saved.request_message_id is None and saved.response_message_id is None


async def test_replay_precedes_revision_checks_and_never_clears_a_new_message(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    operation_id = uuid4()
    target = scenario.annex
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        service = ConversationLifecycle(db)
        first = await service.request_reset(
            scenario.owner, target.id, operation_id=operation_id, expected_revision=target.revision
        )
        db.add(ConversationMessage(conversation_id=target.id, role="user", content="After reset"))
        await db.commit()
        replay = await service.request_reset(
            scenario.owner, target.id, operation_id=operation_id, expected_revision=target.revision
        )
        assert replay.replayed and replay.new_revision == first.new_revision
        assert (
            await db.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.conversation_id == target.id
                )
            )
            == 1
        )
        for other_id, revision in [(scenario.other.id, 0), (target.id, target.revision + 1)]:
            with pytest.raises(BaseAPIException) as conflict:
                await service.request_reset(
                    scenario.owner, other_id, operation_id=operation_id, expected_revision=revision
                )
            assert conflict.value.status_code == 409
            await db.rollback()


async def test_main_cannot_be_deleted_and_foreign_and_missing_have_the_same_refusal(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    scenario: Scenario,
) -> None:
    foreign = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        service = ConversationLifecycle(db)
        with pytest.raises(BaseAPIException) as primary:
            await service.request_delete(
                scenario.owner, scenario.main.id, operation_id=uuid4(), expected_revision=0
            )
        assert primary.value.status_code == 409
        await db.rollback()
        for target_id in (scenario.annex.id, uuid4()):
            with pytest.raises(BaseAPIException) as hidden:
                await service.request_delete(
                    foreign, target_id, operation_id=uuid4(), expected_revision=3
                )
            assert hidden.value.status_code == 404
            await db.rollback()


@pytest.mark.parametrize("kind", list(ExecutionKind))
async def test_a_durable_graph_or_voice_reservation_protects_its_target(
    async_engine: AsyncEngine,
    scenario: Scenario,
    kind: ExecutionKind,
) -> None:
    target = scenario.annex
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).admit(
            target, run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4(), kind=kind
        )
        await db.commit()
        with pytest.raises(BaseAPIException) as busy:
            await ConversationLifecycle(db).request_reset(
                scenario.owner, target.id, operation_id=uuid4(), expected_revision=target.revision
            )
        assert busy.value.status_code == 409
        await db.rollback()
        row = await db.get(Conversation, target.id)
        assert row is not None and row.runtime_id == target.runtime_id


async def test_delete_replay_survives_the_retired_annex_and_stale_reset_refuses(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    target, operation_id = scenario.annex, uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        service = ConversationLifecycle(db)
        first = await service.request_delete(
            scenario.owner, target.id, operation_id=operation_id, expected_revision=target.revision
        )
        replay = await service.request_delete(
            scenario.owner, target.id, operation_id=operation_id, expected_revision=target.revision
        )
        assert first.new_revision is None and replay.replayed
        row = await db.get(Conversation, target.id, populate_existing=True)
        assert row is not None and row.deleted_at is not None
        with pytest.raises(BaseAPIException) as retired:
            await service.request_reset(
                scenario.owner, target.id, operation_id=uuid4(), expected_revision=target.revision
            )
        assert retired.value.status_code == 404


async def test_delete_erases_the_title_the_person_wrote_and_no_other(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    target = scenario.annex
    async with AsyncSession(async_engine) as db:
        await ConversationLifecycle(db).request_delete(
            scenario.owner, target.id, operation_id=uuid4(), expected_revision=target.revision
        )
    async with AsyncSession(async_engine) as observer:
        rows = await observer.execute(
            select(Conversation.id, Conversation.title).where(
                Conversation.user_id == scenario.owner
            )
        )
        titles = dict(rows.tuples().all())
    # The row stays for the receipt and the cleanup; the person's words do not.
    retired = titles[target.id]
    assert retired is not None and "Topic 1" not in retired
    assert (titles[scenario.main.id], titles[scenario.other.id]) == ("Topic 0", "Topic 2")


@pytest.mark.parametrize("cancelled", [False, True])
async def test_failure_before_commit_rolls_back_every_logical_write(
    async_engine: AsyncEngine,
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
    cancelled: bool,
) -> None:
    target, request_id = scenario.annex, uuid4()
    async with AsyncSession(async_engine) as db:

        async def refuse_commit() -> None:
            raise asyncio.CancelledError() if cancelled else RuntimeError("Injected before commit")

        monkeypatch.setattr(db, "commit", refuse_commit)
        with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
            await ConversationLifecycle(db).request_reset(
                scenario.owner,
                target.id,
                operation_id=request_id,
                expected_revision=target.revision,
            )
    async with AsyncSession(async_engine) as observer:
        row = await observer.get(Conversation, target.id)
        assert row is not None and (row.runtime_id, row.revision, row.message_count) == (
            target.runtime_id,
            target.revision,
            1,
        )
        assert (
            await observer.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.conversation_id == target.id
                )
            )
            == 1
        )
        assert (
            await observer.scalar(
                select(ConversationOperation.id).where(
                    ConversationOperation.user_id == scenario.owner,
                    ConversationOperation.request_id == request_id,
                )
            )
            is None
        )


async def test_lost_commit_acknowledgement_is_reconciled_without_another_reset(
    async_engine: AsyncEngine,
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, request_id = scenario.annex, uuid4()
    async with AsyncSession(async_engine) as db:
        real_commit = db.commit

        async def commit_with_lost_reply() -> None:
            await real_commit()
            raise ConnectionError("Injected lost acknowledgement")

        monkeypatch.setattr(db, "commit", commit_with_lost_reply)
        with pytest.raises(ConnectionError):
            await ConversationLifecycle(db).request_reset(
                scenario.owner,
                target.id,
                operation_id=request_id,
                expected_revision=target.revision,
            )
    async with AsyncSession(async_engine) as observer:
        observer.add(
            ConversationMessage(conversation_id=target.id, role="user", content="New generation")
        )
        await observer.commit()
        replay = await ConversationLifecycle(observer).request_reset(
            scenario.owner, target.id, operation_id=request_id, expected_revision=target.revision
        )
        assert replay.replayed and replay.new_revision == target.revision + 1
        assert (
            await observer.scalar(
                select(func.count(ConversationMessage.id)).where(
                    ConversationMessage.conversation_id == target.id
                )
            )
            == 1
        )


async def test_concurrent_requests_cannot_reset_the_generation_twice(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    target = scenario.annex

    async def reset() -> int:
        async with AsyncSession(async_engine) as db:
            try:
                result = await ConversationLifecycle(db).request_reset(
                    scenario.owner,
                    target.id,
                    operation_id=uuid4(),
                    expected_revision=target.revision,
                )
            except BaseAPIException as error:
                return error.status_code
            assert result.new_revision == target.revision + 1
            return 200

    assert sorted(await asyncio.gather(reset(), reset())) == [200, 409]


async def test_other_discussion_activity_does_not_block_a_local_reset(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).admit(
            scenario.main,
            run_id=str(uuid4()),
            stream_id=str(uuid4()),
            worker_id=uuid4(),
        )
        await db.commit()
        result = await ConversationLifecycle(db).request_reset(
            scenario.owner,
            scenario.annex.id,
            operation_id=uuid4(),
            expected_revision=scenario.annex.revision,
        )
        assert result.logical_applied


@pytest.mark.parametrize("succeeds", [False, True])
async def test_legacy_alias_only_succeeds_after_physical_cleanup_and_counts_once(
    async_engine: AsyncEngine,
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
    succeeds: bool,
) -> None:
    monkeypatch.setattr(legacy_reset, "AsyncSessionLocal", async_sessionmaker(async_engine))
    monkeypatch.setattr(cleanup_port, "_runtime_cleanup", NativeCleanupResult(succeeds=succeeds))
    before = conversation_resets_total._value.get()
    request_id = uuid4()
    async with AsyncSession(async_engine) as db:
        if succeeds:
            result = await legacy_reset.reset_primary(
                scenario.owner, db, operation_id=request_id, expected_revision=0
            )
            assert (
                result is not None
                and result.cleanup_complete
                and result.previous_message_count == 1
            )
            replay = await legacy_reset.reset_primary(
                scenario.owner, db, operation_id=request_id, expected_revision=0
            )
            assert replay is not None and replay.replayed and replay.previous_message_count == 1
        else:
            with pytest.raises(BaseAPIException) as pending:
                await legacy_reset.reset_primary(
                    scenario.owner, db, operation_id=request_id, expected_revision=0
                )
            assert pending.value.status_code == 409
            assert isinstance(pending.value.detail, dict)
            assert pending.value.detail["operation_id"] == str(request_id)
            assert (
                pending.value.detail["logical_applied"]
                and not pending.value.detail["cleanup_complete"]
            )
        assert conversation_resets_total._value.get() == before + 1


async def test_reset_withdraws_only_its_derived_supports_and_fences_the_shared_snapshot(
    async_engine: AsyncEngine,
    scenario: Scenario,
) -> None:
    expires = datetime.now(UTC) + timedelta(days=1)
    async with AsyncSession(async_engine) as db:
        db.add(DiscussionPreference(user_id=scenario.owner))
        db.add(
            ContextStateRecord(
                user_id=scenario.owner,
                generation=7,
                ready_context={"signature": "old", "references": {}},
            )
        )
        messages = list(
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id.in_(
                        [scenario.main.id, scenario.annex.id, scenario.other.id]
                    )
                )
            )
        )
        roots = {message.conversation_id: str(message.id) for message in messages}
        for message in messages:
            root = roots[message.conversation_id]
            db.add(
                ContextObservationRecord(
                    user_id=scenario.owner,
                    root=root,
                    source="conversations",
                    version="1",
                    data={"reference": f"conversations:{message.id}"},
                    expires_at=expires,
                )
            )
            db.add(
                ContextItemRecord(
                    user_id=scenario.owner,
                    kind="observation",
                    data={},
                    revision=1,
                    generation=7,
                    root_keys=[root],
                    expires_at=expires,
                )
            )
        mixed_id = uuid4()
        db.add(
            ContextItemRecord(
                id=mixed_id,
                user_id=scenario.owner,
                kind="pattern",
                data={},
                revision=1,
                generation=7,
                root_keys=[roots[scenario.main.id], roots[scenario.annex.id]],
                expires_at=expires,
            )
        )
        await db.commit()
        await ConversationLifecycle(db).request_reset(
            scenario.owner,
            scenario.annex.id,
            operation_id=uuid4(),
            expected_revision=scenario.annex.revision,
        )
        kept = set(
            await db.scalars(
                select(ContextObservationRecord.root).where(
                    ContextObservationRecord.user_id == scenario.owner
                )
            )
        )
        assert kept == {roots[scenario.main.id], roots[scenario.other.id]}
        items = list(
            await db.scalars(
                select(ContextItemRecord).where(ContextItemRecord.user_id == scenario.owner)
            )
        )
        assert {root for item in items for root in item.root_keys} == kept
        assert all(item.id != mixed_id for item in items)
        state = await db.scalar(
            select(ContextStateRecord).where(ContextStateRecord.user_id == scenario.owner)
        )
        pref = await db.scalar(
            select(DiscussionPreference).where(DiscussionPreference.user_id == scenario.owner)
        )
        assert state is not None and state.generation == 8
        assert pref is not None and pref.context_epoch == 1 and pref.run_fence == 1
