"""What a condition routine has already seen (ADR-322).

The ledger used to hold ONE fingerprint of the whole matching SET, so any
change to the set read as a new fact — including a set that SHRANK. Checked
twice a day that was rare; checked every ten minutes it is systematic: an
agenda watch re-fired each time an event ended, a task watch each time a task
was ticked off, a mail watch each time one of two matching mails was read.

A fact is now new when its KEY was never seen. What must hold:

- a fact that disappears and comes back is not new;
- a new fact the tick could not serve (daily cap, pending question, failed
  run) stays new, so the next check tries again;
- a fact still present is never evicted by the bound, or it would read as new;
- every write is a NEW dict (a JSONB column mutated in place is never saved).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domains.scheduled_actions.condition_ledger import (
    CONDITION_LEDGER_MAX_KEYS,
    ConditionLedger,
    with_check_error,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 25, 12, 10, tzinfo=UTC)


class TestReading:
    def test_nothing_stored_has_seen_nothing(self) -> None:
        ledger = ConditionLedger.read(None)

        assert ledger.seen == ()
        assert ledger.last_checked_at is None
        assert ledger.last_check_error is None

    def test_a_set_fingerprint_from_before_is_not_a_list_of_facts(self) -> None:
        # The first check after the upgrade serves what it finds: announcing an
        # awaited fact twice is recoverable, never announcing it is not.
        ledger = ConditionLedger.read({"last_fingerprint": "ab12", "last_fired_at": "x"})

        assert ledger.seen == ()

    def test_a_check_the_usage_ceiling_refused_reads_back_as_such(self) -> None:
        # Written by the executor when the account's ceiling stood the check
        # aside: the routine's card says why nothing was checked.
        state = ConditionLedger.read({"seen": ["a"]}).after_check(
            at=AT, present=(), fired=False, error="quota_blocked"
        )

        ledger = ConditionLedger.read(state)

        assert ledger.last_check_error == "quota_blocked"
        # Nothing was read, so nothing the routine had seen is forgotten.
        assert ledger.seen == ("a",)

    def test_an_error_code_nobody_produces_reads_as_none(self) -> None:
        assert ConditionLedger.read({"last_check_error": "made_up"}).last_check_error is None

    def test_a_malformed_value_reads_as_empty_rather_than_crashing_a_tick(self) -> None:
        ledger = ConditionLedger.read({"seen": "not-a-list", "last_checked_at": 12})

        assert ledger.seen == ()
        assert ledger.last_checked_at is None


class TestNovelty:
    def test_only_unseen_keys_are_new_in_the_order_they_came(self) -> None:
        ledger = ConditionLedger.read({"seen": ["a", "b"]})

        assert ledger.new_keys(["c", "a", "d", "c"]) == ["c", "d"]

    def test_a_shrinking_set_brings_nothing_new(self) -> None:
        ledger = ConditionLedger.read({"seen": ["event-10h", "event-15h"]})

        # 11:00 — the 10:00 event is over. The old fingerprint fired here.
        assert ledger.new_keys(["event-15h"]) == []

    def test_a_fact_that_comes_back_is_not_new(self) -> None:
        stored = ConditionLedger.read(None).after_check(at=AT, present=["mail-1"], fired=True)
        gone = ConditionLedger.read(stored).after_check(at=LATER, present=[], fired=False)

        assert ConditionLedger.read(gone).new_keys(["mail-1"]) == []


class TestAfterACheck:
    def test_a_served_check_remembers_everything_it_saw(self) -> None:
        stored = ConditionLedger.read({"seen": ["a"]}).after_check(
            at=AT, present=["b", "a"], fired=True
        )

        assert stored["seen"] == ["b", "a"]
        assert stored["last_fired_at"] == AT.isoformat()
        assert stored["last_checked_at"] == AT.isoformat()
        assert stored["last_check_error"] is None

    def test_an_unserved_new_fact_stays_new(self) -> None:
        # Capped, a question pending, or a failed run: the fact was not served.
        stored = ConditionLedger.read({"seen": ["a"], "last_fired_at": "earlier"}).after_check(
            at=AT, present=["b", "a"], fired=False
        )

        assert ConditionLedger.read(stored).new_keys(["b", "a"]) == ["b"]
        assert stored["last_fired_at"] == "earlier"
        assert stored["last_checked_at"] == AT.isoformat()

    def test_a_check_that_could_not_read_keeps_what_was_seen_and_says_why(self) -> None:
        stored = ConditionLedger.read({"seen": ["a", "b"]}).after_check(
            at=AT, present=[], fired=False, error="unavailable"
        )

        assert stored["seen"] == ["a", "b"]
        assert stored["last_check_error"] == "unavailable"
        assert ConditionLedger.read(stored).last_check_error == "unavailable"

    def test_a_readable_check_clears_the_previous_error(self) -> None:
        stored = ConditionLedger.read({"seen": [], "last_check_error": "unavailable"}).after_check(
            at=AT, present=[], fired=False
        )

        assert stored["last_check_error"] is None

    def test_every_write_is_a_new_dict(self) -> None:
        state = {"seen": ["a"]}

        stored = ConditionLedger.read(state).after_check(at=AT, present=["a"], fired=True)

        assert stored is not state
        assert state == {"seen": ["a"]}

    def test_the_check_instant_reads_back(self) -> None:
        stored = ConditionLedger.read(None).after_check(at=AT, present=[], fired=False)

        assert ConditionLedger.read(stored).last_checked_at == AT


class TestTheBound:
    def test_the_ledger_never_grows_past_its_bound(self) -> None:
        old = [f"old-{index}" for index in range(CONDITION_LEDGER_MAX_KEYS)]

        stored = ConditionLedger.read({"seen": old}).after_check(
            at=AT, present=["new-1", "new-2"], fired=True
        )

        assert len(stored["seen"]) == CONDITION_LEDGER_MAX_KEYS
        assert stored["seen"][:2] == ["new-1", "new-2"]
        assert "old-0" in stored["seen"]
        assert f"old-{CONDITION_LEDGER_MAX_KEYS - 1}" not in stored["seen"]

    def test_a_fact_still_present_is_never_evicted(self) -> None:
        # The OLDEST key is still there: evicting it would make it new again.
        old = [f"old-{index}" for index in range(CONDITION_LEDGER_MAX_KEYS)]
        still_there = old[-1]

        stored = ConditionLedger.read({"seen": old}).after_check(
            at=AT, present=["new-1", still_there], fired=True
        )

        assert still_there in stored["seen"]


class TestRestatingWhyACheckServedNothing:
    def test_the_reason_is_written_on_a_new_dict_and_nothing_else_moves(self) -> None:
        unserved = ConditionLedger.read({"seen": ["a"]}).after_check(
            at=AT, present=("a", "b"), fired=False
        )

        restated = with_check_error(unserved, "quota_blocked")

        assert restated is not unserved
        assert unserved["last_check_error"] is None
        assert restated == {**unserved, "last_check_error": "quota_blocked"}


class TestASnapshotOfOnePage:
    """ADR-387: a page's lines are ONE thing seen at once, not a stream of facts.

    What left the page is forgotten, so a line that comes back is news again
    (« in stock », sold out, then « in stock » once more); an unserved new line
    stays new; a check that could not read the page forgets nothing.
    """

    def _snapshot(self, seen: list[str]) -> ConditionLedger:
        return ConditionLedger.read({"seen": seen}, condition_type="page_change")

    def test_only_a_page_is_read_as_a_snapshot(self) -> None:
        assert self._snapshot([]).snapshot is True
        assert ConditionLedger.read({"seen": []}, condition_type="mail_match").snapshot is False
        assert ConditionLedger.read({"seen": []}).snapshot is False

    def test_a_served_reading_remembers_exactly_what_the_page_shows(self) -> None:
        stored = self._snapshot(["in stock", "price"]).after_check(
            at=AT, present=["sold out", "price"], fired=True
        )

        assert stored["seen"] == ["sold out", "price"]

    def test_a_line_that_comes_back_is_new_again(self) -> None:
        served = self._snapshot(["in stock"]).after_check(at=AT, present=["sold out"], fired=True)

        again = ConditionLedger.read(served, condition_type="page_change")

        assert again.new_keys(["in stock"]) == ["in stock"]

    def test_a_line_that_left_without_news_is_forgotten_too(self) -> None:
        # Nothing new arrived, so nothing ran: the line that left is still
        # forgotten, and its return will be told.
        quiet = self._snapshot(["banner", "price"]).after_check(
            at=AT, present=["price"], fired=False
        )

        assert quiet["seen"] == ["price"]

    def test_an_unserved_new_line_stays_new_and_what_stayed_is_kept(self) -> None:
        capped = self._snapshot(["price"]).after_check(at=AT, present=["price", "new"], fired=False)

        assert capped["seen"] == ["price"]
        assert ConditionLedger.read(capped, condition_type="page_change").new_keys(
            ["price", "new"]
        ) == ["new"]

    def test_a_reading_that_failed_forgets_nothing_whatever_its_size(self) -> None:
        seen = [f"line-{index}" for index in range(CONDITION_LEDGER_MAX_KEYS + 50)]

        failed = self._snapshot(seen).after_check(
            at=AT, present=(), fired=False, error="unavailable"
        )

        assert failed["seen"] == seen
        assert failed["last_check_error"] == "unavailable"
