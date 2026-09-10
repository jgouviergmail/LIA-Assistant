"""Tests for the batch subject clustering job (ADR-131)."""

import json

import pytest
from sqlalchemy.dialects import postgresql

from src.core.config import settings
from src.infrastructure.scheduler.interest_subject_clustering import (
    parse_assignments,
    refresh_candidates_statement,
    stale_candidates_statement,
)


@pytest.mark.unit
class TestParseAssignments:
    def test_nominal_parse(self) -> None:
        raw = json.dumps(
            {
                "assignments": [
                    {"index": 1, "subject": "  IA générative "},
                    {"index": 2, "subject": "voyage"},
                ]
            }
        )
        out = parse_assignments(raw, expected_indexes={1, 2}, max_length=100)
        assert out == {1: "IA générative", 2: "voyage"}

    def test_code_fences_and_noise_tolerated(self) -> None:
        raw = '```json\n{"assignments": [{"index": 1, "subject": "crypto"}]}\n```'
        assert parse_assignments(raw, {1}, 100) == {1: "crypto"}

    def test_unknown_index_ignored_missing_index_absent(self) -> None:
        raw = json.dumps(
            {"assignments": [{"index": 9, "subject": "x"}, {"index": 1, "subject": "ok"}]}
        )
        out = parse_assignments(raw, {1, 2}, 100)
        assert out == {1: "ok"}  # 9 ignored, 2 absent (caller keeps previous label)

    def test_label_sanitized_and_capped(self) -> None:
        raw = json.dumps({"assignments": [{"index": 1, "subject": "  a   b\n c  " + "x" * 200}]})
        out = parse_assignments(raw, {1}, max_length=20)
        assert len(out[1]) <= 20
        assert "\n" not in out[1]
        assert "  " not in out[1]

    def test_garbage_returns_empty(self) -> None:
        assert parse_assignments("not json at all", {1}, 100) == {}
        assert parse_assignments('{"assignments": "nope"}', {1}, 100) == {}
        assert parse_assignments('{"assignments": [{"index": "1", "subject": 3}]}', {1}, 100) == {}


class TestTheCandidateSweepNeverStarvesAUser:
    """A capped read with no ORDER BY returns a STABLE arbitrary subset.

    Measured 2026-09-10: both jobs read `.distinct().limit(50)` with no
    ordering, so PostgreSQL returned whatever the plan yielded — and a table
    that is not moving yields the SAME rows every time. The nightly job whose
    docstring said "every user with active interests" covered an arbitrary
    fifty, the same fifty, for the life of the instance. Nothing could tell
    that apart from the truth.

    The two jobs answer different questions, so they order differently:
    the backlog DRAINS (labelling a user removes them), so it is served
    oldest-first; the refresh never drains, so it is SAMPLED — an order that
    is stable would starve everyone past the cap forever.
    """

    def test_the_backlog_is_served_oldest_first_and_capped(self) -> None:
        sql = str(
            stale_candidates_statement(limit=7).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "GROUP BY" in sql
        assert "ORDER BY min(user_interests.updated_at) ASC" in sql
        assert "user_interests.user_id ASC" in sql, "the order must be total"
        assert "LIMIT 7" in sql

    def test_the_refresh_is_sampled_so_no_user_is_starved(self) -> None:
        sql = str(
            refresh_candidates_statement(limit=7).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "GROUP BY" in sql
        assert "ORDER BY random()" in sql
        assert "LIMIT 7" in sql

    def test_neither_statement_is_left_unordered(self) -> None:
        """The defect itself: a LIMIT with nothing deciding which rows."""
        for statement in (
            stale_candidates_statement(limit=3),
            refresh_candidates_statement(limit=3),
        ):
            sql = str(
                statement.compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            assert "ORDER BY" in sql

    def test_the_backlog_reads_only_unlabelled_interests(self) -> None:
        sql = str(
            stale_candidates_statement(limit=3).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "subject IS NULL" in sql

    def test_the_cap_comes_from_the_setting_not_a_literal(self) -> None:
        """Configs change; a hard-coded threshold drifts in silence."""
        expected = settings.interest_subject_recluster_batch_size
        sql = str(
            stale_candidates_statement().compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert f"LIMIT {expected}" in sql
