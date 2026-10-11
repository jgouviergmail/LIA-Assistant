"""Original regeneration transitions share a fenced heartbeat owner."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.domains.meetings.models import Meeting, MeetingStage, MeetingStatus


def _threshold(seconds: int) -> ColumnElement[Any]:
    return func.now() - text(":regen_ttl * interval '1 second'").bindparams(regen_ttl=seconds)


def _owned_live(worker_id: str, seconds: int) -> tuple[ColumnElement[bool], ...]:
    return (
        Meeting.status == MeetingStatus.READY,
        Meeting.stage == MeetingStage.SYNTHESIZING,
        Meeting.worker_id == worker_id,
        Meeting.heartbeat_at > _threshold(seconds),
    )


class MeetingRegenerationRepositoryMixin:
    db: AsyncSession

    async def claim_regeneration(
        self, meeting_id: UUID, *, worker_id: str, ttl_seconds: int
    ) -> bool:
        result = await self.db.execute(
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.status == MeetingStatus.READY,
                Meeting.stage == MeetingStage.SYNTHESIZING,
                Meeting.worker_id.is_(None),
                func.coalesce(Meeting.heartbeat_at, Meeting.updated_at) > _threshold(ttl_seconds),
            )
            .values(worker_id=worker_id, heartbeat_at=func.now())
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def heartbeat_regeneration(
        self, meeting_id: UUID, *, worker_id: str, ttl_seconds: int
    ) -> bool:
        result = await self.db.execute(
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                *_owned_live(worker_id, ttl_seconds),
            )
            .values(heartbeat_at=func.now())
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def begin_regenerate(
        self, meeting_id: UUID, *, values: dict[str, Any] | None = None, commit: bool = True
    ) -> bool:
        """``ready`` (idle) → ``ready`` + ``stage=synthesizing``. True iff this call did it.

        The status stays READY so the minutes remain readable while the new
        ones are computed; the stage is the progress the page shows. ``values``
        (ADR-259: the template the rebuild must use) ride on the same UPDATE,
        so the job never reads a ref the claim did not write.
        """
        stmt = (
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.status == MeetingStatus.READY,
                Meeting.stage.is_(None),
            )
            .values(
                stage=MeetingStage.SYNTHESIZING,
                worker_id=None,
                heartbeat_at=func.now(),
                last_error_code=None,
                last_error_message=None,
                **(values or {}),
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        if commit:
            await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def finish_regenerate(
        self,
        meeting_id: UUID,
        *,
        values: dict[str, Any],
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_cache: int = 0,
        cost_eur: float | None = None,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Publish regenerated minutes, clear the stage and ADD the pass to the meeting's spend.

        Every rebuild is paid; the row keeps the sum of every pass (the initial
        synthesis included) so the page states what the minutes cost in total.
        """
        spend: dict[str, Any] = {
            "synthesis_tokens_in": Meeting.synthesis_tokens_in + tokens_in,
            "synthesis_tokens_out": Meeting.synthesis_tokens_out + tokens_out,
            "synthesis_tokens_cache": Meeting.synthesis_tokens_cache + tokens_cache,
        }
        if cost_eur is not None:
            spend["synthesis_cost_eur"] = func.coalesce(Meeting.synthesis_cost_eur, 0.0) + cost_eur
        owned = _owned_live(worker_id, ttl_seconds)
        result = await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id, *owned)
            .values(stage=None, worker_id=None, heartbeat_at=None, **values, **spend)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
        """``ready`` + ``stage`` older than the lease TTL → stage cleared, error recorded (ADR-259).

        Heartbeats determine the current owner's lifetime. Legacy queued rows
        without a heartbeat use their original update timestamp.
        """
        threshold = func.now() - text(":s * interval '1 second'").bindparams(s=older_than_seconds)
        stmt = (
            update(Meeting)
            .where(
                Meeting.status == MeetingStatus.READY,
                Meeting.stage.is_not(None),
                func.coalesce(Meeting.heartbeat_at, Meeting.updated_at) < threshold,
            )
            .values(
                stage=None,
                worker_id=None,
                heartbeat_at=None,
                last_error_code="regeneration_interrupted",
                last_error_message="",
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def fail_regenerate(
        self,
        meeting_id: UUID,
        *,
        code: str,
        message: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Clear the stage and record why the regeneration failed; the old minutes stay."""
        owned = _owned_live(worker_id, ttl_seconds)
        result = await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id, *owned)
            .values(
                stage=None,
                worker_id=None,
                heartbeat_at=None,
                last_error_code=code,
                last_error_message=message,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]
