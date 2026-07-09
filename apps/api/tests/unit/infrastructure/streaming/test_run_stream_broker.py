"""Unit tests for the pure envelope helpers of the run stream broker."""

from __future__ import annotations

import pytest

from src.core.constants import (
    REDIS_KEY_ACTIVE_RUN_PREFIX,
    REDIS_KEY_RUN_LISTENERS_PREFIX,
    REDIS_KEY_RUN_STREAM_PREFIX,
)
from src.infrastructure.streaming.run_stream_broker import (
    RunStreamEvent,
    _stream_entry_id_tuple,
    active_run_key,
    decode_entry,
    encode_chunk_entry,
    encode_end_entry,
    listeners_key,
    run_stream_key,
)


@pytest.mark.unit
class TestRunStreamKey:
    def test_key_uses_prefix(self):
        assert run_stream_key("abc123") == f"{REDIS_KEY_RUN_STREAM_PREFIX}abc123"


@pytest.mark.unit
class TestEnvelope:
    def test_chunk_roundtrip(self):
        chunk_json = '{"type": "token", "content": "hi", "metadata": null}'
        event = decode_entry(encode_chunk_entry(chunk_json))
        assert event == RunStreamEvent(kind="chunk", payload=chunk_json)

    def test_end_roundtrip(self):
        event = decode_entry(encode_end_entry("completed"))
        assert event == RunStreamEvent(kind="end", payload="completed")

    def test_end_takes_precedence_over_chunk(self):
        # A malformed entry carrying both fields must terminate the stream
        # (fail-closed: never leave a subscriber hanging).
        fields = {**encode_chunk_entry("{}"), **encode_end_entry("error")}
        assert decode_entry(fields).kind == "end"

    def test_unknown_entry_raises(self):
        with pytest.raises(ValueError):
            decode_entry({"bogus": "1"})

    def test_is_replay_defaults_false(self):
        # Lot 2: decode_entry never sets is_replay — subscribe() enriches it.
        assert decode_entry(encode_chunk_entry("{}")).is_replay is False


@pytest.mark.unit
class TestLot2Keys:
    def test_active_run_key_prefix(self):
        assert active_run_key("conv1") == f"{REDIS_KEY_ACTIVE_RUN_PREFIX}conv1"

    def test_listeners_key_prefix(self):
        assert listeners_key("s1") == f"{REDIS_KEY_RUN_LISTENERS_PREFIX}s1"


@pytest.mark.unit
class TestStreamEntryIdOrdering:
    def test_numeric_ordering_beats_lexicographic(self):
        # "999-1" > "1000-1" as strings — the tuple compare must be numeric.
        assert _stream_entry_id_tuple("999-1") < _stream_entry_id_tuple("1000-1")

    def test_sequence_part_breaks_ties(self):
        assert _stream_entry_id_tuple("5-2") > _stream_entry_id_tuple("5-1")

    def test_missing_sequence_defaults_to_zero(self):
        assert _stream_entry_id_tuple("7") == (7, 0)
