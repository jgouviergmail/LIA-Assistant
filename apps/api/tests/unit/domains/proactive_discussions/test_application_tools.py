"""Native application identities, exact HITL writes and owner-scoped context selectors."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.discussion_commands import execute_discussion_action
from src.domains.agents.application.discussion_schemas import (
    DiscussionPreferencesIntent,
    DiscussionUseIntent,
)
from src.domains.agents.application.discussion_specs import (
    DISCUSSION_MANIFESTS,
    DISCUSSION_OPERATIONS,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.unit


def test_every_discussion_operation_has_one_native_manifest_with_the_same_schema():
    assert len(DISCUSSION_OPERATIONS) == 8
    assert {"list_lia_discussions_tool", "get_lia_discussion_details_tool"} <= {
        spec.tool_name for spec in DISCUSSION_OPERATIONS
    }
    by_name = {manifest.name: manifest for manifest in DISCUSSION_MANIFESTS}
    for spec in DISCUSSION_OPERATIONS:
        assert spec.tool_name in by_name
        assert spec.sections == ("proactive-discussions",)
        assert not by_name[spec.tool_name].initiative_eligible


def test_context_controls_reject_ambiguous_or_foreign_authority_fields():
    with pytest.raises(ValidationError):
        DiscussionUseIntent.model_validate(
            {
                "discussion_context_use": {
                    "item_id": str(uuid4()),
                    "usable": True,
                    "owner_id": str(uuid4()),
                }
            }
        )
    with pytest.raises(ValidationError):
        DiscussionPreferencesIntent.model_validate({"discussion_preferences": {"enabled": None}})


@pytest.mark.asyncio
async def test_unapproved_internal_execution_never_reaches_the_database():
    from types import SimpleNamespace

    db = AsyncMock()
    with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
        await execute_discussion_action(
            db, uuid4(), SimpleNamespace(actor_id=None), PreferenceWriteReceipt()
        )
    db.execute.assert_not_called()
