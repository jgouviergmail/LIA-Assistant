"""Post-response extraction debug aggregation for the debug panel.

One chokepoint pops every fire-and-forget extraction family's debug cache
(journals, open loops) so the SSE generator emits one debug_metrics_update
chunk per populated family — a new family means one entry here, zero churn
in api/service.py.
"""

from unittest.mock import patch

import pytest

from src.domains.agents.services.streaming.extraction_debug import (
    pop_background_extraction_debug,
)


@pytest.mark.unit
class TestPopBackgroundExtractionDebug:
    def test_returns_pairs_for_every_populated_family(self):
        from src.domains.agents.services import open_loop_extractor
        from src.domains.journals import extraction_service

        extraction_service._store_extraction_debug(
            "run-agg-1", {"actions_parsed": 1, "actions_applied": 1, "entries": []}
        )
        open_loop_extractor._store_extraction_debug(
            "run-agg-1", {"items_parsed": 2, "opened": 1, "closed": 1, "skipped": 0}
        )

        pairs = pop_background_extraction_debug("run-agg-1")

        assert [k for k, _ in pairs] == ["journal_extraction", "open_loop_extraction"]
        assert pairs[1][1]["opened"] == 1

    def test_empty_when_no_family_has_results(self):
        assert pop_background_extraction_debug("run-agg-none") == []

    def test_one_failing_family_does_not_lose_the_others(self):
        from src.domains.agents.services import open_loop_extractor

        open_loop_extractor._store_extraction_debug("run-agg-2", {"items_parsed": 0})

        with patch(
            "src.domains.journals.extraction_service.pop_extraction_debug",
            side_effect=RuntimeError("boom"),
        ):
            pairs = pop_background_extraction_debug("run-agg-2")

        assert [k for k, _ in pairs] == ["open_loop_extraction"]

    def test_voice_family_reads_tts_records(self):
        """TTS spend is tracked but was invisible in the panel — the voice
        family surfaces it through the same debug_metrics_update channel."""
        from decimal import Decimal

        from src.domains.chat.service import TTSUsageRecord, _run_tts_records

        _run_tts_records["run-agg-voice"] = [
            TTSUsageRecord(
                provider="openai",
                model="tts-1",
                characters=420,
                cost_usd=Decimal("0.0063"),
                cost_eur=Decimal("0.0058"),
                usd_to_eur_rate=Decimal("0.92"),
                duration_ms=850.0,
            )
        ]
        try:
            pairs = pop_background_extraction_debug("run-agg-voice")
        finally:
            _run_tts_records.pop("run-agg-voice", None)

        assert [k for k, _ in pairs] == ["voice"]
        voice = pairs[0][1]
        assert voice["total_calls"] == 1
        assert voice["total_characters"] == 420
        assert voice["total_cost_eur"] == 0.0058
        call = voice["calls"][0]
        assert call["provider"] == "openai"
        assert call["model"] == "tts-1"
        assert call["characters"] == 420
        assert call["duration_ms"] == 850.0

    def test_voice_family_absent_without_tts_records(self):
        assert pop_background_extraction_debug("run-agg-novoice") == []
