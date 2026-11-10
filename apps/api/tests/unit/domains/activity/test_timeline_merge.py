"""Pure merge/sort/pagination logic of the activity timeline (Lot 1-A1).

The timeline aggregates events from several proactive sources. The merge is
a pure function: deterministic descending chronological order, stable
tie-break, offset/limit slicing over the ROWS only (exact per-kind totals
are computed separately by SQL aggregates — ADR-185 counting doctrine).
"""

from datetime import UTC, datetime, timedelta
from random import Random
from typing import Literal

import pytest

from src.domains.activity.schemas import ActivityEvent
from src.domains.activity.timeline import merge_timeline

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)


def _event(kind: str, ref_id: str, minutes_ago: int, text: str | None = None) -> ActivityEvent:
    return ActivityEvent(
        kind=kind,
        ref_id=ref_id,
        occurred_at=NOW - timedelta(minutes=minutes_ago),
        text=text,
    )


@pytest.mark.unit
class TestMergeTimeline:
    @pytest.mark.parametrize("sort", ["recent", "oldest"])
    def test_capped_merge_is_always_a_prefix_of_the_complete_reference(
        self, sort: Literal["recent", "oldest"]
    ) -> None:
        """Compare complete vs capped sources across dense date ties and unequal caps."""
        random = Random(421)
        for _ in range(50):
            complete = {
                kind: [
                    _event(kind, f"{kind}-{index:03}", random.randrange(8))
                    for index in range(random.randrange(1, 25))
                ]
                for kind in ("habit_detected", "journal_entry", "open_loop_created")
            }
            reference = merge_timeline(complete, offset=0, limit=100, sort=sort).events
            pools: dict[str, list[ActivityEvent]] = {}
            truncated: set[str] = set()
            for kind, rows in complete.items():
                cap = random.randrange(1, len(rows) + 1)
                pools[kind] = [item for item in reference if item.kind == kind][:cap]
                if cap < len(rows):
                    truncated.add(kind)
            result = merge_timeline(
                pools, offset=0, limit=100, sort=sort, truncated_kinds=truncated
            )
            assert result.events
            assert result.events == reference[: len(result.events)]

    def test_does_not_offer_later_events_past_an_unknown_source_tail(self) -> None:
        events = {
            "habit_detected": [
                _event("habit_detected", "h1", 1),
                _event("habit_detected", "h2", 2),
            ],
            "journal_entry": [_event("journal_entry", "j1", 10)],
        }
        result = merge_timeline(events, offset=0, limit=10, truncated_kinds={"habit_detected"})
        assert [row.ref_id for row in result.events] == ["h1", "h2"]
        assert result.has_more is False
        assert result.total_fetched == 2

    def test_oldest_first_keeps_ties_ascending_and_bounds_a_capped_source(self) -> None:
        events = {
            "habit_detected": [
                _event("habit_detected", "h2", 10),
                _event("habit_detected", "h1", 10),
            ],
            "journal_entry": [_event("journal_entry", "j1", 1)],
        }
        result = merge_timeline(
            events, offset=0, limit=10, sort="oldest", truncated_kinds={"habit_detected"}
        )
        assert [row.ref_id for row in result.events] == ["h1", "h2"]

    def test_missing_capped_source_rows_offer_no_guessed_prefix(self) -> None:
        result = merge_timeline(
            {"habit_detected": [], "journal_entry": [_event("journal_entry", "j1", 1)]},
            offset=0,
            limit=10,
            truncated_kinds={"habit_detected"},
        )
        assert result.events == []

    def test_merges_all_kinds_sorted_descending(self):
        events_by_kind = {
            "reminder_sent": [_event("reminder_sent", "r1", 30)],
            "habit_detected": [_event("habit_detected", "h1", 10)],
            "open_loop_closed": [_event("open_loop_closed", "l1", 20)],
        }

        merged = merge_timeline(events_by_kind, offset=0, limit=10)

        assert [e.ref_id for e in merged.events] == ["h1", "l1", "r1"]
        assert merged.has_more is False
        assert merged.total_fetched == 3

    def test_equal_timestamps_use_deterministic_tie_break(self):
        # Same instant: order falls back to (kind, ref_id) ascending so two
        # calls with the same data always paginate identically.
        events_by_kind = {
            "reminder_sent": [_event("reminder_sent", "r1", 15)],
            "habit_detected": [
                _event("habit_detected", "h2", 15),
                _event("habit_detected", "h1", 15),
            ],
        }

        merged = merge_timeline(events_by_kind, offset=0, limit=10)

        assert [e.ref_id for e in merged.events] == ["h1", "h2", "r1"]

    def test_offset_and_limit_slice_rows_and_flag_more(self):
        events_by_kind = {
            "reminder_sent": [_event("reminder_sent", f"r{i}", i) for i in range(1, 6)],
        }

        page1 = merge_timeline(events_by_kind, offset=0, limit=2)
        page2 = merge_timeline(events_by_kind, offset=2, limit=2)
        page3 = merge_timeline(events_by_kind, offset=4, limit=2)

        assert [e.ref_id for e in page1.events] == ["r1", "r2"]
        assert page1.has_more is True
        assert [e.ref_id for e in page2.events] == ["r3", "r4"]
        assert page2.has_more is True
        assert [e.ref_id for e in page3.events] == ["r5"]
        assert page3.has_more is False
        # total_fetched is the merged row count, identical on every page.
        assert page1.total_fetched == page2.total_fetched == page3.total_fetched == 5

    def test_offset_beyond_end_returns_empty_page(self):
        events_by_kind = {"reminder_sent": [_event("reminder_sent", "r1", 5)]}

        merged = merge_timeline(events_by_kind, offset=10, limit=5)

        assert merged.events == []
        assert merged.has_more is False
        assert merged.total_fetched == 1

    def test_empty_sources_produce_empty_page(self):
        merged = merge_timeline({}, offset=0, limit=10)

        assert merged.events == []
        assert merged.has_more is False
        assert merged.total_fetched == 0

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError, match="offset"):
            merge_timeline({}, offset=-1, limit=10)

    def test_non_positive_limit_rejected(self):
        with pytest.raises(ValueError, match="limit"):
            merge_timeline({}, offset=0, limit=0)
