"""UI management families compose editors without growing the central dispatcher."""

from src.domains.agents.application.asset_delete_editing import rebuild_asset_deletion
from src.domains.agents.application.asset_download_editing import rebuild_asset_download
from src.domains.agents.application.asset_retention_editing import rebuild_asset_retention
from src.domains.agents.application.bookmark_delete_editing import rebuild_bookmark_deletion
from src.domains.agents.application.bookmark_download_editing import rebuild_bookmark_download
from src.domains.agents.application.bookmark_keep_editing import rebuild_bookmark_keep
from src.domains.agents.application.document_archive_editing import rebuild_document_archive
from src.domains.agents.application.document_delete_editing import rebuild_document_deletion
from src.domains.agents.application.document_download_editing import rebuild_document_download
from src.domains.agents.application.document_move_editing import rebuild_document_move
from src.domains.agents.application.document_upload_editing import rebuild_document_upload
from src.domains.agents.application.email_share_send_editing import rebuild_email_share
from src.domains.agents.application.meeting_deletion_editing import rebuild_meeting_deletion
from src.domains.agents.application.meeting_email_editing import rebuild_meeting_email
from src.domains.agents.application.meeting_pdf_editing import rebuild_meeting_pdf
from src.domains.agents.application.meeting_preference_editing import rebuild_meeting_preferences
from src.domains.agents.application.meeting_reformat_editing import rebuild_meeting_reformat
from src.domains.agents.application.meeting_regeneration_editing import rebuild_meeting_regeneration
from src.domains.agents.application.meeting_report_restore_editing import rebuild_report_restoration
from src.domains.agents.application.meeting_report_update_editing import rebuild_report_update
from src.domains.agents.application.meeting_retry_editing import rebuild_meeting_retry
from src.domains.agents.application.meeting_template_editing import rebuild_meeting_template
from src.domains.agents.application.meeting_transcript_editing import rebuild_transcript_deletion
from src.domains.agents.application.people_editors import PEOPLE_EDITORS
from src.domains.agents.application.personal_mcp_configuration_editing import (
    rebuild_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_connection_editing import (
    rebuild_personal_mcp_connection,
)
from src.domains.agents.application.personal_mcp_delete_editing import rebuild_personal_mcp_delete
from src.domains.agents.application.personal_mcp_description_editing import (
    rebuild_personal_mcp_description,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_editing import (
    rebuild_personal_mcp_oauth_disconnect,
)
from src.domains.agents.application.personal_mcp_oauth_editing import rebuild_personal_mcp_oauth
from src.domains.agents.application.personal_mcp_settings_editing import (
    rebuild_personal_mcp_settings,
)
from src.domains.agents.application.personal_mcp_state_editing import rebuild_personal_mcp_state
from src.domains.agents.application.plugin_delete_editing import rebuild_plugin_delete
from src.domains.agents.application.plugin_file_upload_editing import rebuild_plugin_file_upload
from src.domains.agents.application.plugin_url_import_editing import rebuild_plugin_url_import
from src.domains.agents.application.recording_device_editing import rebuild_recording_device
from src.domains.agents.application.skill_delete_editing import rebuild_skill_delete
from src.domains.agents.application.skill_download_editing import rebuild_skill_download
from src.domains.agents.application.skill_file_upload_editing import rebuild_skill_file_upload
from src.domains.agents.application.skill_library_import_editing import rebuild_library_import
from src.domains.agents.application.skill_update_editing import rebuild_skill_update
from src.domains.agents.application.skill_url_import_editing import rebuild_skill_url_import
from src.domains.agents.application.source_delete_editing import rebuild_source_deletion
from src.domains.agents.application.source_link_editing import rebuild_source_link
from src.domains.agents.application.source_sync_editing import rebuild_source_sync
from src.domains.agents.application.source_unlink_editing import rebuild_source_unlink
from src.domains.agents.application.space_create_editing import rebuild_space_creation
from src.domains.agents.application.space_delete_editing import rebuild_space_deletion
from src.domains.agents.application.space_update_editing import rebuild_space_update
from src.domains.agents.application.workboard_comment_editing import rebuild_workboard_comment
from src.domains.agents.application.workboard_create_editing import rebuild_workboard_creation
from src.domains.agents.application.workboard_delete_editing import rebuild_workboard_delete
from src.domains.agents.application.workboard_update_editing import rebuild_workboard_update

MANAGEMENT_EDITORS = {
    "meeting_device.control": rebuild_recording_device,
    "meeting.delete": rebuild_meeting_deletion,
    "meeting_report.reformat": rebuild_meeting_reformat,
    "meeting_report.regenerate": rebuild_meeting_regeneration,
    "meeting.retry": rebuild_meeting_retry,
    "meeting_report.email": rebuild_meeting_email,
    "meeting_report.download": rebuild_meeting_pdf,
    "meeting_report.update": rebuild_report_update,
    "meeting_report.restore": rebuild_report_restoration,
    "meeting_transcript.delete": rebuild_transcript_deletion,
    "meeting_template.create": rebuild_meeting_template,
    "meeting_template.update": rebuild_meeting_template,
    "meeting_template.delete": rebuild_meeting_template,
    "meeting_preferences.update": rebuild_meeting_preferences,
    "knowledge_source.unlink": rebuild_source_unlink,
    "knowledge_source.link": rebuild_source_link,
    "knowledge_source.sync": rebuild_source_sync,
    "knowledge_source.delete": rebuild_source_deletion,
    "generated_assets.retention.update": rebuild_asset_retention,
    "generated_assets.delete": rebuild_asset_deletion,
    "saved_answer.keep": rebuild_bookmark_keep,
    "skill_settings.update": rebuild_skill_update,
    "personal_mcp.state.update": rebuild_personal_mcp_state,
    "personal_mcp.settings.update": rebuild_personal_mcp_settings,
    "personal_mcp.delete": rebuild_personal_mcp_delete,
    "personal_mcp.description.regenerate": rebuild_personal_mcp_description,
    "personal_mcp.connection.test": rebuild_personal_mcp_connection,
    "personal_mcp.oauth.disconnect": rebuild_personal_mcp_oauth_disconnect,
    "personal_mcp.configuration": rebuild_personal_mcp_configuration,
    "personal_mcp.oauth_authorize": rebuild_personal_mcp_oauth,
    "skill_settings.delete": rebuild_skill_delete,
    "plugin.delete": rebuild_plugin_delete,
    "plugin_url.import": rebuild_plugin_url_import,
    "plugin_file.upload": rebuild_plugin_file_upload,
    "skill_file.upload": rebuild_skill_file_upload,
    "skill_url.import": rebuild_skill_url_import,
    "skill_library.install": rebuild_library_import,
    "skill_library.update": rebuild_library_import,
    "skill_settings.download": rebuild_skill_download,
    "email_share.send": rebuild_email_share,
    "saved_answer.delete": rebuild_bookmark_deletion,
    "saved_answer.download": rebuild_bookmark_download,
    "generated_asset.download": rebuild_asset_download,
    **PEOPLE_EDITORS,
    "knowledge_space.create": rebuild_space_creation,
    "knowledge_document.download": rebuild_document_download,
    "knowledge_document.upload": rebuild_document_upload,
    "knowledge_documents.archive": rebuild_document_archive,
    "knowledge_documents.delete": rebuild_document_deletion,
    "knowledge_documents.move": rebuild_document_move,
    "knowledge_space.delete": rebuild_space_deletion,
    "knowledge_space.update": rebuild_space_update,
    "workboard_ticket.create": rebuild_workboard_creation,
    "workboard_ticket.comment": rebuild_workboard_comment,
    "workboard_ticket.delete": rebuild_workboard_delete,
    "workboard_ticket.update": rebuild_workboard_update,
}
