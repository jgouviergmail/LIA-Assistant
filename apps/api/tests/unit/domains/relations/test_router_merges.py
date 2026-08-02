"""Relations router — the merge write surface.

Same contract as the favorites star: the router delegates the RAW names (the
service owns the folding, so identity has one implementation) and answers 204
with no body. What it adds is the refusal path: an ambiguous merge is a 400,
not a silent no-op — the user must learn that nothing happened.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domains.relations.router import merge_relations, router, split_relation
from src.domains.relations.schemas import RelationMergeRequest

pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


class TestMergeEndpoint:
    async def test_it_delegates_the_raw_names_and_answers_204(self) -> None:
        service = MagicMock(merge_relations=AsyncMock(return_value="alice vernier"))
        user = _user()
        payload = RelationMergeRequest(source="0612345678", target="Alice Vernier")

        with patch("src.domains.relations.router.RelationsService", return_value=service) as ctor:
            response = await merge_relations(payload=payload, current_user=user)

        ctor.assert_called_once_with(user.id)
        service.merge_relations.assert_awaited_once_with(
            source="0612345678", target="Alice Vernier"
        )
        assert response.status_code == 204

    async def test_an_ambiguous_merge_is_a_400_not_a_silent_no_op(self) -> None:
        service = MagicMock(merge_relations=AsyncMock(side_effect=ValueError("same relationship")))

        with (
            patch("src.domains.relations.router.RelationsService", return_value=service),
            pytest.raises(HTTPException) as raised,
        ):
            await merge_relations(
                payload=RelationMergeRequest(source="Alice", target="Alice"), current_user=_user()
            )

        assert raised.value.status_code == 400


class TestSplitEndpoint:
    async def test_it_delegates_the_raw_name_and_answers_204(self) -> None:
        service = MagicMock(split_relation=AsyncMock(return_value=True))

        with patch("src.domains.relations.router.RelationsService", return_value=service):
            response = await split_relation(name="0612345678", current_user=_user())

        service.split_relation.assert_awaited_once_with("0612345678")
        assert response.status_code == 204

    async def test_undoing_something_never_merged_still_answers_204(self) -> None:
        """Idempotent, like unstarring: the end state is what was asked for."""
        service = MagicMock(split_relation=AsyncMock(return_value=False))

        with patch("src.domains.relations.router.RelationsService", return_value=service):
            response = await split_relation(name="Inconnu", current_user=_user())

        assert response.status_code == 204


class TestRoutesAreDeclared:
    def test_the_merge_routes_exist(self) -> None:
        paths = {(route.path, tuple(sorted(route.methods))) for route in router.routes}

        assert ("/relations/merges", ("POST",)) in paths
        assert ("/relations/merges/{name}", ("DELETE",)) in paths

    def test_they_are_declared_before_the_catch_all_detail_route(self) -> None:
        """`/relations/{name}` would otherwise swallow `/relations/merges`.

        FastAPI matches in declaration order, so a literal segment must be
        registered before the parameterised one that could absorb it.
        """
        paths = [route.path for route in router.routes]

        assert paths.index("/relations/merges") < paths.index("/relations/{name}")
