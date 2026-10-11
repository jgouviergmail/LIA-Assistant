"""Whole owned reset scope is fingerprinted in bounded cursors; raw private fields never leave it."""

import inspect
import json
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.psyche.engine import PsycheEngine
from src.domains.psyche.management_projection import project_psyche_state
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.psyche.reset_policy import apply_psyche_reset
from src.domains.psyche.schemas import PsycheResetRequest
from src.domains.psyche.service import PsycheService
from src.domains.users.models import User


class PsycheResetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    states: int = Field(ge=0, le=1)
    history: int = Field(ge=0)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]


async def psyche_reset_snapshot(
    db: AsyncSession, actor_id: UUID, request: PsycheResetRequest, *, locked: bool = False
) -> PsycheResetSnapshot:
    digest = sha256(inspect.getsource(apply_psyche_reset).encode())
    counts: dict[str, int] = {}
    for name, model in (("states", PsycheState), ("history", PsycheHistory)):
        columns = tuple(model.__table__.columns)
        digest.update(json.dumps([name, [column.name for column in columns]]).encode())
        statement = select(*columns).where(model.user_id == actor_id).order_by(model.id)
        if locked:
            statement = statement.with_for_update()
        cursor = await db.stream(statement.execution_options(yield_per=200))
        count = 0
        try:
            async for row in cursor.mappings():
                digest.update(
                    json.dumps(dict(row), sort_keys=True, default=str, allow_nan=False).encode()
                )
                digest.update(b"\n")
                count += 1
        finally:
            await cursor.close()
        counts[name] = count
    stored = await db.scalar(
        select(PsycheState)
        .where(PsycheState.user_id == actor_id)
        .execution_options(populate_existing=True)
    )
    owner = await db.scalar(
        select(User).where(User.id == actor_id).execution_options(populate_existing=True)
    )
    if owner is None:
        raise ValueError("Reset owner unavailable")
    digest.update(str(owner.personality_id).encode())
    before: dict[str, JsonValue] = {}
    after: dict[str, JsonValue] = {}
    if stored is not None and request.level != "purge":
        traits, override = await PsycheService(db)._load_personality_traits_and_override(actor_id)
        baseline = PsycheEngine.compute_pad_baseline(
            traits,
            override,
            damping=settings.psyche_baseline_damping,
            dominance_center=settings.psyche_dominance_center,
        )
        observed, _ = project_psyche_state(stored)
        clone = PsycheState(
            **{
                column.name: getattr(stored, column.name)
                for column in PsycheState.__table__.columns
            }
        )
        apply_psyche_reset(clone, request.level, baseline)
        projected, _ = project_psyche_state(clone)
        old, new = observed.model_dump(mode="json"), projected.model_dump(mode="json")
        before = {name: value for name, value in old.items() if value != new[name]}
        after = {name: new[name] for name in before}
        digest.update(json.dumps(after, sort_keys=True, allow_nan=False).encode())
    return PsycheResetSnapshot(**counts, digest=digest.hexdigest(), before=before, after=after)
