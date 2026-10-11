"""Complete owned erasure comparison uses cursors, not display limits or model context."""

import json
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.models import UserActivityDay, UserHabit, UserHabitProfile


class HabitForgetSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    habits: int = Field(ge=0)
    profiles: int = Field(ge=0, le=1)
    activity_days: int = Field(ge=0)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_counts(self) -> dict[str, JsonValue]:
        return {
            "habits": self.habits,
            "profiles": self.profiles,
            "activity_days": self.activity_days,
        }


async def habit_forget_snapshot(
    db: AsyncSession, actor_id: UUID, *, locked: bool = False
) -> HabitForgetSnapshot:
    digest = sha256()
    counts: dict[str, int] = {}
    for name, model in (
        ("habits", UserHabit),
        ("profiles", UserHabitProfile),
        ("activity_days", UserActivityDay),
    ):
        columns = tuple(model.__table__.columns)
        digest.update(
            json.dumps([name, [column.name for column in columns]], separators=(",", ":")).encode()
        )
        statement = select(*columns).where(model.user_id == actor_id).order_by(model.id)
        if locked:
            statement = statement.with_for_update()
        cursor = await db.stream(statement.execution_options(yield_per=200))
        count = 0
        try:
            async for row in cursor.mappings():
                digest.update(
                    json.dumps(
                        dict(row),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                        allow_nan=False,
                    ).encode()
                )
                digest.update(b"\n")
                count += 1
        finally:
            await cursor.close()
        counts[name] = count
    return HabitForgetSnapshot(**counts, digest=digest.hexdigest())
