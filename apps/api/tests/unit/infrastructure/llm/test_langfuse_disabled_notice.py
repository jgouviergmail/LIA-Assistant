"""A configuration state must be reported once, not on every request.

``create_instrumented_config`` runs for every LLM call in a turn. When Langfuse
is deliberately disabled it emitted a WARNING each time::

    langfuse_disabled_skipping_instrumentation llm_type=agent_graph

Measured in production over 7 days (2026-07-29 → 2026-08-05): 828 occurrences,
627 of them on ``POST /api/v1/agents/chat/stream``. It is the second most
frequent warning of the whole platform, and it reports a *setting* — one that
has not changed and is not a fault.

A steady configuration state belongs at boot, once per process, so it stays
discoverable without drowning the signal it competes with. Repeats stay at DEBUG:
the information is not lost, it is merely no longer shouted.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.llm import instrumentation

pytestmark = pytest.mark.unit


@pytest.fixture()
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Records log calls and resets the once-per-process notice."""
    records: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "info": [],
        "warning": [],
        "debug": [],
    }

    class _StubLogger:
        @staticmethod
        def info(event: str, **fields: Any) -> None:
            records["info"].append((event, fields))

        @staticmethod
        def warning(event: str, **fields: Any) -> None:
            records["warning"].append((event, fields))

        @staticmethod
        def debug(event: str, **fields: Any) -> None:
            records["debug"].append((event, fields))

    monkeypatch.setattr(instrumentation, "logger", _StubLogger)
    monkeypatch.setattr(instrumentation, "_langfuse_disabled_notice_emitted", False, raising=False)
    monkeypatch.setattr(instrumentation, "get_callback_factory", lambda: None)
    return records


class TestDisabledLangfuseIsAnnouncedOnce:
    """The setting is stated once per process, then stops competing for attention."""

    def test_first_call_states_it_at_info(
        self, captured: dict[str, list[tuple[str, dict[str, Any]]]]
    ) -> None:
        instrumentation.create_instrumented_config(llm_type="agent_graph")

        assert not captured["warning"], (
            "a deliberate setting is not a warning: 828 occurrences in 7 days made this "
            "the second most frequent warning on the platform."
        )
        events = [event for event, _ in captured["info"]]
        assert "langfuse_disabled" in events

    def test_subsequent_calls_stay_silent(
        self, captured: dict[str, list[tuple[str, dict[str, Any]]]]
    ) -> None:
        for _ in range(50):
            instrumentation.create_instrumented_config(llm_type="agent_graph")

        info_events = [event for event, _ in captured["info"] if event == "langfuse_disabled"]
        assert len(info_events) == 1, (
            f"the disabled state was announced {len(info_events)} times; it is a process-wide "
            f"setting, so once per process is the whole point."
        )
        assert not captured["warning"]

    def test_repeats_remain_traceable_at_debug(
        self, captured: dict[str, list[tuple[str, dict[str, Any]]]]
    ) -> None:
        """Demoted, not deleted — a per-call trace stays available when debugging."""
        instrumentation.create_instrumented_config(llm_type="agent_graph")
        instrumentation.create_instrumented_config(llm_type="react_agent")

        debug_events = [
            fields
            for event, fields in captured["debug"]
            if event == "langfuse_disabled_skipping_instrumentation"
        ]
        assert debug_events, "the per-call detail must still be reachable at DEBUG"
        assert debug_events[-1]["llm_type"] == "react_agent"

    def test_the_config_is_still_returned(
        self, captured: dict[str, list[tuple[str, dict[str, Any]]]]
    ) -> None:
        """Logging is not the feature: the caller must still get a usable config."""
        config = instrumentation.create_instrumented_config(llm_type="agent_graph")

        assert isinstance(config, dict)
        assert "metadata" in config
