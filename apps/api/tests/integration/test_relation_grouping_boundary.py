"""Reassigning an already merged spelling changes both its old and new source identities."""

from contextlib import asynccontextmanager
from datetime import date

import pytest
from sqlalchemy import select

from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.models import RelationAlias
from src.domains.relations.service import RelationsService

pytestmark = pytest.mark.integration


async def test_reassigning_alias_invalidates_old_and_new_group_debriefs(
    async_session, test_user, monkeypatch
):
    owner = test_user.id
    async_session.add(
        RelationAlias(
            user_id=owner, alias_key="papa", canonical_key="jean dupont", alias_display_name="Papa"
        )
    )
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

    @asynccontextmanager
    async def session():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
    assert await RelationsService(owner).merge_relations(source="Papa", target="Bob") == "bob"
    remaining = list(
        await async_session.scalars(
            select(RelationDebrief.name_key).where(RelationDebrief.user_id == owner)
        )
    )
    assert remaining == ["other"]
