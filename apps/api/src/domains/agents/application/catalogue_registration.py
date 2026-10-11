"""Native manifests derived from reviewed application schemas and policies."""

from typing import TYPE_CHECKING

from src.core.config import settings
from src.domains.agents.application.asset_delete_manifest import ASSET_DELETE_MANIFEST
from src.domains.agents.application.asset_download_manifest import (
    ASSET_DOWNLOAD_MANIFEST,
)
from src.domains.agents.application.asset_retention_manifest import (
    ASSET_RETENTION_MANIFEST,
)
from src.domains.agents.application.assistant_catalogue import (
    ASSISTANT_READ_MANIFEST,
    ASSISTANT_UPDATE_MANIFEST,
)
from src.domains.agents.application.bookmark_delete_manifest import (
    BOOKMARK_DELETE_MANIFEST,
)
from src.domains.agents.application.bookmark_download_manifest import (
    BOOKMARK_DOWNLOAD_MANIFEST,
)
from src.domains.agents.application.bookmark_keep_manifest import BOOKMARK_KEEP_MANIFEST
from src.domains.agents.application.bookmark_read_spec import BOOKMARK_READ_MANIFEST
from src.domains.agents.application.channel_catalogue import (
    CHANNEL_UNLINK_MANIFEST,
    CHANNEL_UPDATE_MANIFEST,
    CHANNELS_READ_MANIFEST,
)
from src.domains.agents.application.connection_catalogue import (
    CONNECTOR_CONNECTIONS_READ_MANIFEST,
    CONNECTOR_UNLINK_MANIFEST,
)
from src.domains.agents.application.connector_catalogue import (
    CONNECTOR_PREFERENCES_READ_MANIFEST,
    CONNECTOR_PREFERENCES_UPDATE_MANIFEST,
)
from src.domains.agents.application.document_archive_manifest import (
    DOCUMENT_ARCHIVE_MANIFEST,
)
from src.domains.agents.application.document_delete_manifest import (
    DOCUMENT_DELETE_MANIFEST,
)
from src.domains.agents.application.document_download_manifest import (
    DOCUMENT_DOWNLOAD_MANIFEST,
)
from src.domains.agents.application.document_move_manifest import DOCUMENT_MOVE_MANIFEST
from src.domains.agents.application.document_upload_manifest import (
    DOCUMENT_UPLOAD_MANIFEST,
)
from src.domains.agents.application.email_share_read_spec import (
    EMAIL_SHARE_READ_MANIFEST,
)
from src.domains.agents.application.email_share_send_manifest import (
    EMAIL_SHARE_SEND_MANIFEST,
)
from src.domains.agents.application.export_catalogue import (
    EXPORT_DOWNLOAD_MANIFEST,
    EXPORT_READ_MANIFEST,
    EXPORT_REQUEST_MANIFEST,
)
from src.domains.agents.application.gallery_read_spec import GALLERY_READ_MANIFEST
from src.domains.agents.application.habit_action_catalogue import (
    HABIT_DELETE_MANIFEST,
    HABIT_FORGET_MANIFEST,
    HABIT_RECOMPUTE_MANIFEST,
    HABIT_STATUS_MANIFEST,
)
from src.domains.agents.application.habit_catalogue import (
    HABIT_DETAIL_MANIFEST,
    HABIT_READ_MANIFEST,
    HABIT_SETTINGS_MANIFEST,
)
from src.domains.agents.application.health_aggregate_spec import (
    HEALTH_AGGREGATE_MANIFEST,
)
from src.domains.agents.application.health_read_spec import (
    HEALTH_SAMPLES_MANIFEST,
    HEALTH_TOKENS_MANIFEST,
)
from src.domains.agents.application.health_removal_spec import HEALTH_REMOVAL_MANIFEST
from src.domains.agents.application.health_token_creation_spec import (
    HEALTH_TOKEN_CREATE_MANIFEST,
)
from src.domains.agents.application.health_token_spec import (
    HEALTH_TOKEN_REVOKE_MANIFEST,
)
from src.domains.agents.application.heartbeat_catalogue import (
    HEARTBEAT_READ_MANIFEST,
    HEARTBEAT_UPDATE_MANIFEST,
)
from src.domains.agents.application.interest_catalogue import (
    INTEREST_BULK_DELETE_MANIFEST,
    INTEREST_CREATE_MANIFEST,
    INTEREST_DELETE_MANIFEST,
    INTEREST_DETAILS_MANIFEST,
    INTEREST_FEEDBACK_MANIFEST,
    INTEREST_HISTORY_MANIFEST,
    INTEREST_REACTIVATE_MANIFEST,
    INTEREST_READ_MANIFEST,
    INTEREST_SETTINGS_MANIFEST,
    INTEREST_UPDATE_MANIFEST,
)
from src.domains.agents.application.journal_catalogue import (
    JOURNAL_PORTRAIT_MANIFEST,
    JOURNAL_READ_MANIFEST,
    JOURNAL_SETTINGS_MANIFEST,
)
from src.domains.agents.application.journal_consolidation_spec import (
    JOURNAL_CONSOLIDATE_MANIFEST,
)
from src.domains.agents.application.journal_creation_spec import JOURNAL_CREATE_MANIFEST
from src.domains.agents.application.journal_feedback_spec import (
    JOURNAL_FEEDBACK_MANIFEST,
)
from src.domains.agents.application.journal_provenance_spec import (
    JOURNAL_PROVENANCE_MANIFEST,
)
from src.domains.agents.application.journal_removal_spec import JOURNAL_DELETE_MANIFEST
from src.domains.agents.application.journal_update_spec import JOURNAL_UPDATE_MANIFEST
from src.domains.agents.application.layout_catalogue import (
    LAYOUT_READ_MANIFEST,
    LAYOUT_UPDATE_MANIFEST,
)
from src.domains.agents.application.live_catalogue import (
    LIVE_PREFERENCES_READ_MANIFEST,
    LIVE_PREFERENCES_UPDATE_MANIFEST,
)
from src.domains.agents.application.live_connector_catalogue import (
    LIVE_CONNECTOR_READ_MANIFEST,
    LIVE_CONNECTOR_UPDATE_MANIFEST,
    LIVE_OPTIONS_READ_MANIFEST,
)
from src.domains.agents.application.location_catalogue import (
    HOME_LOCATION_UPDATE_MANIFEST,
    LOCATIONS_READ_MANIFEST,
)
from src.domains.agents.application.management_export_catalogue import (
    INTEREST_EXPORT_MANIFEST,
    JOURNAL_EXPORT_MANIFEST,
    MEMORY_EXPORT_MANIFEST,
)
from src.domains.agents.application.meeting_deletion_spec import (
    MEETING_DELETION_MANIFEST,
)
from src.domains.agents.application.meeting_email_spec import MEETING_EMAIL_MANIFEST
from src.domains.agents.application.meeting_pdf_spec import MEETING_PDF_MANIFEST
from src.domains.agents.application.meeting_preference_catalogue import (
    MEETING_PREFERENCE_READ_MANIFEST,
    MEETING_PREFERENCE_UPDATE_MANIFEST,
)
from src.domains.agents.application.meeting_read_catalogue import (
    MEETING_READ_MANIFEST,
    MEETING_TEMPLATE_READ_MANIFEST,
)
from src.domains.agents.application.meeting_reformat_spec import (
    MEETING_REFORMAT_MANIFEST,
)
from src.domains.agents.application.meeting_regeneration_spec import (
    MEETING_REGENERATION_MANIFEST,
)
from src.domains.agents.application.meeting_report_restore_spec import (
    REPORT_RESTORE_MANIFEST,
)
from src.domains.agents.application.meeting_report_update_spec import (
    REPORT_UPDATE_MANIFEST,
)
from src.domains.agents.application.meeting_retry_spec import MEETING_RETRY_MANIFEST
from src.domains.agents.application.meeting_template_catalogue import (
    TEMPLATE_CREATE_MANIFEST,
    TEMPLATE_DELETE_MANIFEST,
    TEMPLATE_UPDATE_MANIFEST,
)
from src.domains.agents.application.meeting_transcript_spec import (
    TRANSCRIPT_DELETE_MANIFEST,
)
from src.domains.agents.application.memory_catalogue import (
    MEMORY_BULK_DELETE_MANIFEST,
    MEMORY_CREATE_MANIFEST,
    MEMORY_DELETE_MANIFEST,
    MEMORY_PIN_MANIFEST,
    MEMORY_PROVENANCE_MANIFEST,
    MEMORY_READ_MANIFEST,
    MEMORY_UPDATE_MANIFEST,
)
from src.domains.agents.application.notification_catalogue import (
    NOTIFICATION_DEVICE_REMOVE_MANIFEST,
    NOTIFICATION_DEVICES_READ_MANIFEST,
)
from src.domains.agents.application.open_loop_action_catalogue import (
    OPEN_LOOP_CLOSE_MANIFEST,
    OPEN_LOOP_UPDATE_MANIFEST,
)
from src.domains.agents.application.open_loop_catalogue import OPEN_LOOP_READ_MANIFEST
from src.domains.agents.application.peer_block_spec import PEER_BLOCK_MANIFEST
from src.domains.agents.application.peer_discovery_spec import PEER_DISCOVERY_MANIFEST
from src.domains.agents.application.peer_image_spec import PEER_IMAGE_MANIFEST
from src.domains.agents.application.peer_preference_spec import PEER_PREFERENCE_MANIFEST
from src.domains.agents.application.peer_read_spec import PEER_UI_READ_MANIFEST
from src.domains.agents.application.peer_removal_spec import PEER_REMOVAL_MANIFEST
from src.domains.agents.application.peer_request_spec import PEER_REQUEST_MANIFEST
from src.domains.agents.application.peer_response_spec import PEER_RESPONSE_MANIFEST
from src.domains.agents.application.peer_share_spec import PEER_SHARE_MANIFEST
from src.domains.agents.application.personal_mcp_configuration_manifest import (
    PERSONAL_MCP_CONFIGURATION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_connection_manifest import (
    PERSONAL_MCP_CONNECTION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_delete_manifest import (
    PERSONAL_MCP_DELETE_MANIFEST,
)
from src.domains.agents.application.personal_mcp_description_manifest import (
    PERSONAL_MCP_DESCRIPTION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_manifest import (
    PERSONAL_MCP_OAUTH_DISCONNECT_MANIFEST,
)
from src.domains.agents.application.personal_mcp_oauth_manifest import (
    PERSONAL_MCP_OAUTH_MANIFEST,
)
from src.domains.agents.application.personal_mcp_read_spec import (
    PERSONAL_MCP_READ_MANIFEST,
)
from src.domains.agents.application.personal_mcp_settings_manifest import (
    PERSONAL_MCP_SETTINGS_MANIFEST,
)
from src.domains.agents.application.personal_mcp_state_manifest import (
    PERSONAL_MCP_STATE_MANIFEST,
)
from src.domains.agents.application.personality_catalogue import (
    PERSONALITY_READ_MANIFEST,
)
from src.domains.agents.application.phone_catalogue import PHONE_IDENTITY_READ_MANIFEST
from src.domains.agents.application.phone_history_catalogue import (
    PHONE_HISTORY_READ_MANIFEST,
)
from src.domains.agents.application.phone_number_catalogue import (
    PHONE_NUMBER_UPDATE_MANIFEST,
)
from src.domains.agents.application.phone_preference_catalogue import (
    PHONE_PREFERENCES_UPDATE_MANIFEST,
)
from src.domains.agents.application.plugin_delete_manifest import PLUGIN_DELETE_MANIFEST
from src.domains.agents.application.plugin_file_upload_manifest import (
    PLUGIN_FILE_UPLOAD_MANIFEST,
)
from src.domains.agents.application.plugin_read_spec import PLUGIN_READ_MANIFEST
from src.domains.agents.application.plugin_url_import_manifest import (
    PLUGIN_URL_IMPORT_MANIFEST,
)
from src.domains.agents.application.preference_catalogue import (
    PREFERENCES_READ_MANIFEST as PREFERENCES_READ_MANIFEST,
)
from src.domains.agents.application.preference_catalogue import (
    PREFERENCES_UPDATE_MANIFEST as PREFERENCES_UPDATE_MANIFEST,
)
from src.domains.agents.application.psyche_catalogue import (
    PSYCHE_READ_MANIFEST,
    PSYCHE_SETTINGS_MANIFEST,
)
from src.domains.agents.application.psyche_reset_catalogue import PSYCHE_RESET_MANIFEST
from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_MANIFEST
from src.domains.agents.application.recording_device_spec import (
    RECORDING_DEVICE_MANIFEST,
    RECORDING_DEVICE_READ_MANIFEST,
)
from src.domains.agents.application.relation_context_refresh_spec import (
    RELATION_CONTEXT_REFRESH_MANIFEST,
)
from src.domains.agents.application.relation_context_spec import (
    RELATION_CONTEXT_READ_MANIFEST,
)
from src.domains.agents.application.relation_data_spec import RELATION_DATA_MANIFEST
from src.domains.agents.application.relation_debrief_build_spec import (
    RELATION_DEBRIEF_BUILD_MANIFEST,
)
from src.domains.agents.application.relation_debrief_spec import (
    RELATION_DEBRIEF_READ_MANIFEST,
)
from src.domains.agents.application.relation_favorite_spec import (
    RELATION_FAVORITE_MANIFEST,
)
from src.domains.agents.application.relation_grouping_spec import (
    RELATION_GROUPING_MANIFEST,
)
from src.domains.agents.application.relation_settings_spec import (
    RELATION_SETTINGS_READ_MANIFEST,
    RELATION_SETTINGS_UPDATE_MANIFEST,
)
from src.domains.agents.application.reminder_catalogue import (
    REMINDER_CREATE_MANIFEST,
    REMINDER_DELETE_MANIFEST,
    REMINDER_UPDATE_MANIFEST,
    REMINDERS_READ_MANIFEST,
)
from src.domains.agents.application.routine_catalogue import (
    ROUTINE_CREATE_MANIFEST,
    ROUTINE_DELETE_MANIFEST,
    ROUTINE_READ_MANIFEST,
    ROUTINE_RUN_MANIFEST,
    ROUTINE_STATE_MANIFEST,
    ROUTINE_UPDATE_MANIFEST,
)
from src.domains.agents.application.security_catalogue import SECURITY_READ_MANIFEST
from src.domains.agents.application.session_catalogue import (
    OTHER_SESSIONS_REVOKE_MANIFEST,
    SESSION_REVOKE_MANIFEST,
    SESSIONS_READ_MANIFEST,
)
from src.domains.agents.application.shared_mcp_catalogue import (
    SHARED_MCP_READ_MANIFEST,
    SHARED_MCP_UPDATE_MANIFEST,
)
from src.domains.agents.application.skill_delete_manifest import SKILL_DELETE_MANIFEST
from src.domains.agents.application.skill_download_manifest import (
    SKILL_DOWNLOAD_MANIFEST,
)
from src.domains.agents.application.skill_file_upload_manifest import (
    SKILL_FILE_UPLOAD_MANIFEST,
)
from src.domains.agents.application.skill_library_import_manifest import (
    LIBRARY_INSTALL_MANIFEST,
    LIBRARY_UPDATE_MANIFEST,
)
from src.domains.agents.application.skill_library_read_spec import (
    SKILL_LIBRARY_READ_MANIFEST,
)
from src.domains.agents.application.skill_read_spec import SKILL_READ_MANIFEST
from src.domains.agents.application.skill_update_manifest import SKILL_UPDATE_MANIFEST
from src.domains.agents.application.skill_url_import_manifest import (
    SKILL_URL_IMPORT_MANIFEST,
)
from src.domains.agents.application.source_delete_manifest import SOURCE_DELETE_MANIFEST
from src.domains.agents.application.source_link_spec import SOURCE_LINK_MANIFEST
from src.domains.agents.application.source_options_spec import SOURCE_OPTIONS_MANIFEST
from src.domains.agents.application.source_sync_manifest import SOURCE_SYNC_MANIFEST
from src.domains.agents.application.source_unlink_spec import SOURCE_UNLINK_MANIFEST
from src.domains.agents.application.space_create_manifest import SPACE_CREATE_MANIFEST
from src.domains.agents.application.space_delete_manifest import SPACE_DELETE_MANIFEST
from src.domains.agents.application.space_read_spec import SPACE_UI_READ_MANIFEST
from src.domains.agents.application.space_update_manifest import SPACE_UPDATE_MANIFEST
from src.domains.agents.application.workboard_read_spec import (
    WORKBOARD_UI_READ_MANIFEST,
)
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    DisplayMetadata,
)
from src.domains.agents.workboard.catalogue_manifests import (
    comment_ticket_catalogue_manifest,
    delete_ticket_catalogue_manifest,
    update_ticket_catalogue_manifest,
)
from src.domains.agents.workboard.creation_manifest import (
    create_ticket_catalogue_manifest,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry

SETTING_MANIFESTS = (
    RECORDING_DEVICE_MANIFEST,
    RECORDING_DEVICE_READ_MANIFEST,
    MEETING_DELETION_MANIFEST,
    MEETING_REFORMAT_MANIFEST,
    MEETING_REGENERATION_MANIFEST,
    MEETING_RETRY_MANIFEST,
    MEETING_EMAIL_MANIFEST,
    MEETING_PDF_MANIFEST,
    REPORT_UPDATE_MANIFEST,
    REPORT_RESTORE_MANIFEST,
    TRANSCRIPT_DELETE_MANIFEST,
    TEMPLATE_CREATE_MANIFEST,
    TEMPLATE_UPDATE_MANIFEST,
    TEMPLATE_DELETE_MANIFEST,
    MEETING_READ_MANIFEST,
    MEETING_TEMPLATE_READ_MANIFEST,
    MEETING_PREFERENCE_READ_MANIFEST,
    MEETING_PREFERENCE_UPDATE_MANIFEST,
    ASSET_RETENTION_MANIFEST,
    ASSET_DELETE_MANIFEST,
    ASSET_DOWNLOAD_MANIFEST,
    GALLERY_READ_MANIFEST,
    BOOKMARK_READ_MANIFEST,
    EMAIL_SHARE_READ_MANIFEST,
    SKILL_READ_MANIFEST,
    SKILL_LIBRARY_READ_MANIFEST,
    PLUGIN_READ_MANIFEST,
    PERSONAL_MCP_READ_MANIFEST,
    PERSONAL_MCP_STATE_MANIFEST,
    PERSONAL_MCP_SETTINGS_MANIFEST,
    PERSONAL_MCP_DELETE_MANIFEST,
    PERSONAL_MCP_DESCRIPTION_MANIFEST,
    PERSONAL_MCP_CONNECTION_MANIFEST,
    PERSONAL_MCP_OAUTH_DISCONNECT_MANIFEST,
    PERSONAL_MCP_CONFIGURATION_MANIFEST,
    PERSONAL_MCP_OAUTH_MANIFEST,
    PLUGIN_DELETE_MANIFEST,
    PLUGIN_URL_IMPORT_MANIFEST,
    PLUGIN_FILE_UPLOAD_MANIFEST,
    LIBRARY_INSTALL_MANIFEST,
    LIBRARY_UPDATE_MANIFEST,
    SKILL_UPDATE_MANIFEST,
    SKILL_DELETE_MANIFEST,
    SKILL_FILE_UPLOAD_MANIFEST,
    SKILL_URL_IMPORT_MANIFEST,
    SKILL_DOWNLOAD_MANIFEST,
    EMAIL_SHARE_SEND_MANIFEST,
    BOOKMARK_KEEP_MANIFEST,
    BOOKMARK_DELETE_MANIFEST,
    BOOKMARK_DOWNLOAD_MANIFEST,
    SOURCE_OPTIONS_MANIFEST,
    SOURCE_UNLINK_MANIFEST,
    SOURCE_LINK_MANIFEST,
    SOURCE_SYNC_MANIFEST,
    SOURCE_DELETE_MANIFEST,
    SPACE_UI_READ_MANIFEST,
    SPACE_CREATE_MANIFEST,
    DOCUMENT_DOWNLOAD_MANIFEST,
    DOCUMENT_UPLOAD_MANIFEST,
    DOCUMENT_ARCHIVE_MANIFEST,
    DOCUMENT_DELETE_MANIFEST,
    DOCUMENT_MOVE_MANIFEST,
    SPACE_DELETE_MANIFEST,
    SPACE_UPDATE_MANIFEST,
    PEER_RESPONSE_MANIFEST,
    PEER_SHARE_MANIFEST,
    PEER_REMOVAL_MANIFEST,
    PEER_BLOCK_MANIFEST,
    PEER_IMAGE_MANIFEST,
    WORKBOARD_UI_READ_MANIFEST,
    PEER_REQUEST_MANIFEST,
    PEER_DISCOVERY_MANIFEST,
    PEER_PREFERENCE_MANIFEST,
    PEER_UI_READ_MANIFEST,
    RELATION_DATA_MANIFEST,
    RELATION_CONTEXT_READ_MANIFEST,
    RELATION_DEBRIEF_READ_MANIFEST,
    RELATION_DEBRIEF_BUILD_MANIFEST,
    RELATION_CONTEXT_REFRESH_MANIFEST,
    RELATION_FAVORITE_MANIFEST,
    RELATION_GROUPING_MANIFEST,
    JOURNAL_FEEDBACK_MANIFEST,
    JOURNAL_CONSOLIDATE_MANIFEST,
    JOURNAL_PROVENANCE_MANIFEST,
    HEALTH_TOKEN_REVOKE_MANIFEST,
    HEALTH_TOKEN_CREATE_MANIFEST,
    RELATION_SETTINGS_READ_MANIFEST,
    RELATION_SETTINGS_UPDATE_MANIFEST,
    HEALTH_REMOVAL_MANIFEST,
    HEALTH_AGGREGATE_MANIFEST,
    HEALTH_SAMPLES_MANIFEST,
    HEALTH_TOKENS_MANIFEST,
    JOURNAL_UPDATE_MANIFEST,
    JOURNAL_CREATE_MANIFEST,
    JOURNAL_DELETE_MANIFEST,
    JOURNAL_READ_MANIFEST,
    JOURNAL_PORTRAIT_MANIFEST,
    JOURNAL_SETTINGS_MANIFEST,
    PSYCHE_RESET_MANIFEST,
    PSYCHE_SUMMARY_MANIFEST,
    PSYCHE_SETTINGS_MANIFEST,
    PSYCHE_READ_MANIFEST,
    PERSONALITY_READ_MANIFEST,
    HABIT_RECOMPUTE_MANIFEST,
    HABIT_FORGET_MANIFEST,
    HABIT_SETTINGS_MANIFEST,
    HABIT_STATUS_MANIFEST,
    HABIT_DELETE_MANIFEST,
    HABIT_DETAIL_MANIFEST,
    HABIT_READ_MANIFEST,
    OPEN_LOOP_CLOSE_MANIFEST,
    OPEN_LOOP_UPDATE_MANIFEST,
    OPEN_LOOP_READ_MANIFEST,
    MEMORY_EXPORT_MANIFEST,
    JOURNAL_EXPORT_MANIFEST,
    INTEREST_EXPORT_MANIFEST,
    INTEREST_REACTIVATE_MANIFEST,
    INTEREST_FEEDBACK_MANIFEST,
    INTEREST_BULK_DELETE_MANIFEST,
    INTEREST_DELETE_MANIFEST,
    INTEREST_READ_MANIFEST,
    INTEREST_SETTINGS_MANIFEST,
    INTEREST_CREATE_MANIFEST,
    INTEREST_DETAILS_MANIFEST,
    INTEREST_HISTORY_MANIFEST,
    INTEREST_UPDATE_MANIFEST,
    MEMORY_PROVENANCE_MANIFEST,
    MEMORY_BULK_DELETE_MANIFEST,
    MEMORY_DELETE_MANIFEST,
    MEMORY_UPDATE_MANIFEST,
    MEMORY_CREATE_MANIFEST,
    MEMORY_PIN_MANIFEST,
    MEMORY_READ_MANIFEST,
    EXPORT_DOWNLOAD_MANIFEST,
    REMINDER_UPDATE_MANIFEST,
    REMINDER_DELETE_MANIFEST,
    REMINDER_CREATE_MANIFEST,
    REMINDERS_READ_MANIFEST,
    ROUTINE_RUN_MANIFEST,
    ROUTINE_UPDATE_MANIFEST,
    ROUTINE_DELETE_MANIFEST,
    ROUTINE_CREATE_MANIFEST,
    ROUTINE_READ_MANIFEST,
    ROUTINE_STATE_MANIFEST,
    EXPORT_REQUEST_MANIFEST,
    OTHER_SESSIONS_REVOKE_MANIFEST,
    SESSION_REVOKE_MANIFEST,
    PHONE_NUMBER_UPDATE_MANIFEST,
    PHONE_PREFERENCES_UPDATE_MANIFEST,
    PHONE_HISTORY_READ_MANIFEST,
    PHONE_IDENTITY_READ_MANIFEST,
    SESSIONS_READ_MANIFEST,
    EXPORT_READ_MANIFEST,
    SECURITY_READ_MANIFEST,
    LIVE_CONNECTOR_READ_MANIFEST,
    LIVE_CONNECTOR_UPDATE_MANIFEST,
    LIVE_OPTIONS_READ_MANIFEST,
    LIVE_PREFERENCES_READ_MANIFEST,
    LIVE_PREFERENCES_UPDATE_MANIFEST,
    NOTIFICATION_DEVICES_READ_MANIFEST,
    NOTIFICATION_DEVICE_REMOVE_MANIFEST,
    CONNECTOR_CONNECTIONS_READ_MANIFEST,
    CONNECTOR_UNLINK_MANIFEST,
    SHARED_MCP_READ_MANIFEST,
    SHARED_MCP_UPDATE_MANIFEST,
    CONNECTOR_PREFERENCES_READ_MANIFEST,
    CONNECTOR_PREFERENCES_UPDATE_MANIFEST,
    CHANNELS_READ_MANIFEST,
    CHANNEL_UPDATE_MANIFEST,
    CHANNEL_UNLINK_MANIFEST,
    HEARTBEAT_READ_MANIFEST,
    HEARTBEAT_UPDATE_MANIFEST,
    PREFERENCES_READ_MANIFEST,
    PREFERENCES_UPDATE_MANIFEST,
    ASSISTANT_READ_MANIFEST,
    ASSISTANT_UPDATE_MANIFEST,
    LAYOUT_READ_MANIFEST,
    LAYOUT_UPDATE_MANIFEST,
    LOCATIONS_READ_MANIFEST,
    HOME_LOCATION_UPDATE_MANIFEST,
)


APPLICATION_MANIFESTS = (
    *SETTING_MANIFESTS,
    create_ticket_catalogue_manifest,
    comment_ticket_catalogue_manifest,
    delete_ticket_catalogue_manifest,
    update_ticket_catalogue_manifest,
)


def register_application_manifests(registry: AgentRegistry) -> None:
    # Existing domain agents retain ownership of their tools; this is the full
    # management coverage inventory, not a second registration of those tools.
    owned = tuple(
        manifest for manifest in APPLICATION_MANIFESTS if manifest.agent == "setting_agent"
    )
    registry.register_agent_manifest(
        AgentManifest(
            name="setting_agent",
            description="Read and manage the current user's LIA application configuration.",
            tools=[manifest.name for manifest in owned],
            default_timeout_ms=settings.default_tool_timeout_ms,
            display=DisplayMetadata(emoji="⚙️", i18n_key="setting_agent", category="agent"),
        )
    )
    for manifest in owned:
        registry.register_tool_manifest(manifest)
