"""The consolidation assembles its source sections through the seam (part B; nine since 2026-10-12).

What this pins: the declared order; ONE reader at a time (short reads — a
``gather`` would hold sessions for nothing); every item rendered whole; ONE
physical bound, a share of the slot's window, that cuts the LAST sections at
item boundaries and states it, never mid-item; the provenance JSON the
portrait is persisted with; the metric counted per source and status.
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
)

pytestmark = pytest.mark.unit

PROBE = FreshnessProbe(table="t", user_column="user_id", stamp_column="updated_at")


def _reader(key: str, *, text: str = "", status: str = "used", used: int = 1, total: int = 1):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    async def read(*, user_id: uuid.UUID, language: str) -> Any:
        calls.append(language)
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
        SimpleNamespace(journal_consolidation_sources_window_fraction=0.5),
    )
    counter = MagicMock()
    monkeypatch.setattr(assembly, "journal_portrait_sources_total", counter)
    return {"readers": readers, "counter": counter}


async def test_sections_come_back_in_the_declared_order_each_read_once(
    registry: dict[str, Any],
) -> None:
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=12, window_tokens=1_000_000
    )
    assert tuple(bundle.sections) == PORTRAIT_SOURCE_KEYS
    assert bundle.sections["memories"].startswith("## LONG-TERM MEMORIES")
    assert bundle.sections["habits"] == "" and bundle.sections["relation_debriefs"] == ""
    readers = registry["readers"]
    assert all(readers[key].calls == ["fr"] for key in readers)


async def test_the_provenance_says_what_each_source_answered(registry: dict[str, Any]) -> None:
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=12, window_tokens=1_000_000
    )
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


async def test_the_window_share_cuts_the_last_sections_at_item_boundaries_and_says_so(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.journals.portrait_catalogue import render_catalogue_sections
    from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

    memory = "## LONG-TERM MEMORIES\n- first memory kept whole\n- second memory kept whole"
    interests = "## INTERESTS\n- first interest\n- second interest\n- third interest"
    registry["readers"]["memories"] = _reader("memories", text=memory, used=2, total=2)
    registry["readers"]["interests"] = _reader("interests", text=interests, used=3, total=3)
    monkeypatch.setattr(seam, "_REGISTRY", {k: (r, PROBE) for k, r in registry["readers"].items()})
    whole_memories = render_catalogue_sections({"memories": memory})["memories"]
    one_interest = render_catalogue_sections({"interests": "## INTERESTS\n- first interest"})[
        "interests"
    ]
    budget = OpenAITokenCounter().count(whole_memories + "\n\n" + one_interest, "gpt-4o")
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=budget * 2
    )
    assert bundle.sections["memories"] == memory
    assert bundle.sections["interests"] == "## INTERESTS\n- first interest"
    assert bundle.provenance["sources"]["interests"] == {
        "status": "used",
        "used": 1,
        "total": 3,
        "reason": "over_budget",
    }
    assert bundle.provenance["sources"]["habits"]["status"] == "disabled"


async def test_nothing_is_cut_when_the_material_fits(registry: dict[str, Any]) -> None:
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=1_000_000
    )
    assert all("reason" not in v for v in bundle.provenance["sources"].values())


async def test_readers_run_one_at_a_time(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    in_flight = 0
    peak = 0

    def _slow(key: str):  # type: ignore[no-untyped-def]
        async def read(*, user_id: uuid.UUID, language: str) -> Any:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return PortraitSourceSection(key=key, status="empty", text="", used=0, total=0)

        return read

    monkeypatch.setattr(seam, "_REGISTRY", {k: (_slow(k), PROBE) for k in PORTRAIT_SOURCE_KEYS})
    await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=1_000_000
    )
    assert peak == 1


async def test_reference_overhead_counts_against_the_window_share(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

    # The raw source would fit; the references sent to the model do not.
    raw = "## LONG-TERM MEMORIES\n- a"
    tokens = OpenAITokenCounter().count(raw, "gpt-4o")
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=tokens * 2
    )
    assert bundle.sections["memories"] == ""
    assert bundle.provenance["sources"]["memories"]["reason"] == "over_budget"


async def test_source_with_only_incomplete_items_is_not_reported_as_used(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(
        "relation_debriefs",
        text="## RELATIONSHIP DEBRIEFS\n- A description\n  continued on a second line",
        total=2,
    )
    monkeypatch.setitem(seam._REGISTRY, "relation_debriefs", (reader, PROBE))
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=1_000_000
    )
    assert bundle.sections["relation_debriefs"] == ""
    assert bundle.provenance["sources"]["relation_debriefs"] == {
        "status": "empty",
        "used": 0,
        "total": 2,
        "omitted_incomplete": 1,
    }


async def test_an_overlong_item_is_cut_at_the_published_bound_never_dropped(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.shared.portrait_sources import PORTRAIT_ITEM_MAX_CHARS

    long_line = "- " + "x" * (PORTRAIT_ITEM_MAX_CHARS + 40)
    reader = _reader("workboard", text="## WORKBOARD\n" + long_line + "\n- short", used=2, total=2)
    monkeypatch.setitem(seam._REGISTRY, "workboard", (reader, PROBE))
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=1_000_000
    )
    kept = bundle.sections["workboard"].splitlines()[1]
    assert len(kept) == PORTRAIT_ITEM_MAX_CHARS and kept.startswith("- xxx")
    assert bundle.provenance["sources"]["workboard"] == {
        "status": "used",
        "used": 2,
        "total": 2,
        "cut_items": 1,
    }


async def test_a_section_whose_header_alone_exceeds_the_share_stays_used_with_nothing_kept(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not even the header fits: the section is absent from the prompt, and the provenance
    # says it was READ and CUT — never that it could not be read.
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=2
    )
    memories = bundle.provenance["sources"]["memories"]
    assert bundle.sections["memories"] == ""
    assert memories["status"] == "used" and memories["used"] == 0
    assert memories["reason"] == "over_budget" and memories["total"] > 0


async def test_the_cut_counts_eligible_items_only(
    registry: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.journals.portrait_catalogue import render_catalogue_sections
    from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter

    text = "## LONG-TERM MEMORIES\n- first\n- \n- second\n  continued\n- third"
    registry["readers"]["memories"] = _reader("memories", text=text, used=4, total=4)
    monkeypatch.setattr(seam, "_REGISTRY", {"memories": (registry["readers"]["memories"], PROBE)})
    two = render_catalogue_sections({"memories": "## LONG-TERM MEMORIES\n- first\n- third"})
    budget = OpenAITokenCounter().count(two["memories"], "gpt-4o")
    bundle = await build_portrait_source_sections(
        uuid.uuid4(), "fr", journal_entries=0, window_tokens=budget * 2
    )
    # Two eligible items of four lines; both fit exactly, so nothing is cut and
    # ``used`` counts the eligible items, the two incomplete lines being omitted.
    assert bundle.provenance["sources"]["memories"] == {
        "status": "used",
        "used": 2,
        "total": 4,
        "omitted_incomplete": 2,
    }
