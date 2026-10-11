"""Late authority withdrawal must retain its finite public refusal, never provider details."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.agents.application import draft_execution
from src.domains.agents.application.draft_models import ApplicationActionDraftContent

pytestmark = pytest.mark.unit


async def test_authority_withdrawn_after_claim_returns_capability_refusal_without_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = uuid4()
    draft = ApplicationActionDraftContent(
        command_id=uuid4(),
        actor_id=actor_id,
        operation_id="live_connector_preferences.update",
        schema_fingerprint="a" * 64,
        expected_digest="b" * 64,
        intent={},
        before={},
        after={},
        title="Live",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db = AsyncMock()

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(draft_execution, "get_db_context", session)
    monkeypatch.setattr(draft_execution, "validate_execution", AsyncMock(return_value=draft))
    monkeypatch.setattr(draft_execution, "claim_command", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(draft_execution, "close_command", AsyncMock(return_value=True))
    monkeypatch.setattr(
        draft_execution,
        "require_application_tools",
        AsyncMock(
            side_effect=AuthorizationError(
                detail={"error_code": "CAPABILITY_DISABLED", "private": "credential"}
            )
        ),
    )
    effect = AsyncMock()
    monkeypatch.setattr(draft_execution, "execute_preference_patch", effect)
    result = await draft_execution.execute_application_action_draft(
        draft.model_dump(mode="json"), actor_id, None
    )
    assert result["success"] is False and result["error_code"] == "CAPABILITY_DISABLED"
    assert not result["committed"] and "credential" not in str(result)
    effect.assert_not_awaited()
