"""
Internationalized draft execution messages.

Provides centralized translations for draft success and cancellation messages.
Used by DraftExecutionResult to display localized messages.

Supported languages: fr, en, es, de, it, zh-CN
"""

import re

from src.core.i18n import resolve_language
from src.core.i18n_application import (
    APPLICATION_CHANNEL_UNLINK,
    APPLICATION_CONNECTOR_UNLINK,
    APPLICATION_DRAFT_COPY,
    APPLICATION_EXPIRY_LABELS,
    APPLICATION_EXPORT_DOWNLOAD,
    APPLICATION_EXPORT_REQUEST,
    APPLICATION_FIELD_LABELS,
    APPLICATION_INTEREST_BULK,
    APPLICATION_INTEREST_CREATION,
    APPLICATION_INTEREST_FEEDBACK,
    APPLICATION_INTEREST_REACTIVATION,
    APPLICATION_INTEREST_REMOVAL,
    APPLICATION_INTEREST_UPDATE,
    APPLICATION_LIVE_CONNECTOR,
    APPLICATION_LIVE_PREFERENCES,
    APPLICATION_LOCATION_CLEAR,
    APPLICATION_MEMORY_BULK,
    APPLICATION_MEMORY_CREATION,
    APPLICATION_MEMORY_PIN,
    APPLICATION_MEMORY_REMOVAL,
    APPLICATION_MEMORY_UPDATE,
    APPLICATION_NOTIFICATION_DEVICE_REMOVE,
    APPLICATION_NUMBER_STATUS,
    APPLICATION_OTHER_SESSIONS,
    APPLICATION_PHONE_NUMBER,
    APPLICATION_PHONE_PREFERENCES,
    APPLICATION_REMINDER_CREATION,
    APPLICATION_REMINDER_REMOVAL,
    APPLICATION_REMINDER_UPDATE,
    APPLICATION_ROUTINE_CREATION,
    APPLICATION_ROUTINE_REMOVAL,
    APPLICATION_ROUTINE_RUN,
    APPLICATION_ROUTINE_STATE,
    APPLICATION_ROUTINE_UPDATE,
    APPLICATION_SESSION_CLOSED,
    APPLICATION_SESSION_REVOKE,
    APPLICATION_UNAVAILABLE,
)
from src.core.i18n_asset_delete import ASSET_DELETE_COPY
from src.core.i18n_asset_download import ASSET_DOWNLOAD_COPY
from src.core.i18n_asset_retention import ASSET_RETENTION_COPY
from src.core.i18n_bookmark_delete import BOOKMARK_DELETE_COPY
from src.core.i18n_bookmark_download import BOOKMARK_DOWNLOAD_COPY
from src.core.i18n_bookmark_keep import BOOKMARK_KEEP_COPY
from src.core.i18n_document_archive import DOCUMENT_ARCHIVE_COPY
from src.core.i18n_document_delete import DOCUMENT_DELETE_COPY
from src.core.i18n_document_download import DOCUMENT_DOWNLOAD_COPY
from src.core.i18n_document_move import DOCUMENT_MOVE_COPY
from src.core.i18n_document_upload import DOCUMENT_UPLOAD_COPY
from src.core.i18n_email_share_send import EMAIL_SHARE_SEND_COPY
from src.core.i18n_habit_actions import HABIT_ACTION_COPY
from src.core.i18n_habit_forgetting import HABIT_FORGET_COPY, HABIT_FORGET_COUNTS
from src.core.i18n_habit_recompute import HABIT_RECOMPUTE_COPY
from src.core.i18n_habit_settings import HABIT_SETTINGS_COPY
from src.core.i18n_health_removal import HEALTH_REMOVAL_COPY
from src.core.i18n_health_token import HEALTH_TOKEN_COPY
from src.core.i18n_health_token_creation import HEALTH_TOKEN_CREATION_COPY
from src.core.i18n_journal_consolidation import JOURNAL_CONSOLIDATION_COPY
from src.core.i18n_journal_creation import JOURNAL_CREATION_COPY
from src.core.i18n_journal_export import JOURNAL_EXPORT_COPY
from src.core.i18n_journal_feedback import JOURNAL_FEEDBACK_COPY
from src.core.i18n_journal_removal import JOURNAL_REMOVAL_COPY
from src.core.i18n_journal_settings import JOURNAL_SETTINGS_COPY
from src.core.i18n_journal_update import JOURNAL_UPDATE_COPY
from src.core.i18n_management_export import MANAGEMENT_EXPORT_COPY
from src.core.i18n_meeting_deletion import MEETING_DELETION_COPY
from src.core.i18n_meeting_email import MEETING_EMAIL_COPY
from src.core.i18n_meeting_pdf import MEETING_PDF_COPY
from src.core.i18n_meeting_preferences import MEETING_PREFERENCE_COPY
from src.core.i18n_meeting_reformat import MEETING_REFORMAT_COPY
from src.core.i18n_meeting_regeneration import MEETING_REGENERATION_COPY
from src.core.i18n_meeting_report_restore import MEETING_REPORT_RESTORE_COPY
from src.core.i18n_meeting_report_update import MEETING_REPORT_UPDATE_COPY
from src.core.i18n_meeting_retry import MEETING_RETRY_COPY
from src.core.i18n_meeting_template_actions import MEETING_TEMPLATE_ACTION_COPY
from src.core.i18n_meeting_transcripts import MEETING_TRANSCRIPT_COPY
from src.core.i18n_memory_export import MEMORY_EXPORT_COPY
from src.core.i18n_open_loop import OPEN_LOOP_COPY
from src.core.i18n_peer_block import PEER_BLOCK_COPY
from src.core.i18n_peer_image import PEER_IMAGE_COPY
from src.core.i18n_peer_preferences import PEER_PREFERENCES_COPY
from src.core.i18n_peer_removal import PEER_REMOVAL_COPY
from src.core.i18n_peer_request import PEER_REQUEST_COPY
from src.core.i18n_peer_response import PEER_RESPONSE_COPY
from src.core.i18n_peer_share import PEER_SHARE_COPY
from src.core.i18n_personal_mcp import (
    PERSONAL_MCP_CONFIGURATION_COPY,
    PERSONAL_MCP_CONNECTION_COPY,
    PERSONAL_MCP_DELETE_COPY,
    PERSONAL_MCP_DESCRIPTION_COPY,
    PERSONAL_MCP_OAUTH_COPY,
    PERSONAL_MCP_OAUTH_DISCONNECT_COPY,
    PERSONAL_MCP_SETTINGS_COPY,
    PERSONAL_MCP_STATE_COPY,
)
from src.core.i18n_plugin_delete import PLUGIN_DELETE_COPY
from src.core.i18n_plugin_import import PLUGIN_FILE_IMPORT_COPY, PLUGIN_IMPORT_COPY
from src.core.i18n_psyche_reset import PSYCHE_RESET_COPY
from src.core.i18n_psyche_settings import PSYCHE_SETTINGS_COPY
from src.core.i18n_psyche_summary import PSYCHE_SUMMARY_COPY
from src.core.i18n_recording_device import RECORDING_DEVICE_COPY
from src.core.i18n_relation_context_refresh import RELATION_CONTEXT_REFRESH_COPY
from src.core.i18n_relation_debrief_build import RELATION_DEBRIEF_BUILD_COPY
from src.core.i18n_relation_favorite import RELATION_FAVORITE_COPY
from src.core.i18n_relation_grouping import RELATION_GROUPING_COPY
from src.core.i18n_relation_settings import RELATION_SETTINGS_COPY
from src.core.i18n_skill_delete import SKILL_DELETE_COPY
from src.core.i18n_skill_download import SKILL_DOWNLOAD_COPY
from src.core.i18n_skill_file_upload import SKILL_FILE_UPLOAD_COPY
from src.core.i18n_skill_library_import import SKILL_LIBRARY_IMPORT_COPY
from src.core.i18n_skill_personal import SKILL_PERSONAL_COPY
from src.core.i18n_skill_url_import import SKILL_URL_IMPORT_COPY
from src.core.i18n_sms import SMS_APPROVAL_NOTE
from src.core.i18n_source_delete import SOURCE_DELETE_COPY
from src.core.i18n_source_link import SOURCE_LINK_COPY
from src.core.i18n_source_sync import SOURCE_SYNC_COPY
from src.core.i18n_source_unlink import SOURCE_UNLINK_COPY
from src.core.i18n_space_create import SPACE_CREATE_COPY
from src.core.i18n_space_delete import SPACE_DELETE_COPY
from src.core.i18n_space_update import SPACE_UPDATE_COPY
from src.core.i18n_types import Language
from src.core.i18n_workboard_comment import WORKBOARD_COMMENT_COPY
from src.core.i18n_workboard_create import WORKBOARD_CREATE_COPY
from src.core.i18n_workboard_delete import WORKBOARD_DELETE_COPY
from src.core.i18n_workboard_update import WORKBOARD_UPDATE_COPY
from src.core.text_clip import ELLIPSIS, one_line, spell_unseen

# ============================================================================
# SUCCESS MESSAGES
# ============================================================================
# Messages displayed when a draft action is successfully executed.
# Keys correspond to DraftType enum values in drafts/models.py
# Some messages use {name}, {summary}, or {title} placeholders for dynamic content.

DRAFT_SUCCESS_MESSAGES: dict[Language, dict[str, str]] = {
    "fr": {
        "email": "Envoyé avec succès",
        "email_reply": "Réponse envoyée avec succès",
        "email_forward": "Transféré avec succès",
        "mailbox_draft_send": "Brouillon envoyé avec succès",
        "email_delete": "Supprimé avec succès",
        "event": "'{summary}' créé avec succès",
        "event_update": "'{summary}' modifié avec succès",
        "event_delete": "Supprimé avec succès",
        "contact": "'{name}' créé avec succès",
        "contact_update": "'{name}' modifié avec succès",
        "contact_delete": "Supprimé avec succès",
        "task": "'{title}' créée avec succès",
        "task_update": "'{title}' modifiée avec succès",
        "task_delete": "Supprimée avec succès",
        "file_delete": "Supprimé avec succès",
        "label_delete": "Label supprimé avec succès",
        "reminder_delete": "Rappel '{content}' supprimé",
        "ticket_delete": "Ticket '{title}' supprimé",
        "phone_call": "J'appelle **{name}** maintenant, je te fais un retour dès que j'ai la réponse.",
        "_default": "Action exécutée avec succès",
    },
    "en": {
        "email": "Sent successfully",
        "email_reply": "Reply sent successfully",
        "email_forward": "Forwarded successfully",
        "mailbox_draft_send": "Draft sent successfully",
        "email_delete": "Deleted successfully",
        "event": "'{summary}' created successfully",
        "event_update": "'{summary}' updated successfully",
        "event_delete": "Deleted successfully",
        "contact": "'{name}' created successfully",
        "contact_update": "'{name}' updated successfully",
        "contact_delete": "Deleted successfully",
        "task": "'{title}' created successfully",
        "task_update": "'{title}' updated successfully",
        "task_delete": "Deleted successfully",
        "file_delete": "Deleted successfully",
        "label_delete": "Label deleted successfully",
        "reminder_delete": "Reminder '{content}' deleted",
        "ticket_delete": "Ticket '{title}' deleted",
        "phone_call": "I'm calling **{name}** now — I'll get back to you as soon as I have an answer.",
        "_default": "Action completed successfully",
    },
    "es": {
        "email": "Enviado con éxito",
        "email_reply": "Respuesta enviada con éxito",
        "email_forward": "Reenviado con éxito",
        "mailbox_draft_send": "Borrador enviado con éxito",
        "email_delete": "Eliminado con éxito",
        "event": "'{summary}' creado con éxito",
        "event_update": "'{summary}' actualizado con éxito",
        "event_delete": "Eliminado con éxito",
        "contact": "'{name}' creado con éxito",
        "contact_update": "'{name}' actualizado con éxito",
        "contact_delete": "Eliminado con éxito",
        "task": "'{title}' creada con éxito",
        "task_update": "'{title}' actualizada con éxito",
        "task_delete": "Eliminada con éxito",
        "file_delete": "Eliminado con éxito",
        "label_delete": "Etiqueta eliminada con éxito",
        "reminder_delete": "Recordatorio '{content}' eliminado",
        "ticket_delete": "Ticket '{title}' eliminado",
        "phone_call": "Estoy llamando a **{name}** ahora; te aviso en cuanto tenga una respuesta.",
        "_default": "Acción ejecutada con éxito",
    },
    "de": {
        "email": "Erfolgreich gesendet",
        "email_reply": "Antwort erfolgreich gesendet",
        "email_forward": "Erfolgreich weitergeleitet",
        "mailbox_draft_send": "Entwurf erfolgreich gesendet",
        "email_delete": "Erfolgreich gelöscht",
        "event": "'{summary}' erfolgreich erstellt",
        "event_update": "'{summary}' erfolgreich aktualisiert",
        "event_delete": "Erfolgreich gelöscht",
        "contact": "'{name}' erfolgreich erstellt",
        "contact_update": "'{name}' erfolgreich aktualisiert",
        "contact_delete": "Erfolgreich gelöscht",
        "task": "'{title}' erfolgreich erstellt",
        "task_update": "'{title}' erfolgreich aktualisiert",
        "task_delete": "Erfolgreich gelöscht",
        "file_delete": "Erfolgreich gelöscht",
        "label_delete": "Label erfolgreich gelöscht",
        "reminder_delete": "Erinnerung '{content}' gelöscht",
        "ticket_delete": "Ticket '{title}' gelöscht",
        "phone_call": "Ich rufe **{name}** jetzt an und melde mich, sobald ich eine Antwort habe.",
        "_default": "Aktion erfolgreich ausgeführt",
    },
    "it": {
        "email": "Inviata con successo",
        "email_reply": "Risposta inviata con successo",
        "email_forward": "Inoltrata con successo",
        "mailbox_draft_send": "Bozza inviata con successo",
        "email_delete": "Eliminata con successo",
        "event": "'{summary}' creato con successo",
        "event_update": "'{summary}' aggiornato con successo",
        "event_delete": "Eliminato con successo",
        "contact": "'{name}' creato con successo",
        "contact_update": "'{name}' aggiornato con successo",
        "contact_delete": "Eliminato con successo",
        "task": "'{title}' creata con successo",
        "task_update": "'{title}' aggiornata con successo",
        "task_delete": "Eliminata con successo",
        "file_delete": "Eliminato con successo",
        "label_delete": "Etichetta eliminata con successo",
        "reminder_delete": "Promemoria '{content}' eliminato",
        "ticket_delete": "Ticket '{title}' eliminato",
        "phone_call": "Sto chiamando **{name}** adesso; ti aggiorno appena ho una risposta.",
        "_default": "Azione eseguita con successo",
    },
    "zh-CN": {
        "email": "发送成功",
        "email_reply": "回复发送成功",
        "email_forward": "转发成功",
        "mailbox_draft_send": "草稿已成功发送",
        "email_delete": "删除成功",
        "event": "'{summary}' 创建成功",
        "event_update": "'{summary}' 更新成功",
        "event_delete": "删除成功",
        "contact": "'{name}' 创建成功",
        "contact_update": "'{name}' 更新成功",
        "contact_delete": "删除成功",
        "task": "'{title}' 创建成功",
        "task_update": "'{title}' 更新成功",
        "task_delete": "删除成功",
        "file_delete": "删除成功",
        "label_delete": "标签删除成功",
        "reminder_delete": "提醒 '{content}' 已删除",
        "ticket_delete": "工单 '{title}' 已删除",
        "phone_call": "我正在拨打 **{name}**，一有答复我就告诉你。",
        "_default": "操作成功完成",
    },
}

# ============================================================================
# CANCEL MESSAGES
# ============================================================================
# Messages displayed when a draft action is cancelled by the user.

DRAFT_CANCEL_MESSAGES: dict[Language, dict[str, str]] = {
    "fr": {
        "email": "Envoi annulé",
        "email_reply": "Réponse annulée",
        "email_forward": "Transfert annulé",
        "mailbox_draft_send": "Envoi du brouillon annulé",
        "email_delete": "Suppression annulée",
        "event": "Création annulée",
        "event_update": "Modification annulée",
        "event_delete": "Suppression annulée",
        "contact": "Création annulée",
        "contact_update": "Modification annulée",
        "contact_delete": "Suppression annulée",
        "task": "Création annulée",
        "task_update": "Modification annulée",
        "task_delete": "Suppression annulée",
        "file_delete": "Suppression annulée",
        "label_delete": "Suppression annulée",
        "reminder_delete": "Suppression annulée",
        "ticket_delete": "Suppression annulée",
        "phone_call": "Appel annulé",
        "_default": "Action annulée",
    },
    "en": {
        "email": "Sending cancelled",
        "email_reply": "Reply cancelled",
        "email_forward": "Forwarding cancelled",
        "mailbox_draft_send": "Sending the draft cancelled",
        "email_delete": "Deletion cancelled",
        "event": "Creation cancelled",
        "event_update": "Modification cancelled",
        "event_delete": "Deletion cancelled",
        "contact": "Creation cancelled",
        "contact_update": "Modification cancelled",
        "contact_delete": "Deletion cancelled",
        "task": "Creation cancelled",
        "task_update": "Modification cancelled",
        "task_delete": "Deletion cancelled",
        "file_delete": "Deletion cancelled",
        "label_delete": "Deletion cancelled",
        "reminder_delete": "Deletion cancelled",
        "ticket_delete": "Deletion cancelled",
        "phone_call": "Call cancelled",
        "_default": "Action cancelled",
    },
    "es": {
        "email": "Envío cancelado",
        "email_reply": "Respuesta cancelada",
        "email_forward": "Reenvío cancelado",
        "mailbox_draft_send": "Envío del borrador cancelado",
        "email_delete": "Eliminación cancelada",
        "event": "Creación cancelada",
        "event_update": "Modificación cancelada",
        "event_delete": "Eliminación cancelada",
        "contact": "Creación cancelada",
        "contact_update": "Modificación cancelada",
        "contact_delete": "Eliminación cancelada",
        "task": "Creación cancelada",
        "task_update": "Modificación cancelada",
        "task_delete": "Eliminación cancelada",
        "file_delete": "Eliminación cancelada",
        "label_delete": "Eliminación cancelada",
        "reminder_delete": "Eliminación cancelada",
        "ticket_delete": "Eliminación cancelada",
        "phone_call": "Llamada cancelada",
        "_default": "Acción cancelada",
    },
    "de": {
        "email": "Versand abgebrochen",
        "email_reply": "Antwort abgebrochen",
        "email_forward": "Weiterleitung abgebrochen",
        "mailbox_draft_send": "Senden des Entwurfs abgebrochen",
        "email_delete": "Löschung abgebrochen",
        "event": "Erstellung abgebrochen",
        "event_update": "Änderung abgebrochen",
        "event_delete": "Löschung abgebrochen",
        "contact": "Erstellung abgebrochen",
        "contact_update": "Änderung abgebrochen",
        "contact_delete": "Löschung abgebrochen",
        "task": "Erstellung abgebrochen",
        "task_update": "Änderung abgebrochen",
        "task_delete": "Löschung abgebrochen",
        "file_delete": "Löschung abgebrochen",
        "label_delete": "Löschung abgebrochen",
        "reminder_delete": "Löschung abgebrochen",
        "ticket_delete": "Löschung abgebrochen",
        "phone_call": "Anruf abgebrochen",
        "_default": "Aktion abgebrochen",
    },
    "it": {
        "email": "Invio annullato",
        "email_reply": "Risposta annullata",
        "email_forward": "Inoltro annullato",
        "mailbox_draft_send": "Invio della bozza annullato",
        "email_delete": "Eliminazione annullata",
        "event": "Creazione annullata",
        "event_update": "Modifica annullata",
        "event_delete": "Eliminazione annullata",
        "contact": "Creazione annullata",
        "contact_update": "Modifica annullata",
        "contact_delete": "Eliminazione annullata",
        "task": "Creazione annullata",
        "task_update": "Modifica annullata",
        "task_delete": "Eliminazione annullata",
        "file_delete": "Eliminazione annullata",
        "label_delete": "Eliminazione annullata",
        "reminder_delete": "Eliminazione annullata",
        "ticket_delete": "Eliminazione annullata",
        "phone_call": "Chiamata annullata",
        "_default": "Azione annullata",
    },
    "zh-CN": {
        "email": "发送已取消",
        "email_reply": "回复已取消",
        "email_forward": "转发已取消",
        "mailbox_draft_send": "草稿发送已取消",
        "email_delete": "删除已取消",
        "event": "创建已取消",
        "event_update": "修改已取消",
        "event_delete": "删除已取消",
        "contact": "创建已取消",
        "contact_update": "修改已取消",
        "contact_delete": "删除已取消",
        "task": "创建已取消",
        "task_update": "修改已取消",
        "task_delete": "删除已取消",
        "file_delete": "删除已取消",
        "label_delete": "删除已取消",
        "reminder_delete": "删除已取消",
        "ticket_delete": "删除已取消",
        "phone_call": "通话已取消",
        "_default": "操作已取消",
    },
}

# ============================================================================
# ERROR MESSAGES
# ============================================================================
# Messages displayed when a draft execution fails.

DRAFT_ERROR_MESSAGES: dict[Language, str] = {
    "fr": "Erreur lors de l'exécution",
    "en": "Error during execution",
    "es": "Error durante la ejecución",
    "de": "Fehler bei der Ausführung",
    "it": "Errore durante l'esecuzione",
    "zh-CN": "执行时出错",
}


# Shown when a confirmed draft could NOT run because the same action is already
# on record without a result — a first attempt that failed, or one still in
# flight (ADR-263). Repeating it is the one thing the gate must not do, and
# reporting a success it knows nothing about is the one thing it must not say.
DRAFT_ALREADY_CLAIMED_MESSAGES: dict[Language, str] = {
    "fr": "Cette action est déjà enregistrée sans résultat connu : elle n'a pas "
    "été relancée. Vérifie avant de réessayer.",
    "en": "This action is already on record with no known result: it was not "
    "retried. Please check before trying again.",
    "es": "Esta acción ya está registrada sin resultado conocido: no se ha "
    "reintentado. Compruébalo antes de volver a intentarlo.",
    "de": "Diese Aktion ist bereits ohne bekanntes Ergebnis erfasst: Sie wurde "
    "nicht wiederholt. Bitte prüfe es, bevor du es erneut versuchst.",
    "it": "Questa azione è già registrata senza un risultato noto: non è stata "
    "ripetuta. Verifica prima di riprovare.",
    "zh-CN": "此操作已记录但结果未知：未重试。请先确认再重试。",
}


# ============================================================================
# DRAFT SUMMARY LABELS
# ============================================================================
# Labels for get_summary() method - brief one-line draft descriptions.
# Used in LLM summaries and HITL question headers.
# Format: {type}_{action} where action is: to, at, on, delete, update, create

DRAFT_SUMMARY_LABELS: dict[Language, dict[str, str]] = {
    "fr": {
        # Email actions
        "email_to": "Email à {to}",
        "email_reply_to": "Réponse à {to}",
        "email_forward_to": "Transfert à {to}",
        "email_delete": "Suppression email : {subject}",
        # Event actions
        "event_create": "Événement : {summary} le {start}",
        "event_update": "Modification événement : {summary}",
        "event_delete": "Suppression événement : {summary}",
        # Contact actions
        "contact_create": "Contact : {name}",
        "contact_update": "Modification contact : {name}",
        "contact_delete": "Suppression contact : {name}",
        # Task actions
        "task_create": "Tâche : {title}",
        "task_update": "Modification tâche : {title}",
        "task_delete": "Suppression tâche : {title}",
        # File actions
        "file_delete": "Suppression fichier : {name}",
        # Label actions
        "label_delete": "Suppression label : {name}",
        # Phone call action
        "phone_call": "Appel à {name} : {objective}",
        # Draft header
        "draft_created": "📄 **Brouillon créé** : {title}",
        "action_required": "**Action requise** : confirme, modifie ou annule.",
        "devops_task": "Tâche serveur {server} : {task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "Suppression rappel : {content}",
        "ticket_delete": "Suppression ticket : {title}",
        "scheduled_action": "Automatisation : {title}",
        "peer_message": "Message à {name}",
        "vacation_responder_on": "Réponse automatique : {subject}",
        "vacation_responder_off": "Désactivation de la réponse automatique",
        "email_filter": "Filtre email : {criteria}",
        "tool_call": "Action : {tool}",
        "sandbox_egress": "Accès internet : {hosts}",
        "spreadsheet_write": "Écriture dans {file} ({sheet})",
        "document_append": "Ajout dans {file}",
    },
    "en": {
        "email_to": "Email to {to}",
        "email_reply_to": "Reply to {to}",
        "email_forward_to": "Forward to {to}",
        "email_delete": "Delete email: {subject}",
        "event_create": "Event: {summary} on {start}",
        "event_update": "Update event: {summary}",
        "event_delete": "Delete event: {summary}",
        "contact_create": "Contact: {name}",
        "contact_update": "Update contact: {name}",
        "contact_delete": "Delete contact: {name}",
        "task_create": "Task: {title}",
        "task_update": "Update task: {title}",
        "task_delete": "Delete task: {title}",
        "file_delete": "Delete file: {name}",
        "label_delete": "Delete label: {name}",
        "phone_call": "Call to {name}: {objective}",
        "draft_created": "📄 **Draft created**: {title}",
        "action_required": "**Action required**: confirm, edit, or cancel.",
        "devops_task": "Server task on {server}: {task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "Delete reminder: {content}",
        "ticket_delete": "Delete ticket: {title}",
        "scheduled_action": "Automation: {title}",
        "peer_message": "Message to {name}",
        "vacation_responder_on": "Auto-reply: {subject}",
        "vacation_responder_off": "Turn off the auto-reply",
        "email_filter": "Email filter: {criteria}",
        "tool_call": "Action: {tool}",
        "sandbox_egress": "Internet access: {hosts}",
        "spreadsheet_write": "Write to {file} ({sheet})",
        "document_append": "Append to {file}",
    },
    "es": {
        "email_to": "Email a {to}",
        "email_reply_to": "Respuesta a {to}",
        "email_forward_to": "Reenvío a {to}",
        "email_delete": "Eliminación email: {subject}",
        "event_create": "Evento: {summary} el {start}",
        "event_update": "Modificación evento: {summary}",
        "event_delete": "Eliminación evento: {summary}",
        "contact_create": "Contacto: {name}",
        "contact_update": "Modificación contacto: {name}",
        "contact_delete": "Eliminación contacto: {name}",
        "task_create": "Tarea: {title}",
        "task_update": "Modificación tarea: {title}",
        "task_delete": "Eliminación tarea: {title}",
        "file_delete": "Eliminación archivo: {name}",
        "label_delete": "Eliminar etiqueta: {name}",
        "phone_call": "Llamada a {name}: {objective}",
        "draft_created": "📄 **Borrador creado**: {title}",
        "action_required": "**Acción requerida**: confirma, modifica o cancela.",
        "devops_task": "Tarea de servidor en {server}: {task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "Eliminar recordatorio: {content}",
        "ticket_delete": "Eliminar ticket: {title}",
        "scheduled_action": "Automatización: {title}",
        "peer_message": "Mensaje a {name}",
        "vacation_responder_on": "Respuesta automática: {subject}",
        "vacation_responder_off": "Desactivar la respuesta automática",
        "email_filter": "Filtro de correo: {criteria}",
        "tool_call": "Acción: {tool}",
        "sandbox_egress": "Acceso a internet: {hosts}",
        "spreadsheet_write": "Escritura en {file} ({sheet})",
        "document_append": "Añadir en {file}",
    },
    "de": {
        "email_to": "E-Mail an {to}",
        "email_reply_to": "Antwort an {to}",
        "email_forward_to": "Weiterleitung an {to}",
        "email_delete": "E-Mail löschen: {subject}",
        "event_create": "Termin: {summary} am {start}",
        "event_update": "Termin ändern: {summary}",
        "event_delete": "Termin löschen: {summary}",
        "contact_create": "Kontakt: {name}",
        "contact_update": "Kontakt ändern: {name}",
        "contact_delete": "Kontakt löschen: {name}",
        "task_create": "Aufgabe: {title}",
        "task_update": "Aufgabe ändern: {title}",
        "task_delete": "Aufgabe löschen: {title}",
        "file_delete": "Datei löschen: {name}",
        "label_delete": "Label löschen: {name}",
        "phone_call": "Anruf an {name}: {objective}",
        "draft_created": "📄 **Entwurf erstellt**: {title}",
        "action_required": "**Aktion erforderlich**: bestätigen, bearbeiten oder abbrechen.",
        "devops_task": "Serveraufgabe auf {server}: {task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "Erinnerung löschen: {content}",
        "ticket_delete": "Ticket löschen: {title}",
        "scheduled_action": "Automatisierung: {title}",
        "peer_message": "Nachricht an {name}",
        "vacation_responder_on": "Abwesenheitsnotiz: {subject}",
        "vacation_responder_off": "Abwesenheitsnotiz deaktivieren",
        "email_filter": "E-Mail-Filter: {criteria}",
        "tool_call": "Aktion: {tool}",
        "sandbox_egress": "Internetzugriff: {hosts}",
        "spreadsheet_write": "Schreiben in {file} ({sheet})",
        "document_append": "Hinzufügen in {file}",
    },
    "it": {
        "email_to": "Email a {to}",
        "email_reply_to": "Risposta a {to}",
        "email_forward_to": "Inoltro a {to}",
        "email_delete": "Eliminazione email: {subject}",
        "event_create": "Evento: {summary} il {start}",
        "event_update": "Modifica evento: {summary}",
        "event_delete": "Elimina evento: {summary}",
        "contact_create": "Contatto: {name}",
        "contact_update": "Modifica contatto: {name}",
        "contact_delete": "Elimina contatto: {name}",
        "task_create": "Attività: {title}",
        "task_update": "Modifica attività: {title}",
        "task_delete": "Elimina attività: {title}",
        "file_delete": "Elimina file: {name}",
        "label_delete": "Elimina etichetta: {name}",
        "phone_call": "Chiamata a {name}: {objective}",
        "draft_created": "📄 **Bozza creata**: {title}",
        "action_required": "**Azione richiesta**: conferma, modifica o annulla.",
        "devops_task": "Attività server su {server}: {task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "Eliminazione promemoria: {content}",
        "ticket_delete": "Eliminazione ticket: {title}",
        "scheduled_action": "Automazione: {title}",
        "peer_message": "Messaggio a {name}",
        "vacation_responder_on": "Risposta automatica: {subject}",
        "vacation_responder_off": "Disattivazione della risposta automatica",
        "email_filter": "Filtro email: {criteria}",
        "tool_call": "Azione: {tool}",
        "sandbox_egress": "Accesso a internet: {hosts}",
        "spreadsheet_write": "Scrittura in {file} ({sheet})",
        "document_append": "Aggiunta in {file}",
    },
    "zh-CN": {
        "email_to": "发送邮件给 {to}",
        "email_reply_to": "回复 {to}",
        "email_forward_to": "转发给 {to}",
        "email_delete": "删除邮件：{subject}",
        "event_create": "事件：{summary} 于 {start}",
        "event_update": "修改事件：{summary}",
        "event_delete": "删除事件：{summary}",
        "contact_create": "联系人：{name}",
        "contact_update": "修改联系人：{name}",
        "contact_delete": "删除联系人：{name}",
        "task_create": "任务：{title}",
        "task_update": "修改任务：{title}",
        "task_delete": "删除任务：{title}",
        "file_delete": "删除文件：{name}",
        "label_delete": "删除标签：{name}",
        "phone_call": "致电 {name}：{objective}",
        "draft_created": "📄 **草稿已创建**：{title}",
        "action_required": "**需要操作**：确认、修改或取消。",
        "devops_task": "服务器任务 {server}：{task}",
        # Nine draft types reached no branch at all before lot 13 and were
        # titled « Draft (tool_call) » — the enum value, in English, in every
        # language. See drafts/summary_renderer.py, whose boot assert is what
        # keeps this list complete.
        "reminder_delete": "删除提醒：{content}",
        "ticket_delete": "删除工单：{title}",
        "scheduled_action": "自动化：{title}",
        "peer_message": "发送给 {name} 的消息",
        "vacation_responder_on": "自动回复：{subject}",
        "vacation_responder_off": "关闭自动回复",
        "email_filter": "邮件过滤器：{criteria}",
        "tool_call": "操作：{tool}",
        "sandbox_egress": "互联网访问：{hosts}",
        "spreadsheet_write": "写入 {file}（{sheet}）",
        "document_append": "追加到 {file}",
    },
}

# ============================================================================
# DRAFT PREVIEW LABELS
# ============================================================================
# Field labels for get_detailed_preview() method - detailed draft content display.
# Used in HITL confirmation flow to show full draft details before execution.

DRAFT_PREVIEW_LABELS: dict[Language, dict[str, str]] = {
    "fr": {
        "to": "Destinataire",
        "cc": "Cc",
        "bcc": "Cci",
        "subject": "Objet",
        "no_subject": "(sans objet)",
        "steps": "Étapes",
        "body": "Message",
        "from": "De",
        "date": "Date",
        "attachments": "Pièces jointes",
        "event": "Événement",
        "start": "Début",
        "end": "Fin",
        "location": "Lieu",
        "attendees": "Participants",
        "contact": "Contact",
        "email": "Email",
        "phone": "Téléphone",
        "organization": "Organisation",
        "task": "Tâche",
        "due": "Échéance",
        "file": "Fichier",
        "changes": "Modifications",
        "type": "Type",
        "label": "Label",
        "label_parent": "Label parent",
        "sublabels_to_delete": "Sous-labels à supprimer",
        "sublabels_included": "Sous-labels inclus",
        "recipient": "Destinataire",
        "message": "Message",
        "callee": "Correspondant",
        "objective": "Objectif",
        "title": "Titre",
        "schedule": "Planification",
        "instruction": "Instruction",
        "server": "Serveur",
        "tool": "Outil",
        "hosts_unknown": "Hôtes à autoriser",
        "hosts_known": "Déjà permis",
        "purpose": "Motif",
        "turn_data": "Données du tour",
        "turn_data_none": "aucune",
        "turn_data_too_large": "trop volumineuses pour suivre",
        "third_party_skill_note": "Cette skill a été écrite ailleurs. N'envoie les données du tour que si tu lui fais confiance.",
        "stdout": "Résultat",
        "traceback": "Erreur",
        "details": "Détails",
        "context": "Consignes",
        "video_conference": "Visioconférence",
        "video_conference_included": "Incluse",
        "vacation_disabled": "La réponse automatique sera désactivée",
        "sheet": "Feuille",
        "range": "Plage",
        "text": "Texte",
        "query": "Requête",
        "filter_archive": "Les messages seront archivés",
        "filter_mark_read": "Les messages seront marqués comme lus",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": " : ",
    },
    "en": {
        "to": "To",
        "cc": "Cc",
        "bcc": "Bcc",
        "subject": "Subject",
        "no_subject": "(no subject)",
        "steps": "Steps",
        "body": "Message",
        "from": "From",
        "date": "Date",
        "attachments": "Attachments",
        "event": "Event",
        "start": "Start",
        "end": "End",
        "location": "Location",
        "attendees": "Attendees",
        "contact": "Contact",
        "email": "Email",
        "phone": "Phone",
        "organization": "Organization",
        "task": "Task",
        "due": "Due",
        "file": "File",
        "changes": "Changes",
        "type": "Type",
        "label": "Label",
        "label_parent": "Parent label",
        "sublabels_to_delete": "Sub-labels to delete",
        "sublabels_included": "Sub-labels included",
        "recipient": "Recipient",
        "message": "Message",
        "callee": "Callee",
        "objective": "Objective",
        "title": "Title",
        "schedule": "Schedule",
        "instruction": "Instruction",
        "server": "Server",
        "tool": "Tool",
        "hosts_unknown": "Hosts to allow",
        "hosts_known": "Already permitted",
        "purpose": "Purpose",
        "turn_data": "Turn data",
        "turn_data_none": "none",
        "turn_data_too_large": "too large to travel",
        "third_party_skill_note": "This skill was written elsewhere. Send the turn's data only if you trust it.",
        "stdout": "Output",
        "traceback": "Error",
        "details": "Details",
        "context": "Instructions",
        "video_conference": "Video call",
        "video_conference_included": "Included",
        "vacation_disabled": "The auto-reply will be turned off",
        "sheet": "Sheet",
        "range": "Range",
        "text": "Text",
        "query": "Query",
        "filter_archive": "Matching messages will be archived",
        "filter_mark_read": "Matching messages will be marked as read",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": ": ",
    },
    "es": {
        "to": "Destinatario",
        "cc": "Cc",
        "bcc": "Cco",
        "subject": "Asunto",
        "no_subject": "(sin asunto)",
        "steps": "Pasos",
        "body": "Mensaje",
        "from": "De",
        "date": "Fecha",
        "attachments": "Adjuntos",
        "event": "Evento",
        "start": "Inicio",
        "end": "Fin",
        "location": "Ubicación",
        "attendees": "Asistentes",
        "contact": "Contacto",
        "email": "Email",
        "phone": "Teléfono",
        "organization": "Organización",
        "task": "Tarea",
        "due": "Vencimiento",
        "file": "Archivo",
        "changes": "Cambios",
        "type": "Tipo",
        "label": "Etiqueta",
        "label_parent": "Etiqueta padre",
        "sublabels_to_delete": "Subetiquetas a eliminar",
        "sublabels_included": "Subetiquetas incluidas",
        "recipient": "Destinatario",
        "message": "Mensaje",
        "callee": "Interlocutor",
        "objective": "Objetivo",
        "title": "Título",
        "schedule": "Programación",
        "instruction": "Instrucción",
        "server": "Servidor",
        "tool": "Herramienta",
        "hosts_unknown": "Hosts a autorizar",
        "hosts_known": "Ya permitidos",
        "purpose": "Motivo",
        "turn_data": "Datos del turno",
        "turn_data_none": "ninguno",
        "turn_data_too_large": "demasiado voluminosos para viajar",
        "third_party_skill_note": "Esta skill fue escrita en otro lugar. Envía los datos del turno solo si confías en ella.",
        "stdout": "Resultado",
        "traceback": "Error",
        "details": "Detalles",
        "context": "Instrucciones",
        "video_conference": "Videollamada",
        "video_conference_included": "Incluida",
        "vacation_disabled": "La respuesta automática se desactivará",
        "sheet": "Hoja",
        "range": "Rango",
        "text": "Texto",
        "query": "Consulta",
        "filter_archive": "Los mensajes coincidentes se archivarán",
        "filter_mark_read": "Los mensajes coincidentes se marcarán como leídos",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": ": ",
    },
    "de": {
        "to": "An",
        "cc": "Cc",
        "bcc": "Bcc",
        "subject": "Betreff",
        "no_subject": "(kein Betreff)",
        "steps": "Schritte",
        "body": "Nachricht",
        "from": "Von",
        "date": "Datum",
        "attachments": "Anhänge",
        "event": "Termin",
        "start": "Beginn",
        "end": "Ende",
        "location": "Ort",
        "attendees": "Teilnehmer",
        "contact": "Kontakt",
        "email": "E-Mail",
        "phone": "Telefon",
        "organization": "Organisation",
        "task": "Aufgabe",
        "due": "Fällig",
        "file": "Datei",
        "changes": "Änderungen",
        "type": "Typ",
        "label": "Label",
        "label_parent": "Übergeordnetes Label",
        "sublabels_to_delete": "Zu löschende Unterlabels",
        "sublabels_included": "Enthaltene Unterlabels",
        "recipient": "Empfänger",
        "message": "Nachricht",
        "callee": "Angerufener",
        "objective": "Ziel",
        "title": "Titel",
        "schedule": "Zeitplan",
        "instruction": "Anweisung",
        "server": "Server",
        "tool": "Werkzeug",
        "hosts_unknown": "Freizugebende Hosts",
        "hosts_known": "Bereits erlaubt",
        "purpose": "Zweck",
        "turn_data": "Daten des Durchgangs",
        "turn_data_none": "keine",
        "turn_data_too_large": "zu umfangreich zum Mitgeben",
        "third_party_skill_note": "Dieser Skill wurde anderswo geschrieben. Sende die Daten des Durchgangs nur mit, wenn du ihm vertraust.",
        "stdout": "Ergebnis",
        "traceback": "Fehler",
        "details": "Details",
        "context": "Vorgaben",
        "video_conference": "Videokonferenz",
        "video_conference_included": "Inbegriffen",
        "vacation_disabled": "Die Abwesenheitsnotiz wird deaktiviert",
        "sheet": "Tabellenblatt",
        "range": "Bereich",
        "text": "Text",
        "query": "Abfrage",
        "filter_archive": "Passende Nachrichten werden archiviert",
        "filter_mark_read": "Passende Nachrichten werden als gelesen markiert",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": ": ",
    },
    "it": {
        "to": "Destinatario",
        "cc": "Cc",
        "bcc": "Ccn",
        "subject": "Oggetto",
        "no_subject": "(senza oggetto)",
        "steps": "Passaggi",
        "body": "Messaggio",
        "from": "Da",
        "date": "Data",
        "attachments": "Allegati",
        "event": "Evento",
        "start": "Inizio",
        "end": "Fine",
        "location": "Luogo",
        "attendees": "Partecipanti",
        "contact": "Contatto",
        "email": "Email",
        "phone": "Telefono",
        "organization": "Organizzazione",
        "task": "Attività",
        "due": "Scadenza",
        "file": "File",
        "changes": "Modifiche",
        "type": "Tipo",
        "label": "Etichetta",
        "label_parent": "Etichetta padre",
        "sublabels_to_delete": "Sottoetichette da eliminare",
        "sublabels_included": "Sottoetichette incluse",
        "recipient": "Destinatario",
        "message": "Messaggio",
        "callee": "Interlocutore",
        "objective": "Obiettivo",
        "title": "Titolo",
        "schedule": "Pianificazione",
        "instruction": "Istruzione",
        "server": "Server",
        "tool": "Strumento",
        "hosts_unknown": "Host da autorizzare",
        "hosts_known": "Già consentiti",
        "purpose": "Motivo",
        "turn_data": "Dati del turno",
        "turn_data_none": "nessuno",
        "turn_data_too_large": "troppo voluminosi per essere trasmessi",
        "third_party_skill_note": "Questa skill è stata scritta altrove. Invia i dati del turno solo se ti fidi.",
        "stdout": "Risultato",
        "traceback": "Errore",
        "details": "Dettagli",
        "context": "Istruzioni",
        "video_conference": "Videoconferenza",
        "video_conference_included": "Inclusa",
        "vacation_disabled": "La risposta automatica verrà disattivata",
        "sheet": "Foglio",
        "range": "Intervallo",
        "text": "Testo",
        "query": "Query",
        "filter_archive": "I messaggi corrispondenti verranno archiviati",
        "filter_mark_read": "I messaggi corrispondenti verranno segnati come letti",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": ": ",
    },
    "zh-CN": {
        "to": "收件人",
        "cc": "抄送",
        "bcc": "密送",
        "subject": "主题",
        "no_subject": "（无主题）",
        "steps": "步骤",
        "body": "内容",
        "from": "发件人",
        "date": "日期",
        "attachments": "附件",
        "event": "事件",
        "start": "开始",
        "end": "结束",
        "location": "地点",
        "attendees": "参与者",
        "contact": "联系人",
        "email": "邮箱",
        "phone": "电话",
        "organization": "组织",
        "task": "任务",
        "due": "截止日期",
        "file": "文件",
        "changes": "更改",
        "type": "类型",
        "label": "标签",
        "label_parent": "父标签",
        "sublabels_to_delete": "要删除的子标签",
        "sublabels_included": "包含的子标签",
        "recipient": "收件人",
        "message": "消息",
        "callee": "通话对象",
        "objective": "目标",
        "title": "标题",
        "schedule": "计划",
        "instruction": "指令",
        "server": "服务器",
        "tool": "工具",
        "hosts_unknown": "待授权的主机",
        "hosts_known": "已允许",
        "purpose": "目的",
        "turn_data": "本轮数据",
        "turn_data_none": "无",
        "turn_data_too_large": "数据过大，无法传递",
        "third_party_skill_note": "此技能由他人编写。只有在信任它时才发送本轮数据。",
        "stdout": "结果",
        "traceback": "错误",
        "details": "详情",
        "context": "附加说明",
        "video_conference": "视频会议",
        "video_conference_included": "包含",
        "vacation_disabled": "自动回复将被关闭",
        "sheet": "工作表",
        "range": "范围",
        "text": "文本",
        "query": "查询",
        "filter_archive": "匹配的邮件将被归档",
        "filter_mark_read": "匹配的邮件将被标记为已读",
        # Not a label: what a preview row puts between one and its value.
        # A literal ": " in the renderer would publish English punctuation
        # in six languages.
        "separator": "：",
    },
}


# ============================================================================
# HITL ITEM PREVIEW — recipient connector
# ============================================================================
# Localized preposition inserted between the noun and the recipient in a batch
# item preview for send-type drafts (email / reply / forward), producing
# "Email à {to}" / "Email to {to}" / "E-Mail an {to}" ... Consumed by
# format_hitl_item_preview when the draft's DraftDisplayConfig declares an
# item_recipient_field. Kept as a bare connector (not a full per-type template)
# so the generic "{emoji} {Noun} {connector} {recipient} : {label}" composition
# stays draft-type-agnostic.

DRAFT_RECIPIENT_CONNECTOR: dict[Language, str] = {
    "fr": "à",
    "en": "to",
    "es": "a",
    "de": "an",
    "it": "a",
    "zh-CN": "给",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


#: How long a row's recipients may grow before the next ones are counted rather
#: than shown — the first is shown whole, whatever its length.
_RECIPIENT_PREVIEW_MAX_CHARS = 60
#: What separates two recipients on a row.
_RECIPIENT_JOINER = ", "


for _language, _application_copy in APPLICATION_DRAFT_COPY.items():
    DRAFT_SUCCESS_MESSAGES[_language]["application_action"] = _application_copy.success
    DRAFT_CANCEL_MESSAGES[_language]["application_action"] = _application_copy.cancelled
    DRAFT_SUMMARY_LABELS[_language]["application_action"] = _application_copy.summary
    DRAFT_PREVIEW_LABELS[_language].update(
        application_before=_application_copy.before,
        application_after=_application_copy.after,
        application_unavailable=APPLICATION_UNAVAILABLE[_language],
        application_expiry=APPLICATION_EXPIRY_LABELS[_language],
        application_location_clear=APPLICATION_LOCATION_CLEAR[_language],
        application_channel_unlink=APPLICATION_CHANNEL_UNLINK[_language],
        application_connector_unlink=APPLICATION_CONNECTOR_UNLINK[_language],
        application_notification_device_remove=APPLICATION_NOTIFICATION_DEVICE_REMOVE[_language],
        application_live_preferences=APPLICATION_LIVE_PREFERENCES[_language],
        application_live_connector=APPLICATION_LIVE_CONNECTOR[_language],
        application_phone_preferences=APPLICATION_PHONE_PREFERENCES[_language],
        application_phone_number=APPLICATION_PHONE_NUMBER[_language],
        application_session_revoke=APPLICATION_SESSION_REVOKE[_language],
        application_session_closed=APPLICATION_SESSION_CLOSED[_language],
        application_other_sessions_note=APPLICATION_OTHER_SESSIONS[_language].note,
        application_other_sessions_count=APPLICATION_OTHER_SESSIONS[_language].count_label,
        application_current_session_kept=APPLICATION_OTHER_SESSIONS[_language].current,
        application_export_note=APPLICATION_EXPORT_REQUEST[_language].note,
        application_management_export_note=MANAGEMENT_EXPORT_COPY[_language].note,
        application_interests_export_title=MANAGEMENT_EXPORT_COPY[_language].interests,
        application_journal_feedback_note=JOURNAL_FEEDBACK_COPY[_language][1],
        application_sms_note=SMS_APPROVAL_NOTE[_language],
        application_health_token_note=HEALTH_TOKEN_COPY[_language][1],
        application_health_token_creation_note=HEALTH_TOKEN_CREATION_COPY[_language][1],
        application_field_health_token_to_create=HEALTH_TOKEN_CREATION_COPY[_language][0],
        application_field_health_token_to_revoke=HEALTH_TOKEN_COPY[_language][0],
        application_health_removal_note=HEALTH_REMOVAL_COPY[_language][1],
        application_field_health_samples_to_delete=HEALTH_REMOVAL_COPY[_language][0],
        application_psyche_summary_note=PSYCHE_SUMMARY_COPY[_language][1],
        application_field_psyche_summary=PSYCHE_SUMMARY_COPY[_language][0],
        application_field_journal_feedback=JOURNAL_FEEDBACK_COPY[_language][0],
        application_journal_consolidation_note=JOURNAL_CONSOLIDATION_COPY[_language][1],
        application_field_journal_consolidation=JOURNAL_CONSOLIDATION_COPY[_language][0],
        application_journal_export_note=JOURNAL_EXPORT_COPY[_language].note,
        application_journals_export_title=JOURNAL_EXPORT_COPY[_language].title,
        application_memory_export_note=MEMORY_EXPORT_COPY[_language].note,
        application_memories_export_title=MEMORY_EXPORT_COPY[_language].title,
        application_export_download_note=APPLICATION_EXPORT_DOWNLOAD[_language].note,
        application_export_download_title=APPLICATION_EXPORT_DOWNLOAD[_language].title,
        application_export_title=APPLICATION_EXPORT_REQUEST[_language].title,
        application_routine_note=APPLICATION_ROUTINE_STATE[_language].note,
        application_routine_title=APPLICATION_ROUTINE_STATE[_language].title,
        application_routine_enabled=APPLICATION_ROUTINE_STATE[_language].enabled,
        application_routine_disabled=APPLICATION_ROUTINE_STATE[_language].disabled,
        application_routine_creation_note=APPLICATION_ROUTINE_CREATION[_language].note,
        application_routine_creation_title=APPLICATION_ROUTINE_CREATION[_language].title,
        application_reminder_creation_note=APPLICATION_REMINDER_CREATION[_language].note,
        application_reminder_creation_title=APPLICATION_REMINDER_CREATION[_language].title,
        application_reminder_removal_note=APPLICATION_REMINDER_REMOVAL[_language],
        application_reminder_update_note=APPLICATION_REMINDER_UPDATE[_language],
        application_memory_pin_note=APPLICATION_MEMORY_PIN[_language].note,
        application_memory_bulk_note=APPLICATION_MEMORY_BULK[_language].note,
        application_field_memories_to_delete=APPLICATION_MEMORY_BULK[_language].title,
        application_memory_removal_note=APPLICATION_MEMORY_REMOVAL[_language],
        application_field_memory_to_delete=APPLICATION_MEMORY_CREATION[_language].title,
        application_memory_update_note=APPLICATION_MEMORY_UPDATE[_language],
        application_field_memory_configuration=APPLICATION_MEMORY_CREATION[_language].title,
        application_memory_creation_note=APPLICATION_MEMORY_CREATION[_language].note,
        application_interest_creation_note=APPLICATION_INTEREST_CREATION[_language].note,
        application_interest_bulk_note=APPLICATION_INTEREST_BULK[_language].note,
        application_interest_feedback_note=APPLICATION_INTEREST_FEEDBACK[_language].note,
        application_open_loop_note=OPEN_LOOP_COPY[_language][1],
        application_field_habits_enabled=HABIT_SETTINGS_COPY[_language][0],
        application_habit_settings_note=HABIT_SETTINGS_COPY[_language][1],
        application_psyche_settings_note=PSYCHE_SETTINGS_COPY[_language][4],
        application_relation_settings_note=RELATION_SETTINGS_COPY[_language][2],
        application_relation_favorite_note=RELATION_FAVORITE_COPY[_language][1],
        application_relation_grouping_note=RELATION_GROUPING_COPY[_language][1],
        application_relation_debrief_build_note=RELATION_DEBRIEF_BUILD_COPY[_language][1],
        application_peer_preferences_note=PEER_PREFERENCES_COPY[_language][2],
        application_peer_request_note=PEER_REQUEST_COPY[_language][1],
        application_peer_response_note=PEER_RESPONSE_COPY[_language][1],
        application_field_peer_response=PEER_RESPONSE_COPY[_language][0],
        application_peer_share_note=PEER_SHARE_COPY[_language][1],
        application_field_peer_share=PEER_SHARE_COPY[_language][0],
        application_peer_removal_note=PEER_REMOVAL_COPY[_language][1],
        application_field_peer_removal=PEER_REMOVAL_COPY[_language][0],
        application_peer_block_note=PEER_BLOCK_COPY[_language][1],
        application_peer_image_note=PEER_IMAGE_COPY[_language][1],
        application_workboard_create_note=WORKBOARD_CREATE_COPY[_language][1],
        application_space_create_note=SPACE_CREATE_COPY[_language][1],
        application_field_space_create=SPACE_CREATE_COPY[_language][0],
        application_document_download_note=DOCUMENT_DOWNLOAD_COPY[_language][1],
        application_asset_download_note=ASSET_DOWNLOAD_COPY[_language][1],
        application_field_asset_to_download=ASSET_DOWNLOAD_COPY[_language][0],
        application_document_upload_note=DOCUMENT_UPLOAD_COPY[_language][1],
        application_source_unlink_note=SOURCE_UNLINK_COPY[_language][1],
        application_field_source_to_unlink=SOURCE_UNLINK_COPY[_language][0],
        application_source_link_note=SOURCE_LINK_COPY[_language][1],
        application_field_source_to_link=SOURCE_LINK_COPY[_language][0],
        application_source_sync_note=SOURCE_SYNC_COPY[_language][1],
        application_field_source_to_sync=SOURCE_SYNC_COPY[_language][0],
        application_source_delete_note=SOURCE_DELETE_COPY[_language][1],
        application_field_source_to_delete=SOURCE_DELETE_COPY[_language][0],
        application_asset_retention_note=ASSET_RETENTION_COPY[_language][1],
        application_field_asset_retention=ASSET_RETENTION_COPY[_language][0],
        application_asset_delete_note=ASSET_DELETE_COPY[_language][1],
        application_bookmark_keep_note=BOOKMARK_KEEP_COPY[_language][1],
        application_field_skill_personal_state=SKILL_PERSONAL_COPY[_language][0],
        application_field_personal_mcp_state=PERSONAL_MCP_STATE_COPY[_language][0],
        application_personal_mcp_state_note=PERSONAL_MCP_STATE_COPY[_language][1],
        application_field_personal_mcp_configuration=PERSONAL_MCP_CONFIGURATION_COPY[_language][0],
        application_personal_mcp_configuration_note=PERSONAL_MCP_CONFIGURATION_COPY[_language][1],
        application_field_personal_mcp_oauth=PERSONAL_MCP_OAUTH_COPY[_language][0],
        application_personal_mcp_oauth_note=PERSONAL_MCP_OAUTH_COPY[_language][1],
        application_field_meeting_delete=MEETING_DELETION_COPY[_language][0],
        application_field_device_recording=RECORDING_DEVICE_COPY[_language][0],
        application_recording_device_note=RECORDING_DEVICE_COPY[_language][1],
        application_meeting_deletion_note=MEETING_DELETION_COPY[_language][1],
        application_field_meeting_reformat=MEETING_REFORMAT_COPY[_language][0],
        application_meeting_reformat_note=MEETING_REFORMAT_COPY[_language][1],
        application_field_meeting_regeneration=MEETING_REGENERATION_COPY[_language][0],
        application_meeting_regeneration_note=MEETING_REGENERATION_COPY[_language][1],
        application_field_meeting_retry=MEETING_RETRY_COPY[_language][0],
        application_meeting_retry_note=MEETING_RETRY_COPY[_language][1],
        application_field_meeting_email_send=MEETING_EMAIL_COPY[_language][0],
        application_meeting_email_note=MEETING_EMAIL_COPY[_language][1],
        application_field_meeting_pdf_download=MEETING_PDF_COPY[_language][0],
        application_meeting_pdf_note=MEETING_PDF_COPY[_language][1],
        application_field_meeting_report_update=MEETING_REPORT_UPDATE_COPY[_language][0],
        application_meeting_report_update_note=MEETING_REPORT_UPDATE_COPY[_language][1],
        application_field_meeting_report_restore=MEETING_REPORT_RESTORE_COPY[_language][0],
        application_meeting_report_restore_note=MEETING_REPORT_RESTORE_COPY[_language][1],
        application_field_meeting_transcript_delete=MEETING_TRANSCRIPT_COPY[_language][0],
        application_meeting_transcript_delete_note=MEETING_TRANSCRIPT_COPY[_language][1],
        application_field_meeting_preferences=MEETING_PREFERENCE_COPY[_language][0],
        application_meeting_preferences_note=MEETING_PREFERENCE_COPY[_language][1],
        application_field_meeting_template_create=MEETING_TEMPLATE_ACTION_COPY[_language][0],
        application_field_meeting_template_update=MEETING_TEMPLATE_ACTION_COPY[_language][1],
        application_field_meeting_template_delete=MEETING_TEMPLATE_ACTION_COPY[_language][2],
        application_meeting_template_create_note=MEETING_TEMPLATE_ACTION_COPY[_language][3],
        application_meeting_template_update_note=MEETING_TEMPLATE_ACTION_COPY[_language][3],
        application_meeting_template_delete_note=MEETING_TEMPLATE_ACTION_COPY[_language][3],
        application_field_personal_mcp_settings=PERSONAL_MCP_SETTINGS_COPY[_language][0],
        application_personal_mcp_settings_note=PERSONAL_MCP_SETTINGS_COPY[_language][1],
        application_field_personal_mcp_server_delete=PERSONAL_MCP_DELETE_COPY[_language][0],
        application_personal_mcp_delete_note=PERSONAL_MCP_DELETE_COPY[_language][1],
        application_field_personal_mcp_description=PERSONAL_MCP_DESCRIPTION_COPY[_language][0],
        application_personal_mcp_description_note=PERSONAL_MCP_DESCRIPTION_COPY[_language][1],
        application_field_personal_mcp_connection=PERSONAL_MCP_CONNECTION_COPY[_language][0],
        application_personal_mcp_connection_note=PERSONAL_MCP_CONNECTION_COPY[_language][1],
        application_field_personal_mcp_oauth_disconnect=PERSONAL_MCP_OAUTH_DISCONNECT_COPY[
            _language
        ][0],
        application_personal_mcp_oauth_disconnect_note=PERSONAL_MCP_OAUTH_DISCONNECT_COPY[
            _language
        ][1],
        application_skill_update_note=SKILL_PERSONAL_COPY[_language][1],
        application_field_skill_to_delete=SKILL_DELETE_COPY[_language][0],
        application_skill_delete_note=SKILL_DELETE_COPY[_language][1],
        application_field_plugin_to_delete=PLUGIN_DELETE_COPY[_language][0],
        application_plugin_delete_note=PLUGIN_DELETE_COPY[_language][1],
        application_field_plugin_url_import=PLUGIN_IMPORT_COPY[_language][0],
        application_plugin_url_import_note=PLUGIN_IMPORT_COPY[_language][1],
        application_field_plugin_file_upload=PLUGIN_FILE_IMPORT_COPY[_language][0],
        application_plugin_file_upload_note=PLUGIN_FILE_IMPORT_COPY[_language][1],
        application_field_skill_file_upload=SKILL_FILE_UPLOAD_COPY[_language][0],
        application_skill_file_upload_note=SKILL_FILE_UPLOAD_COPY[_language][1],
        application_field_skill_url_import=SKILL_URL_IMPORT_COPY[_language][0],
        application_skill_url_import_note=SKILL_URL_IMPORT_COPY[_language][1],
        application_field_skill_library_import=SKILL_LIBRARY_IMPORT_COPY[_language][0],
        application_skill_library_import_note=SKILL_LIBRARY_IMPORT_COPY[_language][1],
        application_field_skill_to_download=SKILL_DOWNLOAD_COPY[_language][0],
        application_skill_download_note=SKILL_DOWNLOAD_COPY[_language][1],
        application_bookmark_download_note=BOOKMARK_DOWNLOAD_COPY[_language][1],
        application_field_saved_answer_to_download=BOOKMARK_DOWNLOAD_COPY[_language][0],
        application_email_share_send_note=EMAIL_SHARE_SEND_COPY[_language][1],
        application_field_email_to_send=EMAIL_SHARE_SEND_COPY[_language][0],
        application_field_saved_answer_to_keep=BOOKMARK_KEEP_COPY[_language][0],
        application_bookmark_delete_note=BOOKMARK_DELETE_COPY[_language][1],
        application_field_saved_answer_to_delete=BOOKMARK_DELETE_COPY[_language][0],
        application_field_assets_to_delete=ASSET_DELETE_COPY[_language][0],
        application_field_document_to_upload=DOCUMENT_UPLOAD_COPY[_language][0],
        application_field_document_to_download=DOCUMENT_DOWNLOAD_COPY[_language][0],
        application_document_archive_note=DOCUMENT_ARCHIVE_COPY[_language][1],
        application_field_archive_to_download=DOCUMENT_ARCHIVE_COPY[_language][0],
        application_document_delete_note=DOCUMENT_DELETE_COPY[_language][1],
        application_field_documents_to_delete=DOCUMENT_DELETE_COPY[_language][0],
        application_document_move_note=DOCUMENT_MOVE_COPY[_language][1],
        application_field_documents_to_move=DOCUMENT_MOVE_COPY[_language][0],
        application_space_delete_note=SPACE_DELETE_COPY[_language][1],
        application_field_space_delete=SPACE_DELETE_COPY[_language][0],
        application_space_update_note=SPACE_UPDATE_COPY[_language][1],
        application_field_space_update=SPACE_UPDATE_COPY[_language][0],
        application_workboard_comment_note=WORKBOARD_COMMENT_COPY[_language][1],
        application_field_workboard_comment=WORKBOARD_COMMENT_COPY[_language][0],
        application_workboard_delete_note=WORKBOARD_DELETE_COPY[_language][1],
        application_field_workboard_delete=WORKBOARD_DELETE_COPY[_language][0],
        application_workboard_update_note=WORKBOARD_UPDATE_COPY[_language][1],
        application_field_workboard_update=WORKBOARD_UPDATE_COPY[_language][0],
        application_field_workboard_create=WORKBOARD_CREATE_COPY[_language][0],
        application_field_peer_image=PEER_IMAGE_COPY[_language][0],
        application_field_peer_block=PEER_BLOCK_COPY[_language][0],
        application_field_peer_request=PEER_REQUEST_COPY[_language][0],
        application_field_discovery_enabled=PEER_PREFERENCES_COPY[_language][0],
        application_field_email_visible=PEER_PREFERENCES_COPY[_language][1],
        application_relation_context_refresh_note=RELATION_CONTEXT_REFRESH_COPY[_language][1],
        application_field_relation_context=RELATION_CONTEXT_REFRESH_COPY[_language][0],
        application_field_relation_debrief=RELATION_DEBRIEF_BUILD_COPY[_language][0],
        application_field_relation_grouping=RELATION_GROUPING_COPY[_language][0],
        application_field_relation_favorite=RELATION_FAVORITE_COPY[_language][0],
        application_field_relation_debrief_enabled=RELATION_SETTINGS_COPY[_language][0],
        application_field_relation_overview_scope=RELATION_SETTINGS_COPY[_language][1],
        application_journal_settings_note=JOURNAL_SETTINGS_COPY[_language][7],
        application_field_journal_entries_to_delete=JOURNAL_REMOVAL_COPY[_language][0],
        application_journal_removal_note=JOURNAL_REMOVAL_COPY[_language][1],
        application_field_journal_entry_to_create=JOURNAL_CREATION_COPY[_language][0],
        application_journal_creation_note=JOURNAL_CREATION_COPY[_language][1],
        application_field_journal_entry=JOURNAL_UPDATE_COPY[_language][0],
        application_journal_update_note=JOURNAL_UPDATE_COPY[_language][1],
        **{
            f"application_field_{field}": JOURNAL_SETTINGS_COPY[_language][index]
            for index, field in enumerate(
                (
                    "journals_enabled",
                    "journal_consolidation_enabled",
                    "journal_consolidation_with_history",
                    "journal_max_total_chars",
                    "journal_context_max_chars",
                    "journal_max_entry_chars",
                    "journal_context_max_results",
                )
            )
        },
        application_psyche_reset_note=PSYCHE_RESET_COPY[_language][1],
        application_field_psyche_reset=PSYCHE_RESET_COPY[_language][0],
        application_field_psyche_enabled=PSYCHE_SETTINGS_COPY[_language][0],
        application_field_psyche_display_avatar=PSYCHE_SETTINGS_COPY[_language][1],
        application_field_psyche_sensitivity=PSYCHE_SETTINGS_COPY[_language][2],
        application_field_psyche_stability=PSYCHE_SETTINGS_COPY[_language][3],
        application_field_habit=HABIT_ACTION_COPY[_language][0],
        application_habit_status_note=HABIT_ACTION_COPY[_language][1],
        application_habit_delete_note=HABIT_ACTION_COPY[_language][2],
        application_field_habit_data=HABIT_FORGET_COPY[_language][0],
        application_habit_forget_note=HABIT_FORGET_COPY[_language][1],
        application_habit_count=HABIT_FORGET_COUNTS[_language][0],
        application_habit_profile_count=HABIT_FORGET_COUNTS[_language][1],
        application_habit_activity_count=HABIT_FORGET_COUNTS[_language][2],
        application_field_habit_recompute=HABIT_RECOMPUTE_COPY[_language][0],
        application_habit_recompute_note=HABIT_RECOMPUTE_COPY[_language][1],
        application_field_open_loop=OPEN_LOOP_COPY[_language][0],
        application_interest_reactivation_note=APPLICATION_INTEREST_REACTIVATION[_language].note,
        application_field_interest_to_reactivate=APPLICATION_INTEREST_REACTIVATION[_language].title,
        application_field_interest_feedback=APPLICATION_INTEREST_FEEDBACK[_language].title,
        application_field_interests_to_delete=APPLICATION_INTEREST_BULK[_language].title,
        application_interest_removal_note=APPLICATION_INTEREST_REMOVAL[_language].note,
        application_field_interest_to_delete=APPLICATION_INTEREST_REMOVAL[_language].title,
        application_interest_update_note=APPLICATION_INTEREST_UPDATE[_language].note,
        application_field_interest_configuration=APPLICATION_INTEREST_UPDATE[_language].title,
        application_field_interest_to_create=APPLICATION_INTEREST_CREATION[_language].title,
        application_field_memory_to_create=APPLICATION_MEMORY_CREATION[_language].title,
        application_field_memory_pin=APPLICATION_MEMORY_PIN[_language].title,
        application_memory_pinned=APPLICATION_MEMORY_PIN[_language].pinned,
        application_memory_unpinned=APPLICATION_MEMORY_PIN[_language].unpinned,
        application_field_reminder_to_delete=APPLICATION_REMINDER_CREATION[_language].title,
        application_routine_removal_note=APPLICATION_ROUTINE_REMOVAL[_language],
        application_routine_update_note=APPLICATION_ROUTINE_UPDATE[_language],
        application_routine_run_note=APPLICATION_ROUTINE_RUN[_language].note,
        application_field_routine_to_delete=APPLICATION_ROUTINE_STATE[_language].title,
    )
    DRAFT_PREVIEW_LABELS[_language].update(
        {
            f"application_number_{key}": value
            for key, value in APPLICATION_NUMBER_STATUS[_language].items()
        }
    )
    DRAFT_PREVIEW_LABELS[_language].update(
        {
            f"application_field_{key}": value
            for key, value in APPLICATION_FIELD_LABELS[_language].items()
        }
    )


def _stringify_recipient(value: object) -> str:
    """Draw an email recipient field on one preview row, every recipient whole.

    A draft ``to`` field is either one string — which may name several
    addresses — or a list of them. Each is drawn on one line (``one_line``: a
    display name keeps its no-break spaces) and spelled where it would mislead
    (``spell_unseen``). A recipient is NEVER cut: a display name the sender
    chose pushed the address it names out of the row — « support@your-bank
    .example Customer Service Team… » for a reply going to
    ``attacker@evil.example`` (review 14). A list shows its recipients in order
    while they fit :data:`_RECIPIENT_PREVIEW_MAX_CHARS` — the first always,
    whatever its length — and counts the others (« … (+3) »).

    Args:
        value: Raw recipient value from the draft content (str, list, or None).

    Returns:
        The recipients as a person reads them, or ``""`` when the value is empty.
    """
    if not value:
        return ""
    raw = value if isinstance(value, (list, tuple)) else [value]
    recipients = [drawn for v in raw if v and (drawn := spell_unseen(one_line(str(v))))]
    shown: list[str] = []
    length = 0
    for recipient in recipients:
        added = len(recipient) + (len(_RECIPIENT_JOINER) if shown else 0)
        if shown and length + added > _RECIPIENT_PREVIEW_MAX_CHARS:
            break
        shown.append(recipient)
        length += added
    left_out = len(recipients) - len(shown)
    drawn = _RECIPIENT_JOINER.join(shown)
    return f"{drawn}{_RECIPIENT_JOINER}{ELLIPSIS} (+{left_out})" if left_out else drawn


#: A placeholder of a message template, and one written between quotes.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_QUOTED_PLACEHOLDER = re.compile(r"\s*'\{(\w+)\}'")


def get_draft_success_message(
    draft_type: str,
    language: str | None = None,
    **kwargs: str,
) -> str:
    """
    Get localized success message for a draft type.

    The template is Markdown (``phone_call`` emphasises its name); each value
    is put in ONCE, as the caller drew it — never read as a template, never
    touched by the removal of a placeholder nobody filled (a summary
    holding « '{title}' » lost it, and « {summary} » in a name was filled).

    Args:
        draft_type: Draft type (e.g., "email", "event", "contact")
        language: Target language code (default: the declared language)
        **kwargs: Placeholder values (name, summary, title), drawn by the
            caller for the Markdown they land in; an empty one removes its
            placeholder, the quotes around it included.

    Returns:
        Localized success message with placeholders replaced

    Example:
        >>> get_draft_success_message("event", "fr", summary="Meeting")
        "'Meeting' créé avec succès"
        >>> get_draft_success_message("email", "en")
        "Sent successfully"
    """
    lang = resolve_language(language)
    messages = DRAFT_SUCCESS_MESSAGES[lang]
    template = messages.get(draft_type, messages["_default"])

    values = {key: value for key, value in kwargs.items() if value}
    # A placeholder nobody filled goes, with its quotes: « '{summary}' créé ».
    template = _QUOTED_PLACEHOLDER.sub(
        lambda match: match.group(0) if match.group(1) in values else "", template
    )
    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1), ""), template).strip()


def get_draft_cancel_message(
    draft_type: str,
    language: str | None = None,
) -> str:
    """
    Get localized cancellation message for a draft type.

    Args:
        draft_type: Draft type (e.g., "email", "event", "contact")
        language: Target language code (default: the declared language)

    Returns:
        Localized cancellation message

    Example:
        >>> get_draft_cancel_message("email", "fr")
        "Envoi d'email annulé"
        >>> get_draft_cancel_message("event", "en")
        "Event creation cancelled"
    """
    lang = resolve_language(language)
    messages = DRAFT_CANCEL_MESSAGES[lang]
    return messages.get(draft_type, messages["_default"])


def get_draft_error_message(
    language: str | None = None,
) -> str:
    """
    Get localized error message for draft execution failures.

    Args:
        language: Target language code (default: the declared language)

    Returns:
        Localized error message

    Example:
        >>> get_draft_error_message("en")
        "Error during execution"
    """
    lang = resolve_language(language)
    return DRAFT_ERROR_MESSAGES[lang]


def get_draft_already_claimed_message(language: str | None = None) -> str:
    """The localized sentence for a draft that was not repeated (ADR-263).

    Args:
        language: Target language code; the declared language when absent.

    Returns:
        The localized message.
    """
    lang = resolve_language(language)
    return DRAFT_ALREADY_CLAIMED_MESSAGES[lang]


def get_draft_summary_label(
    label_key: str,
    language: str | None = None,
    **kwargs: str,
) -> str:
    """
    Get localized summary label for draft display.

    Args:
        label_key: Label key (e.g., "email_to", "event_create", "draft_created")
        language: Target language code (default: the declared language)
        **kwargs: Placeholder values (to, subject, summary, name, title, start)

    Returns:
        Localized summary label with placeholders replaced

    Example:
        >>> get_draft_summary_label("email_to", "fr", to="john@example.com")
        "Email à john@example.com"
        >>> get_draft_summary_label("draft_created", "zh-CN", title="邮件草稿")
        "📄 **草稿已创建**：邮件草稿"
    """
    lang = resolve_language(language)
    labels = DRAFT_SUMMARY_LABELS[lang]
    template = labels.get(label_key, label_key)

    # Replace placeholders with provided values
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value or "?")

    return template


def get_draft_preview_labels(
    language: str | None = None,
) -> dict[str, str]:
    """
    Get all preview field labels for a language.

    Args:
        language: Target language code (default: the declared language)

    Returns:
        Dict of field labels (to, cc, subject, body, etc.)

    Example:
        >>> labels = get_draft_preview_labels("zh-CN")
        >>> labels["to"]
        "收件人"
        >>> labels["subject"]
        "主题"
    """
    lang = resolve_language(language)
    return DRAFT_PREVIEW_LABELS[lang]


def label_separator(language: str | None = None) -> str:
    """What goes between a label and its value, in ``language``.

    ONE punctuation per language for every surface a person reads — a card, a
    draft, a dialog, an e-mail, the minutes: a French colon takes a no-break
    space before it, a Chinese one is full-width. Written in the code, a
    ``": "`` published English punctuation in six languages and a ``" : "``
    French punctuation (guard: ``test_label_separator_guard.py``).

    Args:
        language: The reader's language (default: the declared language).

    Returns:
        The separator, its trailing space included where the language has one.
    """
    return get_draft_preview_labels(language)["separator"]


# ============================================================================
# DRAFT RESULT HEADER COMPOSITION
# ============================================================================
# Tables and helpers for composing the localized result header displayed after
# a HITL confirmation, e.g. "3 rappels supprimés" / "2/3 emails envoyés".
#
# Design (ADR-085):
# - DRAFT_RESULT_NOUNS: per-language noun forms (singular/plural) + grammatical
#   gender for languages that need participle agreement (fr/es/it).
# - DRAFT_RESULT_VERBS_PAST: past-participle forms. ``str`` for invariant
#   languages (en/de/zh-CN); ``dict`` with 4 gender/number keys for languages
#   with agreement (fr/es/it). Keys: ``m_sing``, ``m_plur``, ``f_sing``,
#   ``f_plur``.
# - RESULT_HEADER_TEMPLATES: per-language word-order template (Chinese differs).
# - get_plural_form: per-language pluralization rule (French treats 0 as
#   singular; English/Spanish/German/Italian treat 0 as plural; Chinese is
#   invariant).
# - compose_result_header: assembles the localized header from a count and the
#   noun/verb keys declared in DRAFT_DISPLAY_REGISTRY.
#
# Invariant: noun_key and verb_past_key referenced by any
# DraftDisplayConfig MUST exist in DRAFT_RESULT_NOUNS / DRAFT_RESULT_VERBS_PAST
# for every supported language. Enforced by test_display_registry.py.

DRAFT_RESULT_NOUNS: dict[Language, dict[str, dict[str, str]]] = {
    "fr": {
        "peer_message": {"singular": "message", "plural": "messages", "gender": "m"},
        "reminder": {"singular": "rappel", "plural": "rappels", "gender": "m"},
        "ticket": {"singular": "ticket", "plural": "tickets", "gender": "m"},
        "email": {"singular": "email", "plural": "emails", "gender": "m"},
        "event": {"singular": "événement", "plural": "événements", "gender": "m"},
        "contact": {"singular": "contact", "plural": "contacts", "gender": "m"},
        "task": {"singular": "tâche", "plural": "tâches", "gender": "f"},
        "file": {"singular": "fichier", "plural": "fichiers", "gender": "m"},
        "label": {"singular": "label", "plural": "labels", "gender": "m"},
        "call": {"singular": "appel", "plural": "appels", "gender": "m"},
        "action": {"singular": "action", "plural": "actions", "gender": "f"},
        "script": {"singular": "script", "plural": "scripts", "gender": "m"},
        "automation": {"singular": "automatisation", "plural": "automatisations", "gender": "f"},
        "auto_reply": {
            "singular": "réponse automatique",
            "plural": "réponses automatiques",
            "gender": "f",
        },
        "spreadsheet": {
            "singular": "feuille de calcul",
            "plural": "feuilles de calcul",
            "gender": "f",
        },
        "document": {"singular": "document", "plural": "documents", "gender": "m"},
        "filter": {"singular": "filtre", "plural": "filtres", "gender": "m"},
    },
    "en": {
        "peer_message": {"singular": "message", "plural": "messages"},
        "reminder": {"singular": "reminder", "plural": "reminders"},
        "ticket": {"singular": "ticket", "plural": "tickets"},
        "email": {"singular": "email", "plural": "emails"},
        "event": {"singular": "event", "plural": "events"},
        "contact": {"singular": "contact", "plural": "contacts"},
        "task": {"singular": "task", "plural": "tasks"},
        "file": {"singular": "file", "plural": "files"},
        "label": {"singular": "label", "plural": "labels"},
        "call": {"singular": "call", "plural": "calls"},
        "action": {"singular": "action", "plural": "actions"},
        "script": {"singular": "script", "plural": "scripts"},
        "automation": {"singular": "automation", "plural": "automations"},
        "auto_reply": {"singular": "auto-reply", "plural": "auto-replies"},
        "spreadsheet": {"singular": "spreadsheet", "plural": "spreadsheets"},
        "document": {"singular": "document", "plural": "documents"},
        "filter": {"singular": "filter", "plural": "filters"},
    },
    "es": {
        "peer_message": {"singular": "mensaje", "plural": "mensajes", "gender": "m"},
        "reminder": {
            "singular": "recordatorio",
            "plural": "recordatorios",
            "gender": "m",
        },
        "ticket": {"singular": "ticket", "plural": "tickets", "gender": "m"},
        "email": {"singular": "email", "plural": "emails", "gender": "m"},
        "event": {"singular": "evento", "plural": "eventos", "gender": "m"},
        "contact": {"singular": "contacto", "plural": "contactos", "gender": "m"},
        "task": {"singular": "tarea", "plural": "tareas", "gender": "f"},
        "file": {"singular": "archivo", "plural": "archivos", "gender": "m"},
        "label": {"singular": "etiqueta", "plural": "etiquetas", "gender": "f"},
        "call": {"singular": "llamada", "plural": "llamadas", "gender": "f"},
        "action": {"singular": "acción", "plural": "acciones", "gender": "f"},
        "script": {"singular": "script", "plural": "scripts", "gender": "m"},
        "automation": {"singular": "automatización", "plural": "automatizaciones", "gender": "f"},
        "auto_reply": {
            "singular": "respuesta automática",
            "plural": "respuestas automáticas",
            "gender": "f",
        },
        "spreadsheet": {
            "singular": "hoja de cálculo",
            "plural": "hojas de cálculo",
            "gender": "f",
        },
        "document": {"singular": "documento", "plural": "documentos", "gender": "m"},
        "filter": {"singular": "filtro", "plural": "filtros", "gender": "m"},
    },
    "de": {
        "peer_message": {"singular": "Nachricht", "plural": "Nachrichten"},
        "reminder": {"singular": "Erinnerung", "plural": "Erinnerungen"},
        "ticket": {"singular": "Ticket", "plural": "Tickets"},
        "email": {"singular": "E-Mail", "plural": "E-Mails"},
        "event": {"singular": "Termin", "plural": "Termine"},
        "contact": {"singular": "Kontakt", "plural": "Kontakte"},
        "task": {"singular": "Aufgabe", "plural": "Aufgaben"},
        "file": {"singular": "Datei", "plural": "Dateien"},
        "label": {"singular": "Label", "plural": "Labels"},
        "call": {"singular": "Anruf", "plural": "Anrufe"},
        "action": {"singular": "Aktion", "plural": "Aktionen"},
        "script": {"singular": "Skript", "plural": "Skripte"},
        "automation": {"singular": "Automatisierung", "plural": "Automatisierungen"},
        "auto_reply": {"singular": "Abwesenheitsnotiz", "plural": "Abwesenheitsnotizen"},
        "spreadsheet": {"singular": "Tabelle", "plural": "Tabellen"},
        "document": {"singular": "Dokument", "plural": "Dokumente"},
        "filter": {"singular": "Filter", "plural": "Filter"},
    },
    "it": {
        "peer_message": {"singular": "messaggio", "plural": "messaggi", "gender": "m"},
        # Italian: "promemoria", "email", "attività", "file" are invariant for number.
        "reminder": {"singular": "promemoria", "plural": "promemoria", "gender": "m"},
        "ticket": {"singular": "ticket", "plural": "ticket", "gender": "m"},
        "email": {"singular": "email", "plural": "email", "gender": "f"},
        "event": {"singular": "evento", "plural": "eventi", "gender": "m"},
        "contact": {"singular": "contatto", "plural": "contatti", "gender": "m"},
        "task": {"singular": "attività", "plural": "attività", "gender": "f"},
        "file": {"singular": "file", "plural": "file", "gender": "m"},
        "label": {"singular": "etichetta", "plural": "etichette", "gender": "f"},
        "call": {"singular": "chiamata", "plural": "chiamate", "gender": "f"},
        "action": {"singular": "azione", "plural": "azioni", "gender": "f"},
        "script": {"singular": "script", "plural": "script", "gender": "m"},
        "automation": {"singular": "automazione", "plural": "automazioni", "gender": "f"},
        "auto_reply": {
            "singular": "risposta automatica",
            "plural": "risposte automatiche",
            "gender": "f",
        },
        "spreadsheet": {
            "singular": "foglio di calcolo",
            "plural": "fogli di calcolo",
            "gender": "m",
        },
        "document": {"singular": "documento", "plural": "documenti", "gender": "m"},
        "filter": {"singular": "filtro", "plural": "filtri", "gender": "m"},
    },
    "zh-CN": {
        "peer_message": {"singular": "消息", "plural": "消息"},
        # Chinese has no grammatical number; both forms hold the same string.
        "reminder": {"singular": "提醒", "plural": "提醒"},
        "ticket": {"singular": "工单", "plural": "工单"},
        "email": {"singular": "邮件", "plural": "邮件"},
        "event": {"singular": "事件", "plural": "事件"},
        "contact": {"singular": "联系人", "plural": "联系人"},
        "task": {"singular": "任务", "plural": "任务"},
        "file": {"singular": "文件", "plural": "文件"},
        "label": {"singular": "标签", "plural": "标签"},
        "call": {"singular": "通话", "plural": "通话"},
        "action": {"singular": "操作", "plural": "操作"},
        "script": {"singular": "脚本", "plural": "脚本"},
        "automation": {"singular": "自动化任务", "plural": "自动化任务"},
        "auto_reply": {"singular": "自动回复", "plural": "自动回复"},
        "spreadsheet": {"singular": "电子表格", "plural": "电子表格"},
        "document": {"singular": "文档", "plural": "文档"},
        "filter": {"singular": "过滤器", "plural": "过滤器"},
    },
}

# Past-participle table. Two possible shapes per language:
# - dict[str, str]              for invariant languages (en/de/zh-CN)
# - dict[str, dict[str, str]]   for languages with gender+number agreement
#                                with keys: m_sing / m_plur / f_sing / f_plur
DRAFT_RESULT_VERBS_PAST: dict[Language, dict[str, str | dict[str, str]]] = {
    "fr": {
        "sent": {
            "m_sing": "envoyé",
            "m_plur": "envoyés",
            "f_sing": "envoyée",
            "f_plur": "envoyées",
        },
        "deleted": {
            "m_sing": "supprimé",
            "m_plur": "supprimés",
            "f_sing": "supprimée",
            "f_plur": "supprimées",
        },
        "created": {
            "m_sing": "créé",
            "m_plur": "créés",
            "f_sing": "créée",
            "f_plur": "créées",
        },
        "updated": {
            "m_sing": "modifié",
            "m_plur": "modifiés",
            "f_sing": "modifiée",
            "f_plur": "modifiées",
        },
        "placed": {
            "m_sing": "passé",
            "m_plur": "passés",
            "f_sing": "passée",
            "f_plur": "passées",
        },
        "scheduled": {
            "m_sing": "programmé",
            "m_plur": "programmés",
            "f_sing": "programmée",
            "f_plur": "programmées",
        },
        "executed": {
            "m_sing": "exécuté",
            "m_plur": "exécutés",
            "f_sing": "exécutée",
            "f_plur": "exécutées",
        },
    },
    "en": {
        "sent": "sent",
        "deleted": "deleted",
        "created": "created",
        "updated": "updated",
        "placed": "placed",
        "scheduled": "scheduled",
        "executed": "executed",
    },
    "es": {
        "sent": {
            "m_sing": "enviado",
            "m_plur": "enviados",
            "f_sing": "enviada",
            "f_plur": "enviadas",
        },
        "deleted": {
            "m_sing": "eliminado",
            "m_plur": "eliminados",
            "f_sing": "eliminada",
            "f_plur": "eliminadas",
        },
        "created": {
            "m_sing": "creado",
            "m_plur": "creados",
            "f_sing": "creada",
            "f_plur": "creadas",
        },
        "updated": {
            "m_sing": "actualizado",
            "m_plur": "actualizados",
            "f_sing": "actualizada",
            "f_plur": "actualizadas",
        },
        "placed": {
            "m_sing": "realizado",
            "m_plur": "realizados",
            "f_sing": "realizada",
            "f_plur": "realizadas",
        },
        "scheduled": {
            "m_sing": "programado",
            "m_plur": "programados",
            "f_sing": "programada",
            "f_plur": "programadas",
        },
        "executed": {
            "m_sing": "ejecutado",
            "m_plur": "ejecutados",
            "f_sing": "ejecutada",
            "f_plur": "ejecutadas",
        },
    },
    "de": {
        "sent": "gesendet",
        "deleted": "gelöscht",
        "created": "erstellt",
        "updated": "aktualisiert",
        "placed": "getätigt",
        "scheduled": "geplant",
        "executed": "ausgeführt",
    },
    "it": {
        "sent": {
            "m_sing": "inviato",
            "m_plur": "inviati",
            "f_sing": "inviata",
            "f_plur": "inviate",
        },
        "deleted": {
            "m_sing": "eliminato",
            "m_plur": "eliminati",
            "f_sing": "eliminata",
            "f_plur": "eliminate",
        },
        "created": {
            "m_sing": "creato",
            "m_plur": "creati",
            "f_sing": "creata",
            "f_plur": "create",
        },
        "updated": {
            "m_sing": "modificato",
            "m_plur": "modificati",
            "f_sing": "modificata",
            "f_plur": "modificate",
        },
        "placed": {
            "m_sing": "effettuato",
            "m_plur": "effettuati",
            "f_sing": "effettuata",
            "f_plur": "effettuate",
        },
        "scheduled": {
            "m_sing": "programmato",
            "m_plur": "programmati",
            "f_sing": "programmata",
            "f_plur": "programmate",
        },
        "executed": {
            "m_sing": "eseguito",
            "m_plur": "eseguiti",
            "f_sing": "eseguita",
            "f_plur": "eseguite",
        },
    },
    "zh-CN": {
        "sent": "已发送",
        "deleted": "已删除",
        "created": "已创建",
        "updated": "已更新",
        "placed": "已拨打",
        "scheduled": "已安排",
        "executed": "已执行",
    },
}

# Header word-order template per language.
# Placeholders: {count}, {noun}, {verb}.
#: How a language quotes a text it cites — the excerpt of a batch result row
#: (ADR-289), in the catalogs' typography (ADR-323): French guillemets with a
#: no-break space inside, Spanish and Italian ones with none; English and
#: Chinese curly double quotes; German its low-high pair.
EXCERPT_QUOTES: dict[Language, tuple[str, str]] = {
    "fr": ("« ", " »"),
    "en": ("“", "”"),
    "es": ("«", "»"),
    "de": ("„", "“"),
    "it": ("«", "»"),
    "zh-CN": ("“", "”"),
}

RESULT_HEADER_TEMPLATES: dict[Language, str] = {
    "fr": "{count} {noun} {verb}",
    "en": "{count} {noun} {verb}",
    "es": "{count} {noun} {verb}",
    "de": "{count} {noun} {verb}",
    "it": "{count} {noun} {verb}",
    "zh-CN": "{verb} {count} 个{noun}",
}

# Pluralization rules per language (CLDR-aligned for the languages we support).
# - French: 0 and 1 → singular (RFC 3066 fr-FR convention).
# - English/Spanish/German/Italian: 1 → singular, everything else (0, ≥2) → plural.
# - Chinese: no grammatical number, returns "singular" as a no-op label.
_PLURAL_RULES_SINGULAR_FOR_ZERO: frozenset[Language] = frozenset({"fr"})
_PLURAL_RULES_INVARIANT: frozenset[Language] = frozenset({"zh-CN"})


def get_plural_form(count: int, language: str | None = None) -> str:
    """Return the grammatical number for a count in a given language.

    Args:
        count: The cardinal number being modified.
        language: Language code (any normalized form accepted).

    Returns:
        Either ``"singular"`` or ``"plural"``. For Chinese (invariant
        number), always returns ``"singular"`` since both forms in
        :data:`DRAFT_RESULT_NOUNS` hold the same string.

    Example:
        >>> get_plural_form(0, "fr")
        'singular'
        >>> get_plural_form(0, "en")
        'plural'
        >>> get_plural_form(1, "en")
        'singular'
        >>> get_plural_form(3, "fr")
        'plural'
        >>> get_plural_form(3, "zh-CN")
        'singular'
    """
    lang = resolve_language(language)
    if lang in _PLURAL_RULES_INVARIANT:
        return "singular"
    if lang in _PLURAL_RULES_SINGULAR_FOR_ZERO:
        return "singular" if count <= 1 else "plural"
    return "singular" if count == 1 else "plural"


def format_hitl_item_preview(
    draft_type: str,
    content: dict[str, object],
    language: str | None = None,
    user_timezone: str | None = None,
) -> str | None:
    """Format a single HITL item preview consistently across all interactions.

    Unified rendering used by both ``DraftCritiqueInteraction`` (batch path)
    and ``ForEachConfirmationInteraction`` (item previews section). Reads
    everything from :data:`DRAFT_DISPLAY_REGISTRY` (ADR-085) so the result
    is grammatically correct and structurally consistent for every
    ``DraftType`` in every supported language.

    Output format::

        {emoji} {Noun}{separator}{label} - {datetime_with_day_name}

    The separator is the reader's (:func:`label_separator`: a no-break space
    before the French colon, a full-width colon in Chinese). The row is
    streamed as Markdown, so the label and the recipient — the draft's own
    data — are drawn as themselves (``markdown_data_literal``): a subject
    spelled as a link or an image drew one in the question.

    Examples (en):
        ``🔔 Reminder: Doctor - Sunday 17 May 2026 at 19:00``
        ``📧 Email: Appointment confirmed - Thursday 16 May 2026 at 14:00``
        ``📅 Event: Team meeting - Monday 20 May 2026 at 10:00``
        ``👤 Contact: Jane Doe``

    Args:
        draft_type: Draft type identifier (e.g. ``"reminder_delete"``,
            ``"email_delete"``). For paths that only know a base domain and
            a mutation verb, the caller is responsible for synthesizing the
            ``"{domain}_{mutation}"`` candidate first and falling back to
            the bare ``domain`` if the registry has no specific entry.
        content: Item dict carrying the fields declared in the registry's
            ``item_label_fields`` and ``item_secondary_datetime_key``.
            Nested keys are resolved via :func:`resolve_nested_value`.
        language: Target language (fr/en/es/de/it/zh-CN); the declared
            language when absent (``resolve_language``).
        user_timezone: User's IANA timezone for datetime formatting; falls
            back to :data:`src.core.constants.DEFAULT_USER_DISPLAY_TIMEZONE`.

    Returns:
        Localized preview string, or ``None`` if ``draft_type`` is not
        registered. ``None`` lets the caller fall back to a legacy/generic
        renderer (useful for FOR_EACH on non-draft domains like ``place``
        or ``weather``).
    """
    from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
    from src.core.time_utils import format_datetime_for_display
    from src.domains.agents.drafts.display import (
        get_draft_display_config,
        item_label,
        resolve_nested_value,
    )
    from src.domains.shared.markdown_literal import markdown_data_literal

    config = get_draft_display_config(draft_type)
    if config is None:
        return None

    lang = resolve_language(language)
    tz = user_timezone or DEFAULT_USER_DISPLAY_TIMEZONE

    # Localized capitalized noun (e.g. "rappel" → "Rappel"). Chinese has no
    # case but ``.capitalize()`` is a no-op on it, so this is safe.
    noun_entry = DRAFT_RESULT_NOUNS.get(lang, {}).get(config.noun_key)
    noun: str = noun_entry["singular"].capitalize() if noun_entry else ""

    # The registry's priority chain, read as the card's title reads it.
    label = markdown_data_literal(item_label(config, content))

    # Optional recipient (send-type drafts only): the WHO of the action — the
    # critical discriminating field when a batch sends to several people (two
    # rows would otherwise be identical). Rendered as "{Noun} {connector}
    # {recipient}" (e.g. "Email à marie@ex.com"). Falls back silently to the
    # plain noun when the field is unset or empty (delete/create/update types).
    noun_display: str = noun
    if config.item_recipient_field and noun:
        rcpt_value = (
            resolve_nested_value(content, config.item_recipient_field)
            if "." in config.item_recipient_field
            else content.get(config.item_recipient_field)
        )
        recipient = markdown_data_literal(_stringify_recipient(rcpt_value))
        if recipient:
            connector = DRAFT_RECIPIENT_CONNECTOR[lang]
            noun_display = f"{noun} {connector} {recipient}"

    # Extract and format the contextual datetime (with weekday name).
    dt_str: str = ""
    if config.item_secondary_datetime_key:
        dt_value = (
            resolve_nested_value(content, config.item_secondary_datetime_key)
            if "." in config.item_secondary_datetime_key
            else content.get(config.item_secondary_datetime_key)
        )
        if dt_value and isinstance(dt_value, str):
            try:
                dt_str = format_datetime_for_display(
                    dt_value,
                    user_timezone=tz,
                    locale=lang,
                    include_time=True,
                    include_day_name=True,
                )
            except ValueError, TypeError:
                dt_str = ""

    # Compose: "{emoji} {Noun[ connector recipient]}{separator}{label}" + optional
    # date — the separator is the reader's punctuation (ADR-323).
    head_parts: list[str] = [config.emoji]
    if noun_display and label:
        head_parts.append(f"{noun_display}{label_separator(lang)}{label}")
    elif noun_display:
        head_parts.append(noun_display)
    elif label:
        head_parts.append(label)
    head = " ".join(head_parts).strip()

    return f"{head} - {dt_str}" if dt_str else head


def compose_result_header(
    success_count: int,
    total_count: int,
    noun_key: str,
    verb_past_key: str,
    language: str | None = None,
) -> str:
    """Compose a localized batch result header with proper grammar.

    Produces strings like ``"3 rappels supprimés"`` (fr, m, plur),
    ``"1 tâche créée"`` (fr, f, sing), or ``"已删除 2/3 个提醒"`` (zh-CN).
    When ``success_count != total_count``, the count rendered is
    ``"{success}/{total}"`` to signal a partial result; the noun and verb
    still agree with ``total_count`` (we attempted total, we succeeded
    success).

    Args:
        success_count: Items that succeeded.
        total_count: Total items attempted. Drives grammatical agreement.
        noun_key: Key in :data:`DRAFT_RESULT_NOUNS` (e.g. ``"reminder"``).
            Sourced from :attr:`DraftDisplayConfig.noun_key`.
        verb_past_key: Key in :data:`DRAFT_RESULT_VERBS_PAST` (e.g.
            ``"deleted"``). Sourced from
            :attr:`DraftDisplayConfig.verb_past_key`.
        language: Target language code (fr/en/es/de/it/zh-CN); the declared
            language when absent (``resolve_language``).

    Returns:
        Localized, grammatically agreed header string.

    Raises:
        KeyError: If ``noun_key`` or ``verb_past_key`` is missing for the
            resolved language. The registry self-test in
            ``test_display_registry.py`` is designed to catch this before
            runtime.

    Example:
        >>> compose_result_header(3, 3, "reminder", "deleted", "fr")
        '3 rappels supprimés'
        >>> compose_result_header(1, 1, "task", "created", "fr")
        '1 tâche créée'
        >>> compose_result_header(2, 3, "email", "sent", "en")
        '2/3 emails sent'
        >>> compose_result_header(3, 3, "reminder", "deleted", "zh-CN")
        '已删除 3 个提醒'
    """
    lang = resolve_language(language)

    noun_entry = DRAFT_RESULT_NOUNS[lang][noun_key]
    verb_entry = DRAFT_RESULT_VERBS_PAST[lang][verb_past_key]

    plural_form = get_plural_form(total_count, lang)
    noun_str = noun_entry["singular" if plural_form == "singular" else "plural"]

    if isinstance(verb_entry, str):
        # Invariant participle (en, de, zh-CN).
        verb_str = verb_entry
    else:
        gender = noun_entry.get("gender", "m")
        gender_number_key = f"{gender}_{'sing' if plural_form == 'singular' else 'plur'}"
        verb_str = verb_entry[gender_number_key]

    count_part = (
        str(success_count) if success_count == total_count else f"{success_count}/{total_count}"
    )

    template = RESULT_HEADER_TEMPLATES[lang]
    return template.format(count=count_part, noun=noun_str, verb=verb_str)
