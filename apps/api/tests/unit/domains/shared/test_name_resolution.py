"""One rule decides which entry of a directory a spoken name designates.

What must hold:
- an EXACT folded full name is decided first, and two homonyms are an
  ambiguity, never "the first one";
- otherwise every word said must be a WHOLE word of the name (two letters and
  up), an initial only completing one of them — never a fragment inside a word;
- one match is resolved, several are ambiguous, none is unknown;
- a directory naming one identity under several spellings counts it ONCE.
"""

from __future__ import annotations

import pytest

from src.domains.shared.name_resolution import (
    MIN_WORD_LEN,
    ResolutionStatus,
    resolve_name,
)

pytestmark = pytest.mark.unit

DIRECTORY = [
    ("Marie Dupont", "marie-dupont"),
    ("Paul Martin", "paul-martin"),
    ("Mei Lin", "mei-lin"),
    ("Mei Durand", "mei-durand"),
    ("Jean-Pierre Roux", "jean-pierre-roux"),
    ("Li Wei", "li-wei"),
]


class TestExactTier:
    def test_a_full_name_resolves_whatever_the_case_and_accents(self) -> None:
        resolution = resolve_name("MARIE dupont", DIRECTORY)

        assert resolution.status is ResolutionStatus.RESOLVED
        assert resolution.match == "marie-dupont"
        assert resolution.exact is True

    def test_two_homonyms_are_an_ambiguity_never_the_first_one(self) -> None:
        directory = [("Marie Dupont", "first"), ("Marie Dupont", "second")]

        resolution = resolve_name("Marie Dupont", directory)

        assert resolution.status is ResolutionStatus.AMBIGUOUS
        assert resolution.matches == ("first", "second")
        assert resolution.match is None

    def test_an_exact_match_wins_over_partial_ones(self) -> None:
        directory = [("Mei", "mei-alone"), ("Mei Lin", "mei-lin")]

        resolution = resolve_name("mei", directory)

        assert resolution.status is ResolutionStatus.RESOLVED
        assert resolution.match == "mei-alone"
        assert resolution.exact is True


class TestWordTier:
    def test_a_first_name_alone_resolves_when_unique(self) -> None:
        resolution = resolve_name("Paul", DIRECTORY)

        assert resolution.status is ResolutionStatus.RESOLVED
        assert resolution.match == "paul-martin"
        assert resolution.exact is False

    def test_a_last_name_alone_resolves_when_unique(self) -> None:
        assert resolve_name("dupont", DIRECTORY).match == "marie-dupont"

    def test_the_words_may_come_in_any_order(self) -> None:
        assert resolve_name("Martin Paul", DIRECTORY).match == "paul-martin"

    def test_a_shared_first_name_is_an_ambiguity(self) -> None:
        resolution = resolve_name("Mei", DIRECTORY)

        assert resolution.status is ResolutionStatus.AMBIGUOUS
        assert set(resolution.matches) == {"mei-lin", "mei-durand"}

    def test_an_initial_completes_a_word_and_settles_the_ambiguity(self) -> None:
        resolution = resolve_name("Mei D", DIRECTORY)

        assert resolution.status is ResolutionStatus.RESOLVED
        assert resolution.match == "mei-durand"

    def test_an_initial_alone_designates_nobody(self) -> None:
        assert resolve_name("M", DIRECTORY).status is ResolutionStatus.UNKNOWN

    def test_a_two_letter_name_is_a_word(self) -> None:
        # Two letters is a whole first name in several languages.
        assert MIN_WORD_LEN == 2
        assert resolve_name("Li", DIRECTORY).match == "li-wei"

    def test_a_fragment_inside_a_word_never_matches(self) -> None:
        assert resolve_name("pont", DIRECTORY).status is ResolutionStatus.UNKNOWN

    def test_every_word_said_must_be_in_the_name(self) -> None:
        assert resolve_name("Marie Martin", DIRECTORY).status is ResolutionStatus.UNKNOWN

    def test_a_word_said_twice_needs_the_name_to_carry_it_twice(self) -> None:
        assert resolve_name("Marie Marie", DIRECTORY).status is ResolutionStatus.UNKNOWN

    def test_hyphens_and_apostrophes_separate_words(self) -> None:
        assert resolve_name("Pierre", DIRECTORY).match == "jean-pierre-roux"
        directory = [("Liam O'Brien", "liam")]
        assert resolve_name("obrien", directory).status is ResolutionStatus.UNKNOWN
        assert resolve_name("brien", directory).match == "liam"

    def test_accents_fold_on_both_sides(self) -> None:
        directory = [("Hélène Garçon", "helene")]

        assert resolve_name("helene", directory).match == "helene"
        assert resolve_name("GARCON", directory).match == "helene"

    def test_an_email_is_not_a_name(self) -> None:
        resolution = resolve_name("marie.dupont@example.com", DIRECTORY)

        assert resolution.status is ResolutionStatus.UNKNOWN


class TestIdentities:
    def test_several_spellings_of_one_identity_count_once(self) -> None:
        directory = [("Marie Dupont", "marie"), ("Marie D.", "marie"), ("Paul Martin", "paul")]

        resolution = resolve_name("Marie", directory)

        assert resolution.status is ResolutionStatus.RESOLVED
        assert resolution.matches == ("marie",)

    def test_matches_keep_directory_order(self) -> None:
        directory = [("Mei Lin", "b"), ("Mei Durand", "a")]

        assert resolve_name("mei", directory).matches == ("b", "a")


class TestNothingToResolve:
    @pytest.mark.parametrize("spoken", ["", "   ", "!!", "😀"])
    def test_a_name_with_no_word_is_unknown(self, spoken: str) -> None:
        assert resolve_name(spoken, DIRECTORY).status is ResolutionStatus.UNKNOWN

    def test_an_empty_directory_resolves_nothing(self) -> None:
        resolution = resolve_name("Marie", [])

        assert resolution.status is ResolutionStatus.UNKNOWN
        assert resolution.matches == ()

    def test_a_blank_entry_never_matches(self) -> None:
        assert resolve_name("Marie", [("", "blank"), ("   ", "spaces")]).matches == ()
