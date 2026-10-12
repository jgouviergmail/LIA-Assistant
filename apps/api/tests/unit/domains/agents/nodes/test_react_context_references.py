"""The ReAct loop reads the turn's references under the pipeline's own section."""

import pytest

from src.domains.agents.analysis.resolved_references import (
    ReferenceSource,
    ReferenceValueKind,
    ResolvedReferenceEntry,
)
from src.domains.agents.nodes.react_context import build_reference_resolution_block

pytestmark = pytest.mark.unit


def test_the_block_is_the_pipeline_section_with_kinds() -> None:
    entry = ResolvedReferenceEntry(
        "montbéliard", "Montbéliard", ReferenceValueKind.PLACE, ReferenceSource.ANALYZER
    )
    block = build_reference_resolution_block(
        {"query_intelligence": {"resolved_references": [entry.to_dict()]}}
    )
    assert block is not None
    assert "<ResolvedReferences>" in block and "</ResolvedReferences>" in block
    assert "References resolved for this turn" in block
    assert '- "montbéliard" = Montbéliard [place]' in block
    assert "MemoryContext" not in block


def test_no_reference_no_block() -> None:
    assert (
        build_reference_resolution_block({"query_intelligence": {"resolved_references": None}})
        is None
    )


def test_a_stale_state_copy_never_reaches_the_loop() -> None:
    assert (
        build_reference_resolution_block(
            {
                "query_intelligence": {"resolved_references": None},
                "resolved_references": {"montbéliard": "Montbéliard"},
            }
        )
        is None
    )
