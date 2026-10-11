"""Addressed invalidation hints carry no setting values or administrative data."""

import asyncio
from datetime import UTC, datetime
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.asset_delete_schemas import AssetDeleteField
from src.domains.agents.application.asset_retention_schemas import AssetRetentionField
from src.domains.agents.application.assistant_schemas import AssistantPreferenceField
from src.domains.agents.application.bookmark_delete_schemas import BookmarkDeleteField
from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepField
from src.domains.agents.application.channel_schemas import ChannelField
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionField,
    ConnectorConnectionUnlinkPatch,
)
from src.domains.agents.application.connector_schemas import ConnectorPreferenceField
from src.domains.agents.application.document_delete_schemas import DocumentDeleteField
from src.domains.agents.application.document_move_schemas import DocumentMoveField
from src.domains.agents.application.document_upload_schemas import DocumentUploadField
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.email_share_send_schemas import EmailShareSendField
from src.domains.agents.application.habit_action_schemas import HabitActionField
from src.domains.agents.application.habit_settings_schemas import HabitSettingField
from src.domains.agents.application.health_removal_schemas import HealthRemovalField
from src.domains.agents.application.health_token_schemas import HealthTokenField
from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferenceField
from src.domains.agents.application.interest_fields import InterestActionField
from src.domains.agents.application.interest_settings_schemas import InterestSettingField
from src.domains.agents.application.journal_consolidation_schemas import JournalConsolidationField
from src.domains.agents.application.journal_create_schemas import JournalCreationField
from src.domains.agents.application.journal_feedback_schemas import JournalFeedbackField
from src.domains.agents.application.journal_removal_schemas import JournalRemovalField
from src.domains.agents.application.journal_settings_schemas import JournalSettingField
from src.domains.agents.application.journal_update_schemas import JournalUpdateField
from src.domains.agents.application.layout_schemas import LayoutPreferenceField
from src.domains.agents.application.live_connector_schemas import LiveConnectorSettingField
from src.domains.agents.application.live_schemas import LivePreferenceField
from src.domains.agents.application.location_schemas import LocationField
from src.domains.agents.application.meeting_deletion_schemas import (
    MeetingDeletionField,
    MeetingDeletionPatch,
)
from src.domains.agents.application.meeting_email_schemas import MeetingEmailField
from src.domains.agents.application.meeting_preference_schemas import MeetingPreferenceField
from src.domains.agents.application.meeting_reformat_schemas import MeetingReformatField
from src.domains.agents.application.meeting_regeneration_schemas import MeetingRegenerationField
from src.domains.agents.application.meeting_report_restore_schemas import ReportRestoreField
from src.domains.agents.application.meeting_report_update_schemas import ReportUpdateField
from src.domains.agents.application.meeting_retry_schemas import MeetingRetryField
from src.domains.agents.application.meeting_template_schemas import (
    TemplateActionField,
    TemplateDeletePatch,
)
from src.domains.agents.application.meeting_transcript_schemas import TranscriptActionField
from src.domains.agents.application.memory_pin_schemas import MemoryField
from src.domains.agents.application.notification_schemas import NotificationDeviceField
from src.domains.agents.application.open_loop_fields import OpenLoopField
from src.domains.agents.application.peer_block_schemas import PeerBlockField, PeerBlockPatch
from src.domains.agents.application.peer_image_schemas import PeerImageField
from src.domains.agents.application.peer_preference_schemas import PeerPreferenceField
from src.domains.agents.application.peer_removal_schemas import PeerRemovalField
from src.domains.agents.application.peer_request_schemas import PeerRequestField
from src.domains.agents.application.peer_response_schemas import PeerResponseField
from src.domains.agents.application.peer_share_schemas import PeerShareField
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationField,
)
from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionField,
)
from src.domains.agents.application.personal_mcp_delete_schemas import PersonalMCPDeleteField
from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionField,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    PersonalMCPOAuthDisconnectField,
)
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthField
from src.domains.agents.application.personal_mcp_settings_schemas import PersonalMCPSettingsField
from src.domains.agents.application.personal_mcp_state_schemas import PersonalMCPStateField
from src.domains.agents.application.phone_number_schemas import PhoneNumberField
from src.domains.agents.application.phone_preference_schemas import PhonePreferenceField
from src.domains.agents.application.plugin_delete_schemas import PluginDeleteField
from src.domains.agents.application.plugin_file_upload_schemas import PluginFileUploadField
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportField
from src.domains.agents.application.preference_fields import PreferenceField
from src.domains.agents.application.psyche_reset_schemas import PsycheResetField
from src.domains.agents.application.psyche_settings_schemas import PsycheSettingField
from src.domains.agents.application.psyche_summary_schemas import PsycheSummaryField
from src.domains.agents.application.recording_device_schemas import RecordingDeviceField
from src.domains.agents.application.relation_favorite_schemas import RelationActionField
from src.domains.agents.application.relation_settings_schemas import RelationSettingField
from src.domains.agents.application.reminder_schemas import ReminderField
from src.domains.agents.application.routine_schemas import RoutineField
from src.domains.agents.application.session_revocation_schemas import DeviceSessionField
from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferenceField
from src.domains.agents.application.skill_delete_schemas import SkillDeleteField
from src.domains.agents.application.skill_file_upload_schemas import SkillFileUploadField
from src.domains.agents.application.skill_library_import_schemas import LibraryImportField
from src.domains.agents.application.skill_update_schemas import SkillUpdateField
from src.domains.agents.application.skill_url_import_schemas import SkillUrlImportField
from src.domains.agents.application.source_delete_schemas import SourceDeleteField
from src.domains.agents.application.source_link_schemas import SourceLinkField
from src.domains.agents.application.source_sync_schemas import SourceSyncField
from src.domains.agents.application.source_unlink_schemas import SourceUnlinkField
from src.domains.agents.application.space_create_schemas import SpaceCreateField
from src.domains.agents.application.space_delete_schemas import SpaceDeleteField
from src.domains.agents.application.space_update_schemas import SpaceUpdateField
from src.domains.agents.application.state_resources import (
    DEDICATED_RESOURCES,
    GROUP_RESOURCES,
)
from src.domains.agents.application.state_resources import (
    ApplicationResource as ApplicationResource,
)
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentField
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateField
from src.domains.agents.application.workboard_delete_schemas import WorkboardDeleteField
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateField
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES
from src.domains.users.preference_cas import PreferenceWriteReceipt


class ApplicationStateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    command_id: UUID
    actor_id: UUID
    resources: list[ApplicationResource] = Field(
        min_length=1, max_length=len(get_args(ApplicationResource))
    )
    changed_fields: list[
        PreferenceField
        | AssistantPreferenceField
        | LayoutPreferenceField
        | LocationField
        | HeartbeatPreferenceField
        | ChannelField
        | ConnectorPreferenceField
        | SharedMCPPreferenceField
        | ConnectorConnectionField
        | NotificationDeviceField
        | LivePreferenceField
        | LiveConnectorSettingField
        | PhonePreferenceField
        | PhoneNumberField
        | DeviceSessionField
        | RoutineField
        | ReminderField
        | MemoryField
        | InterestSettingField
        | InterestActionField
        | OpenLoopField
        | HabitSettingField
        | PsycheSettingField
        | JournalSettingField
        | JournalRemovalField
        | JournalFeedbackField
        | JournalConsolidationField
        | JournalCreationField
        | JournalUpdateField
        | PsycheResetField
        | HealthTokenField
        | HealthRemovalField
        | PsycheSummaryField
        | RelationSettingField
        | RelationActionField
        | PeerPreferenceField
        | PeerRequestField
        | PeerResponseField
        | PeerShareField
        | PeerRemovalField
        | PeerBlockField
        | PeerImageField
        | WorkboardCreateField
        | SpaceCreateField
        | SpaceDeleteField
        | DocumentDeleteField
        | DocumentMoveField
        | DocumentUploadField
        | SourceUnlinkField
        | SourceLinkField
        | SourceSyncField
        | SourceDeleteField
        | AssetRetentionField
        | AssetDeleteField
        | SkillDeleteField
        | PluginDeleteField
        | PluginUrlImportField
        | PluginFileUploadField
        | SkillFileUploadField
        | SkillUrlImportField
        | LibraryImportField
        | SkillUpdateField
        | PersonalMCPStateField
        | PersonalMCPSettingsField
        | PersonalMCPDeleteField
        | PersonalMCPDescriptionField
        | PersonalMCPConnectionField
        | PersonalMCPOAuthDisconnectField
        | PersonalMCPConfigurationField
        | PersonalMCPOAuthField
        | MeetingPreferenceField
        | TemplateActionField
        | TranscriptActionField
        | MeetingDeletionField
        | RecordingDeviceField
        | MeetingReformatField
        | MeetingRegenerationField
        | MeetingRetryField
        | MeetingEmailField
        | ReportRestoreField
        | ReportUpdateField
        | BookmarkKeepField
        | EmailShareSendField
        | BookmarkDeleteField
        | SpaceUpdateField
        | WorkboardCommentField
        | WorkboardDeleteField
        | WorkboardUpdateField
        | HabitActionField
    ] = Field(
        min_length=1,
        max_length=len(PreferenceField)
        + len(AssistantPreferenceField)
        + len(LayoutPreferenceField)
        + len(LocationField)
        + len(HeartbeatPreferenceField)
        + len(ChannelField)
        + len(ConnectorPreferenceField)
        + len(SharedMCPPreferenceField)
        + len(ConnectorConnectionField)
        + len(NotificationDeviceField)
        + len(LivePreferenceField)
        + len(LiveConnectorSettingField)
        + len(PhonePreferenceField)
        + len(PhoneNumberField)
        + len(DeviceSessionField)
        + len(RoutineField)
        + len(ReminderField)
        + len(MemoryField)
        + len(InterestSettingField)
        + len(InterestActionField)
        + len(OpenLoopField)
        + len(HabitSettingField)
        + len(PsycheSettingField)
        + len(JournalSettingField)
        + len(JournalRemovalField)
        + len(JournalFeedbackField)
        + len(JournalConsolidationField)
        + len(JournalCreationField)
        + len(JournalUpdateField)
        + len(PsycheResetField)
        + len(HealthTokenField)
        + len(HealthRemovalField)
        + len(PsycheSummaryField)
        + len(RelationSettingField)
        + len(RelationActionField)
        + len(PeerPreferenceField)
        + len(PeerRequestField)
        + len(PeerResponseField)
        + len(PeerShareField)
        + len(PeerRemovalField)
        + len(PeerBlockField)
        + len(PeerImageField)
        + len(WorkboardCreateField)
        + len(SpaceCreateField)
        + len(SpaceDeleteField)
        + len(DocumentDeleteField)
        + len(DocumentMoveField)
        + len(DocumentUploadField)
        + len(SourceUnlinkField)
        + len(SourceLinkField)
        + len(SourceSyncField)
        + len(SourceDeleteField)
        + len(AssetRetentionField)
        + len(AssetDeleteField)
        + len(SkillDeleteField)
        + len(PluginDeleteField)
        + len(PluginUrlImportField)
        + len(PluginFileUploadField)
        + len(SkillFileUploadField)
        + len(SkillUrlImportField)
        + len(LibraryImportField)
        + len(SkillUpdateField)
        + len(PersonalMCPStateField)
        + len(PersonalMCPSettingsField)
        + len(PersonalMCPDeleteField)
        + len(PersonalMCPDescriptionField)
        + len(PersonalMCPConnectionField)
        + len(PersonalMCPOAuthDisconnectField)
        + len(PersonalMCPConfigurationField)
        + len(PersonalMCPOAuthField)
        + len(MeetingPreferenceField)
        + len(TemplateActionField)
        + len(TranscriptActionField)
        + len(MeetingDeletionField)
        + len(RecordingDeviceField)
        + len(MeetingReformatField)
        + len(MeetingRegenerationField)
        + len(MeetingRetryField)
        + len(MeetingEmailField)
        + len(ReportRestoreField)
        + len(ReportUpdateField)
        + len(BookmarkKeepField)
        + len(EmailShareSendField)
        + len(BookmarkDeleteField)
        + len(SpaceUpdateField)
        + len(WorkboardCommentField)
        + len(WorkboardDeleteField)
        + len(WorkboardUpdateField)
        + len(HabitActionField),
    )
    observed_at: datetime


def _conditional_resources(
    draft: ApplicationActionDraftContent,
) -> list[ApplicationResource] | None:
    if draft.operation_id == "meeting.delete":
        meeting_deletion = MeetingDeletionPatch.model_validate(draft.intent).meeting_delete
        return ["meetings", "spaces"] if meeting_deletion.projection_present else ["meetings"]
    if draft.operation_id == "meeting_template.delete":
        selected_template = TemplateDeletePatch.model_validate(draft.intent).meeting_template_delete
        return (
            ["meeting_templates", "meeting_preferences"]
            if selected_template.default_template_ref == selected_template.request.ref
            else ["meeting_templates"]
        )
    if draft.operation_id == "peer_block.update":
        selected = PeerBlockPatch.model_validate(draft.intent).peer_block
        return ["peers", "relations", "workboard"] if selected.severs_pair else ["peers"]
    return None


def changed_resources(draft: ApplicationActionDraftContent) -> list[ApplicationResource]:
    if conditional := _conditional_resources(draft):
        return conditional
    if group := GROUP_RESOURCES.get(draft.operation_id):
        return list(group)
    if draft.operation_id == "connector_connection.unlink":
        resources: list[ApplicationResource] = ["connectors"]
        saved = ConnectorConnectionUnlinkPatch.model_validate(draft.intent).connector_to_disconnect
        for category in ("avatar", "live"):
            if saved.connector_type in CONNECTOR_FUNCTIONAL_CATEGORIES[category]:
                resources.append("avatar" if category == "avatar" else "live_connectors")
        return resources

    if resource := DEDICATED_RESOURCES.get(draft.operation_id):
        return [resource]
    resources = ["profile"]
    if "briefing_preferences" in draft.after:
        resources.append("briefing_preferences")
    if "chat_shortcuts" in draft.after:
        resources.append("chat_shortcuts")
    if (
        "home_location" in draft.after
        or "last_known_location" in draft.after
        or draft.after.get("use_last_known_location") is False
    ):
        resources.append("locations")
    return resources


def publish_preference_change(
    draft: ApplicationActionDraftContent, receipt: PreferenceWriteReceipt
) -> None:
    if not receipt.committed or receipt.no_op:
        return
    context = runtime_context_if_running()
    if context is None or context.user_id != draft.actor_id or context.side_channel_queue is None:
        return
    change = ApplicationStateChange(
        command_id=draft.command_id,
        actor_id=draft.actor_id,
        resources=changed_resources(draft),
        changed_fields=[
            field
            for field in (
                *PreferenceField,
                *AssistantPreferenceField,
                *LayoutPreferenceField,
                *LocationField,
                *HeartbeatPreferenceField,
                *ChannelField,
                *ConnectorPreferenceField,
                *SharedMCPPreferenceField,
                *ConnectorConnectionField,
                *NotificationDeviceField,
                *LivePreferenceField,
                *LiveConnectorSettingField,
                *PhonePreferenceField,
                *PhoneNumberField,
                *DeviceSessionField,
                *RoutineField,
                *ReminderField,
                *MemoryField,
                *InterestSettingField,
                *InterestActionField,
                *OpenLoopField,
                *HabitSettingField,
                *PsycheSettingField,
                *RelationSettingField,
                *RelationActionField,
                *PeerPreferenceField,
                *PeerRequestField,
                *PeerResponseField,
                *PeerShareField,
                *PeerRemovalField,
                *PeerBlockField,
                *PeerImageField,
                *WorkboardCreateField,
                *SpaceCreateField,
                *SpaceDeleteField,
                *DocumentDeleteField,
                *DocumentMoveField,
                *DocumentUploadField,
                *SourceUnlinkField,
                *SourceLinkField,
                *SourceSyncField,
                *SourceDeleteField,
                *AssetRetentionField,
                *AssetDeleteField,
                *SkillDeleteField,
                *PluginDeleteField,
                *PluginUrlImportField,
                *PluginFileUploadField,
                *SkillFileUploadField,
                *SkillUrlImportField,
                *LibraryImportField,
                *SkillUpdateField,
                *PersonalMCPStateField,
                *PersonalMCPSettingsField,
                *PersonalMCPDeleteField,
                *PersonalMCPDescriptionField,
                *PersonalMCPConnectionField,
                *PersonalMCPOAuthDisconnectField,
                *PersonalMCPConfigurationField,
                *PersonalMCPOAuthField,
                *MeetingPreferenceField,
                *TemplateActionField,
                *TranscriptActionField,
                *MeetingDeletionField,
                *RecordingDeviceField,
                *MeetingReformatField,
                *MeetingRegenerationField,
                *MeetingRetryField,
                *MeetingEmailField,
                *ReportRestoreField,
                *ReportUpdateField,
                *BookmarkKeepField,
                *EmailShareSendField,
                *BookmarkDeleteField,
                *SpaceUpdateField,
                *WorkboardCommentField,
                *WorkboardDeleteField,
                *WorkboardUpdateField,
                *JournalSettingField,
                *JournalRemovalField,
                *JournalFeedbackField,
                *JournalConsolidationField,
                *JournalCreationField,
                *JournalUpdateField,
                *PsycheResetField,
                *HealthTokenField,
                *HealthRemovalField,
                *PsycheSummaryField,
                *HabitActionField,
            )
            if field.value in draft.after
        ],
        observed_at=datetime.now(UTC),
    )
    try:
        context.side_channel_queue.put_nowait(
            ChatStreamChunk(
                type="application_state_changed",
                content="",
                metadata={"change": change.model_dump(mode="json")},
            )
        )
    except asyncio.QueueFull:
        # Delivery cannot turn a verified commit into a failed business operation.
        return
