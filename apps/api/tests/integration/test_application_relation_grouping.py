"""A grouping proposal pins source identities and invalidates only affected debriefs."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.relation_grouping import (
    execute_relation_grouping,
    prepare_relation_grouping,
)
from src.domains.agents.application.relation_grouping_schemas import RelationGroupingRequest
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.models import RelationAlias
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["merge", "split", "stale", "stale_debrief", "false_source_ack"]
)
async def test_grouping_preserves_source_data_and_exact_confirmed_identity(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    alias = RelationAlias(
        user_id=owner, alias_key="papa", canonical_key="jean dupont", alias_display_name="Papa"
    )
    async_session.add(alias)
    async_session.add_all(
        [
            RelationDebrief(
                user_id=owner,
                name_key=key,
                display_name=key,
                generated_for=date.today(),
                language="fr",
                scope_digest="a" * 64,
                state=DebriefState.EMPTY,
            )
            for key in ("papa", "jean dupont", "bob", "other")
        ]
    )
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService.build",
        AsyncMock(side_effect=AssertionError("Grouping cannot start paid synthesis")),
    )
    request = (
        RelationGroupingRequest(action="split", source="Papa")
        if scenario == "split"
        else RelationGroupingRequest(action="merge", source="Papa", target="Bob")
    )
    draft = await prepare_relation_grouping(async_session, owner, request)
    assert (
        await async_session.scalar(
            select(RelationAlias.canonical_key).where(RelationAlias.id == alias.id)
        )
        == "jean dupont"
    )
    if scenario == "stale":
        await async_session.execute(
            update(RelationAlias).where(RelationAlias.id == alias.id).values(canonical_key="carol")
        )
        await async_session.commit()
        with pytest.raises(ResourceConflictError):
            await execute_relation_grouping(async_session, owner, draft, PreferenceWriteReceipt())
        return
    if scenario == "stale_debrief":
        await async_session.execute(
            update(RelationDebrief)
            .where(RelationDebrief.user_id == owner, RelationDebrief.name_key == "jean dupont")
            .values(display_name="Changed")
        )
        await async_session.commit()
        with pytest.raises(ResourceConflictError):
            await execute_relation_grouping(async_session, owner, draft, PreferenceWriteReceipt())
        return
    if scenario == "false_source_ack":
        monkeypatch.setattr(
            "src.domains.relations.service.RelationsService.merge_in_session",
            AsyncMock(return_value="bob"),
        )
        receipt = PreferenceWriteReceipt()
        with pytest.raises(ValueError, match="postcondition"):
            await execute_relation_grouping(async_session, owner, draft, receipt)
        assert not receipt.committed
        return
    receipt = PreferenceWriteReceipt()
    await execute_relation_grouping(async_session, owner, draft, receipt)
    assert receipt.committed
    saved = await async_session.scalar(
        select(RelationAlias.canonical_key).where(RelationAlias.id == alias.id)
    )
    assert saved == ("bob" if scenario == "merge" else None)
    remaining = set(
        await async_session.scalars(
            select(RelationDebrief.name_key).where(RelationDebrief.user_id == owner)
        )
    )
    assert remaining == ({"other"} if scenario == "merge" else {"bob", "other"})


@pytest.mark.parametrize("action", ["merge", "split"])
async def test_grouping_noop_retains_stored_debriefs(async_session, test_user, action):
    owner = test_user.id
    async_session.add(
        RelationAlias(
            user_id=owner, alias_key="papa", canonical_key="bob", alias_display_name="Papa"
        )
    )
    async_session.add(
        RelationDebrief(
            user_id=owner,
            name_key="bob",
            display_name="Bob",
            generated_for=date.today(),
            language="fr",
            scope_digest="a" * 64,
            state=DebriefState.EMPTY,
        )
    )
    await async_session.commit()
    request = RelationGroupingRequest(
        action=action,
        source="Papa" if action == "merge" else "Alice",
        target="Bob" if action == "merge" else None,
    )
    draft = await prepare_relation_grouping(async_session, owner, request)
    receipt = PreferenceWriteReceipt()
    await execute_relation_grouping(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.no_op
    assert (
        await async_session.scalar(
            select(RelationDebrief.name_key).where(RelationDebrief.user_id == owner)
        )
        == "bob"
    )
