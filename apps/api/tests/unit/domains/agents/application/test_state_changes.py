"""Only verified saved changes invalidate the authenticated account's UI."""

import asyncio
from uuid import uuid4

import pytest

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.helpers.runtime_context import installed_runtime_context
from tests.unit.domains.agents.application.test_native_draft import content

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("committed,no_op", [(False, False), (True, False), (True, True)])
def test_invalidation_reflects_the_actual_write_receipt(committed: bool, no_op: bool) -> None:
    draft = ApplicationActionDraftContent.model_validate(content())
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=draft.actor_id, side_channel_queue=queue):
        publish_preference_change(draft, PreferenceWriteReceipt(committed=committed, no_op=no_op))
    assert queue.qsize() == int(committed and not no_op)
    if not queue.empty():
        event = queue.get_nowait()
        assert event.type == "application_state_changed"
        assert event.metadata["change"]["actor_id"] == str(draft.actor_id)
        assert event.metadata["change"]["resources"] == ["profile"]
        assert event.metadata["change"]["changed_fields"] == list(draft.after)
        assert "values" not in event.metadata["change"]


def test_no_event_can_invalidate_another_accounts_interface() -> None:
    draft = ApplicationActionDraftContent.model_validate(content())
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=uuid4(), side_channel_queue=queue):
        publish_preference_change(draft, PreferenceWriteReceipt(committed=True))
    assert queue.empty()


def test_every_native_action_field_can_publish_a_typed_ui_invalidation() -> None:
    from typing import get_args

    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.application.state_changes import ApplicationStateChange

    union = get_args(ApplicationStateChange.model_fields["changed_fields"].annotation)[0]
    declared = {field.value for enum in get_args(union) for field in enum}
    missing_operations = {}
    for operation in APPLICATION_OPERATIONS.all():
        if operation.kind == OperationKind.ACTION:
            fields = set(operation.input_model.model_fields)
            # Source journal editing stores configuration privately, while its
            # canonical before/after and UI event name the resulting entry.
            if operation.operation_id == "journal_entries.update":
                assert fields == {"journal_configuration"}
                fields = {"journal_entry"}
            missing = fields - declared
            if missing:
                missing_operations[operation.operation_id] = missing
    assert not missing_operations, missing_operations


def test_shared_mcp_invalidation_contains_no_server_data_or_digest() -> None:
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferencePatch
    from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot

    before = SharedMCPPreferenceSnapshot(
        server_key="private-service",
        name="Private",
        enabled_for_user=True,
        tools_count=1,
        catalogue_digest="a" * 64,
    )
    draft = _preference_content(
        uuid4(),
        SharedMCPPreferencePatch(
            shared_mcp_server=before.model_copy(update={"enabled_for_user": False})
        ),
        {"shared_mcp_server": before.model_dump(mode="json")},
    )
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=draft.actor_id, side_channel_queue=queue):
        publish_preference_change(draft, PreferenceWriteReceipt(committed=True))
    event = queue.get_nowait()
    assert event.metadata["change"]["resources"] == ["shared_mcp_preferences"]
    assert event.metadata["change"]["changed_fields"] == ["shared_mcp_server"]
    assert "private-service" not in str(event.metadata) and "a" * 64 not in str(event.metadata)


@pytest.mark.parametrize(
    "connector_type,resources",
    [
        ("google_gmail", ["connectors"]),
        ("simli", ["connectors", "avatar"]),
        ("gemini_live", ["connectors", "live_connectors"]),
        ("gpt_live", ["connectors", "live_connectors"]),
        ("elevenlabs_live", ["connectors", "live_connectors"]),
    ],
)
def test_connection_unlink_invalidates_its_owned_card_list_without_private_identity(
    connector_type: str, resources: list[str]
) -> None:
    from src.domains.agents.application.connection_schemas import ConnectorConnectionUnlinkPatch
    from src.domains.agents.application.preparation import _preference_content
    from src.domains.connectors.models import ConnectorType
    from src.domains.connectors.removal_commands import connector_removal_snapshot
    from src.domains.users.models import User
    from tests.unit.domains.connectors.test_removal_commands import connector

    actor = User(id=uuid4())
    saved = connector(actor)
    saved.connector_type = ConnectorType(connector_type)
    snapshot = connector_removal_snapshot(saved)
    draft = _preference_content(
        actor.id,
        ConnectorConnectionUnlinkPatch(connector_to_disconnect=snapshot),
        {"connector_to_disconnect": snapshot.model_dump(mode="json")},
    )
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=actor.id, side_channel_queue=queue):
        publish_preference_change(draft, PreferenceWriteReceipt(committed=True))
    event = queue.get_nowait()
    assert event.metadata["change"]["resources"] == resources
    assert event.metadata["change"]["changed_fields"] == ["connector_to_disconnect"]
    assert "reader@example.test" not in str(event.metadata) and str(saved.id) not in str(
        event.metadata
    )
