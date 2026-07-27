"""The destructive-action cap on background extractions.

This guard exists because of a measured event, not a hypothetical one: on
2026-07-27, replaying 45 real production conversation windows through the
shipped interest prompt, one ordinary turn — a plain "where am I on a map"
request — made the model emit 19 ``delete`` actions, the user's entire active
profile. Deletions carry no confidence field and are validated only for UUID
validity and ownership, so nothing else stood between that generation and the
data.

What these tests pin:
* the cap is inclusive — ordinary maintenance keeps working;
* above it, EVERY deletion of the batch goes, not just the surplus (a batch
  that proposes twenty deletions is a generation failure, not user intent);
* the survivors keep their order and identity — dropping a legitimate create
  because the same answer also contained deletions would be a second bug;
* the metric is best-effort — an observability failure must never turn a
  protective guard into an exception on a fire-and-forget path.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.utils import extraction_guards
from src.domains.agents.utils.extraction_guards import enforce_delete_cap
from src.domains.interests.schemas import ExtractedInterest
from src.domains.memories.schemas import ExtractedMemory

pytestmark = pytest.mark.unit


class _Action:
    """Minimal structural stand-in for a parsed extraction action."""

    def __init__(self, action: str, label: str = "") -> None:
        self.action = action
        self.label = label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.action}:{self.label}>"


def _batch(*actions: str) -> list[_Action]:
    return [_Action(action, label=f"{index}") for index, action in enumerate(actions)]


class TestUnderTheCap:
    def test_an_empty_batch_stays_empty(self) -> None:
        assert enforce_delete_cap([], kind="interests", cap=2) == []

    def test_a_batch_without_deletions_is_untouched(self) -> None:
        batch = _batch("create", "update", "create")

        assert enforce_delete_cap(batch, kind="interests", cap=2) is batch

    def test_the_cap_is_inclusive(self) -> None:
        # Ordinary maintenance ("I'm not into that any more") must keep working:
        # exactly `cap` deletions is a normal turn, not a runaway generation.
        batch = _batch("delete", "delete")

        assert enforce_delete_cap(batch, kind="interests", cap=2) is batch

    def test_a_single_deletion_passes_the_default_cap(self) -> None:
        batch = _batch("create", "delete")

        assert enforce_delete_cap(batch, kind="memory", cap=2) is batch


class TestOverTheCap:
    def test_every_deletion_goes_not_only_the_surplus(self) -> None:
        kept = enforce_delete_cap(_batch("delete", "delete", "delete"), kind="interests", cap=2)

        assert kept == []

    def test_the_non_destructive_actions_survive_in_order(self) -> None:
        batch = _batch("create", "delete", "update", "delete", "delete", "create")

        kept = enforce_delete_cap(batch, kind="interests", cap=1)

        assert [(a.action, a.label) for a in kept] == [
            ("create", "0"),
            ("update", "2"),
            ("create", "5"),
        ]

    def test_the_survivors_are_the_same_objects(self) -> None:
        # The applier mutates ORM rows from these objects; a copy would silently
        # drop the mutation.
        batch = _batch("create", "delete", "delete", "delete")

        kept = enforce_delete_cap(batch, kind="interests", cap=0)

        assert kept[0] is batch[0]

    def test_a_zero_cap_forbids_deletion_entirely(self) -> None:
        kept = enforce_delete_cap(_batch("delete", "create"), kind="memory", cap=0)

        assert [a.action for a in kept] == ["create"]

    def test_the_nineteen_deletion_case_that_motivated_the_guard(self) -> None:
        # The exact shape observed in production on 2026-07-27.
        batch = _batch(*(["delete"] * 19))

        assert enforce_delete_cap(batch, kind="interests", cap=2) == []


class TestRealSchemas:
    """The guard is structurally typed — prove it on the real payloads."""

    def test_interest_actions_are_accepted(self) -> None:
        batch = [
            ExtractedInterest(action="create", topic="escalade", category="sports", confidence=0.9),
            ExtractedInterest(action="delete", interest_id="a"),
            ExtractedInterest(action="delete", interest_id="b"),
            ExtractedInterest(action="delete", interest_id="c"),
        ]

        kept = enforce_delete_cap(batch, kind="interests", cap=2)

        assert [a.action for a in kept] == ["create"]

    def test_memory_actions_are_accepted(self) -> None:
        batch = [
            ExtractedMemory(action="delete", memory_id="a"),
            ExtractedMemory(action="delete", memory_id="b"),
            ExtractedMemory(action="delete", memory_id="c"),
            ExtractedMemory(action="create", content="x", category="preference"),
        ]

        kept = enforce_delete_cap(batch, kind="memory", cap=1)

        assert [a.action for a in kept] == ["create"]


class TestObservability:
    def test_the_rejection_is_counted_once_per_dropped_deletion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[dict[str, Any], float]] = []

        class _Counter:
            def labels(self, **labels: str) -> _Counter:
                self._labels = labels
                return self

            def inc(self, amount: float = 1.0) -> None:
                seen.append((self._labels, amount))

        monkeypatch.setattr(extraction_guards, "extraction_action_rejected_total", _Counter())

        enforce_delete_cap(_batch("delete", "delete", "delete"), kind="interests", cap=2)

        assert seen == [({"kind": "interests", "reason": "delete_cap"}, 3)]

    def test_nothing_is_counted_when_the_batch_is_admissible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[str] = []

        class _Counter:
            def labels(self, **_labels: str) -> _Counter:
                called.append("labels")
                return self

            def inc(self, amount: float = 1.0) -> None:  # pragma: no cover - must not run
                called.append("inc")

        monkeypatch.setattr(extraction_guards, "extraction_action_rejected_total", _Counter())

        enforce_delete_cap(_batch("delete"), kind="interests", cap=2)

        assert called == []

    def test_a_broken_metric_never_breaks_the_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Exploding:
            def labels(self, **_labels: str) -> None:
                raise RuntimeError("prometheus registry is gone")

        monkeypatch.setattr(extraction_guards, "extraction_action_rejected_total", _Exploding())

        kept = enforce_delete_cap(_batch("delete", "delete", "delete", "create"), kind="x", cap=1)

        assert [a.action for a in kept] == ["create"]
