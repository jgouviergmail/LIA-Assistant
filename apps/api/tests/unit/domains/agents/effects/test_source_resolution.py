"""Who asked for this turn — decided once, read everywhere (ADR-248).

The same ternary existed in four places when this file was written:
``decisions.py:102``, ``runtime.py:301``, ``scope.py:141`` and
``treatments.py:231``, each spelling ``"scheduled" if automated else "user"``.
Four copies of a rule are four opportunities for one of them to stop agreeing,
and the amendment that adds a third origin would have had to find all four —
the exact shape ADR-248 forbids for the ReAct stop condition, applied to the
register's own vocabulary.

The third origin matters and is not cosmetic. ``scheduled`` is the person's own
instruction, deferred: they wrote the routine, so its actions belong beside the
ones they typed. ``proactive`` is LIA deciding — a morning briefing that reads
their mail, a heartbeat that reaches out. Measured 2026-09-07: 228 proactive
runs over fourteen days produced no register row at all, while every
conversational surface was recorded in full.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.source import resolve_source

pytestmark = pytest.mark.unit


def _context(*, automated: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-1",
        execution_mode="pipeline",
        is_automated_source=automated,
    )


class TestTheThreeOriginsAreDistinguished:
    """One predicate, three answers, no caller re-deriving any of them."""

    def test_a_typed_turn_is_the_persons_own(self) -> None:
        assert resolve_source(_context()) == EffectSource.USER.value

    def test_a_routine_stays_scheduled(self) -> None:
        """The routine's actions must not move out of the person's lists.

        They wrote it; the scheduler only chose the minute. Reading it as
        ``proactive`` would relocate every existing row — fourteen decisions and
        thirty-one consultations at the time of writing — into a tab their
        owner never put them in.
        """
        assert resolve_source(_context(automated=True)) == EffectSource.SCHEDULED.value

    def test_lia_taking_the_initiative_is_its_own_origin(self) -> None:
        assert resolve_source(None, proactive=True) == EffectSource.PROACTIVE.value

    def test_proactive_wins_over_the_automation_flag(self) -> None:
        """A proactive run may carry an automated context; it is still LIA's.

        Both are true — nobody typed it, and LIA chose it — so the more
        specific answer must be the one that survives, or every proactive run
        would be filed as a routine the person configured.
        """
        assert (
            resolve_source(_context(automated=True), proactive=True) == EffectSource.PROACTIVE.value
        )


class TestTheScopeStaysTheAuthority:
    """A published scope already decided; the predicate must not overrule it."""

    def test_a_scope_source_is_returned_verbatim(self) -> None:
        scope = SimpleNamespace(source=EffectSource.SUBAGENT.value)
        assert resolve_source(_context(), scope=scope) == EffectSource.SUBAGENT.value

    def test_a_scope_without_a_source_falls_through(self) -> None:
        scope = SimpleNamespace(source=None)
        assert resolve_source(_context(automated=True), scope=scope) == (
            EffectSource.SCHEDULED.value
        )


class TestOutsideAnyTurn:
    """A probe, a script or a boot check names no authority."""

    def test_no_context_and_no_flag_reads_as_the_person(self) -> None:
        """The pre-existing default, preserved deliberately.

        Every one of the four copies answered ``user`` here, and rows written
        under it exist. Changing that answer now would reclassify history.
        """
        assert resolve_source(None) == EffectSource.USER.value


class TestTheVocabularyIsClosed:
    """Whatever comes out is a value the registers accept."""

    @pytest.mark.parametrize(
        ("context", "scope", "proactive"),
        [
            (None, None, False),
            (None, None, True),
            (_context(), None, False),
            (_context(automated=True), None, False),
            (_context(), SimpleNamespace(source="subagent"), False),
        ],
    )
    def test_every_answer_is_a_declared_source(
        self, context: object, scope: object, proactive: bool
    ) -> None:
        answer = resolve_source(context, scope=scope, proactive=proactive)
        assert answer in {member.value for member in EffectSource}


class TestTheFlagWithoutAContext:
    """The turn factory holds the boolean, not the running context."""

    def test_an_explicit_flag_decides_alone(self) -> None:
        assert resolve_source(None, automated=True) == EffectSource.SCHEDULED.value
        assert resolve_source(None, automated=False) == EffectSource.USER.value

    def test_an_explicit_flag_overrides_the_context(self) -> None:
        """The caller that passes it knows better than the ambient context.

        A scheduled turn resumed from a HITL interrupt runs under a context
        rebuilt from the checkpoint; the factory's argument is what the
        original turn actually was.
        """
        assert resolve_source(_context(automated=False), automated=True) == (
            EffectSource.SCHEDULED.value
        )

    def test_proactive_still_wins(self) -> None:
        assert resolve_source(None, automated=True, proactive=True) == (
            EffectSource.PROACTIVE.value
        )
