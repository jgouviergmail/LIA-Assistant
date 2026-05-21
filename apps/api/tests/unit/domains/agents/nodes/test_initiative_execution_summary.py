"""Unit tests for ``_format_execution_summary`` registry handling (ADR-070).

Registry items reach the Initiative node in two shapes:
- **dict** in the pipeline (after a checkpoint serialization round-trip);
- **Pydantic `RegistryItem` objects** in ReAct (built in-memory by
  ``react_execute_tools``, no round-trip).

Before the fix, the function only handled dicts (`if not isinstance(item, dict):
continue`), so in ReAct it silently dropped every item and produced
``"No execution results."`` — leaving the Initiative LLM blind to the data the
ReAct loop had just fetched (observed live: "Sans détails sur les rendez-vous …",
``should_act=false``). These tests pin dual-format handling.
"""

from __future__ import annotations

import pytest

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.nodes.initiative_node import _format_execution_summary


@pytest.mark.unit
class TestFormatExecutionSummaryRegistryShapes:
    def test_pydantic_registry_item_is_surfaced(self):
        """ReAct shape: RegistryItem objects must be summarised, not skipped."""
        item = RegistryItem(
            id="event_1",
            type=RegistryItemType.EVENT,
            payload={"summary": "Ramonage", "start": "2026-05-22T09:00:00"},
            meta=RegistryItemMeta(source="google_calendar", domain="calendar"),
        )
        summary = _format_execution_summary({}, registry={"event_1": item}, current_turn_id=4)
        assert "Ramonage" in summary
        assert "calendar" in summary
        assert summary != "No execution results."

    def test_dict_registry_item_still_works(self):
        """Pipeline shape: serialized dict items keep working (no regression)."""
        registry = {
            "event_1": {
                "payload": {"summary": "Ramonage", "start": "2026-05-22T09:00:00"},
                "meta": {"domain": "calendar", "source": "google_calendar"},
            }
        }
        summary = _format_execution_summary({}, registry=registry, current_turn_id=4)
        assert "Ramonage" in summary
        assert "calendar" in summary

    def test_empty_registry_returns_sentinel(self):
        summary = _format_execution_summary({}, registry={}, current_turn_id=4)
        assert summary == "No execution results."
