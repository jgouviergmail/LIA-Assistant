"""`GET /journals` must survive a theme value it does not recognise.

``by_theme`` is built by mapping raw DB strings onto :class:`JournalTheme`.
``JournalTheme(unknown)`` raises ``ValueError``, and the list endpoint is what
renders the whole journal panel — so one unexpected row would 500 the entire
page rather than degrade one counter.

Every write path validates the theme today, so this is defence in depth for the
paths that bypass the ORM: a manual fix in psql, a data migration, or a row
predating a taxonomy change. The anomaly is logged rather than swallowed —
CLAUDE.md forbids silent fallbacks on unknown registry keys.
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.journals.models import JournalTheme
from src.domains.journals.router import _build_theme_counts

pytestmark = pytest.mark.unit


class TestBuildThemeCounts:
    """Raw counts in, validated response items out."""

    def test_maps_every_known_theme(self) -> None:
        """All four themes round-trip with their counts."""
        raw = {theme.value: index + 1 for index, theme in enumerate(JournalTheme)}

        counts = _build_theme_counts(raw, user_id=uuid.uuid4())

        assert {c.theme.value: c.count for c in counts} == raw

    def test_skips_an_unknown_theme_instead_of_raising(self) -> None:
        """One rogue value must not take the endpoint down."""
        raw = {JournalTheme.LEARNINGS.value: 3, "legacy_theme": 7}

        counts = _build_theme_counts(raw, user_id=uuid.uuid4())

        assert [c.theme for c in counts] == [JournalTheme.LEARNINGS]
        assert counts[0].count == 3

    def test_logs_the_anomaly(self, caplog: pytest.LogCaptureFixture) -> None:
        """Skipping is not swallowing: the unknown theme is reported."""
        with caplog.at_level("WARNING"):
            _build_theme_counts({"legacy_theme": 1}, user_id=uuid.uuid4())

        assert "journal_unknown_theme_in_corpus" in caplog.text

    def test_empty_corpus_yields_no_counts(self) -> None:
        """A user with no entries gets an empty list, not an error."""
        assert _build_theme_counts({}, user_id=uuid.uuid4()) == []
