"""The vendored registry snapshot loads, is complete and carries no excluded field."""

from __future__ import annotations

from datetime import UTC, datetime

from src.infrastructure.llm.catalogue.snapshot_loader import (
    SNAPSHOT_PATH,
    load_snapshot,
    snapshot_generated_at,
)

FORBIDDEN_SUBSTRINGS = ("cost", "price", "reasoning", "effort", "streaming", "temperature")


def test_snapshot_file_is_vendored() -> None:
    assert SNAPSHOT_PATH.is_file(), "the snapshot must ship with the source tree"


def test_snapshot_has_both_sources() -> None:
    snap = load_snapshot()
    assert set(snap) == {"litellm", "modelsdev"}
    assert len(snap["litellm"]) > 100
    assert len(snap["modelsdev"]) > 50


def test_snapshot_carries_no_excluded_field() -> None:
    """Prices, reasoning, streaming and sampling flags are never vendored."""
    snap = load_snapshot()
    for source, entries in snap.items():
        for key, fields in entries.items():
            for field in fields:
                lowered = field.lower()
                assert not any(
                    bad in lowered for bad in FORBIDDEN_SUBSTRINGS
                ), f"{source}/{key} carries excluded field {field!r}"


def test_snapshot_generated_at_is_utc() -> None:
    stamp = snapshot_generated_at()
    assert stamp.tzinfo is UTC or stamp.utcoffset() is not None
    assert stamp <= datetime.now(UTC)
