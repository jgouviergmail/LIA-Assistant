"""A JEV qualification reaches the model's data block as labels and a state (2026-10-25).

The ReAct loop and the pipeline's tool data read one function, ``extract_data_block``.
The structured data a tool returns is also what the cards and the registry read,
with the annotation's instants: only the model's copy is projected.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest

from src.core.content_classification import EventClassification
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import extract_data_block

pytestmark = pytest.mark.unit

AN_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def test_the_model_reads_the_state_never_the_annotation_s_instants() -> None:
    now = datetime.now(UTC)
    annotation = EventClassification.model_validate(
        {
            "category": "personal",
            "evidence_scope": "event",
            "evaluated_at": now,
            "valid_until": now + timedelta(hours=1),
        }
    ).model_dump(mode="json")
    output = UnifiedToolOutput.data_success(
        message="1 event",
        structured_data={"events": [{"id": "e1", "classification": annotation}]},
    )

    block = extract_data_block(output, 4000)

    assert block is not None
    assert '"state": "current"' in block.text
    assert '"category": "personal"' in block.text
    assert "valid_until" not in block.text
    assert not AN_INSTANT.search(block.text)
    # What the cards read keeps the annotation whole.
    assert "valid_until" in output.structured_data["events"][0]["classification"]
