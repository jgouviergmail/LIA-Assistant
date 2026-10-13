"""The deterministic admission: what the batch changed, what the parser could not read."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_output import (
    MaintenanceAction,
    MaintenanceOutput,
    PortraitClaim,
    PortraitSupport,
    admit_portrait_claims,
    changed_entry_ids,
)

pytestmark = pytest.mark.unit


def _entry(content: str):
    return SimpleNamespace(
        id=uuid4(),
        content=content,
        level="L1",
        confidence="high",
        contradiction_count=0,
        theme="learnings",
        revision=1,
        evidence_count=0,
    )


def _claim(entry, text="Une lecture fondée sur la règle du journal, formulée en prose."):
    return PortraitClaim(
        facet="posture",
        text=text,
        supports=[PortraitSupport(source=f"journal:{entry.id}", quote=entry.content)],
    )


def test_only_an_entry_the_batch_actually_changed_bars_the_claims_citing_it():
    entry = _entry("WHEN planning -> DO compare two options BECAUSE it was asked.")
    output = MaintenanceOutput(
        actions=[MaintenanceAction(action="update", entry_id=str(entry.id), title="Same title")],
        portrait_claims=[_claim(entry)],
        valid=True,
    )
    # Left to the proposal, a zero-effect update would drop the claim; told nothing
    # changed, the settlement keeps it.
    assert admit_portrait_claims(output, [entry], {}) == []
    assert admit_portrait_claims(output, [entry], {}, changed=set()) == [_claim(entry)]
    assert admit_portrait_claims(output, [entry], {}, changed={str(entry.id)}) == []


def test_a_merge_bars_the_winner_and_every_absorbed_source():
    winner, absorbed = _entry("WHEN a -> DO b BECAUSE c."), _entry("WHEN a -> DO b BECAUSE c.")
    output = MaintenanceOutput(
        actions=[
            MaintenanceAction(
                action="merge", entry_id=str(winner.id), merge_source_ids=[absorbed.id]
            )
        ],
        portrait_claims=[_claim(winner), _claim(absorbed, "Une autre lecture, autre prose.")],
        valid=True,
    )
    assert changed_entry_ids(output) == {str(winner.id), str(absorbed.id)}
    assert admit_portrait_claims(output, [winner, absorbed], {}) == []


def test_the_parsers_rejections_are_counted_with_the_drops(caplog):
    entry = _entry("WHEN x -> DO y BECAUSE z.")
    output = MaintenanceOutput(
        actions=[],
        portrait_claims=[_claim(entry)],
        rejected_claims=[{"claim_index": 1, "reason": "unreadable portrait claim", "codes": ["x"]}],
        valid=True,
    )
    with caplog.at_level("WARNING"):
        admitted = admit_portrait_claims(output, [entry], {})
    assert admitted == [_claim(entry)]
    event = next(r for r in caplog.records if "journal_portrait_claims_dropped" in r.getMessage())
    assert "'proposed': 2" in event.getMessage() and "'dropped': 1" in event.getMessage()


def test_a_validation_pass_parses_each_section_once(monkeypatch):
    # Resolving every support against a freshly parsed section cost 0.8 s on a 150-item
    # section and 10.6 s on 2000 items (32 claims x 40 supports, measured 2026-10-12 c),
    # synchronous CPU under the owner lock: one pass parses each section ONCE.
    from src.domains.journals import portrait_catalogue

    parses: list[str] = []
    original = portrait_catalogue.complete_item_lines

    def counted(section: str) -> list[str]:
        parses.append(section[:8])
        return original(section)

    monkeypatch.setattr(portrait_catalogue, "complete_item_lines", counted)
    lines = [f"- [personal] Observation {word} de la semaine. (2026-10-01)" for word in "abcde"]
    section = "## LONG-TERM MEMORIES (five of five)\n" + "\n".join(lines)
    claims = [
        PortraitClaim(
            facet="posture",
            text=f"Lecture {word} croisant plusieurs observations sans en recopier une seule.",
            supports=[PortraitSupport(source="memories", quote=line) for line in lines],
        )
        for word in "xyz"
    ]
    output = MaintenanceOutput(actions=[], portrait_claims=claims, valid=True)
    assert len(admit_portrait_claims(output, [], {"memories": section})) == 3
    assert len(parses) == 1
