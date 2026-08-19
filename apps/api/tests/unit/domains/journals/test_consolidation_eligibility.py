"""Delta-driven consolidation eligibility (audit B-03, lot 2).

The historical gate required ``min_entries`` ACTIVE entries (default 3) while
consolidation itself prunes journals down to 2 — so every real user became
permanently ineligible and portraits stalled for months (two prod users stuck
on June portraits with 2 entries each). The new gate is delta-driven: a user
is eligible when there is WORK — at least one active entry AND (never
consolidated OR an entry touched since the last consolidation). The stamp is
written AFTER the run's actions, so a consolidation's own edits never
re-trigger it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from src.core.config import settings
from src.domains.journals.repository import build_consolidation_eligible_users_query


def _sql(cooldown: datetime | None = None) -> str:
    query = build_consolidation_eligible_users_query(
        cooldown_threshold=cooldown or datetime.now(UTC),
        min_entries=settings.journal_consolidation_min_entries,
    )
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))


class TestEligibilityQueryShape:
    def test_delta_predicate_present(self) -> None:
        """Never-consolidated users OR entries touched since the last stamp."""
        sql = _sql()
        assert "journal_last_consolidated_at IS NULL" in sql
        assert "last_touched_at > users.journal_last_consolidated_at" in sql

    def test_active_entries_floor_still_applies(self) -> None:
        sql = _sql()
        assert "count(journal_entries.id) >= " in sql

    def test_cooldown_still_paces_the_scheduler(self) -> None:
        sql = _sql()
        assert "journal_last_consolidated_at < " in sql

    def test_only_active_entries_count(self) -> None:
        """Archived entries are not work: they never re-trigger a run."""
        sql = _sql()
        assert "journal_entries.status = " in sql

    def test_min_entries_default_no_longer_starves_two_entry_users(self) -> None:
        """The default floor must be reachable by a post-prune journal.

        Consolidation prunes toward ~2 entries; a floor above 1 recreates the
        self-starvation this change removes. The setting stays env-overridable
        (prod pins its own value) but the DEFAULT must not starve.
        """
        from src.core.constants import JOURNAL_CONSOLIDATION_MIN_ENTRIES_DEFAULT

        assert JOURNAL_CONSOLIDATION_MIN_ENTRIES_DEFAULT == 1
