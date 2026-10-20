"""Bounded native editing prompt; no actor, secret or structural draft field."""

import json

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkPatch,
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdatePatch,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionUnlinkPatch,
    ConnectorUnlinkRequest,
)
from src.domains.agents.application.connector_schemas import (
    ConnectorPreferencePatch,
    ConnectorPreferenceUpdateRequest,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_action import AccountExportRequest
from src.domains.agents.application.export_download_schemas import (
    ExportDownloadPatch,
    ExportDownloadRequest,
)
from src.domains.agents.application.habit_action_schemas import (
    HabitDeletePatch,
    HabitDeleteRequest,
    HabitStatusPatch,
    HabitStatusRequest,
)
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch, HabitForgetRequest
from src.domains.agents.application.habit_recompute_schemas import (
    HabitRecomputePatch,
    HabitRecomputeRequest,
)
from src.domains.agents.application.health_removal_schemas import (
    HealthRemovalPatch,
    HealthRemovalRequest,
)
from src.domains.agents.application.health_token_creation_schemas import (
    HealthTokenCreatePatch,
    HealthTokenCreateRequest,
)
from src.domains.agents.application.health_token_schemas import (
    HealthTokenRevokePatch,
    HealthTokenRevokeRequest,
)
from src.domains.agents.application.interest_bulk_schemas import (
    InterestBulkDeletePatch,
    InterestBulkDeleteRequest,
)
from src.domains.agents.application.interest_create_schemas import (
    InterestCreateConfiguration,
    InterestCreatePatch,
)
from src.domains.agents.application.interest_feedback_schemas import (
    InterestFeedbackPatch,
    InterestFeedbackSelection,
)
from src.domains.agents.application.interest_reactivation_schemas import (
    InterestReactivateRequest,
    InterestReactivationPatch,
)
from src.domains.agents.application.interest_removal_schemas import (
    InterestDeletePatch,
    InterestDeleteRequest,
)
from src.domains.agents.application.interest_update_schemas import (
    InterestUpdatePatch,
    InterestUpdateRequest,
)
from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationPatch,
    JournalConsolidationRequest,
)
from src.domains.agents.application.journal_create_schemas import (
    JournalCreateConfiguration,
    JournalCreatePatch,
)
from src.domains.agents.application.journal_feedback_schemas import (
    JournalFeedbackPatch,
    JournalFeedbackRequest,
)
from src.domains.agents.application.journal_removal_schemas import (
    JournalDeletePatch,
    JournalDeleteRequest,
)
from src.domains.agents.application.journal_update_schemas import (
    JournalUpdatePatch,
    JournalUpdateRequest,
)
from src.domains.agents.application.live_connector_schemas import (
    LiveConnectorChangeRequest,
    LiveConnectorPreferencePatch,
)
from src.domains.agents.application.live_schemas import LivePreferencePatch, LivePreferenceRequest
from src.domains.agents.application.location_schemas import HomeLocationPatch, LocationChangeRequest
from src.domains.agents.application.management_editor_inputs import (
    MANAGEMENT_EDITOR_MODELS,
    management_editor_request,
)
from src.domains.agents.application.management_export_schemas import (
    ManagementExportPatch,
    ManagementExportRequest,
)
from src.domains.agents.application.memory_bulk_schemas import (
    MemoryBulkDeletePatch,
    MemoryBulkDeleteRequest,
)
from src.domains.agents.application.memory_create_schemas import (
    MemoryCreateConfiguration,
    MemoryCreatePatch,
)
from src.domains.agents.application.memory_pin_schemas import MemoryPinPatch, MemoryPinRequest
from src.domains.agents.application.memory_removal_schemas import (
    MemoryDeletePatch,
    MemoryDeleteRequest,
)
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdatePatch,
    MemoryUpdateRequest,
)
from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemovePatch,
    NotificationDeviceRemoveRequest,
)
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopClosePatch,
    OpenLoopCloseRequest,
    OpenLoopUpdatePatch,
    OpenLoopUpdateRequest,
)
from src.domains.agents.application.operation_spec import ApplicationEmptyRead, OperationKind
from src.domains.agents.application.peer_block_schemas import PeerBlockInput, PeerBlockPatch
from src.domains.agents.application.peer_image_schemas import PeerImageInput, PeerImagePatch
from src.domains.agents.application.peer_removal_schemas import PeerRemovalInput, PeerRemovalPatch
from src.domains.agents.application.peer_request_schemas import PeerRequestInput, PeerRequestPatch
from src.domains.agents.application.peer_response_schemas import (
    PeerResponseInput,
    PeerResponsePatch,
)
from src.domains.agents.application.peer_share_schemas import PeerShareInput, PeerSharePatch
from src.domains.agents.application.phone_number_schemas import PhoneNumberPatch, PhoneNumberRequest
from src.domains.agents.application.phone_preference_schemas import (
    PhonePreferencePatch,
    PhonePreferenceRequest,
)
from src.domains.agents.application.psyche_reset_schemas import PsycheResetIntent, PsycheResetPatch
from src.domains.agents.application.psyche_summary_schemas import (
    PsycheSummaryPatch,
    PsycheSummaryRequest,
)
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.relation_context_refresh_schemas import (
    RelationContextRefreshPatch,
    RelationContextRefreshRequest,
)
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildPatch,
    RelationDebriefBuildRequest,
)
from src.domains.agents.application.relation_favorite_schemas import (
    RelationFavoritePatch,
    RelationFavoriteRequest,
)
from src.domains.agents.application.relation_grouping_schemas import (
    RelationGroupingPatch,
    RelationGroupingRequest,
)
from src.domains.agents.application.reminder_create_schemas import (
    ReminderCreatePatch,
    ReminderCreateRequest,
)
from src.domains.agents.application.reminder_removal_schemas import (
    ReminderDeletePatch,
    ReminderDeleteRequest,
)
from src.domains.agents.application.reminder_update_schemas import (
    ReminderUpdatePatch,
    ReminderUpdateRequest,
)
from src.domains.agents.application.routine_create_schemas import (
    RoutineCreatePatch,
    RoutineCreateRequest,
)
from src.domains.agents.application.routine_removal_schemas import (
    RoutineDeletePatch,
    RoutineDeleteRequest,
)
from src.domains.agents.application.routine_run_schemas import RoutineRunPatch, RoutineRunRequest
from src.domains.agents.application.routine_schemas import RoutineStatePatch, RoutineStateRequest
from src.domains.agents.application.routine_update_schemas import (
    RoutineUpdatePatch,
    RoutineUpdateRequest,
)
from src.domains.agents.application.session_bulk_operations import OtherSessionsRevokePatch
from src.domains.agents.application.session_revocation_schemas import (
    DeviceSessionRevokePatch,
    DeviceSessionRevokeRequest,
)
from src.domains.agents.application.shared_mcp_schemas import (
    SharedMCPPreferencePatch,
    SharedMCPPreferenceUpdateRequest,
)
from src.domains.agents.application.sms_editor_inputs import SMS_EDITOR_MODELS, sms_editor_request
from src.domains.agents.prompts import load_prompt


def build_application_edit_prompt(
    original: dict[str, object], instructions: str
) -> list[dict[str, str]]:
    draft = ApplicationActionDraftContent.model_validate(original)
    model: type[BaseModel] = _editable_model(draft.operation_id)
    model, intent = _safe_editor_request(model, draft.intent)
    if model is PhoneNumberPatch:
        number = PhoneNumberPatch.model_validate(intent).phone_number.number
        intent = {"action": "set", "phone_number": number} if number else {"action": "clear"}
        model = PhoneNumberRequest
    if model is PhonePreferencePatch:
        current_phone = PhonePreferencePatch.model_validate(intent).phone_preferences
        intent = current_phone.values.model_dump(mode="json")
        model = PhonePreferenceRequest
    if model is HomeLocationPatch:
        home = HomeLocationPatch.model_validate(intent).home_location
        intent = {"action": "set", "address": home.address} if home else {"action": "clear"}
        model = LocationChangeRequest
    if model is ChannelBindingUpdatePatch:
        binding = ChannelBindingUpdatePatch.model_validate(intent).channel_binding
        intent = {"binding_id": str(binding.id), "enabled": binding.is_active}
        model = ChannelBindingUpdateRequest
    if model is ChannelBindingUnlinkPatch:
        binding = ChannelBindingUnlinkPatch.model_validate(intent).channel_binding
        intent = {"binding_id": str(binding.id)}
        model = ChannelBindingUnlinkRequest
    if model is ConnectorPreferencePatch:
        connector = ConnectorPreferencePatch.model_validate(intent).connector_preferences
        intent = {
            "connector_id": str(connector.id),
            "preferences": dict(connector.preferences),
        }
        model = ConnectorPreferenceUpdateRequest
    if model is SharedMCPPreferencePatch:
        shared = SharedMCPPreferencePatch.model_validate(intent).shared_mcp_server
        intent = {"server_key": shared.server_key, "enabled": shared.enabled_for_user}
        model = SharedMCPPreferenceUpdateRequest
    if model is ConnectorConnectionUnlinkPatch:
        connection = ConnectorConnectionUnlinkPatch.model_validate(intent).connector_to_disconnect
        intent = {"connector_id": str(connection.id)}
        model = ConnectorUnlinkRequest
    if model is NotificationDeviceRemovePatch:
        device = NotificationDeviceRemovePatch.model_validate(intent).notification_device_to_remove
        intent = {"device_id": str(device.id)}
        model = NotificationDeviceRemoveRequest
    if model is LivePreferencePatch:
        current = LivePreferencePatch.model_validate(intent).live_reflexes
        intent = current.values.model_dump(mode="json")
        model = LivePreferenceRequest
    if model is LiveConnectorPreferencePatch:
        current_settings = LiveConnectorPreferencePatch.model_validate(
            intent
        ).live_connector_settings
        intent = {
            "provider": current_settings.expected.provider,
            "settings": current_settings.settings.model_dump(mode="json"),
        }
        model = LiveConnectorChangeRequest
    system = load_prompt("application_draft_modifier_prompt").replace(
        "{preference_schema}", json.dumps(model.model_json_schema(), ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {"intent": intent, "revision_request": instructions},
                ensure_ascii=False,
            ),
        },
    ]


def _editable_model(operation_id: str) -> type[BaseModel]:
    try:
        spec = APPLICATION_OPERATIONS.get(operation_id)
    except KeyError:
        raise ValueError("Unknown application action") from None
    if spec.kind not in {OperationKind.ACTION, OperationKind.SECURE_HANDOFF, OperationKind.DEVICE}:
        raise ValueError("Operation cannot be edited as an action")
    return spec.input_model


def _memory_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is MemoryBulkDeletePatch:
        erased = MemoryBulkDeletePatch.model_validate(intent).memories_to_delete
        return MemoryBulkDeleteRequest, {"preserve_pinned": erased.preserve_pinned}
    if model is MemoryDeletePatch:
        removed = MemoryDeletePatch.model_validate(intent).memory_to_delete
        return MemoryDeleteRequest, {"memory_id": str(removed.id)}
    if model is MemoryUpdatePatch:
        edit = MemoryUpdatePatch.model_validate(intent).memory_configuration
        return MemoryUpdateRequest, {
            "memory_id": str(edit.expected.id),
            "changes": edit.changes.model_dump(mode="json", exclude_unset=True),
        }
    if model is MemoryCreatePatch:
        memory_creation = MemoryCreatePatch.model_validate(intent).memory_to_create
        return MemoryCreateConfiguration, memory_creation.configuration.model_dump(mode="json")
    if model is MemoryPinPatch:
        pinned_memory = MemoryPinPatch.model_validate(intent).memory_pin
        return MemoryPinRequest, {
            "memory_id": str(pinned_memory.expected.id),
            "pinned": pinned_memory.pinned,
        }
    raise ValueError("Unsupported memory editor")


def _interest_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is InterestReactivationPatch:
        dormant = InterestReactivationPatch.model_validate(intent).interest_to_reactivate
        return InterestReactivateRequest, {"interest_id": str(dormant.expected.id)}
    if model is InterestFeedbackPatch:
        verdict = InterestFeedbackPatch.model_validate(intent).interest_feedback
        selection = InterestFeedbackSelection(
            feedback=verdict.feedback,
            interest_id=None if verdict.notification else verdict.expected.id,
            notification_id=verdict.notification.id if verdict.notification else None,
        )
        return InterestFeedbackSelection, selection.model_dump(mode="json", exclude_none=True)
    if model is InterestBulkDeletePatch:
        InterestBulkDeletePatch.model_validate(intent)
        return InterestBulkDeleteRequest, {"scope": "all_owned"}
    if model is InterestCreatePatch:
        creation = InterestCreatePatch.model_validate(intent).interest_to_create
        return InterestCreateConfiguration, creation.configuration.model_dump(mode="json")
    if model is InterestUpdatePatch:
        edit = InterestUpdatePatch.model_validate(intent).interest_configuration
        return InterestUpdateRequest, {
            "interest_id": str(edit.expected.id),
            "changes": edit.changes.model_dump(mode="json", exclude_unset=True),
        }
    if model is InterestDeletePatch:
        removed = InterestDeletePatch.model_validate(intent).interest_to_delete
        return InterestDeleteRequest, {"interest_id": str(removed.expected.id)}
    raise ValueError("Unsupported interest editor")


def _relation_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is PeerImagePatch:
        return PeerImageInput, PeerImagePatch.model_validate(intent).peer_image.request.model_dump(
            mode="json"
        )
    if model is PeerBlockPatch:
        return PeerBlockInput, PeerBlockPatch.model_validate(intent).peer_block.request.model_dump(
            mode="json"
        )
    if model is PeerRemovalPatch:
        return PeerRemovalInput, PeerRemovalPatch.model_validate(
            intent
        ).peer_removal.request.model_dump(mode="json")
    if model is PeerSharePatch:
        return PeerShareInput, PeerSharePatch.model_validate(intent).peer_share.request.model_dump(
            mode="json"
        )
    if model is PeerResponsePatch:
        return PeerResponseInput, PeerResponsePatch.model_validate(
            intent
        ).peer_response.request.model_dump(mode="json")
    if model is PeerRequestPatch:
        return PeerRequestInput, PeerRequestPatch.model_validate(
            intent
        ).peer_request.request.model_dump(mode="json")
    if model is RelationContextRefreshPatch:
        return RelationContextRefreshRequest, RelationContextRefreshPatch.model_validate(
            intent
        ).relation_context.model_dump(mode="json")
    if model is RelationDebriefBuildPatch:
        return RelationDebriefBuildRequest, RelationDebriefBuildPatch.model_validate(
            intent
        ).relation_debrief.request.model_dump(mode="json")
    if model is RelationGroupingPatch:
        grouping_values = RelationGroupingPatch.model_validate(intent).relation_grouping
        return RelationGroupingRequest, {
            "action": grouping_values.action,
            "source": grouping_values.source,
            "target": grouping_values.target,
        }
    if model is RelationFavoritePatch:
        favorite_values = RelationFavoritePatch.model_validate(intent).relation_favorite
        return RelationFavoriteRequest, {
            "name": favorite_values.expected.name,
            "starred": favorite_values.starred,
        }
    raise ValueError("Unsupported relation editor")


def _reminder_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is ReminderDeletePatch:
        reminder = ReminderDeletePatch.model_validate(intent).reminder_to_delete
        return ReminderDeleteRequest, {"reminder_id": str(reminder.id)}
    if model is ReminderUpdatePatch:
        edited = ReminderUpdatePatch.model_validate(intent).reminder_configuration
        return ReminderUpdateRequest, {
            "reminder_id": str(edited.expected.id),
            "changes": edited.changes.model_dump(mode="json", exclude_unset=True),
        }
    created = ReminderCreatePatch.model_validate(intent).reminder_to_create
    return ReminderCreateRequest, created.configuration.model_dump(mode="json")


def _safe_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model in SMS_EDITOR_MODELS:
        return sms_editor_request(model, intent)
    if model in (
        RelationGroupingPatch,
        RelationFavoritePatch,
        RelationDebriefBuildPatch,
        RelationContextRefreshPatch,
        PeerRequestPatch,
        PeerResponsePatch,
        PeerSharePatch,
        PeerRemovalPatch,
        PeerBlockPatch,
        PeerImagePatch,
    ):
        return _relation_editor_request(model, intent)
    if model in (
        JournalDeletePatch,
        *MANAGEMENT_EDITOR_MODELS,
        JournalCreatePatch,
        JournalUpdatePatch,
        JournalFeedbackPatch,
        JournalConsolidationPatch,
        HabitStatusPatch,
        HabitDeletePatch,
        HabitForgetPatch,
        HabitRecomputePatch,
        OpenLoopUpdatePatch,
        PsycheResetPatch,
        HealthTokenRevokePatch,
        HealthTokenCreatePatch,
        HealthRemovalPatch,
        PsycheSummaryPatch,
        OpenLoopClosePatch,
    ):
        return _record_editor_request(model, intent)
    if model in (
        InterestReactivationPatch,
        InterestFeedbackPatch,
        InterestCreatePatch,
        InterestUpdatePatch,
        InterestDeletePatch,
        InterestBulkDeletePatch,
    ):
        return _interest_editor_request(model, intent)
    if model in (
        MemoryCreatePatch,
        MemoryPinPatch,
        MemoryUpdatePatch,
        MemoryDeletePatch,
        MemoryBulkDeletePatch,
    ):
        return _memory_editor_request(model, intent)
    if model is ManagementExportPatch:
        export = ManagementExportPatch.model_validate(intent).management_export
        return ManagementExportRequest, {"format": export.format}
    if model is ExportDownloadPatch:
        archive = ExportDownloadPatch.model_validate(intent).archive_to_download
        return ExportDownloadRequest, {"job_id": str(archive.job_id)}
    if model in (ReminderDeletePatch, ReminderUpdatePatch, ReminderCreatePatch):
        return _reminder_editor_request(model, intent)
    if model in (
        RoutineRunPatch,
        RoutineUpdatePatch,
        RoutineDeletePatch,
        RoutineCreatePatch,
        RoutineStatePatch,
    ):
        return _routine_editor_request(model, intent)
    if model is AccountExportRequest:
        AccountExportRequest.model_validate(intent)
        return ApplicationEmptyRead, {}
    if model is OtherSessionsRevokePatch:
        OtherSessionsRevokePatch.model_validate(intent)
        return ApplicationEmptyRead, {}
    if model is DeviceSessionRevokePatch:
        selected = DeviceSessionRevokePatch.model_validate(intent).session_to_revoke
        return DeviceSessionRevokeRequest, {"display_id": selected.id}
    return model, intent


def _record_editor_request(
    model: type[BaseModel],
    intent: dict[str, JsonValue],
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    fixed_requests: dict[type[BaseModel], tuple[type[BaseModel], str]] = {
        PsycheSummaryPatch: (PsycheSummaryRequest, "current_account"),
        JournalConsolidationPatch: (JournalConsolidationRequest, "current_account"),
        HabitRecomputePatch: (HabitRecomputeRequest, "current_account"),
        HabitForgetPatch: (HabitForgetRequest, "all_owned"),
    }
    if fixed := fixed_requests.get(model):
        model.model_validate(intent)
        request_type, scope = fixed
        return request_type, {"scope": scope}
    if model in (HealthTokenRevokePatch, HealthTokenCreatePatch, HealthRemovalPatch):
        return _health_editor_request(model, intent)
    if model in MANAGEMENT_EDITOR_MODELS:
        return management_editor_request(model, intent)
    if model is JournalFeedbackPatch:
        feedback = JournalFeedbackPatch.model_validate(intent).journal_feedback
        return JournalFeedbackRequest, feedback.request.model_dump(mode="json")
    if model is JournalUpdatePatch:
        edit = JournalUpdatePatch.model_validate(intent).journal_configuration
        return JournalUpdateRequest, {
            "entry_id": str(edit.expected.entry_id),
            "changes": edit.changes.model_dump(mode="json", exclude_unset=True),
        }
    if model is JournalCreatePatch:
        creation = JournalCreatePatch.model_validate(intent).journal_entry_to_create
        return JournalCreateConfiguration, creation.configuration.model_dump(mode="json")
    if model is JournalDeletePatch:
        selected = JournalDeletePatch.model_validate(intent).journal_entries_to_delete
        return JournalDeleteRequest, {
            "entry_id": str(selected.entry_id) if selected.entry_id else None
        }
    if model is PsycheResetPatch:
        reset = PsycheResetPatch.model_validate(intent).psyche_reset
        return PsycheResetIntent, reset.request.model_dump(mode="json")
    if model is HabitStatusPatch:
        changed = HabitStatusPatch.model_validate(intent).habit
        return HabitStatusRequest, {
            "habit_id": str(changed.expected.id),
            "status": changed.status.status,
        }
    if model is HabitDeletePatch:
        removed = HabitDeletePatch.model_validate(intent).habit
        return HabitDeleteRequest, {"habit_id": str(removed.id)}
    if model is OpenLoopUpdatePatch:
        correction = OpenLoopUpdatePatch.model_validate(intent).open_loop
        return OpenLoopUpdateRequest, {
            "loop_id": str(correction.expected.id),
            "changes": correction.changes.model_dump(mode="json", exclude_unset=True),
        }
    if model is OpenLoopClosePatch:
        closure = OpenLoopClosePatch.model_validate(intent).open_loop
        return OpenLoopCloseRequest, {
            "loop_id": str(closure.expected.id),
            "action": closure.action.action,
        }
    raise ValueError("Unsupported record editor")


def _health_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is HealthTokenCreatePatch:
        creation = HealthTokenCreatePatch.model_validate(intent).health_token_to_create
        return HealthTokenCreateRequest, creation.model_dump(mode="json")
    if model is HealthTokenRevokePatch:
        token = HealthTokenRevokePatch.model_validate(intent).health_token_to_revoke
        return HealthTokenRevokeRequest, {"token_id": str(token.token.id)}
    removal = HealthRemovalPatch.model_validate(intent).health_samples_to_delete
    return HealthRemovalRequest, {"kind": removal.kind}


def _routine_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is RoutineRunPatch:
        launch = RoutineRunPatch.model_validate(intent).routine_to_run
        return RoutineRunRequest, {"routine_id": str(launch.expected.id)}
    if model is RoutineUpdatePatch:
        edited = RoutineUpdatePatch.model_validate(intent).routine_configuration
        return RoutineUpdateRequest, {
            "routine_id": str(edited.expected.id),
            "changes": edited.changes.model_dump(mode="json", exclude_unset=True),
        }
    if model is RoutineDeletePatch:
        deletion = RoutineDeletePatch.model_validate(intent).routine_to_delete
        return RoutineDeleteRequest, {"routine_id": str(deletion.id)}
    if model is RoutineCreatePatch:
        creation = RoutineCreatePatch.model_validate(intent).routine_to_create
        return RoutineCreateRequest, creation.configuration.model_dump(mode="json")
    if model is RoutineStatePatch:
        selected = RoutineStatePatch.model_validate(intent).routine_state
        return RoutineStateRequest, {
            "routine_id": str(selected.expected.id),
            "enabled": selected.enabled,
        }
    raise ValueError("Unsupported routine editor")
