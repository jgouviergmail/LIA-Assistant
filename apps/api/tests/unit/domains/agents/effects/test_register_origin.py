"""Separating what the person asked for from what LIA decided alone.

Both registers gained a fourth authorship (``proactive``) and, with it, a
reading problem: a heartbeat sweep runs on its own schedule and can outnumber
by far the handful of actions a person actually requested. Mixed into one list,
the four lines that matter drown under four hundred that do not — the same
argument that made Actions and Consultations two tabs rather than one.

So the two journals gained an ORIGIN filter, and the vocabulary is shared
between them: one enum, one translation to sources, two readers. Splitting the
rule in two is how the Actions tab and the Consultations tab would come to
disagree about what « mine » means.

``mine`` is deliberately everything that is NOT an initiative — user, scheduled
AND subagent — rather than an enumeration that a fifth authorship would silently
fall outside of. A new source added tomorrow shows up in the person's own list
by default, which is the safe direction: visible and possibly misfiled, never
invisible.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.origin import RegisterOrigin, origin_sources

pytestmark = pytest.mark.unit


class TestTheVocabulary:
    """Three readings, and each says exactly which authorships it holds."""

    def test_mine_holds_everything_the_person_set_in_motion(self) -> None:
        held = origin_sources(RegisterOrigin.MINE)
        assert held is not None
        assert set(held) == {
            EffectSource.USER.value,
            EffectSource.SCHEDULED.value,
            EffectSource.SUBAGENT.value,
        }

    def test_initiative_holds_only_what_lia_decided(self) -> None:
        assert origin_sources(RegisterOrigin.INITIATIVE) == (EffectSource.PROACTIVE.value,)

    def test_all_filters_nothing(self) -> None:
        """None, not the full tuple: the caller must add no WHERE clause."""
        assert origin_sources(RegisterOrigin.ALL) is None


class TestThePartitionIsExhaustiveAndDisjoint:
    """The property that makes the tabs watertight."""

    def test_every_authorship_belongs_to_exactly_one_reading(self) -> None:
        mine = set(origin_sources(RegisterOrigin.MINE) or ())
        initiative = set(origin_sources(RegisterOrigin.INITIATIVE) or ())

        assert not (mine & initiative), "an authorship would appear in two tabs"
        assert mine | initiative == {member.value for member in EffectSource}, (
            "a source belongs to no tab — it would be invisible in the interface "
            "while sitting in the register"
        )

    def test_a_new_authorship_cannot_silently_vanish(self) -> None:
        """The guard that survives a future addition.

        ``mine`` is defined by exclusion, so a fifth source lands there rather
        than nowhere. This pins that choice: were it re-written as a positive
        list, this test fails and the author has to decide on purpose.
        """
        mine = set(origin_sources(RegisterOrigin.MINE) or ())
        assert mine == {member.value for member in EffectSource} - {EffectSource.PROACTIVE.value}
