"""Declaring (and undoing) a merge — every way it can be asked wrongly.

Merging is the one CRM write that changes what a relationship IS, so the
service refuses anything ambiguous rather than guessing, and stays idempotent
so a double-click cannot create a second identity.

The most important property is negative: **a cycle is structurally
impossible**. Merging B into A when A is already merged into B resolves the
target to B first, sees source == target, and does nothing. There is no cycle
to detect at read time because none can be written.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.service import RelationsService

pytestmark = pytest.mark.unit


def _alias_row(alias: str, canonical: str):
    return SimpleNamespace(alias_key=alias, canonical_key=canonical, alias_display_name=alias)


def _patched(existing=()):
    """Patch the alias repository, exposing what was written."""
    repo = SimpleNamespace(
        list_for_user=AsyncMock(return_value=[_alias_row(a, c) for a, c in existing]),
        merge=AsyncMock(),
        split=AsyncMock(return_value=True),
    )
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace()

    return (
        patch("src.domains.relations.service.get_db_context", _ctx),
        patch("src.domains.relations.service.RelationAliasRepository", return_value=repo),
        repo,
    )


async def _merge(source: str, target: str, existing=()):
    ctx, repo_patch, repo = _patched(existing)
    with ctx, repo_patch:
        result = await RelationsService(uuid4()).merge_relations(source=source, target=target)
    return result, repo


async def _split(name: str, existing=()):
    ctx, repo_patch, repo = _patched(existing)
    with ctx, repo_patch:
        result = await RelationsService(uuid4()).split_relation(name)
    return result, repo


class TestTheNominalMerge:
    async def test_the_source_becomes_an_alias_of_the_target(self) -> None:
        _, repo = await _merge("0612345678", "Alice Vernier")

        repo.merge.assert_awaited_once()
        kwargs = repo.merge.await_args.kwargs
        assert kwargs["alias_key"] == "0612345678"
        assert kwargs["canonical_key"] == "alice vernier"

    async def test_the_merged_away_spelling_is_kept_for_the_undo(self) -> None:
        """The undo must be able to NAME what it splits back out."""
        _, repo = await _merge("0612345678", "Alice Vernier")

        assert repo.merge.await_args.kwargs["alias_display_name"] == "0612345678"

    async def test_it_reports_the_canonical_identity(self) -> None:
        result, _ = await _merge("0612345678", "Alice Vernier")

        assert result == "alice vernier"


class TestMergingIntoAnAlreadyMergedRelationship:
    async def test_the_target_resolves_to_its_canonical(self) -> None:
        """Merging X into B, where B already belongs to C, stores X→C.

        Storing X→B would build a chain, and every read would then have to
        walk it. The table stays flat instead.
        """
        _, repo = await _merge("papa", "B", existing=[("b", "c")])

        assert repo.merge.await_args.kwargs["canonical_key"] == "c"


class TestNothingAmbiguousIsAccepted:
    @pytest.mark.parametrize(
        ("source", "target"),
        [
            ("Alice Vernier", "Alice Vernier"),
            ("alice vernier", "ALICE VERNIER"),
            ("  Alice Vernier  ", "Alice Vernier"),
        ],
    )
    async def test_merging_a_relationship_with_itself_is_refused(
        self, source: str, target: str
    ) -> None:
        """Same identity after folding: there is nothing to merge."""
        with pytest.raises(ValueError, match="same relationship"):
            await _merge(source, target)

    @pytest.mark.parametrize(("source", "target"), [("", "Alice"), ("Alice", ""), ("  ", "Alice")])
    async def test_a_blank_side_is_refused(self, source: str, target: str) -> None:
        with pytest.raises(ValueError, match="name"):
            await _merge(source, target)


class TestIdempotence:
    async def test_merging_twice_writes_nothing_the_second_time(self) -> None:
        """A double-click must not create a second identity."""
        _, repo = await _merge(
            "0612345678", "Alice Vernier", existing=[("0612345678", "alice vernier")]
        )

        repo.merge.assert_not_awaited()

    async def test_it_still_reports_the_canonical_identity(self) -> None:
        result, _ = await _merge(
            "0612345678", "Alice Vernier", existing=[("0612345678", "alice vernier")]
        )

        assert result == "alice vernier"


class TestNoCycleCanBeWritten:
    async def test_merging_back_the_other_way_is_a_no_op(self) -> None:
        """A→B exists; merging B into A resolves A to B, sees B==B, stops.

        This is why the reader needs no cycle detection: the writer cannot
        produce one.
        """
        _, repo = await _merge(
            "Alice Vernier", "0612345678", existing=[("0612345678", "alice vernier")]
        )

        repo.merge.assert_not_awaited()


class TestUndo:
    async def test_it_splits_the_alias_back_out(self) -> None:
        result, repo = await _split("0612345678", existing=[("0612345678", "alice vernier")])

        assert result is True
        assert repo.split.await_args.kwargs["alias_key"] == "0612345678"

    async def test_splitting_something_that_was_never_merged(self) -> None:
        repo = SimpleNamespace(
            list_for_user=AsyncMock(return_value=[]),
            merge=AsyncMock(),
            split=AsyncMock(return_value=False),
        )
        import contextlib

        @contextlib.asynccontextmanager
        async def _ctx():
            yield SimpleNamespace()

        with (
            patch("src.domains.relations.service.get_db_context", _ctx),
            patch("src.domains.relations.service.RelationAliasRepository", return_value=repo),
        ):
            assert await RelationsService(uuid4()).split_relation("Inconnu") is False

    async def test_a_blank_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="name"):
            await _split("   ")
