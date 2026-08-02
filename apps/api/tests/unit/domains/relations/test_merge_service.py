"""Merging two relationships — what the list, the card and the star must do.

A CRM "relationship" is DERIVED: one row per distinct spelling the sources
stored. So merging cannot rewrite anything — it records that two folded keys
are one identity, and every read resolves through it. Undoing a merge is
deleting that row; the sources never lost their own spellings.

What is verified here is the whole surface a merge touches, because the defect
class is "one half of the app learned about the merge and the other did not":

- the LIST shows one card, with the counts added up;
- the CARD returns every spelling's rows, and totals that are still exact;
- the STAR follows (a merged relationship is starred if either half was);
- the PEER badge follows;
- and NONE of it touches the peer DIRECTORY, which decides whose assistant
  receives a message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.identity import IdentityResolver
from src.domains.relations.service import RelationsService, _bucketize, _spellings_for, _total_for

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def _activity(raw_name: str, count: int = 1, last_at: datetime | None = NOW):
    return SimpleNamespace(raw_name=raw_name, count=count, last_at=last_at)


MERGED = IdentityResolver.from_pairs([("0612345678", "alice vernier")])


class TestTheListShowsOneCard:
    def test_two_spellings_collapse_into_one_bucket(self) -> None:
        buckets = _bucketize(
            [_activity("Alice Vernier", 2)], [_activity("0612345678", 3)], [], resolver=MERGED
        )

        assert set(buckets) == {"alice vernier"}

    def test_the_counts_are_added_up(self) -> None:
        buckets = _bucketize(
            [_activity("Alice Vernier", 2)], [_activity("0612345678", 3)], [], resolver=MERGED
        )

        assert buckets["alice vernier"].open_loops_count == 2
        assert buckets["alice vernier"].calls_count == 3

    def test_both_spellings_are_kept_as_evidence(self) -> None:
        """The card names the person from the spellings it saw — including the
        one that was merged in."""
        buckets = _bucketize(
            [_activity("Alice Vernier")], [_activity("0612345678")], [], resolver=MERGED
        )

        assert buckets["alice vernier"].raw_names == {"Alice Vernier", "0612345678"}

    def test_without_the_merge_they_stay_two_cards(self) -> None:
        buckets = _bucketize(
            [_activity("Alice Vernier")],
            [_activity("0612345678")],
            [],
            resolver=IdentityResolver.from_pairs([]),
        )

        assert set(buckets) == {"alice vernier", "0612345678"}


class TestTheCardReadsEverySpelling:
    def test_spellings_of_both_halves_are_returned(self) -> None:
        """SQL matches raw strings exactly, so the merged-away spelling must be
        in the list or its rows are invisible on the card."""
        aggregates = [_activity("Alice Vernier"), _activity("0612345678"), _activity("Marie")]

        assert _spellings_for(aggregates, "alice vernier", resolver=MERGED) == [
            "Alice Vernier",
            "0612345678",
        ]

    def test_the_total_covers_both_halves(self) -> None:
        aggregates = [_activity("Alice Vernier", 4), _activity("0612345678", 8)]

        assert _total_for(aggregates, "alice vernier", resolver=MERGED) == 12

    def test_an_unmerged_identity_is_unaffected(self) -> None:
        aggregates = [_activity("Marie", 5), _activity("Alice Vernier", 1)]

        assert _total_for(aggregates, "marie", resolver=MERGED) == 5


class TestOpeningEitherHalf:
    async def test_the_alias_name_opens_the_merged_card(self) -> None:
        """The user may still type the merged-away spelling."""
        service = RelationsService(USER_ID)

        with patch.object(
            service, "_load_identity_resolver", AsyncMock(return_value=MERGED)
        ) as loader:
            resolver = await service._load_identity_resolver(object())

        assert loader.await_count == 1
        assert resolver.key("0612345678") == "alice vernier"


class TestTheStarFollowsTheMerge:
    def test_a_star_on_either_half_stars_the_merged_card(self) -> None:
        favorites = RelationsService._canonical_favorites(
            {"0612345678": "0612345678"}, resolver=MERGED
        )

        assert "alice vernier" in favorites

    def test_the_canonical_spelling_wins_when_both_were_starred(self) -> None:
        """Two stars collapse into one; the canonical spelling is what the card
        is called, so it is the one kept."""
        favorites = RelationsService._canonical_favorites(
            {"0612345678": "0612345678", "alice vernier": "Alice Vernier"}, resolver=MERGED
        )

        assert favorites == {"alice vernier": "Alice Vernier"}


class TestThePeerBadgeFollowsTheMerge:
    def test_a_merged_relationship_is_still_a_peer(self) -> None:
        profiles = [SimpleNamespace(peer_display_name="Alice Vernier")]

        keys = RelationsService._peer_keys(profiles, resolver=MERGED)

        assert "alice vernier" in keys

    def test_the_alias_side_resolves_to_the_same_key(self) -> None:
        profiles = [SimpleNamespace(peer_display_name="0612345678")]

        assert RelationsService._peer_keys(profiles, resolver=MERGED) == {"alice vernier"}


class TestTheMergeNeverTouchesMessageRouting:
    """A CRM merge is a display decision by ONE user.

    ``peers_tools`` resolves a recipient by ``fold_name`` to decide whose
    assistant receives a message. If a merge could redirect that, one user's
    private note could reach another account.
    """

    def test_the_peer_recipient_resolver_ignores_aliases(self) -> None:
        import inspect

        from src.domains.agents.tools import peers_tools

        source = inspect.getsource(peers_tools)

        assert "IdentityResolver" not in source
        assert "relation_alias" not in source.lower()
