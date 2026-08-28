"""LogQL builder — the ONLY producer of LogQL in the subsystem.

Injection is closed by construction: service is a closed enum, level a closed
set, the event name a strict pattern; range and line count are clamped to the
hard caps (Loki OOM history on the Pi). What is mechanically repairable is
clamped; what cannot be repaired without inventing intent is rejected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.constants import (
    DIAGNOSTICS_LOKI_MAX_LINES,
    DIAGNOSTICS_LOKI_MAX_RANGE_HOURS,
)
from src.domains.diagnostics.logql import DiagService, build_log_query


@pytest.mark.unit
class TestBuildLogQuery:
    def test_nominal_error_query(self) -> None:
        bounded = build_log_query(
            service=DiagService.API,
            level="error",
            event="chat_run_failed",
            minutes=60,
            limit=100,
        )
        assert bounded.logql == '{service="api", level="error"} | json | event="chat_run_failed"'
        assert bounded.limit == 100
        assert bounded.end - bounded.start == timedelta(minutes=60)
        assert bounded.start.tzinfo is UTC

    def test_no_event_means_plain_selector_without_json_stage(self) -> None:
        bounded = build_log_query(service=DiagService.API, level="error")
        assert bounded.logql == '{service="api", level="error"}'

    def test_no_level_means_service_only_selector(self) -> None:
        bounded = build_log_query(service=DiagService.POSTGRES)
        assert bounded.logql == '{service="postgres"}'

    def test_range_is_clamped_to_the_hard_cap(self) -> None:
        bounded = build_log_query(service=DiagService.API, minutes=10_000_000)
        assert bounded.end - bounded.start <= timedelta(hours=DIAGNOSTICS_LOKI_MAX_RANGE_HOURS)

    def test_limit_is_clamped_to_the_hard_cap_and_floor(self) -> None:
        assert (
            build_log_query(service=DiagService.API, limit=999_999).limit
            == DIAGNOSTICS_LOKI_MAX_LINES
        )
        assert build_log_query(service=DiagService.API, limit=0).limit == 1

    def test_injection_shaped_event_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_log_query(
                service=DiagService.API,
                event='x"} |= "secret',
            )

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_log_query(service=DiagService.API, level="loud")

    def test_service_must_be_the_enum_not_a_string(self) -> None:
        with pytest.raises(ValueError):
            build_log_query(service="api; drop table")  # type: ignore[arg-type]

    def test_end_defaults_to_now_utc(self) -> None:
        before = datetime.now(UTC)
        bounded = build_log_query(service=DiagService.API, minutes=5)
        after = datetime.now(UTC)
        assert before <= bounded.end <= after
