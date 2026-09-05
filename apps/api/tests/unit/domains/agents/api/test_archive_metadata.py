"""The metadata an archived assistant message carries (ADR-263 extraction).

Four enrichers were applied inline in ``api/service.py``: widgets, execution
trace, follow-up chips, initiative motivation. ADR-263 adds a fifth — the
effects performed during the turn — and that file sits three logical lines
under its frozen cap, so the chain moves to a module of its own instead.

This file is written BEFORE the extraction, against the four existing
enrichers, so the move is proved behaviour-preserving rather than assumed.
Every enricher is branch-free and returns a NEW dict; the chain must keep both
properties, because the caller assigns the result back and a shared dict would
leak one turn's metadata into another.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.api.archive_metadata import build_assistant_metadata

pytestmark = [pytest.mark.unit]


class _Capture:
    """Stands in for ``TraceCapture``: only ``snapshot()`` is called."""

    def __init__(self, steps: list[dict[str, str]]) -> None:
        self._steps = steps

    def snapshot(self) -> list[dict[str, str]]:
        return self._steps


def _expected_from_the_original_chain(
    base: dict[str, Any],
    widgets: Any,
    steps: list[dict[str, str]],
    duration_ms: int,
    run_id: str,
    followups: Any,
    motivation: Any,
) -> dict[str, Any]:
    """The four calls exactly as ``api/service.py`` made them, in order."""
    from src.domains.agents.data_registry.message_widgets import with_persisted_widgets
    from src.domains.agents.services.streaming.followup_metadata import (
        with_followup_suggestions,
        with_initiative_motivation,
    )
    from src.domains.agents.services.streaming.trace_capture import with_persisted_trace

    metadata = with_persisted_widgets(base, widgets, run_id=run_id)
    metadata = with_persisted_trace(metadata, steps, duration_ms=duration_ms, run_id=run_id)
    metadata = with_followup_suggestions(metadata, followups)
    return with_initiative_motivation(metadata, motivation)


class TestTheChainIsUnchanged:
    """Characterisation: same inputs, same metadata as the inline version."""

    @pytest.mark.parametrize(
        ("steps", "followups", "motivation"),
        [
            ([], None, None),
            ([{"emoji": "🔍", "i18n_key": "trace.search", "category": "search"}], None, None),
            ([], ["Et demain ?"], None),
            ([], None, "curiosity"),
            (
                [{"emoji": "✉️", "i18n_key": "trace.email", "category": "send"}],
                ["Envoyer un rappel ?"],
                "follow_up",
            ),
        ],
        ids=["empty", "trace", "followups", "motivation", "everything"],
    )
    def test_it_matches_the_inline_chain(
        self, steps: list[dict[str, str]], followups: Any, motivation: Any
    ) -> None:
        base = {"llm_calls": 2}
        expected = _expected_from_the_original_chain(
            dict(base), None, steps, 1234, "run-1", followups, motivation
        )

        produced = build_assistant_metadata(
            dict(base),
            widgets=None,
            trace_capture=_Capture(steps),
            duration_ms=1234,
            run_id="run-1",
            followup_suggestions=followups,
            initiative_motivation=motivation,
            effects=None,
        )

        assert produced == expected

    def test_the_caller_s_dict_is_never_mutated(self) -> None:
        """Each enricher returns a new dict; the chain must not break that."""
        base = {"llm_calls": 2}
        build_assistant_metadata(
            base,
            widgets=None,
            trace_capture=_Capture([{"emoji": "🔍", "i18n_key": "k", "category": "search"}]),
            duration_ms=10,
            run_id="run-1",
            followup_suggestions=["a"],
            initiative_motivation="m",
            effects=None,
        )
        assert base == {"llm_calls": 2}


class TestTheFifthEnricher:
    """ADR-263: what the turn actually performed travels with the message."""

    def test_no_effect_attaches_nothing(self) -> None:
        """The pure-conversation common case must add no key at all."""
        produced = build_assistant_metadata(
            {"llm_calls": 1},
            widgets=None,
            trace_capture=_Capture([]),
            duration_ms=1,
            run_id="run-1",
            followup_suggestions=None,
            initiative_motivation=None,
            effects=[],
        )
        assert "performed_effects" not in produced

    def test_effects_travel_as_keys_and_values_never_as_sentences(self) -> None:
        """The frontend resolves the label; the API never ships a translation.

        ``apps/web/CLAUDE.md``: backend contracts ship structured data plus
        ``label_key``s resolved client-side.
        """
        produced = build_assistant_metadata(
            {},
            widgets=None,
            trace_capture=_Capture([]),
            duration_ms=1,
            run_id="run-1",
            followup_suggestions=None,
            initiative_motivation=None,
            effects=[
                {
                    "label_key": "effects.labels.send_email_tool",
                    "values": {"recipient": "Marie"},
                    "status": "succeeded",
                    "tool_name": "send_email_tool",
                }
            ],
        )

        entries = produced["performed_effects"]
        assert entries == [
            {
                "label_key": "effects.labels.send_email_tool",
                "values": {"recipient": "Marie"},
                "status": "succeeded",
                "tool_name": "send_email_tool",
            }
        ]
        assert all("label" not in entry for entry in entries), (
            "a pre-translated sentence in the payload would freeze the user's "
            "language at archive time"
        )
