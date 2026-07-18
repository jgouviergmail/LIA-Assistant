"""Tests for the batch subject clustering job (ADR-131)."""

import json

import pytest

from src.infrastructure.scheduler.interest_subject_clustering import parse_assignments


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
