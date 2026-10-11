"""A changed second phase must not hide an acknowledged first-phase write."""

from uuid import uuid4

import pytest

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application import draft_execution
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.psyche_summary_schemas import (
    PsycheSummaryPatch,
    PsycheSummaryScope,
)
from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


async def test_stale_remaining_phase_preserves_committed_first_phase(monkeypatch):
    scope = PsycheSummaryScope(
        digest="a" * 64, input_digest="b" * 64, state_present=False, language="fr", settings={}
    )
    public = scope.public_scope()
    draft = build_action_content(
        uuid4(),
        PSYCHE_SUMMARY_OPERATION,
        PsycheSummaryPatch(psyche_summary=scope),
        {"psyche_summary": public},
        {"psyche_summary": {**public, "requested": True}},
    )
    observed = {"psyche_summary": {"state_initialized": True, "generation_status": "not_started"}}

    async def partial(draft, actor_id, receipt):
        receipt.committed, receipt.values = True, observed
        raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})

    monkeypatch.setattr(draft_execution, "_apply_approved_action", partial)
    result = await draft_execution._execute_outcome(draft, draft.actor_id, PreferenceWriteReceipt())
    assert not result.success and result.error_code == "STALE_STATE"
    assert result.committed and result.values == observed
