"""The claim's two state sets must PARTITION ``DebriefState``.

A state in neither set is claimable by nothing: its row is never rebuilt, never
released and never reported — the debrief simply stops existing for that
person, with no error anywhere. That is the ADR-085 class ("silent fallbacks on
unknown keys are how features die invisibly"), and the claim is the one place
in this domain where an omission is permanent rather than merely wrong.

The two sets carry different meaning, so the test asserts the partition rather
than a union: a state that landed in BOTH would let a settled answer be
re-claimed on an expired lease it never had.
"""

from src.domains.relations.debrief.models import DebriefState
from src.domains.relations.debrief.repository import _HELD, _SETTLED


def test_every_state_is_either_held_or_settled() -> None:
    unclassified = sorted(state.value for state in DebriefState if state not in (*_HELD, *_SETTLED))
    assert unclassified == [], (
        f"{unclassified} belong to neither _HELD nor _SETTLED, so no claim can "
        "ever reach a row in that state — see debrief/repository.py."
    )


def test_no_state_is_both_held_and_settled() -> None:
    both = sorted(state.value for state in _HELD if state in _SETTLED)
    assert both == [], f"{both} are claimable under two contradictory rules"


def test_the_two_sets_are_non_empty_and_disjointly_cover_the_enum() -> None:
    assert set(_HELD) | set(_SETTLED) == set(DebriefState)
    assert set(_HELD) and set(_SETTLED)
