"""The process knows when it started — the one "recent change" every diagnosis asks about.

Three of four stored diagnoses (2026-09-02 → 2026-09-05) recommended checking
"recent configuration or deployment changes" without being able to: nothing in
the evidence said which build was running or for how long. A module-level
timestamp captured when `main` imports is the cheapest honest answer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core import process_info

pytestmark = pytest.mark.unit


class TestProcessStartedAt:
    def test_is_an_aware_utc_datetime(self) -> None:
        assert process_info.PROCESS_STARTED_AT.tzinfo is UTC

    def test_is_not_in_the_future(self) -> None:
        assert process_info.PROCESS_STARTED_AT <= datetime.now(UTC)

    def test_uptime_is_non_negative_and_grows(self) -> None:
        first = process_info.uptime_seconds()
        assert first >= 0
        assert process_info.uptime_seconds() >= first

    def test_main_imports_it_so_the_stamp_is_the_boot_not_the_first_diagnosis(self) -> None:
        """A lazily imported constant would date the first incident, not the boot."""
        import inspect
        from pathlib import Path

        main_source = (Path(process_info.__file__).parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        assert (
            "src.core.process_info" in main_source
            or "from src.core import process_info" in main_source
        )
        assert inspect.ismodule(process_info)
