"""Folding an identity, including the merges the USER declared.

``fold_name`` answers "are these literally the same spelling of a name". It
cannot know that ``0612345678`` and ``alice vernier`` are one relationship, or
that ``Papa`` is ``Jean Dupont`` — only the user knows, so only the user may
say it (merges are manual, never proposed).

The whole point of routing every merge through THIS object is ADR-185: one
implementation of "same person". A second place applying aliases would make
the list and the card disagree about who someone is.

The table is flat by construction — an alias never points at another alias —
so resolution is a single lookup: no chain to walk, no cycle to detect at
read time. The flattening happens once, at merge time.
"""

from __future__ import annotations

import pytest

from src.domains.relations.identity import IdentityResolver

pytestmark = pytest.mark.unit


class TestWithoutAnyMerge:
    def test_it_is_exactly_fold_name(self) -> None:
        resolver = IdentityResolver.from_pairs([])

        assert resolver.key("Alice Vernier") == "alice vernier"
        assert resolver.key("ALICE VERNIER") == resolver.key("alice vernier")

    def test_it_does_not_second_guess_fold_name(self) -> None:
        """Whatever fold_name separates stays separated here.

        Double spacing is NOT folded away (measured): "Alice  Vernier" is a
        different key from "Alice Vernier". Widening the fold would silently
        re-key every stored favorite, so the CRM offers the user a MERGE
        instead — which is exactly the case this feature exists for.
        """
        resolver = IdentityResolver.from_pairs([])

        assert resolver.key("Alice  Vernier") != resolver.key("Alice Vernier")

    def test_accents_fold_as_before(self) -> None:
        resolver = IdentityResolver.from_pairs([])

        assert resolver.key("Jérôme") == resolver.key("Jerome")

    def test_a_blank_name_has_no_identity(self) -> None:
        assert IdentityResolver.from_pairs([]).key("   ") == ""


class TestWithAMerge:
    def test_the_alias_answers_with_the_canonical_key(self) -> None:
        resolver = IdentityResolver.from_pairs([("0612345678", "alice vernier")])

        assert resolver.key("0612345678") == "alice vernier"

    def test_the_canonical_side_is_untouched(self) -> None:
        resolver = IdentityResolver.from_pairs([("0612345678", "alice vernier")])

        assert resolver.key("Alice Vernier") == "alice vernier"

    def test_an_unrelated_name_is_untouched(self) -> None:
        resolver = IdentityResolver.from_pairs([("0612345678", "alice vernier")])

        assert resolver.key("Marie Martin") == "marie martin"

    def test_raw_spellings_of_the_alias_also_resolve(self) -> None:
        """The alias key is folded, so any spelling of it lands on it first."""
        resolver = IdentityResolver.from_pairs([("papa", "jean dupont")])

        assert resolver.key("Papa") == "jean dupont"
        assert resolver.key("PAPA") == "jean dupont"


class TestTheKeysOfOneIdentity:
    def test_it_lists_the_canonical_and_everything_merged_into_it(self) -> None:
        resolver = IdentityResolver.from_pairs(
            [("0612345678", "alice vernier"), ("papa", "jean dupont")]
        )

        assert resolver.keys_of("alice vernier") == frozenset({"alice vernier", "0612345678"})

    def test_an_identity_with_no_merge_is_just_itself(self) -> None:
        resolver = IdentityResolver.from_pairs([])

        assert resolver.keys_of("marie martin") == frozenset({"marie martin"})

    def test_asking_from_the_alias_side_returns_the_whole_identity(self) -> None:
        """Whichever half the caller holds, the answer is the same set."""
        resolver = IdentityResolver.from_pairs([("0612345678", "alice vernier")])

        assert resolver.keys_of("0612345678") == resolver.keys_of("alice vernier")


class TestChainsAreFlattenedNotWalked:
    def test_a_chain_stored_flat_resolves_in_one_hop(self) -> None:
        """A→C and B→C, never A→B→C: the writer compresses the path."""
        resolver = IdentityResolver.from_pairs([("a", "c"), ("b", "c")])

        assert resolver.key("a") == "c"
        assert resolver.key("b") == "c"
        assert resolver.keys_of("c") == frozenset({"a", "b", "c"})

    def test_a_malformed_chain_never_loops(self) -> None:
        """Defence in depth: even if a chain reached the table, reading it
        terminates — one lookup, no recursion."""
        resolver = IdentityResolver.from_pairs([("a", "b"), ("b", "a")])

        assert resolver.key("a") in {"a", "b"}
        assert resolver.key("b") in {"a", "b"}


class TestAMalformedRowNeverCreatesAPhantom:
    """The writer refuses blank names, so a blank side can only come from a
    corrupted or hand-edited row. Reading one must not invent an identity."""

    def test_a_row_pointing_at_nothing_is_dropped(self) -> None:
        """`papa -> ""` would fold a real relationship into the empty identity,
        where it would silently join every other broken row."""
        resolver = IdentityResolver.from_pairs([("papa", "")])

        assert resolver.key("Papa") == "papa"
        assert resolver.keys_of("papa") == frozenset({"papa"})

    def test_a_row_with_no_alias_is_dropped(self) -> None:
        resolver = IdentityResolver.from_pairs([("", "jean dupont")])

        assert resolver.key("") == ""
        assert resolver.keys_of("jean dupont") == frozenset({"jean dupont"})


class TestMergeTargetResolution:
    """What the WRITER must compute before storing a merge."""

    def test_merging_into_an_alias_targets_its_canonical(self) -> None:
        """Merging X into B, where B is already merged into C, stores X→C."""
        resolver = IdentityResolver.from_pairs([("b", "c")])

        assert resolver.canonical("b") == "c"

    def test_canonical_of_an_unknown_key_is_itself(self) -> None:
        assert IdentityResolver.from_pairs([]).canonical("marie martin") == "marie martin"
