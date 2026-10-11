"""Public canonical data and effect notes compose across management families."""

from src.domains.agents.application.asset_delete_schemas import canonical_asset_deletion
from src.domains.agents.application.asset_download_schemas import canonical_asset_download
from src.domains.agents.application.asset_retention_schemas import canonical_asset_retention
from src.domains.agents.application.bookmark_delete_schemas import canonical_bookmark_deletion
from src.domains.agents.application.bookmark_download_schemas import canonical_bookmark_download
from src.domains.agents.application.bookmark_keep_schemas import canonical_bookmark_keep
from src.domains.agents.application.document_archive_schemas import canonical_document_archive
from src.domains.agents.application.document_delete_schemas import canonical_document_deletion
from src.domains.agents.application.document_download_schemas import canonical_document_download
from src.domains.agents.application.document_move_schemas import canonical_document_move
from src.domains.agents.application.document_upload_schemas import canonical_document_upload
from src.domains.agents.application.email_share_send_schemas import canonical_email_share
from src.domains.agents.application.meeting_deletion_schemas import canonical_meeting_deletion
from src.domains.agents.application.meeting_email_schemas import canonical_meeting_email
from src.domains.agents.application.meeting_pdf_schemas import canonical_meeting_pdf
from src.domains.agents.application.meeting_preference_schemas import canonical_meeting_preferences
from src.domains.agents.application.meeting_reformat_schemas import canonical_meeting_reformat
from src.domains.agents.application.meeting_regeneration_schemas import (
    canonical_meeting_regeneration,
)
from src.domains.agents.application.meeting_report_restore_schemas import (
    canonical_report_restoration,
)
from src.domains.agents.application.meeting_report_update_schemas import canonical_report_update
from src.domains.agents.application.meeting_retry_schemas import canonical_meeting_retry
from src.domains.agents.application.meeting_template_schemas import (
    canonical_template_creation,
    canonical_template_removal,
    canonical_template_replacement,
)
from src.domains.agents.application.meeting_transcript_schemas import canonical_transcript_deletion
from src.domains.agents.application.people_rendering import PEOPLE_CANONICAL, PEOPLE_PREVIEW_NOTES
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    canonical_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_connection_schemas import (
    canonical_personal_mcp_connection,
)
from src.domains.agents.application.personal_mcp_delete_schemas import canonical_personal_mcp_delete
from src.domains.agents.application.personal_mcp_description_schemas import (
    canonical_personal_mcp_description,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    canonical_personal_mcp_oauth_disconnect,
)
from src.domains.agents.application.personal_mcp_oauth_schemas import canonical_personal_mcp_oauth
from src.domains.agents.application.personal_mcp_settings_schemas import (
    canonical_personal_mcp_settings,
)
from src.domains.agents.application.personal_mcp_state_schemas import canonical_personal_mcp_state
from src.domains.agents.application.plugin_delete_schemas import canonical_plugin_deletion
from src.domains.agents.application.plugin_file_upload_schemas import canonical_plugin_file_upload
from src.domains.agents.application.plugin_url_import_schemas import canonical_plugin_url_import
from src.domains.agents.application.recording_device_schemas import canonical_recording_device
from src.domains.agents.application.skill_delete_schemas import canonical_skill_deletion
from src.domains.agents.application.skill_download_schemas import canonical_skill_download
from src.domains.agents.application.skill_file_upload_schemas import canonical_skill_file_upload
from src.domains.agents.application.skill_library_import_schemas import canonical_library_import
from src.domains.agents.application.skill_update_schemas import canonical_skill_update
from src.domains.agents.application.skill_url_import_schemas import canonical_skill_url_import
from src.domains.agents.application.source_delete_schemas import canonical_source_deletion
from src.domains.agents.application.source_link_schemas import canonical_source_link
from src.domains.agents.application.source_sync_schemas import canonical_source_sync
from src.domains.agents.application.source_unlink_schemas import canonical_source_unlink
from src.domains.agents.application.space_create_schemas import canonical_space_creation
from src.domains.agents.application.space_delete_schemas import canonical_space_deletion
from src.domains.agents.application.space_update_schemas import canonical_space_update
from src.domains.agents.application.workboard_comment_schemas import canonical_workboard_comment
from src.domains.agents.application.workboard_create import canonical_workboard_creation
from src.domains.agents.application.workboard_delete_schemas import canonical_workboard_delete
from src.domains.agents.application.workboard_update_schemas import canonical_workboard_update

MANAGEMENT_CANONICAL = {
    "meeting_device.control": canonical_recording_device,
    "meeting.delete": canonical_meeting_deletion,
    "meeting_report.reformat": canonical_meeting_reformat,
    "meeting_report.regenerate": canonical_meeting_regeneration,
    "meeting.retry": canonical_meeting_retry,
    "meeting_report.email": canonical_meeting_email,
    "meeting_report.download": canonical_meeting_pdf,
    "meeting_report.update": canonical_report_update,
    "meeting_report.restore": canonical_report_restoration,
    "meeting_transcript.delete": canonical_transcript_deletion,
    "meeting_template.create": canonical_template_creation,
    "meeting_template.update": canonical_template_replacement,
    "meeting_template.delete": canonical_template_removal,
    "meeting_preferences.update": canonical_meeting_preferences,
    "knowledge_source.unlink": canonical_source_unlink,
    "knowledge_source.link": canonical_source_link,
    "knowledge_source.sync": canonical_source_sync,
    "knowledge_source.delete": canonical_source_deletion,
    "generated_assets.retention.update": canonical_asset_retention,
    "generated_assets.delete": canonical_asset_deletion,
    "saved_answer.keep": canonical_bookmark_keep,
    "skill_settings.update": canonical_skill_update,
    "personal_mcp.state.update": canonical_personal_mcp_state,
    "personal_mcp.settings.update": canonical_personal_mcp_settings,
    "personal_mcp.delete": canonical_personal_mcp_delete,
    "personal_mcp.description.regenerate": canonical_personal_mcp_description,
    "personal_mcp.connection.test": canonical_personal_mcp_connection,
    "personal_mcp.oauth.disconnect": canonical_personal_mcp_oauth_disconnect,
    "personal_mcp.configuration": canonical_personal_mcp_configuration,
    "personal_mcp.oauth_authorize": canonical_personal_mcp_oauth,
    "skill_settings.delete": canonical_skill_deletion,
    "plugin.delete": canonical_plugin_deletion,
    "plugin_url.import": canonical_plugin_url_import,
    "plugin_file.upload": canonical_plugin_file_upload,
    "skill_file.upload": canonical_skill_file_upload,
    "skill_url.import": canonical_skill_url_import,
    "skill_library.install": canonical_library_import,
    "skill_library.update": canonical_library_import,
    "skill_settings.download": canonical_skill_download,
    "email_share.send": canonical_email_share,
    "saved_answer.delete": canonical_bookmark_deletion,
    "saved_answer.download": canonical_bookmark_download,
    "generated_asset.download": canonical_asset_download,
    **PEOPLE_CANONICAL,
    "knowledge_space.create": canonical_space_creation,
    "knowledge_document.download": canonical_document_download,
    "knowledge_document.upload": canonical_document_upload,
    "knowledge_documents.archive": canonical_document_archive,
    "knowledge_documents.delete": canonical_document_deletion,
    "knowledge_documents.move": canonical_document_move,
    "knowledge_space.delete": canonical_space_deletion,
    "knowledge_space.update": canonical_space_update,
    "workboard_ticket.create": canonical_workboard_creation,
    "workboard_ticket.comment": canonical_workboard_comment,
    "workboard_ticket.delete": canonical_workboard_delete,
    "workboard_ticket.update": canonical_workboard_update,
}
MANAGEMENT_PREVIEW_NOTES = {
    "meeting_device.control": "application_recording_device_note",
    "meeting.delete": "application_meeting_deletion_note",
    "meeting_report.reformat": "application_meeting_reformat_note",
    "meeting_report.regenerate": "application_meeting_regeneration_note",
    "meeting.retry": "application_meeting_retry_note",
    "meeting_report.email": "application_meeting_email_note",
    "meeting_report.download": "application_meeting_pdf_note",
    "meeting_report.update": "application_meeting_report_update_note",
    "meeting_report.restore": "application_meeting_report_restore_note",
    "meeting_transcript.delete": "application_meeting_transcript_delete_note",
    "meeting_template.create": "application_meeting_template_create_note",
    "meeting_template.update": "application_meeting_template_update_note",
    "meeting_template.delete": "application_meeting_template_delete_note",
    "meeting_preferences.update": "application_meeting_preferences_note",
    "knowledge_source.unlink": "application_source_unlink_note",
    "knowledge_source.link": "application_source_link_note",
    "knowledge_source.sync": "application_source_sync_note",
    "knowledge_source.delete": "application_source_delete_note",
    "generated_assets.retention.update": "application_asset_retention_note",
    "generated_assets.delete": "application_asset_delete_note",
    "saved_answer.keep": "application_bookmark_keep_note",
    "skill_settings.update": "application_skill_update_note",
    "personal_mcp.state.update": "application_personal_mcp_state_note",
    "personal_mcp.settings.update": "application_personal_mcp_settings_note",
    "personal_mcp.delete": "application_personal_mcp_delete_note",
    "personal_mcp.description.regenerate": "application_personal_mcp_description_note",
    "personal_mcp.connection.test": "application_personal_mcp_connection_note",
    "personal_mcp.oauth.disconnect": "application_personal_mcp_oauth_disconnect_note",
    "personal_mcp.configuration": "application_personal_mcp_configuration_note",
    "personal_mcp.oauth_authorize": "application_personal_mcp_oauth_note",
    "skill_settings.delete": "application_skill_delete_note",
    "plugin.delete": "application_plugin_delete_note",
    "skill_file.upload": "application_skill_file_upload_note",
    "skill_url.import": "application_skill_url_import_note",
    "plugin_url.import": "application_plugin_url_import_note",
    "plugin_file.upload": "application_plugin_file_upload_note",
    "skill_library.install": "application_skill_library_import_note",
    "skill_library.update": "application_skill_library_import_note",
    "skill_settings.download": "application_skill_download_note",
    "email_share.send": "application_email_share_send_note",
    "saved_answer.delete": "application_bookmark_delete_note",
    "saved_answer.download": "application_bookmark_download_note",
    "generated_asset.download": "application_asset_download_note",
    **PEOPLE_PREVIEW_NOTES,
    "knowledge_space.create": "application_space_create_note",
    "knowledge_document.download": "application_document_download_note",
    "knowledge_document.upload": "application_document_upload_note",
    "knowledge_documents.archive": "application_document_archive_note",
    "knowledge_documents.delete": "application_document_delete_note",
    "knowledge_documents.move": "application_document_move_note",
    "knowledge_space.delete": "application_space_delete_note",
    "knowledge_space.update": "application_space_update_note",
    "workboard_ticket.create": "application_workboard_create_note",
    "workboard_ticket.comment": "application_workboard_comment_note",
    "workboard_ticket.delete": "application_workboard_delete_note",
    "workboard_ticket.update": "application_workboard_update_note",
}
