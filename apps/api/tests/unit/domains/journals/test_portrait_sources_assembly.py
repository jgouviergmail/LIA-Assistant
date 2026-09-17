"""The consolidation assembles its four source sections through the seam (part B).

What this pins: the declared order; ONE reader at a time (four short reads —
a ``gather`` would hold four sessions for nothing); each reader handed its
own budget from the settings; the global cap that drops a section WHOLE and
reports it, never cuts mid-item; the provenance JSON the portrait is persisted
with; the metric counted per source and status.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.journals import portrait_sources as assembly
from src.domains.journals.portrait_sources import build_portrait_source_sections
from src.domains.shared import portrait_sources as seam
from src.domains.shared.portrait_sources import (
    PORTRAIT_SOURCE_KEYS,
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
)

pytestmark = pytest.mark.unit

PROBE = FreshnessProbe(table="t", user_column="user_id", stamp_column="updated_at")


def _reader(key: str, *, text: str = "", status: str = "used", used: int = 1, total: int = 1):  # type: ignore[no-untyped-def]
    calls: list[SourceBudget] = []

    async def read(*, user_id: uuid.UUID, language: str, budget: SourceBudget) -> Any:
        calls.append(budget)
        return PortraitSourceSection(
            key=key, status=status, text=text, used=used if text else 0, total=total  # type: ignore[arg-type]
        )

    read.calls = calls  # type: ignore[attr-defined]
    return read


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    readers = {
        "memories": _reader("memories", text="## LONG-TERM MEMORIES\n- a", total=3),
        "interests": _reader("interests", text="## INTERESTS\n- b", total=2),
        "habits": _reader("habits", status="disabled", total=0),
        "relation_debriefs": _reader("relation_debriefs", status="unavailable", total=0),
    }
    monkeypatch.setattr(seam, "_REGISTRY", {k: (r, PROBE) for k, r in readers.items()})
    monkeypatch.setattr(
        assembly,
        "settings",
        SimpleNamespace(
            journal_consolidation_memories_max=40,
            journal_consolidation_interests_max=30,
            journal_consolidation_debriefs_max=10,
            journal_consolidation_source_item_max_chars=200,
            journal_consolidation_sources_max_chars=12_000,
        ),
    )
    counter = MagicMock()
    monkeypatch.setattr(assembly, "journal_portrait_sources_total", counter)
    return {"readers": readers, "counter": counter}


async def test_sections_come_back_in_the_declared_order_with_their_budgets(
    registry: dict[str, Any],
) -> None:
    bundle = await build_portrait_source_sections(uuid.uuid4(), "fr", journal_entries=12)
    assert tuple(bundle.sections) == PORTRAIT_SOURCE_KEYS
    assert bundle.sections["memories"].startswith("## LONG-TERM MEMORIES")
    assert bundle.sections["habits"] == "" and bundle.sections["relation_debriefs"] == ""
    readers = registry["readers"]
    assert readers["memories"].calls == [SourceBudget(40, 200)]
    assert readers["interests"].calls == [SourceBudget(30, 200)]
    assert readers["relation_debriefs"].calls == [SourceBudget(10, 200)]
    # Habits are bounded by construction: no item budget, the clamp only.
    assert readers["habits"].calls[0].item_max_chars == 200


async def test_the_provenance_says_what_each_source_answered(registry: dict[str, Any]) -> None:
    bundle = await build_portrait_source_sections(uuid.uuid4(), "fr", journal_entries=12)
    assert bundle.provenance == {
        "version": 1,
        "journal_entries": 12,
        "sources": {
            "memories": {"status": "used", "used": 1, "total": 3},
            "interests": {"status": "used", "used": 1, "total": 2},
            "habits": {"status": "disabled", "used": 0, "total": 0},
            "relation_debriefs": {"status": "unavailable", "used": 0, "total": 0},
        },
    }
    labels = [c.kwargs for c in registry["counter"].labels.call_args_list]
    assert {"source": "habits", "status": "disabled"} in labels
    assert {"source": "memories", "status": "used"} in labels


async def test_a_section_that_breaks_the_global_cap_is_dropped_whole_and_reported(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assembly.settings, "journal_consolidation_sources_max_chars", 30)
    bundle = await build_portrait_source_sections(uuid.uuid4(), "fr", journal_entries=0)
    # The memories section (28 chars) fits; the interests one would exceed 30.
    assert bundle.sections["memories"] and bundle.sections["interests"] == ""
    assert bundle.provenance["sources"]["interests"] == {
        "status": "unavailable",
        "used": 0,
        "total": 2,
    }
    assert "\n- b"[:1] not in bundle.sections["interests"]


async def test_readers_run_one_at_a_time(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    in_flight = 0
    peak = 0

    def _slow(key: str):  # type: ignore[no-untyped-def]
        async def read(*, user_id: uuid.UUID, language: str, budget: SourceBudget) -> Any:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return PortraitSourceSection(key=key, status="empty", text="", used=0, total=0)

        return read

    monkeypatch.setattr(seam, "_REGISTRY", {k: (_slow(k), PROBE) for k in PORTRAIT_SOURCE_KEYS})
    await build_portrait_source_sections(uuid.uuid4(), "fr", journal_entries=0)
    assert peak == 1
