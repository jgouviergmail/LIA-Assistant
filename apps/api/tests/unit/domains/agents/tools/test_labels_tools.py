"""Unit tests for labels_tools disambiguation handling.

Regression coverage for the 2026-07 codebase audit (wave 1):
- The disambiguation dict returned by ``execute_api_call`` has no
  ``label_id`` key, but ``DeleteLabelDraftTool.format_registry_response``
  accessed ``result["label_id"]`` unconditionally -> KeyError -> the user got
  a generic INTERNAL_ERROR instead of the disambiguation question.
- ``ApplyLabelsTool``/``RemoveLabelsTool`` reported the disambiguation dict
  through ``action_success`` -> the LLM believed the action succeeded.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.tools.labels_tools import (
    ApplyLabelsTool,
    DeleteLabelDraftTool,
    RemoveLabelsTool,
)

# ============================================================================
# FIXTURES
# ============================================================================

CANDIDATES = [
    {"id": "Label_1", "name": "Perso/Factures"},
    {"id": "Label_2", "name": "Travail/Factures"},
]


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid4()


@pytest.fixture
def ambiguous_client():
    """Gmail client mock whose label resolution is ambiguous."""
    client = AsyncMock()
    client.is_system_label = lambda name: False
    client.resolve_label_with_disambiguation = AsyncMock(
        return_value={"resolved": False, "candidates": CANDIDATES}
    )
    return client


# ============================================================================
# REGRESSION: delete of an ambiguous label must ask, not crash (audit item 7)
# ============================================================================


@pytest.mark.unit
async def test_delete_ambiguous_label_returns_disambiguation_not_error(ambiguous_client, user_id):
    """The disambiguation path must produce a non-success output with the question."""
    tool = DeleteLabelDraftTool()

    result = await tool.execute_api_call(
        ambiguous_client, user_id, label_name="Factures", language="fr"
    )
    output = tool.format_registry_response(result)  # KeyError before the fix

    assert output.success is False
    assert output.message == result["message"]
    assert output.metadata.get("requires_disambiguation") is True
    assert output.metadata.get("candidates") == CANDIDATES


@pytest.mark.unit
async def test_apply_ambiguous_label_is_not_reported_as_success(ambiguous_client, user_id):
    """Apply on an ambiguous label must not claim the labels were applied."""
    tool = ApplyLabelsTool()

    result = await tool.execute_api_call(
        ambiguous_client, user_id, message_ids=["m1"], label_names=["Factures"], language="fr"
    )
    output = tool.format_registry_response(result)

    assert output.success is False
    assert output.metadata.get("requires_disambiguation") is True


@pytest.mark.unit
async def test_remove_ambiguous_label_is_not_reported_as_success(ambiguous_client, user_id):
    """Remove on an ambiguous label must not claim the labels were removed."""
    tool = RemoveLabelsTool()

    result = await tool.execute_api_call(
        ambiguous_client, user_id, message_ids=["m1"], label_names=["Factures"], language="fr"
    )
    output = tool.format_registry_response(result)

    assert output.success is False
    assert output.metadata.get("requires_disambiguation") is True
