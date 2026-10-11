"""A confirmed caller can revoke authority before provider work or settlement."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_controls import (
    ConsolidationControlRefused,
    ConsolidationControls,
    installed_consolidation_controls,
)
from src.domains.journals.service import _generate_document_embedding

pytestmark = pytest.mark.unit


async def test_withdrawn_embedding_authority_is_not_swallowed_as_provider_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MagicMock()
    monkeypatch.setattr("src.domains.journals.embedding.get_journal_embeddings", provider)
    controls = ConsolidationControls(
        user_id=uuid4(),
        before_work=AsyncMock(),
        before_commit=AsyncMock(),
        before_embedding=AsyncMock(side_effect=PermissionError("withdrawn")),
        note_committed=MagicMock(),
    )
    with installed_consolidation_controls(controls):
        with pytest.raises(ConsolidationControlRefused):
            await _generate_document_embedding("owned text")
    provider.assert_not_called()


async def test_caller_scope_is_restored_after_nested_control_lifetimes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.domains.journals.consolidation_controls.enforce_usage_limit", AsyncMock()
    )
    from src.domains.journals.consolidation_controls import check_consolidation_embedding

    def controls():
        return ConsolidationControls(
            user_id=uuid4(),
            before_work=AsyncMock(),
            before_commit=AsyncMock(),
            before_embedding=AsyncMock(),
            note_committed=MagicMock(),
        )

    outer, inner = controls(), controls()
    with installed_consolidation_controls(outer):
        with installed_consolidation_controls(inner):
            await check_consolidation_embedding()
        await check_consolidation_embedding()
    await check_consolidation_embedding()
    outer.before_embedding.assert_awaited_once()
    inner.before_embedding.assert_awaited_once()
