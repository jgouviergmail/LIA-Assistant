"""Independent PostgreSQL transactions prove child comparison and external-work lock boundaries."""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.llm_usage import LLMUsage
from src.domains.agents.application.relation_debrief_build import (
    _ApprovedDebrief,
    execute_relation_debrief_build,
    prepare_relation_debrief_build,
)
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildPatch,
    RelationDebriefBuildRequest,
)
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.debrief.schemas import DebriefBody
from src.domains.relations.overview import OverviewEvidence
from src.domains.relations.schemas import RelationDetail
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_paid_debrief_work_releases_real_owner_and_child_locks(async_engine, monkeypatch):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"debrief-paid-lock-{owner}@example.test", is_active=True))
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)

            @asynccontextmanager
            async def session():
                try:
                    yield db
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise

            for module in (
                "src.domains.agents.application.relation_debrief_build",
                "src.domains.relations.debrief.service",
            ):
                monkeypatch.setattr(f"{module}.get_db_context", session)
            detail = RelationDetail(
                display_name="Alice",
                identity_confidence="exact",
                open_loops=[],
                recent_calls=[],
                memories=[],
            )
            monkeypatch.setattr(
                "src.domains.relations.debrief.service.build_overview_evidence",
                AsyncMock(
                    return_value=OverviewEvidence(
                        detail=detail, blocks={"open_loops": [{"subject": "Owned"}]}, unavailable=[]
                    )
                ),
            )
            monkeypatch.setattr(
                "src.domains.relations.debrief.service.RelationDebriefService._record_consultations",
                lambda *args: None,
            )

            async def write(**kwargs):
                async with AsyncSession(async_engine) as observer:
                    assert await observer.scalar(select(func.pg_backend_pid())) != await db.scalar(
                        select(func.pg_backend_pid())
                    )
                    assert (
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                        == owner
                    )
                    assert (
                        await observer.scalar(
                            select(RelationDebrief.id)
                            .where(RelationDebrief.user_id == owner)
                            .with_for_update(nowait=True)
                        )
                        is not None
                    )
                return DebriefBody(headline="Controlled", where_we_stand="Owned"), LLMUsage(
                    tokens_in=1,
                    tokens_out=1,
                    cost_eur=0,
                    model_name="controlled",
                    accounting_handled=True,
                )

            model = AsyncMock(side_effect=write)
            monkeypatch.setattr("src.domains.relations.debrief.service.write_debrief", model)
            draft = await prepare_relation_debrief_build(
                db, owner, RelationDebriefBuildRequest(name="Alice")
            )
            receipt = PreferenceWriteReceipt()
            await execute_relation_debrief_build(db, owner, draft, receipt)
            assert receipt.committed
            model.assert_awaited_once()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()


async def test_exact_debrief_comparison_waits_for_background_child_settlement(async_engine):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"debrief-child-{owner}@example.test", is_active=True))
        await seed.flush()
        seed.add(
            RelationDebrief(
                user_id=owner,
                name_key="alice",
                display_name="Alice",
                generated_for=date.today(),
                language="fr",
                scope_digest="a" * 64,
                state=DebriefState.EMPTY,
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as holder:
            draft = await prepare_relation_debrief_build(
                holder, owner, RelationDebriefBuildRequest(name="Alice")
            )
            await assert_independent_lock_control(holder, async_engine, owner)
            await holder.scalar(
                select(RelationDebrief.id).where(RelationDebrief.user_id == owner).with_for_update()
            )
            async with AsyncSession(async_engine) as claimant:
                assert await claimant.scalar(select(func.pg_backend_pid())) != await holder.scalar(
                    select(func.pg_backend_pid())
                )
                with pytest.raises(DBAPIError) as positive:
                    await claimant.scalar(
                        select(RelationDebrief.id)
                        .where(RelationDebrief.user_id == owner)
                        .with_for_update(nowait=True)
                    )
                assert getattr(positive.value.orig, "sqlstate", None) == "55P03"
                await claimant.rollback()
                await claimant.execute(text("SET LOCAL lock_timeout = '100ms'"))
                selected = RelationDebriefBuildPatch.model_validate(draft.intent).relation_debrief
                approved = _ApprovedDebrief(owner, draft, selected, PreferenceWriteReceipt())
                with pytest.raises(DBAPIError) as blocked:
                    await approved.claim(claimant)
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await claimant.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
