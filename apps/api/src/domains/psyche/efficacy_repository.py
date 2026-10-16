"""Transactional owner-private experience. Callers own commit and feature gates."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.psyche.constants import EFFICACY_MAX_EPISODES, EFFICACY_WINDOW_DAYS
from src.domains.psyche.efficacy_contracts import (
    EfficacyEpisodeInput,
    EfficacyEpisodeView,
    EfficacyEpoch,
    EfficacyFeedback,
    EfficacyObservation,
    EfficacyProfile,
)
from src.domains.psyche.efficacy_models import EfficacyEpisode
from src.domains.psyche.efficacy_scoring import build_profile
from src.domains.psyche.models import PsycheState
from src.domains.users.models import User


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Evidence timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _key(terminal_at: datetime, message_id: UUID) -> tuple[datetime, UUID]:
    return (_utc(terminal_at), message_id)


def _view(row: EfficacyEpisode) -> EfficacyEpisodeView:
    return EfficacyEpisodeView(
        run_id=row.run_id,
        message_id=row.message_id,
        terminal_at=row.terminal_at,
        observations=tuple(EfficacyObservation.model_validate(item) for item in row.observations),
        feedback=EfficacyFeedback(row.feedback) if row.feedback else None,
    )


class EfficacyRepository:
    """Serialise writes by owner BEFORE reading state, feedback or evidence.

    A delayed writer only observes an existing state. It never creates one, and
    an immutable canonical timestamp plus monotone eviction floor prevent replay
    from extending an observation's lifetime.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def capture_epoch(self, user_id: UUID) -> EfficacyEpoch | None:
        row = await self.db.scalar(
            select(PsycheState)
            .where(PsycheState.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        return EfficacyEpoch(state_id=row.id, generation=row.efficacy_generation)

    async def read_profile(
        self,
        user_id: UUID,
        *,
        now: datetime,
        collection_enabled: bool = True,
        influence_enabled: bool = True,
    ) -> EfficacyProfile:
        """Rebuild with canonical age on reads: cleanup is never a validity gate."""
        reference = _utc(now)
        state = await self.db.scalar(
            select(PsycheState)
            .where(PsycheState.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        rows = await self._rows(state) if state is not None else []
        return build_profile(
            [_view(row) for row in rows],
            now=reference,
            window_days=EFFICACY_WINDOW_DAYS,
            collection_enabled=collection_enabled,
            influence_enabled=influence_enabled,
        )

    async def record_episode(
        self,
        user_id: UUID,
        episode: EfficacyEpisodeInput,
        *,
        now: datetime,
        feedback: EfficacyFeedback | None = None,
        replace_feedback: bool = False,
    ) -> bool:
        reference = _utc(now)
        state = await self._locked_state(user_id)
        if state is None or not self._eligible(state, episode, reference):
            return False
        rows = await self._rows(state)
        existing = next(
            (
                row
                for row in rows
                if row.run_id == episode.run_id or row.message_id == episode.message_id
            ),
            None,
        )
        if existing is not None:
            if not self._same_episode(existing, episode):
                return False
            if replace_feedback:
                existing.feedback = EfficacyFeedback(feedback).value if feedback else None
            await self._refresh(state, rows, reference)
            return True
        if not self._fits_retention(rows, episode, reference):
            return False
        row = EfficacyEpisode(
            user_id=user_id,
            state_id=state.id,
            generation=state.efficacy_generation,
            run_id=episode.run_id,
            message_id=episode.message_id,
            terminal_at=episode.terminal_at,
            observations=[item.model_dump(mode="json") for item in episode.observations],
            config_fingerprint=episode.config_fingerprint,
            feedback=EfficacyFeedback(feedback).value if feedback else None,
        )
        self.db.add(row)
        await self._refresh(state, [*rows, row], reference)
        return True

    async def apply_feedback(
        self,
        user_id: UUID,
        message_id: UUID,
        verdict: EfficacyFeedback,
        *,
        now: datetime,
    ) -> bool:
        """Replace one utility contribution; never fabricate a factual result."""
        reference = _utc(now)
        feedback = EfficacyFeedback(verdict)
        state = await self._locked_state(user_id)
        if state is None:
            return False
        rows = await self._rows(state)
        row = next((item for item in rows if item.message_id == message_id), None)
        if row is None or not self._current(row.terminal_at, reference):
            return False
        row.feedback = feedback.value
        await self._refresh(state, rows, reference)
        return True

    async def _locked_state(self, user_id: UUID) -> PsycheState | None:
        with self.db.no_autoflush:
            owner = await self.db.scalar(
                select(User.id).where(User.id == user_id).with_for_update()
            )
            if owner is None:
                return None
            state: PsycheState | None = await self.db.scalar(
                select(PsycheState)
                .where(PsycheState.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            return state

    async def _rows(self, state: PsycheState) -> list[EfficacyEpisode]:
        result = await self.db.scalars(
            select(EfficacyEpisode)
            .where(
                EfficacyEpisode.user_id == state.user_id,
                EfficacyEpisode.state_id == state.id,
                EfficacyEpisode.generation == state.efficacy_generation,
            )
            .order_by(EfficacyEpisode.terminal_at, EfficacyEpisode.message_id)
            .execution_options(populate_existing=True)
        )
        return list(result)

    @staticmethod
    def _current(terminal_at: datetime, now: datetime) -> bool:
        return now - timedelta(days=EFFICACY_WINDOW_DAYS) <= _utc(terminal_at) <= now

    @classmethod
    def _eligible(cls, state: PsycheState, episode: EfficacyEpisodeInput, now: datetime) -> bool:
        if episode.epoch != EfficacyEpoch(state_id=state.id, generation=state.efficacy_generation):
            return False
        if not cls._current(episode.terminal_at, now):
            return False
        if state.efficacy_evicted_at is None or state.efficacy_evicted_message_id is None:
            return True
        return _key(episode.terminal_at, episode.message_id) > _key(
            state.efficacy_evicted_at, state.efficacy_evicted_message_id
        )

    @staticmethod
    def _same_episode(row: EfficacyEpisode, episode: EfficacyEpisodeInput) -> bool:
        return (
            row.run_id == episode.run_id
            and row.message_id == episode.message_id
            and _utc(row.terminal_at) == episode.terminal_at
            and row.config_fingerprint == episode.config_fingerprint
            and row.observations == [item.model_dump(mode="json") for item in episode.observations]
        )

    @staticmethod
    def _fits_retention(
        rows: Sequence[EfficacyEpisode], episode: EfficacyEpisodeInput, now: datetime
    ) -> bool:
        """Do not report a write that would immediately evict itself.

        Already accepted future rows keep their places during a clock rollback.
        Refusing an older arrival leaves both those rows and the replay floor
        untouched; chronological retention still has one global physical cap.
        """
        cutoff = now - timedelta(days=EFFICACY_WINDOW_DAYS)
        keys = sorted(
            _key(row.terminal_at, row.message_id) for row in rows if _utc(row.terminal_at) >= cutoff
        )
        return (
            len(keys) < EFFICACY_MAX_EPISODES
            or _key(episode.terminal_at, episode.message_id) > keys[-EFFICACY_MAX_EPISODES]
        )

    async def _refresh(
        self, state: PsycheState, rows: Sequence[EfficacyEpisode], now: datetime
    ) -> None:
        current = sorted(
            # A clock rollback can make an already accepted row temporarily
            # future-dated. Hide it in aggregation, never destroy it or advance
            # the replay floor into the future.
            (
                row
                for row in rows
                if _utc(row.terminal_at) >= now - timedelta(days=EFFICACY_WINDOW_DAYS)
            ),
            key=lambda row: _key(row.terminal_at, row.message_id),
        )
        retained = current[-EFFICACY_MAX_EPISODES:]
        keep = {row.message_id for row in retained}
        evicted = [row for row in rows if row.message_id not in keep]
        self._advance_floor(state, evicted)
        if evicted:
            await self.db.execute(
                delete(EfficacyEpisode).where(
                    EfficacyEpisode.state_id == state.id,
                    EfficacyEpisode.message_id.in_([row.message_id for row in evicted]),
                )
            )
        profile = build_profile(
            [_view(row) for row in retained], now=now, window_days=EFFICACY_WINDOW_DAYS
        )
        state.efficacy_profile = profile.model_dump(mode="json")
        await self.db.flush()

    @staticmethod
    def _advance_floor(state: PsycheState, evicted: Sequence[EfficacyEpisode]) -> None:
        if not evicted:
            return
        boundary = max(_key(row.terminal_at, row.message_id) for row in evicted)
        if state.efficacy_evicted_at is not None and state.efficacy_evicted_message_id is not None:
            boundary = max(
                boundary, _key(state.efficacy_evicted_at, state.efficacy_evicted_message_id)
            )
        state.efficacy_evicted_at, state.efficacy_evicted_message_id = boundary
