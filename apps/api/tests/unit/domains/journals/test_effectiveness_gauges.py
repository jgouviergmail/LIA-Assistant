"""Unit guards for the journal effectiveness gauges (ADR-159).

``_refresh_effectiveness_gauge`` is the only writer of the theme distribution,
the level distribution and the portrait-age gauges. Two properties matter and
neither is obvious from reading the call site:

1. **Absent labels must publish 0, not disappear.** A Prometheus series that
   stops being written keeps its last value (``mostrecent``) or simply has no
   data — and "no data" is not alertable. A theme at 0 is. The whole point of
   the theme gauge is to make an unreachable theme visible, so the reset loop
   over the enum is the feature, not boilerplate.
2. **A metric failure must never break the consolidation batch.** The refresh
   runs after the batch, best-effort, on the scheduler's critical path.

The repository is faked: these are about the publishing contract, not SQL.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.journals.models import JournalTheme
from src.infrastructure.observability.metrics_journals import (
    journal_level_distribution,
    journal_portrait_age_hours,
    journal_theme_distribution,
)
from src.infrastructure.scheduler import journal_consolidation

pytestmark = pytest.mark.unit


class _FakeRepo:
    """Repository stub returning fixed aggregates."""

    def __init__(
        self,
        theme_counts: dict[str, int] | None = None,
        level_counts: dict[str, int] | None = None,
        portrait_age: float = 0.0,
        avg_days: float = 0.0,
    ) -> None:
        self._theme_counts = theme_counts or {}
        self._level_counts = level_counts or {}
        self._portrait_age = portrait_age
        self._avg_days = avg_days

    async def compute_zero_injection_age_days_avg(self) -> float:
        return self._avg_days

    async def count_by_level_global(self) -> dict[str, int]:
        return self._level_counts

    async def count_by_theme_global(self) -> dict[str, int]:
        return self._theme_counts

    async def compute_max_portrait_age_hours(self) -> float:
        return self._portrait_age


@pytest.fixture
def _fake_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the DB session used by the refresh."""
    from contextlib import asynccontextmanager

    from src.infrastructure import database

    @asynccontextmanager
    async def _ctx() -> Any:
        yield object()

    monkeypatch.setattr(database, "get_db_context", _ctx)


def _install_repo(monkeypatch: pytest.MonkeyPatch, repo: _FakeRepo) -> None:
    """Make ``JournalEntryRepository(db)`` return the stub."""
    from src.domains.journals import repository

    monkeypatch.setattr(repository, "JournalEntryRepository", lambda _db: repo)


def _theme_value(theme: str) -> float:
    """Read back the published gauge value for one theme."""
    return float(journal_theme_distribution.labels(theme=theme)._value.get())


class TestThemeDistributionPublishing:
    """Every theme publishes a value, present or not."""

    async def test_absent_theme_publishes_zero(
        self, monkeypatch: pytest.MonkeyPatch, _fake_db: None
    ) -> None:
        """A theme with no entry must read 0 — the alertable value.

        Publishing only the themes present in the corpus would have left
        `self_reflection` and `ideas_analyses` without a series for two months,
        which is exactly why the defect stayed invisible.
        """
        # Seed non-zero so a missing write would be visible as a stale value.
        for theme in JournalTheme:
            journal_theme_distribution.labels(theme=theme.value).set(99)

        _install_repo(monkeypatch, _FakeRepo(theme_counts={JournalTheme.LEARNINGS.value: 7}))
        await journal_consolidation._refresh_effectiveness_gauge()

        assert _theme_value(JournalTheme.LEARNINGS.value) == 7.0
        for theme in (
            JournalTheme.SELF_REFLECTION,
            JournalTheme.USER_OBSERVATIONS,
            JournalTheme.IDEAS_ANALYSES,
        ):
            assert _theme_value(theme.value) == 0.0, (
                f"{theme.value} kept a stale value instead of publishing 0 — an "
                "unreachable theme would stay invisible"
            )

    async def test_unknown_theme_in_the_corpus_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, _fake_db: None
    ) -> None:
        """A theme outside the enum must not create a rogue series.

        The gauge is driven by ``JournalTheme``, the single source of truth, so
        a stray value in the column cannot invent a label.
        """
        _install_repo(monkeypatch, _FakeRepo(theme_counts={"not_a_theme": 3}))
        await journal_consolidation._refresh_effectiveness_gauge()

        published = {
            sample.labels["theme"]
            for metric in journal_theme_distribution.collect()
            for sample in metric.samples
        }
        assert "not_a_theme" not in published


class TestOtherGauges:
    """Level distribution and portrait age publish alongside the themes."""

    async def test_all_levels_and_portrait_age_are_published(
        self, monkeypatch: pytest.MonkeyPatch, _fake_db: None
    ) -> None:
        """Levels reset to 0 the same way, and the age is forwarded verbatim."""
        for level in ("L0", "L1", "L2", "L3"):
            journal_level_distribution.labels(level=level).set(42)

        _install_repo(monkeypatch, _FakeRepo(level_counts={"L1": 5}, portrait_age=31.5))
        await journal_consolidation._refresh_effectiveness_gauge()

        assert float(journal_level_distribution.labels(level="L1")._value.get()) == 5.0
        assert float(journal_level_distribution.labels(level="L2")._value.get()) == 0.0
        assert float(journal_portrait_age_hours._value.get()) == 31.5


class TestBestEffort:
    """The refresh must never take the consolidation batch down."""

    async def test_repository_failure_is_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, _fake_db: None
    ) -> None:
        """A DB error while sampling metrics is logged, not raised.

        The refresh runs at the end of the scheduler batch; raising there would
        turn an observability hiccup into a failed consolidation run.
        """

        class _BoomRepo(_FakeRepo):
            async def count_by_theme_global(self) -> dict[str, int]:
                raise RuntimeError("db went away")

        _install_repo(monkeypatch, _BoomRepo())
        await journal_consolidation._refresh_effectiveness_gauge()
