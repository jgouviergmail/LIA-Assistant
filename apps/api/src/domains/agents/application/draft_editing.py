"""Rebuild a modified proposal from current state and replace its approval digest."""

from pydantic import TypeAdapter, ValidationError

from src.domains.agents.application.channel_operations import (
    prepare_channel_binding_content,
    prepare_channel_unlink_content,
)
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.connection_operations import prepare_connector_unlink_content
from src.domains.agents.application.connection_schemas import ConnectorUnlinkRequest
from src.domains.agents.application.connector_operations import prepare_connector_preference_content
from src.domains.agents.application.connector_schemas import ConnectorPreferenceUpdateRequest
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_action import prepare_account_export
from src.domains.agents.application.export_download import prepare_export_download
from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.agents.application.habit_editing import rebuild_habit_draft
from src.domains.agents.application.habit_settings_editing import rebuild_habit_settings_draft
from src.domains.agents.application.heartbeat_operations import prepare_heartbeat_content
from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferencePatch
from src.domains.agents.application.ingestion_editors import INGESTION_EDITORS
from src.domains.agents.application.interest_editing import rebuild_interest_draft
from src.domains.agents.application.interest_settings import prepare_interest_settings
from src.domains.agents.application.interest_settings_schemas import InterestSettingsPatch
from src.domains.agents.application.journal_consolidation_editing import (
    rebuild_journal_consolidation_draft,
)
from src.domains.agents.application.journal_creation_editing import rebuild_journal_creation_draft
from src.domains.agents.application.journal_feedback_editing import rebuild_journal_feedback_draft
from src.domains.agents.application.journal_removal_editing import rebuild_journal_removal_draft
from src.domains.agents.application.journal_settings_editing import rebuild_journal_settings_draft
from src.domains.agents.application.journal_update_editing import rebuild_journal_update_draft
from src.domains.agents.application.layout_editing import _revision_intent
from src.domains.agents.application.live_connector_operations import prepare_live_connector_content
from src.domains.agents.application.live_connector_schemas import LiveConnectorChangeRequest
from src.domains.agents.application.live_operations import prepare_live_preference_content
from src.domains.agents.application.live_schemas import LivePreferenceRequest
from src.domains.agents.application.location_preparation import (
    prepare_location_change,
    prepare_location_patch,
)
from src.domains.agents.application.location_schemas import HomeLocationPatch, LocationChangeRequest
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_export_editing import rebuild_management_export_draft
from src.domains.agents.application.memory_editing import rebuild_memory_draft
from src.domains.agents.application.notification_operations import (
    prepare_notification_device_removal,
)
from src.domains.agents.application.notification_schemas import NotificationDeviceRemoveRequest
from src.domains.agents.application.open_loop_editing import rebuild_open_loop_draft
from src.domains.agents.application.operation_spec import ApplicationEmptyRead
from src.domains.agents.application.phone_number_operations import prepare_phone_number
from src.domains.agents.application.phone_number_schemas import PhoneNumberRequest
from src.domains.agents.application.phone_preference_operations import prepare_phone_preferences
from src.domains.agents.application.phone_preference_schemas import PhonePreferenceRequest
from src.domains.agents.application.preference_dispatch import PreferenceIntent, preference_model
from src.domains.agents.application.preparation import (
    prepare_assistant_content,
    prepare_layout_content,
    prepare_preference_content,
)
from src.domains.agents.application.psyche_reset_editing import rebuild_psyche_reset_draft
from src.domains.agents.application.psyche_settings_editing import rebuild_psyche_settings_draft
from src.domains.agents.application.psyche_summary_editing import rebuild_psyche_summary_draft
from src.domains.agents.application.reminder_card_selection import reminder_card_scope
from src.domains.agents.application.reminder_create_schemas import ReminderCreateRequest
from src.domains.agents.application.reminder_creation import prepare_reminder_creation
from src.domains.agents.application.reminder_removal import prepare_reminder_removal
from src.domains.agents.application.reminder_removal_schemas import (
    ReminderDeletePatch,
    ReminderDeleteRequest,
)
from src.domains.agents.application.reminder_update import prepare_reminder_update
from src.domains.agents.application.reminder_update_schemas import ReminderUpdateRequest
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_creation import prepare_routine_creation
from src.domains.agents.application.routine_execution import prepare_routine_launch
from src.domains.agents.application.routine_operations import prepare_routine_state
from src.domains.agents.application.routine_removal import prepare_routine_removal
from src.domains.agents.application.routine_removal_schemas import RoutineDeleteRequest
from src.domains.agents.application.routine_run_schemas import RoutineRunRequest
from src.domains.agents.application.routine_schemas import RoutineStateRequest
from src.domains.agents.application.routine_update import prepare_routine_update
from src.domains.agents.application.routine_update_schemas import RoutineUpdateRequest
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.agents.application.session_bulk_operations import prepare_other_sessions_revocation
from src.domains.agents.application.session_revocation_operations import prepare_session_revocation
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.agents.application.shared_mcp_operations import prepare_shared_mcp_content
from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferenceUpdateRequest
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.auth.preference_commands import AssistantPreferencePatch
from src.infrastructure.account_preferences import LayoutPreferencePatch
from src.infrastructure.database.session import get_db_context

_REMOVALS: TypeAdapter[list[str]] = TypeAdapter(list[str])


async def _rebuild_session_revocation(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        if old.operation_id == "device_sessions.revoke_others":
            ApplicationEmptyRead.model_validate(modified.get("intent"))
            revised = await prepare_other_sessions_revocation(
                db, old.actor_id, origin=context.application_origin, command_id=old.command_id
            )
        else:
            request = DeviceSessionRevokeRequest.model_validate(modified.get("intent"))
            revised = await prepare_session_revocation(
                db,
                old.actor_id,
                request,
                origin=context.application_origin,
                command_id=old.command_id,
            )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_export_download(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ExportDownloadRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_export_download(
            db, old.actor_id, request, origin=context.application_origin, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_export(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    ApplicationEmptyRead.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_account_export(
            db, old.actor_id, origin=context.application_origin, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def rebuild_application_draft(
    original: dict[str, object], modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    try:
        old = ApplicationActionDraftContent.model_validate(original)
        editor = {
            "journal_portrait.feedback": rebuild_journal_feedback_draft,
            "journals.consolidate": rebuild_journal_consolidation_draft,
            "journal_entries.update": rebuild_journal_update_draft,
            "journal_entries.create": rebuild_journal_creation_draft,
            "journal_entries.delete": rebuild_journal_removal_draft,
            "journal_settings.update": rebuild_journal_settings_draft,
            "psyche.reset": rebuild_psyche_reset_draft,
            **INGESTION_EDITORS,
            "psyche.summary": rebuild_psyche_summary_draft,
            "psyche_settings.update": rebuild_psyche_settings_draft,
            **MANAGEMENT_EDITORS,
            "habit_settings.update": rebuild_habit_settings_draft,
            "habits.status": rebuild_habit_draft,
            "habits.delete": rebuild_habit_draft,
            "habits.forget": rebuild_habit_draft,
            "habits.recompute": rebuild_habit_draft,
            "open_loops.update": rebuild_open_loop_draft,
            "open_loops.close": rebuild_open_loop_draft,
            "interests.export": rebuild_management_export_draft,
            "memories.export": rebuild_management_export_draft,
            "journals.export": rebuild_management_export_draft,
            "interests.feedback": _rebuild_interest,
            "interests.reactivate": _rebuild_interest,
            "interests.create": _rebuild_interest,
            "interests.delete_all": _rebuild_interest,
            "interests.delete": _rebuild_interest,
            "interests.update": _rebuild_interest,
            "memories.update": _rebuild_memory,
            "memories.delete": _rebuild_memory,
            "memories.delete_all": _rebuild_memory,
            "memories.create": _rebuild_memory,
            "memories.pin": _rebuild_memory,
            "account_export.download": _rebuild_export_download,
            "reminder.update": _rebuild_reminder_update,
            "reminder.create": _rebuild_reminder_creation,
            "reminder.delete": _rebuild_reminder_removal,
            "account_export.request": _rebuild_export,
            "routine_state.update": _rebuild_routine_state,
            "routine.create": _rebuild_routine_creation,
            "routine.delete": _rebuild_routine_removal,
            "routine.update": _rebuild_routine_update,
            "routine.execute": _rebuild_routine_launch,
            "home_location.update": _rebuild_location,
            "channel_binding.update": _rebuild_channel,
            "channel_binding.unlink": _rebuild_channel,
            "connector_preferences.update": _rebuild_connector,
            "shared_mcp_preferences.update": _rebuild_shared_mcp,
            "connector_connection.unlink": _rebuild_connector_unlink,
            "notification_device.remove": _rebuild_notification_removal,
            "live_preferences.update": _rebuild_live_preferences,
            "live_connector_preferences.update": _rebuild_live_connector,
            "phone_preferences.update": _rebuild_phone_preferences,
            "phone_number.update": _rebuild_phone_number,
            "device_session.revoke": _rebuild_session_revocation,
            "device_sessions.revoke_others": _rebuild_session_revocation,
        }.get(old.operation_id)
        if editor is not None:
            return await editor(old, modified)
        patch = _modified_preference_patch(old, modified)
    except CommandRejected:
        raise
    except ValidationError, ValueError:
        raise CommandRejected("INVALID_INPUT") from None
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    async with get_db_context() as db:
        if isinstance(patch, PreferencePatch):
            revised = await prepare_preference_content(
                db, context.user_id, patch, command_id=old.command_id
            )
        elif isinstance(patch, AssistantPreferencePatch):
            revised = await prepare_assistant_content(
                db, context.user_id, patch, command_id=old.command_id
            )
        elif isinstance(patch, LayoutPreferencePatch):
            revised = await prepare_layout_content(
                db, context.user_id, patch, command_id=old.command_id
            )
        elif isinstance(patch, HeartbeatPreferencePatch):
            revised = await prepare_heartbeat_content(
                db, context.user_id, patch, command_id=old.command_id
            )
        elif isinstance(patch, InterestSettingsPatch):
            revised = await prepare_interest_settings(
                db, context.user_id, patch, command_id=old.command_id
            )
        else:
            raise CommandRejected("UNKNOWN_OPERATION")
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_connector(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ConnectorPreferenceUpdateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_connector_preference_content(
            db,
            old.actor_id,
            request,
            command_id=old.command_id,
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_routine_state(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RoutineStateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_routine_state(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_memory(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    async with get_db_context() as db:
        return await rebuild_memory_draft(db, old, modified)


async def _rebuild_reminder_update(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ReminderUpdateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_reminder_update(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_reminder_removal(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ReminderDeleteRequest.model_validate(modified.get("intent"))
    selected = ReminderDeletePatch.model_validate(old.intent).reminder_to_delete
    async with reminder_card_scope(old.actor_id, selected.id, selected.card_selection):
        async with get_db_context() as db:
            revised = await prepare_reminder_removal(
                db, old.actor_id, request, command_id=old.command_id
            )
            if not await replace_pending_command(db, old, revised):
                raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_reminder_creation(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ReminderCreateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_reminder_creation(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_interest(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    async with get_db_context() as db:
        return await rebuild_interest_draft(db, old, modified)


async def _rebuild_routine_creation(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RoutineCreateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_routine_creation(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_routine_launch(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RoutineRunRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_routine_launch(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_routine_update(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RoutineUpdateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_routine_update(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_routine_removal(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = RoutineDeleteRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_routine_removal(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_phone_number(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = PhoneNumberRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_phone_number(db, old.actor_id, request, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_phone_preferences(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = PhonePreferenceRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_phone_preferences(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_live_connector(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = LiveConnectorChangeRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_live_connector_content(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_live_preferences(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = LivePreferenceRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_live_preference_content(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_notification_removal(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = NotificationDeviceRemoveRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_notification_device_removal(
            db,
            old.actor_id,
            request,
            command_id=old.command_id,
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_connector_unlink(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = ConnectorUnlinkRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_connector_unlink_content(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_shared_mcp(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = SharedMCPPreferenceUpdateRequest.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        revised = await prepare_shared_mcp_content(
            db, old.actor_id, request, command_id=old.command_id
        )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


async def _rebuild_channel(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        if old.operation_id == "channel_binding.unlink":
            unlink = ChannelBindingUnlinkRequest.model_validate(modified.get("intent"))
            revised = await prepare_channel_unlink_content(
                db,
                old.actor_id,
                unlink,
                command_id=old.command_id,
            )
        else:
            request = ChannelBindingUpdateRequest.model_validate(modified.get("intent"))
            revised = await prepare_channel_binding_content(
                db,
                old.actor_id,
                request,
                command_id=old.command_id,
            )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")


def _modified_preference_patch(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> PreferenceIntent:
    model = preference_model(old.operation_id)
    requested = (
        model.model_validate(_revision_intent(old, modified["intent"]))
        if modified.get("intent")
        else None
    )
    removals = _REMOVALS.validate_python(modified.get("remove_fields", []), strict=True)
    if not set(removals) <= set(model.model_fields) or len(removals) != len(set(removals)):
        raise ValueError("Unknown or duplicate removal field")
    return model.model_validate(
        {
            **{key: value for key, value in old.intent.items() if key not in removals},
            **(
                {
                    key: value
                    for key, value in requested.model_dump(exclude_unset=True).items()
                    if key not in removals
                }
                if requested is not None
                else {}
            ),
        }
    )


async def _rebuild_location(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    request = LocationChangeRequest.model_validate(modified.get("intent"))
    previous = HomeLocationPatch.model_validate(old.intent)
    unchanged = request.action == ("set" if previous.home_location else "clear") and (
        previous.home_location is None or request.address == previous.home_location.address
    )
    async with get_db_context() as db:
        if unchanged:
            revised = await prepare_location_patch(
                db, old.actor_id, previous, command_id=old.command_id
            )
        else:
            revised = await prepare_location_change(
                db, old.actor_id, request, command_id=old.command_id
            )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
