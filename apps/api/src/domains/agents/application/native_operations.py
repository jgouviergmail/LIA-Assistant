"""Finite native family declarations composed by the application registry."""

from src.domains.agents.application.asset_delete_spec import ASSET_DELETE_OPERATION
from src.domains.agents.application.asset_download_spec import ASSET_DOWNLOAD_OPERATION
from src.domains.agents.application.asset_retention_spec import ASSET_RETENTION_OPERATION
from src.domains.agents.application.bookmark_delete_spec import BOOKMARK_DELETE_OPERATION
from src.domains.agents.application.bookmark_download_spec import BOOKMARK_DOWNLOAD_OPERATION
from src.domains.agents.application.bookmark_keep_spec import BOOKMARK_KEEP_OPERATION
from src.domains.agents.application.bookmark_read_spec import BOOKMARK_READ_OPERATION
from src.domains.agents.application.document_archive_spec import DOCUMENT_ARCHIVE_OPERATION
from src.domains.agents.application.document_delete_spec import DOCUMENT_DELETE_OPERATION
from src.domains.agents.application.document_download_spec import DOCUMENT_DOWNLOAD_OPERATION
from src.domains.agents.application.document_move_spec import DOCUMENT_MOVE_OPERATION
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.application.email_share_read_spec import EMAIL_SHARE_READ_OPERATION
from src.domains.agents.application.email_share_send_spec import EMAIL_SHARE_SEND_OPERATION
from src.domains.agents.application.export_action import EXPORT_REQUEST_OPERATION
from src.domains.agents.application.export_download_spec import EXPORT_DOWNLOAD_OPERATION
from src.domains.agents.application.gallery_read_spec import GALLERY_READ_OPERATION
from src.domains.agents.application.habit_spec import (
    HABIT_DELETE_OPERATION,
    HABIT_DETAIL_OPERATION,
    HABIT_FORGET_OPERATION,
    HABIT_READ_OPERATION,
    HABIT_RECOMPUTE_OPERATION,
    HABIT_SETTINGS_OPERATION,
    HABIT_STATUS_OPERATION,
)
from src.domains.agents.application.health_aggregate_spec import HEALTH_AGGREGATE_OPERATION
from src.domains.agents.application.health_read_spec import (
    HEALTH_SAMPLES_OPERATION,
    HEALTH_TOKENS_OPERATION,
)
from src.domains.agents.application.health_removal_spec import HEALTH_REMOVAL_OPERATION
from src.domains.agents.application.health_token_creation_spec import HEALTH_TOKEN_CREATE_OPERATION
from src.domains.agents.application.health_token_spec import HEALTH_TOKEN_REVOKE_OPERATION
from src.domains.agents.application.interest_spec import (
    INTEREST_BULK_DELETE_OPERATION,
    INTEREST_CREATE_OPERATION,
    INTEREST_DELETE_OPERATION,
    INTEREST_DETAILS_OPERATION,
    INTEREST_FEEDBACK_OPERATION,
    INTEREST_HISTORY_OPERATION,
    INTEREST_REACTIVATE_OPERATION,
    INTEREST_READ_OPERATION,
    INTEREST_SETTINGS_OPERATION,
    INTEREST_UPDATE_OPERATION,
)
from src.domains.agents.application.journal_catalogue import (
    JOURNAL_PORTRAIT_OPERATION,
    JOURNAL_READ_OPERATION,
    JOURNAL_SETTINGS_OPERATION,
)
from src.domains.agents.application.journal_consolidation_spec import JOURNAL_CONSOLIDATE_OPERATION
from src.domains.agents.application.journal_creation_spec import JOURNAL_CREATE_OPERATION
from src.domains.agents.application.journal_feedback_spec import JOURNAL_FEEDBACK_OPERATION
from src.domains.agents.application.journal_provenance_spec import JOURNAL_PROVENANCE_OPERATION
from src.domains.agents.application.journal_removal_spec import JOURNAL_DELETE_OPERATION
from src.domains.agents.application.journal_update_spec import JOURNAL_UPDATE_OPERATION
from src.domains.agents.application.management_export_spec import (
    INTEREST_EXPORT_OPERATION,
    JOURNAL_EXPORT_OPERATION,
    MEMORY_EXPORT_OPERATION,
)
from src.domains.agents.application.meeting_deletion_spec import MEETING_DELETION_OPERATION
from src.domains.agents.application.meeting_email_spec import MEETING_EMAIL_OPERATION
from src.domains.agents.application.meeting_pdf_spec import MEETING_PDF_OPERATION
from src.domains.agents.application.meeting_preference_spec import (
    MEETING_PREFERENCE_READ_OPERATION,
    MEETING_PREFERENCE_UPDATE_OPERATION,
)
from src.domains.agents.application.meeting_read_spec import (
    MEETING_READ_OPERATION,
    MEETING_TEMPLATE_READ_OPERATION,
)
from src.domains.agents.application.meeting_reformat_spec import MEETING_REFORMAT_OPERATION
from src.domains.agents.application.meeting_regeneration_spec import MEETING_REGENERATION_OPERATION
from src.domains.agents.application.meeting_report_restore_spec import REPORT_RESTORE_OPERATION
from src.domains.agents.application.meeting_report_update_spec import REPORT_UPDATE_OPERATION
from src.domains.agents.application.meeting_retry_spec import MEETING_RETRY_OPERATION
from src.domains.agents.application.meeting_template_spec import (
    TEMPLATE_CREATE_OPERATION,
    TEMPLATE_DELETE_OPERATION,
    TEMPLATE_UPDATE_OPERATION,
)
from src.domains.agents.application.meeting_transcript_spec import TRANSCRIPT_DELETE_OPERATION
from src.domains.agents.application.memory_spec import (
    MEMORY_BULK_DELETE_OPERATION,
    MEMORY_CREATE_OPERATION,
    MEMORY_DELETE_OPERATION,
    MEMORY_PIN_OPERATION,
    MEMORY_PROVENANCE_OPERATION,
    MEMORY_READ_OPERATION,
    MEMORY_UPDATE_OPERATION,
)
from src.domains.agents.application.open_loop_spec import (
    OPEN_LOOP_CLOSE_OPERATION,
    OPEN_LOOP_READ_OPERATION,
    OPEN_LOOP_UPDATE_OPERATION,
)
from src.domains.agents.application.peer_block_spec import PEER_BLOCK_OPERATION
from src.domains.agents.application.peer_discovery_spec import PEER_DISCOVERY_OPERATION
from src.domains.agents.application.peer_image_spec import PEER_IMAGE_OPERATION
from src.domains.agents.application.peer_preference_spec import PEER_PREFERENCE_OPERATION
from src.domains.agents.application.peer_read_spec import PEER_UI_READ_OPERATION
from src.domains.agents.application.peer_removal_spec import PEER_REMOVAL_OPERATION
from src.domains.agents.application.peer_request_spec import PEER_REQUEST_OPERATION
from src.domains.agents.application.peer_response_spec import PEER_RESPONSE_OPERATION
from src.domains.agents.application.peer_share_spec import PEER_SHARE_OPERATION
from src.domains.agents.application.personal_mcp_configuration_spec import (
    PERSONAL_MCP_CONFIGURATION_OPERATION,
)
from src.domains.agents.application.personal_mcp_connection_spec import (
    PERSONAL_MCP_CONNECTION_OPERATION,
)
from src.domains.agents.application.personal_mcp_delete_spec import PERSONAL_MCP_DELETE_OPERATION
from src.domains.agents.application.personal_mcp_description_spec import (
    PERSONAL_MCP_DESCRIPTION_OPERATION,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_spec import (
    PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
)
from src.domains.agents.application.personal_mcp_oauth_spec import PERSONAL_MCP_OAUTH_OPERATION
from src.domains.agents.application.personal_mcp_read_spec import PERSONAL_MCP_READ_OPERATION
from src.domains.agents.application.personal_mcp_settings_spec import (
    PERSONAL_MCP_SETTINGS_OPERATION,
)
from src.domains.agents.application.personal_mcp_state_spec import PERSONAL_MCP_STATE_OPERATION
from src.domains.agents.application.personality_catalogue import PERSONALITY_READ_OPERATION
from src.domains.agents.application.plugin_delete_spec import PLUGIN_DELETE_OPERATION
from src.domains.agents.application.plugin_file_upload_spec import PLUGIN_FILE_UPLOAD_OPERATION
from src.domains.agents.application.plugin_read_spec import PLUGIN_READ_OPERATION
from src.domains.agents.application.plugin_url_import_spec import PLUGIN_URL_IMPORT_OPERATION
from src.domains.agents.application.psyche_catalogue import (
    PSYCHE_READ_OPERATION,
    PSYCHE_SETTINGS_OPERATION,
)
from src.domains.agents.application.psyche_reset_spec import PSYCHE_RESET_OPERATION
from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_OPERATION
from src.domains.agents.application.recording_device_spec import (
    RECORDING_DEVICE_OPERATION,
    RECORDING_DEVICE_READ_OPERATION,
)
from src.domains.agents.application.relation_context_refresh_spec import (
    RELATION_CONTEXT_REFRESH_OPERATION,
)
from src.domains.agents.application.relation_context_spec import RELATION_CONTEXT_READ_OPERATION
from src.domains.agents.application.relation_data_spec import RELATION_DATA_OPERATION
from src.domains.agents.application.relation_debrief_build_spec import (
    RELATION_DEBRIEF_BUILD_OPERATION,
)
from src.domains.agents.application.relation_debrief_spec import RELATION_DEBRIEF_READ_OPERATION
from src.domains.agents.application.relation_favorite_spec import RELATION_FAVORITE_OPERATION
from src.domains.agents.application.relation_grouping_spec import RELATION_GROUPING_OPERATION
from src.domains.agents.application.relation_settings_spec import (
    RELATION_SETTINGS_READ_OPERATION,
    RELATION_SETTINGS_UPDATE_OPERATION,
)
from src.domains.agents.application.reminder_spec import (
    REMINDER_CREATE_OPERATION,
    REMINDER_DELETE_OPERATION,
    REMINDER_READ_OPERATION,
    REMINDER_UPDATE_OPERATION,
)
from src.domains.agents.application.routine_spec import (
    ROUTINE_CREATE_OPERATION,
    ROUTINE_DELETE_OPERATION,
    ROUTINE_READ_OPERATION,
    ROUTINE_RUN_OPERATION,
    ROUTINE_STATE_OPERATION,
    ROUTINE_UPDATE_OPERATION,
)
from src.domains.agents.application.session_bulk_operations import SESSION_FLEET_OPERATION
from src.domains.agents.application.skill_delete_spec import SKILL_DELETE_OPERATION
from src.domains.agents.application.skill_download_spec import SKILL_DOWNLOAD_OPERATION
from src.domains.agents.application.skill_file_upload_spec import SKILL_FILE_UPLOAD_OPERATION
from src.domains.agents.application.skill_library_import_spec import (
    LIBRARY_INSTALL_OPERATION,
    LIBRARY_UPDATE_OPERATION,
)
from src.domains.agents.application.skill_library_read_spec import SKILL_LIBRARY_READ_OPERATION
from src.domains.agents.application.skill_read_spec import SKILL_READ_OPERATION
from src.domains.agents.application.skill_update_spec import SKILL_UPDATE_OPERATION
from src.domains.agents.application.skill_url_import_spec import SKILL_URL_IMPORT_OPERATION
from src.domains.agents.application.sms_action_spec import SMS_NATIVE_OPERATIONS
from src.domains.agents.application.source_delete_spec import SOURCE_DELETE_OPERATION
from src.domains.agents.application.source_link_spec import SOURCE_LINK_OPERATION
from src.domains.agents.application.source_options_spec import SOURCE_OPTIONS_OPERATION
from src.domains.agents.application.source_sync_spec import SOURCE_SYNC_OPERATION
from src.domains.agents.application.source_unlink_spec import SOURCE_UNLINK_OPERATION
from src.domains.agents.application.space_create_spec import SPACE_CREATE_OPERATION
from src.domains.agents.application.space_delete_spec import SPACE_DELETE_OPERATION
from src.domains.agents.application.space_read_spec import SPACE_UI_READ_OPERATION
from src.domains.agents.application.space_update_spec import SPACE_UPDATE_OPERATION
from src.domains.agents.application.workboard_comment_spec import WORKBOARD_COMMENT_OPERATION
from src.domains.agents.application.workboard_create_spec import WORKBOARD_CREATE_OPERATION
from src.domains.agents.application.workboard_delete_spec import WORKBOARD_DELETE_OPERATION
from src.domains.agents.application.workboard_read_spec import WORKBOARD_UI_READ_OPERATION
from src.domains.agents.application.workboard_update_spec import WORKBOARD_UPDATE_OPERATION

NATIVE_OPERATIONS = (
    *SMS_NATIVE_OPERATIONS,
    RECORDING_DEVICE_OPERATION,
    RECORDING_DEVICE_READ_OPERATION,
    MEETING_DELETION_OPERATION,
    MEETING_REFORMAT_OPERATION,
    MEETING_REGENERATION_OPERATION,
    MEETING_RETRY_OPERATION,
    MEETING_EMAIL_OPERATION,
    MEETING_PDF_OPERATION,
    REPORT_UPDATE_OPERATION,
    REPORT_RESTORE_OPERATION,
    TRANSCRIPT_DELETE_OPERATION,
    TEMPLATE_CREATE_OPERATION,
    TEMPLATE_UPDATE_OPERATION,
    TEMPLATE_DELETE_OPERATION,
    MEETING_READ_OPERATION,
    MEETING_TEMPLATE_READ_OPERATION,
    MEETING_PREFERENCE_READ_OPERATION,
    MEETING_PREFERENCE_UPDATE_OPERATION,
    ASSET_RETENTION_OPERATION,
    ASSET_DELETE_OPERATION,
    ASSET_DOWNLOAD_OPERATION,
    GALLERY_READ_OPERATION,
    BOOKMARK_READ_OPERATION,
    EMAIL_SHARE_READ_OPERATION,
    SKILL_READ_OPERATION,
    SKILL_LIBRARY_READ_OPERATION,
    PLUGIN_READ_OPERATION,
    PERSONAL_MCP_READ_OPERATION,
    PERSONAL_MCP_STATE_OPERATION,
    PERSONAL_MCP_SETTINGS_OPERATION,
    PERSONAL_MCP_DELETE_OPERATION,
    PERSONAL_MCP_DESCRIPTION_OPERATION,
    PERSONAL_MCP_CONNECTION_OPERATION,
    PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
    PERSONAL_MCP_CONFIGURATION_OPERATION,
    PERSONAL_MCP_OAUTH_OPERATION,
    PLUGIN_DELETE_OPERATION,
    PLUGIN_URL_IMPORT_OPERATION,
    PLUGIN_FILE_UPLOAD_OPERATION,
    LIBRARY_INSTALL_OPERATION,
    LIBRARY_UPDATE_OPERATION,
    SKILL_UPDATE_OPERATION,
    SKILL_DELETE_OPERATION,
    SKILL_FILE_UPLOAD_OPERATION,
    SKILL_URL_IMPORT_OPERATION,
    SKILL_DOWNLOAD_OPERATION,
    EMAIL_SHARE_SEND_OPERATION,
    BOOKMARK_KEEP_OPERATION,
    BOOKMARK_DELETE_OPERATION,
    BOOKMARK_DOWNLOAD_OPERATION,
    SOURCE_OPTIONS_OPERATION,
    SOURCE_UNLINK_OPERATION,
    SOURCE_LINK_OPERATION,
    SOURCE_SYNC_OPERATION,
    SOURCE_DELETE_OPERATION,
    SPACE_UI_READ_OPERATION,
    SPACE_CREATE_OPERATION,
    DOCUMENT_DOWNLOAD_OPERATION,
    DOCUMENT_UPLOAD_OPERATION,
    DOCUMENT_ARCHIVE_OPERATION,
    DOCUMENT_DELETE_OPERATION,
    DOCUMENT_MOVE_OPERATION,
    SPACE_DELETE_OPERATION,
    SPACE_UPDATE_OPERATION,
    WORKBOARD_UI_READ_OPERATION,
    WORKBOARD_CREATE_OPERATION,
    WORKBOARD_COMMENT_OPERATION,
    WORKBOARD_DELETE_OPERATION,
    WORKBOARD_UPDATE_OPERATION,
    PEER_IMAGE_OPERATION,
    PEER_BLOCK_OPERATION,
    PEER_REMOVAL_OPERATION,
    PEER_SHARE_OPERATION,
    PEER_RESPONSE_OPERATION,
    PEER_REQUEST_OPERATION,
    PEER_DISCOVERY_OPERATION,
    PEER_PREFERENCE_OPERATION,
    PEER_UI_READ_OPERATION,
    RELATION_CONTEXT_REFRESH_OPERATION,
    RELATION_DATA_OPERATION,
    RELATION_CONTEXT_READ_OPERATION,
    RELATION_DEBRIEF_READ_OPERATION,
    RELATION_DEBRIEF_BUILD_OPERATION,
    RELATION_FAVORITE_OPERATION,
    RELATION_GROUPING_OPERATION,
    RELATION_SETTINGS_READ_OPERATION,
    RELATION_SETTINGS_UPDATE_OPERATION,
    JOURNAL_PROVENANCE_OPERATION,
    HEALTH_TOKEN_REVOKE_OPERATION,
    HEALTH_TOKEN_CREATE_OPERATION,
    HEALTH_REMOVAL_OPERATION,
    HEALTH_AGGREGATE_OPERATION,
    HEALTH_SAMPLES_OPERATION,
    HEALTH_TOKENS_OPERATION,
    JOURNAL_FEEDBACK_OPERATION,
    JOURNAL_CONSOLIDATE_OPERATION,
    JOURNAL_READ_OPERATION,
    JOURNAL_PORTRAIT_OPERATION,
    JOURNAL_SETTINGS_OPERATION,
    JOURNAL_DELETE_OPERATION,
    JOURNAL_CREATE_OPERATION,
    JOURNAL_UPDATE_OPERATION,
    PSYCHE_RESET_OPERATION,
    PSYCHE_SUMMARY_OPERATION,
    PSYCHE_SETTINGS_OPERATION,
    PSYCHE_READ_OPERATION,
    PERSONALITY_READ_OPERATION,
    HABIT_READ_OPERATION,
    HABIT_DETAIL_OPERATION,
    HABIT_SETTINGS_OPERATION,
    HABIT_STATUS_OPERATION,
    HABIT_DELETE_OPERATION,
    HABIT_FORGET_OPERATION,
    HABIT_RECOMPUTE_OPERATION,
    OPEN_LOOP_READ_OPERATION,
    OPEN_LOOP_CLOSE_OPERATION,
    OPEN_LOOP_UPDATE_OPERATION,
    INTEREST_EXPORT_OPERATION,
    MEMORY_EXPORT_OPERATION,
    JOURNAL_EXPORT_OPERATION,
    INTEREST_READ_OPERATION,
    INTEREST_FEEDBACK_OPERATION,
    INTEREST_REACTIVATE_OPERATION,
    INTEREST_BULK_DELETE_OPERATION,
    INTEREST_SETTINGS_OPERATION,
    INTEREST_CREATE_OPERATION,
    INTEREST_DELETE_OPERATION,
    INTEREST_UPDATE_OPERATION,
    INTEREST_DETAILS_OPERATION,
    INTEREST_HISTORY_OPERATION,
    MEMORY_CREATE_OPERATION,
    MEMORY_BULK_DELETE_OPERATION,
    MEMORY_DELETE_OPERATION,
    MEMORY_UPDATE_OPERATION,
    MEMORY_PIN_OPERATION,
    MEMORY_PROVENANCE_OPERATION,
    MEMORY_READ_OPERATION,
    REMINDER_READ_OPERATION,
    REMINDER_CREATE_OPERATION,
    REMINDER_DELETE_OPERATION,
    REMINDER_UPDATE_OPERATION,
    ROUTINE_STATE_OPERATION,
    ROUTINE_CREATE_OPERATION,
    ROUTINE_DELETE_OPERATION,
    ROUTINE_UPDATE_OPERATION,
    ROUTINE_READ_OPERATION,
    ROUTINE_RUN_OPERATION,
    EXPORT_REQUEST_OPERATION,
    EXPORT_DOWNLOAD_OPERATION,
    SESSION_FLEET_OPERATION,
)
