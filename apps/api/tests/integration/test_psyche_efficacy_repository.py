"""Real PostgreSQL proves private, transactional and replay-safe experience."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.psyche.efficacy_contracts import (
    EfficacyDomainProfile,
    EfficacyEpisodeInput,
    EfficacyEpoch,
    EfficacyObservation,
    EfficacyProfile,
)
from src.domains.psyche.efficacy_models import EfficacyEpisode
from src.domains.psyche.efficacy_repository import EfficacyRepository
from src.domains.psyche.engine import PADVector
from src.domains.psyche.models import PsycheState
from src.domains.psyche.repository import PsycheStateRepository
from src.domains.psyche.reset_policy import apply_psyche_reset
from src.domains.psyche.reset_snapshot import psyche_reset_snapshot
from src.domains.psyche.schemas import PsycheResetRequest
from src.domains.users.account_deletion_service import build_purge_statements
from src.domains.users.models import User

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def _episode(
    epoch: EfficacyEpoch,
    *,
    when: datetime = NOW,
    run_id: str | None = None,
    message_id: UUID | None = None,
) -> EfficacyEpisodeInput:
    return EfficacyEpisodeInput(
        epoch=epoch,
        run_id=run_id or str(uuid4()),
        message_id=message_id or uuid4(),
        terminal_at=when,
        config_fingerprint="a" * 64,
        observations=(
            EfficacyObservation(domain="technical", verdict="success", reason="goal_satisfied"),
        ),
    )


async def _state(db: AsyncSession, owner: UUID) -> EfficacyEpoch:
    db.add(PsycheState(user_id=owner))
    await db.flush()
    epoch = await EfficacyRepository(db).capture_epoch(owner)
    assert epoch is not None
    return epoch


def _technical(profile: EfficacyProfile) -> EfficacyDomainProfile:
    return next(item for item in profile.domains if item.domain == "technical")


async def test_retry_does_not_double_count_or_replace_current_feedback(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EfficacyRepository(async_session)
    episode = _episode(await _state(async_session, test_user.id))
    assert await repo.record_episode(test_user.id, episode, now=NOW, feedback="helpful")
    assert await repo.apply_feedback(test_user.id, episode.message_id, "unhelpful", now=NOW)
    assert await repo.record_episode(test_user.id, episode, now=NOW, feedback="helpful")
    domain = _technical(await repo.read_profile(test_user.id, now=NOW))
    assert domain.result_count == 1
    assert domain.feedback.helpful == 0 and domain.feedback.unhelpful == 1
    assert await repo.apply_feedback(test_user.id, episode.message_id, "helpful", now=NOW)
    domain = _technical(await repo.read_profile(test_user.id, now=NOW))
    assert domain.feedback.helpful == 1 and domain.feedback.unhelpful == 0
    count = await async_session.scalar(select(func.count()).select_from(EfficacyEpisode))
    assert count == 1


@pytest.mark.parametrize("conflict", ["message", "timestamp", "run", "config"])
async def test_conflicting_retry_is_refused_without_rewriting_canonical_provenance(
    async_session: AsyncSession, test_user: User, conflict: str
) -> None:
    repo = EfficacyRepository(async_session)
    episode = _episode(await _state(async_session, test_user.id))
    assert await repo.record_episode(test_user.id, episode, now=NOW)
    changes = {
        "message": {"message_id": uuid4()},
        "timestamp": {"terminal_at": NOW - timedelta(seconds=1)},
        "run": {"run_id": str(uuid4())},
        "config": {"config_fingerprint": "b" * 64},
    }
    altered = episode.model_copy(update=changes[conflict])
    assert not await repo.record_episode(test_user.id, altered, now=NOW)
    row = await async_session.scalar(select(EfficacyEpisode))
    assert row is not None and row.message_id == episode.message_id and row.terminal_at == NOW
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == 1


async def test_owner_cannot_record_or_change_another_owners_experience(
    async_session: AsyncSession, test_user: User
) -> None:
    other = User(email=f"efficacy-{uuid4()}@example.test", full_name="Other", is_active=True)
    async_session.add(other)
    await async_session.flush()
    repo = EfficacyRepository(async_session)
    episode = _episode(await _state(async_session, test_user.id))
    await _state(async_session, other.id)
    assert not await repo.record_episode(other.id, episode, now=NOW)
    assert await repo.record_episode(test_user.id, episode, now=NOW)
    assert not await repo.apply_feedback(other.id, episode.message_id, "helpful", now=NOW)
    assert _technical(await repo.read_profile(other.id, now=NOW)).result_count == 0
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).feedback_count == 0


@pytest.mark.parametrize("kind", ["purge", "full", "soft"])
async def test_delayed_episode_cannot_revive_purged_or_fully_reset_learning(
    async_session: AsyncSession, test_user: User, kind: str
) -> None:
    repo = EfficacyRepository(async_session)
    episode = _episode(await _state(async_session, test_user.id))
    assert await repo.record_episode(test_user.id, episode, now=NOW)
    state = await async_session.scalar(
        select(PsycheState).where(PsycheState.user_id == test_user.id)
    )
    assert state is not None
    if kind == "purge":
        await PsycheStateRepository(async_session).delete_for_user(test_user.id)
    else:
        apply_psyche_reset(state, kind, PADVector(0.0, 0.0, 0.0))
        await PsycheStateRepository(async_session).update(state)
    assert await repo.record_episode(test_user.id, episode, now=NOW) is (kind == "soft")
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == (
        1 if kind == "soft" else 0
    )
    if kind == "purge":
        assert await repo.capture_epoch(test_user.id) is None
    assert await async_session.scalar(select(func.count()).select_from(EfficacyEpisode)) == (
        1 if kind == "soft" else 0
    )


async def test_expiration_uses_terminal_time_on_read_and_replay_never_refreshes_it(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EfficacyRepository(async_session)
    episode = _episode(await _state(async_session, test_user.id))
    assert await repo.record_episode(test_user.id, episode, now=NOW)
    future = NOW + timedelta(days=90, microseconds=1)
    assert _technical(await repo.read_profile(test_user.id, now=future)).result_count == 0
    assert not await repo.record_episode(test_user.id, episode, now=future)
    assert not await repo.apply_feedback(test_user.id, episode.message_id, "helpful", now=future)
    at_boundary = await repo.read_profile(test_user.id, now=NOW + timedelta(days=90))
    assert _technical(at_boundary).result_count == 1


async def test_capacity_eviction_floor_rejects_replay_without_extending_lifetime(
    async_session: AsyncSession, test_user: User
) -> None:
    epoch = await _state(async_session, test_user.id)
    first = _episode(epoch, when=NOW - timedelta(hours=2))
    rows = [
        first,
        *[_episode(epoch, when=NOW - timedelta(minutes=501 - index)) for index in range(500)],
    ]
    # Seed the durable boundary at capacity; the actual writer must evict and fence.
    async_session.add_all(
        [
            EfficacyEpisode(
                user_id=test_user.id,
                state_id=epoch.state_id,
                generation=epoch.generation,
                run_id=item.run_id,
                message_id=item.message_id,
                terminal_at=item.terminal_at,
                observations=[
                    observation.model_dump(mode="json") for observation in item.observations
                ],
                config_fingerprint=item.config_fingerprint,
            )
            for item in rows
        ]
    )
    await async_session.flush()
    repo = EfficacyRepository(async_session)
    latest = _episode(epoch)
    assert await repo.record_episode(test_user.id, latest, now=NOW)
    count = await async_session.scalar(select(func.count()).select_from(EfficacyEpisode))
    assert count == 500
    oldest = min(rows, key=lambda item: (item.terminal_at, item.message_id))
    assert not await repo.record_episode(test_user.id, oldest, now=NOW)
    assert not await repo.apply_feedback(test_user.id, oldest.message_id, "helpful", now=NOW)
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == 500


async def _committed_state(
    engine: AsyncEngine, identities: list[UUID]
) -> tuple[UUID, EfficacyEpoch]:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        owner = User(
            email=f"efficacy-concurrent-{uuid4()}@example.test",
            full_name="Disposable",
            is_active=True,
        )
        db.add(owner)
        await db.flush()
        identities.append(owner.id)
        epoch = await _state(db, owner.id)
        await db.commit()
        return owner.id, epoch


async def test_owner_fence_is_acquired_before_any_child_lock_or_read(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, epoch = await _committed_state(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as manager, AsyncSession(async_engine) as writer:
        await manager.scalar(select(User.id).where(User.id == owner).with_for_update())
        await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError) as blocked:
            await EfficacyRepository(writer).record_episode(owner, _episode(epoch), now=NOW)
        assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
        # The writer waiting on the owner has not taken the child lock.
        state = await manager.scalar(
            select(PsycheState).where(PsycheState.user_id == owner).with_for_update(nowait=True)
        )
        assert state is not None
        await writer.rollback()


async def test_independent_writers_and_feedback_race_preserve_both_results(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, epoch = await _committed_state(async_engine, committed_user_ids)
    one, two = _episode(epoch), _episode(epoch)

    async def persist(episode: EfficacyEpisodeInput, *, feedback: str | None = None) -> None:
        async with AsyncSession(async_engine) as db:
            assert await EfficacyRepository(db).record_episode(
                owner, episode, now=NOW, feedback=feedback
            )
            await db.commit()

    await asyncio.gather(persist(one, feedback="helpful"), persist(one), persist(two))
    async with AsyncSession(async_engine) as db:
        repo = EfficacyRepository(db)
        assert await repo.apply_feedback(owner, one.message_id, "unhelpful", now=NOW)
        await db.commit()
    await persist(one)
    async with AsyncSession(async_engine) as db:
        domain = _technical(await EfficacyRepository(db).read_profile(owner, now=NOW))
        assert domain.result_count == 2
        assert domain.feedback.helpful == 0 and domain.feedback.unhelpful == 1


async def test_caller_rollback_undoes_episode_and_projection(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, epoch = await _committed_state(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as writer:
        assert await EfficacyRepository(writer).record_episode(owner, _episode(epoch), now=NOW)
        await writer.rollback()
    async with AsyncSession(async_engine) as reader:
        profile = await EfficacyRepository(reader).read_profile(owner, now=NOW)
        assert _technical(profile).result_count == 0
        state = await reader.scalar(select(PsycheState).where(PsycheState.user_id == owner))
        assert state is not None and state.efficacy_profile is None


async def test_account_deletion_cascades_evidence_without_message_dependency(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EfficacyRepository(async_session)
    assert await repo.record_episode(
        test_user.id, _episode(await _state(async_session, test_user.id)), now=NOW
    )
    await async_session.execute(delete(User).where(User.id == test_user.id))
    assert await async_session.scalar(select(func.count()).select_from(EfficacyEpisode)) == 0


async def test_warm_identity_map_cannot_reuse_an_epoch_after_an_independent_reset(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner, epoch = await _committed_state(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as delayed, AsyncSession(async_engine) as manager:
        old = await delayed.scalar(select(PsycheState).where(PsycheState.user_id == owner))
        assert old is not None and old.efficacy_generation == epoch.generation
        managed = await manager.scalar(select(PsycheState).where(PsycheState.user_id == owner))
        assert managed is not None
        await PsycheStateRepository(manager).lock_reset_owner(owner)
        apply_psyche_reset(managed, "full", PADVector(0.0, 0.0, 0.0))
        await PsycheStateRepository(manager).update(managed)
        await manager.commit()
        fresh = await EfficacyRepository(delayed).capture_epoch(owner)
        assert fresh is not None and fresh.generation != epoch.generation
        assert not await EfficacyRepository(delayed).record_episode(owner, _episode(epoch), now=NOW)
        assert (
            _technical(await EfficacyRepository(delayed).read_profile(owner, now=NOW)).result_count
            == 0
        )


async def test_clock_rollback_hides_future_evidence_without_evicting_or_poisoning_floor(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = EfficacyRepository(async_session)
    epoch = await _state(async_session, test_user.id)
    assert await repo.record_episode(test_user.id, _episode(epoch), now=NOW)
    earlier = NOW - timedelta(seconds=1)
    assert await repo.record_episode(test_user.id, _episode(epoch, when=earlier), now=earlier)
    assert _technical(await repo.read_profile(test_user.id, now=earlier)).result_count == 1
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == 2


@pytest.mark.parametrize("level", ["full", "purge"])
async def test_reset_scope_digest_detects_new_evidence_even_when_profile_is_unchanged(
    async_session: AsyncSession, test_user: User, level: str
) -> None:
    repo = EfficacyRepository(async_session)
    epoch = await _state(async_session, test_user.id)
    first = _episode(epoch).model_copy(update={"observations": ()})
    assert await repo.record_episode(test_user.id, first, now=NOW)
    request = PsycheResetRequest(level=level)
    before = await psyche_reset_snapshot(async_session, test_user.id, request)
    second = _episode(epoch).model_copy(update={"observations": ()})
    assert await repo.record_episode(test_user.id, second, now=NOW)
    after = await psyche_reset_snapshot(async_session, test_user.id, request)
    assert before.before == after.before and before.after == after.after
    assert before.digest != after.digest


async def test_soft_account_purge_removes_own_episodes_before_state_and_preserves_others(
    async_session: AsyncSession, test_user: User
) -> None:
    foreign = User(
        email=f"efficacy-purge-{uuid4()}@example.test", full_name="Other", is_active=True
    )
    async_session.add(foreign)
    await async_session.flush()
    repo = EfficacyRepository(async_session)
    for owner in (test_user.id, foreign.id):
        assert await repo.record_episode(
            owner, _episode(await _state(async_session, owner)), now=NOW
        )
    statements = build_purge_statements(test_user.id)
    names = [name for name, _ in statements]
    assert names.index("psyche_efficacy_episodes") < names.index("psyche_states")
    _, purge = next(item for item in statements if item[0] == "psyche_efficacy_episodes")
    removed = await async_session.execute(purge)
    assert removed.rowcount == 1
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == 0
    assert _technical(await repo.read_profile(foreign.id, now=NOW)).result_count == 1
    assert await async_session.scalar(select(User.id).where(User.id == test_user.id)) is not None


async def test_full_future_capacity_refuses_two_rollback_batches_without_eviction_or_floor(
    async_session: AsyncSession, test_user: User
) -> None:
    epoch = await _state(async_session, test_user.id)
    accepted = [_episode(epoch) for _ in range(500)]
    async_session.add_all(
        EfficacyEpisode(
            user_id=test_user.id,
            state_id=epoch.state_id,
            generation=epoch.generation,
            run_id=item.run_id,
            message_id=item.message_id,
            terminal_at=item.terminal_at,
            observations=[observation.model_dump(mode="json") for observation in item.observations],
            config_fingerprint=item.config_fingerprint,
        )
        for item in accepted
    )
    await async_session.flush()
    repo = EfficacyRepository(async_session)
    original_ids = {item.message_id for item in accepted}
    # The same admission rule also rejects a late older event without a clock
    # rollback: a True receipt always means the new contribution is retained.
    assert not await repo.record_episode(
        test_user.id, _episode(epoch, when=NOW - timedelta(hours=1)), now=NOW
    )
    for rollback_days in (1, 2):
        earlier = NOW - timedelta(days=rollback_days)
        for _ in range(3):
            assert not await repo.record_episode(
                test_user.id, _episode(epoch, when=earlier), now=earlier
            )
        actual_ids = set((await async_session.scalars(select(EfficacyEpisode.message_id))).all())
        assert actual_ids == original_ids
        state = await async_session.scalar(
            select(PsycheState).where(PsycheState.user_id == test_user.id)
        )
        assert state is not None and state.efficacy_evicted_at is None
        assert state.efficacy_evicted_message_id is None
        assert _technical(await repo.read_profile(test_user.id, now=earlier)).result_count == 0
    assert _technical(await repo.read_profile(test_user.id, now=NOW)).result_count == 500
