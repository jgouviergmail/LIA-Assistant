"""The silent corrections a turn makes to itself (B8, lot 7.6).

Six corrections happen mid-turn and change what comes out; every one of them was
counted in Prometheus, where an operator sees a RATE. A person debugging ONE
exchange needs the opposite question answered: which of them happened HERE.

Three properties this collector must have, and all three have been got wrong in
this codebase before:

- **it never costs a turn anything**: silent outside a turn, so a probe, a test
  or a background task can call the producers without knowing it exists;
- **the vocabulary is CLOSED**: a kind nobody declared reaches the panel as a
  word no reader can interpret, and the frontend resolves each kind to a
  sentence;
- **it is BOUNDED and says so**: a loop repairing the same history every
  iteration would otherwise grow the list without limit, and a capped list that
  does not say it is capped reads as an exact count (ADR-185).
"""

from __future__ import annotations

import pytest

from src.core.turn_verdicts import (
    MAX_VERDICTS_PER_TURN,
    VERDICT_KINDS,
    collected_verdicts,
    dropped_verdicts,
    is_collecting_verdicts,
    note_verdict,
    verdict_collector,
)

pytestmark = pytest.mark.unit


class TestItNeverCostsATurnAnything:
    async def test_noting_outside_a_turn_does_nothing_at_all(self) -> None:
        note_verdict("reasoning_coerced", "high->medium")

        assert collected_verdicts() == ()
        assert is_collecting_verdicts() is False

    async def test_an_undeclared_kind_is_dropped_rather_than_stored(self) -> None:
        # A typo reaching the panel is a word nobody can read: the frontend
        # resolves each kind to a sentence, and there is none for a typo.
        async with verdict_collector():
            note_verdict("reasonning_coerced", "typo")

            assert collected_verdicts() == ()

    async def test_the_collector_is_released_on_the_way_out(self) -> None:
        async with verdict_collector():
            note_verdict("history_repaired", "tool_calls")

        assert is_collecting_verdicts() is False
        assert collected_verdicts() == ()

    async def test_it_is_released_even_when_the_body_raises(self) -> None:
        with pytest.raises(RuntimeError):
            async with verdict_collector():
                note_verdict("history_repaired")
                raise RuntimeError("the turn died")

        assert is_collecting_verdicts() is False


class TestWhatItRecords:
    @pytest.mark.parametrize("kind", sorted(VERDICT_KINDS))
    async def test_every_declared_kind_is_accepted(self, kind: str) -> None:
        async with verdict_collector():
            note_verdict(kind, "d")

            assert [row.kind for row in collected_verdicts()] == [kind]

    async def test_it_keeps_the_order_things_happened_in(self) -> None:
        async with verdict_collector():
            note_verdict("parameter_clamped", "max_results")
            note_verdict("history_repaired", "call_block")
            note_verdict("quota_refused")

            assert [row.kind for row in collected_verdicts()] == [
                "parameter_clamped",
                "history_repaired",
                "quota_refused",
            ]

    async def test_the_detail_travels_with_its_kind(self) -> None:
        async with verdict_collector():
            note_verdict("reasoning_coerced", "minimal->low")

            row = collected_verdicts()[0]
            assert (row.kind, row.detail) == ("reasoning_coerced", "minimal->low")

    async def test_a_verdict_may_carry_no_detail(self) -> None:
        async with verdict_collector():
            note_verdict("quota_refused")

            assert collected_verdicts()[0].detail is None

    async def test_the_same_correction_twice_is_two_rows(self) -> None:
        # Repairing two orphan calls is two repairs: folding them would hide
        # how much of the history the turn had to rewrite.
        async with verdict_collector():
            note_verdict("history_repaired", "tool_calls")
            note_verdict("history_repaired", "tool_calls")

            assert len(collected_verdicts()) == 2


class TestItIsBoundedAndSaysSo:
    async def test_it_stops_at_the_cap(self) -> None:
        async with verdict_collector():
            for _ in range(MAX_VERDICTS_PER_TURN + 10):
                note_verdict("history_repaired")

            assert len(collected_verdicts()) == MAX_VERDICTS_PER_TURN

    async def test_what_the_cap_dropped_is_counted_rather_than_lost(self) -> None:
        # A capped list that does not say it is capped reads as an exact count.
        async with verdict_collector():
            for _ in range(MAX_VERDICTS_PER_TURN + 7):
                note_verdict("history_repaired")

            assert dropped_verdicts() == 7

    async def test_a_turn_under_the_cap_dropped_nothing(self) -> None:
        async with verdict_collector():
            note_verdict("history_repaired")

            assert dropped_verdicts() == 0


class TestTurnsDoNotLeakIntoEachOther:
    async def test_a_second_turn_starts_empty(self) -> None:
        async with verdict_collector():
            note_verdict("history_repaired")
        async with verdict_collector():
            assert collected_verdicts() == ()

    async def test_a_nested_collector_shadows_its_parent(self) -> None:
        # A sub-agent runs inside its own collector; its corrections belong to
        # its own turn, not to the one that delegated.
        async with verdict_collector() as outer:
            note_verdict("quota_refused")
            async with verdict_collector() as inner:
                note_verdict("history_repaired")
                assert len(inner) == 1
            assert len(outer) == 1
