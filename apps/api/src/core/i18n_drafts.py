"""
Internationalized draft execution messages.

Provides centralized translations for draft success and cancellation messages.
Used by DraftExecutionResult to display localized messages.

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n import DEFAULT_LANGUAGE, normalize_language
from src.core.i18n_types import Language

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
        "_default": "Action exécutée avec succès",
    },
    "en": {
        "email": "Sent successfully",
        "email_reply": "Reply sent successfully",
        "email_forward": "Forwarded successfully",
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
        "_default": "Action completed successfully",
    },
    "es": {
        "email": "Enviado con éxito",
        "email_reply": "Respuesta enviada con éxito",
        "email_forward": "Reenviado con éxito",
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
        "_default": "Acción ejecutada con éxito",
    },
    "de": {
        "email": "Erfolgreich gesendet",
        "email_reply": "Antwort erfolgreich gesendet",
        "email_forward": "Erfolgreich weitergeleitet",
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
        "_default": "Aktion erfolgreich ausgeführt",
    },
    "it": {
        "email": "Inviata con successo",
        "email_reply": "Risposta inviata con successo",
        "email_forward": "Inoltrata con successo",
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
        "_default": "Azione eseguita con successo",
    },
    "zh-CN": {
        "email": "发送成功",
        "email_reply": "回复发送成功",
        "email_forward": "转发成功",
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
        "_default": "Action annulée",
    },
    "en": {
        "email": "Sending cancelled",
        "email_reply": "Reply cancelled",
        "email_forward": "Forwarding cancelled",
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
        "_default": "Action cancelled",
    },
    "es": {
        "email": "Envío cancelado",
        "email_reply": "Respuesta cancelada",
        "email_forward": "Reenvío cancelado",
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
        "_default": "Acción cancelada",
    },
    "de": {
        "email": "Versand abgebrochen",
        "email_reply": "Antwort abgebrochen",
        "email_forward": "Weiterleitung abgebrochen",
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
        "_default": "Aktion abgebrochen",
    },
    "it": {
        "email": "Invio annullato",
        "email_reply": "Risposta annullata",
        "email_forward": "Inoltro annullato",
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
        "_default": "Azione annullata",
    },
    "zh-CN": {
        "email": "发送已取消",
        "email_reply": "回复已取消",
        "email_forward": "转发已取消",
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
        "email_delete": "Suppression email: {subject}",
        # Event actions
        "event_create": "Événement: {summary} le {start}",
        "event_update": "Modification événement: {summary}",
        "event_delete": "Suppression événement: {summary}",
        # Contact actions
        "contact_create": "Contact: {name}",
        "contact_update": "Modification contact: {name}",
        "contact_delete": "Suppression contact: {name}",
        # Task actions
        "task_create": "Tâche: {title}",
        "task_update": "Modification tâche: {title}",
        "task_delete": "Suppression tâche: {title}",
        # File actions
        "file_delete": "Suppression fichier: {name}",
        # Label actions
        "label_delete": "Suppression label: {name}",
        # Draft header
        "draft_created": "📄 **Brouillon créé**: {title}",
        "action_required": "**Action requise**: confirmez, modifiez ou annulez.",
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
        "draft_created": "📄 **Draft created**: {title}",
        "action_required": "**Action required**: confirm, edit, or cancel.",
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
        "draft_created": "📄 **Borrador creado**: {title}",
        "action_required": "**Acción requerida**: confirme, modifique o cancele.",
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
        "draft_created": "📄 **Entwurf erstellt**: {title}",
        "action_required": "**Aktion erforderlich**: bestätigen, bearbeiten oder abbrechen.",
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
        "draft_created": "📄 **Bozza creata**: {title}",
        "action_required": "**Azione richiesta**: conferma, modifica o annulla.",
    },
    "zh-CN": {
        "email_to": "发送邮件给 {to}",
        "email_reply_to": "回复 {to}",
        "email_forward_to": "转发给 {to}",
        "email_delete": "删除邮件: {subject}",
        "event_create": "事件: {summary} 于 {start}",
        "event_update": "修改事件: {summary}",
        "event_delete": "删除事件: {summary}",
        "contact_create": "联系人: {name}",
        "contact_update": "修改联系人: {name}",
        "contact_delete": "删除联系人: {name}",
        "task_create": "任务: {title}",
        "task_update": "修改任务: {title}",
        "task_delete": "删除任务: {title}",
        "file_delete": "删除文件: {name}",
        "label_delete": "删除标签: {name}",
        "draft_created": "📄 **草稿已创建**: {title}",
        "action_required": "**需要操作**: 确认、修改或取消。",
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
    },
    "en": {
        "to": "To",
        "cc": "Cc",
        "bcc": "Bcc",
        "subject": "Subject",
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
    },
    "es": {
        "to": "Destinatario",
        "cc": "Cc",
        "bcc": "Cco",
        "subject": "Asunto",
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
    },
    "de": {
        "to": "An",
        "cc": "Cc",
        "bcc": "Bcc",
        "subject": "Betreff",
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
    },
    "it": {
        "to": "Destinatario",
        "cc": "Cc",
        "bcc": "Ccn",
        "subject": "Oggetto",
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
    },
    "zh-CN": {
        "to": "收件人",
        "cc": "抄送",
        "bcc": "密送",
        "subject": "主题",
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


def _stringify_recipient(value: object) -> str:
    """Normalize an email recipient field to a compact one-line string.

    A draft ``to`` field is either a single address string or a list of
    addresses. This collapses internal whitespace, joins a list with commas,
    and bounds the length so a long recipient list stays on one preview row.

    Args:
        value: Raw recipient value from the draft content (str, list, or None).

    Returns:
        A compact recipient string, or ``""`` when the value is empty.
    """
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [" ".join(str(v).split()) for v in value if v]
        recipient = ", ".join(p for p in parts if p)
    else:
        recipient = " ".join(str(value).split())
    if len(recipient) > 60:
        recipient = recipient[:57].rstrip() + "..."
    return recipient


def _normalize_language(language: str | None) -> Language:
    """
    Normalize language code to supported Language type.

    Args:
        language: Language code (e.g., "fr", "en", "zh-CN", "zh")

    Returns:
        Normalized Language code

    Example:
        >>> _normalize_language("zh")
        "zh-CN"
        >>> _normalize_language("fr-FR")
        "fr"
    """
    if not language:
        return DEFAULT_LANGUAGE

    # Single normalization chokepoint (audit wave 2, zh) — DRAFT_* tables are
    # keyed on its output (all 6 canonical languages, zh-CN included)
    return normalize_language(language)


def get_draft_success_message(
    draft_type: str,
    language: str | None = None,
    **kwargs: str,
) -> str:
    """
    Get localized success message for a draft type.

    Args:
        draft_type: Draft type (e.g., "email", "event", "contact")
        language: Target language code (default: fr)
        **kwargs: Placeholder values (name, summary, title)

    Returns:
        Localized success message with placeholders replaced

    Example:
        >>> get_draft_success_message("event", "fr", summary="Meeting")
        "Événement 'Meeting' créé avec succès"
        >>> get_draft_success_message("email", "en")
        "Email sent successfully"
    """
    lang = _normalize_language(language)
    messages = DRAFT_SUCCESS_MESSAGES.get(lang, DRAFT_SUCCESS_MESSAGES[DEFAULT_LANGUAGE])
    template = messages.get(draft_type, messages["_default"])

    # Replace placeholders with provided values or empty string
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value or "")

    # Clean up any unreplaced placeholders
    import re

    template = re.sub(r"\s*'\{[^}]+\}'", "", template)  # Remove '{placeholder}'
    template = re.sub(r"\{[^}]+\}", "", template)  # Remove remaining {placeholder}

    return template.strip()


def get_draft_cancel_message(
    draft_type: str,
    language: str | None = None,
) -> str:
    """
    Get localized cancellation message for a draft type.

    Args:
        draft_type: Draft type (e.g., "email", "event", "contact")
        language: Target language code (default: fr)

    Returns:
        Localized cancellation message

    Example:
        >>> get_draft_cancel_message("email", "fr")
        "Envoi d'email annulé"
        >>> get_draft_cancel_message("event", "en")
        "Event creation cancelled"
    """
    lang = _normalize_language(language)
    messages = DRAFT_CANCEL_MESSAGES.get(lang, DRAFT_CANCEL_MESSAGES[DEFAULT_LANGUAGE])
    return messages.get(draft_type, messages["_default"])


def get_draft_error_message(
    language: str | None = None,
) -> str:
    """
    Get localized error message for draft execution failures.

    Args:
        language: Target language code (default: fr)

    Returns:
        Localized error message

    Example:
        >>> get_draft_error_message("en")
        "Error during execution"
    """
    lang = _normalize_language(language)
    return DRAFT_ERROR_MESSAGES.get(lang, DRAFT_ERROR_MESSAGES[DEFAULT_LANGUAGE])


def get_draft_summary_label(
    label_key: str,
    language: str | None = None,
    **kwargs: str,
) -> str:
    """
    Get localized summary label for draft display.

    Args:
        label_key: Label key (e.g., "email_to", "event_create", "draft_created")
        language: Target language code (default: fr)
        **kwargs: Placeholder values (to, subject, summary, name, title, start)

    Returns:
        Localized summary label with placeholders replaced

    Example:
        >>> get_draft_summary_label("email_to", "fr", to="john@example.com", subject="Test")
        "Email à john@example.com: Test"
        >>> get_draft_summary_label("draft_created", "zh-CN", title="邮件草稿")
        "📄 **草稿已创建**: 邮件草稿"
    """
    lang = _normalize_language(language)
    labels = DRAFT_SUMMARY_LABELS.get(lang, DRAFT_SUMMARY_LABELS[DEFAULT_LANGUAGE])
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
        language: Target language code (default: fr)

    Returns:
        Dict of field labels (to, cc, subject, body, etc.)

    Example:
        >>> labels = get_draft_preview_labels("zh-CN")
        >>> labels["to"]
        "收件人"
        >>> labels["subject"]
        "主题"
    """
    lang = _normalize_language(language)
    return DRAFT_PREVIEW_LABELS.get(lang, DRAFT_PREVIEW_LABELS[DEFAULT_LANGUAGE])


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
        "reminder": {"singular": "rappel", "plural": "rappels", "gender": "m"},
        "email": {"singular": "email", "plural": "emails", "gender": "m"},
        "event": {"singular": "événement", "plural": "événements", "gender": "m"},
        "contact": {"singular": "contact", "plural": "contacts", "gender": "m"},
        "task": {"singular": "tâche", "plural": "tâches", "gender": "f"},
        "file": {"singular": "fichier", "plural": "fichiers", "gender": "m"},
        "label": {"singular": "label", "plural": "labels", "gender": "m"},
    },
    "en": {
        "reminder": {"singular": "reminder", "plural": "reminders"},
        "email": {"singular": "email", "plural": "emails"},
        "event": {"singular": "event", "plural": "events"},
        "contact": {"singular": "contact", "plural": "contacts"},
        "task": {"singular": "task", "plural": "tasks"},
        "file": {"singular": "file", "plural": "files"},
        "label": {"singular": "label", "plural": "labels"},
    },
    "es": {
        "reminder": {"singular": "recordatorio", "plural": "recordatorios", "gender": "m"},
        "email": {"singular": "email", "plural": "emails", "gender": "m"},
        "event": {"singular": "evento", "plural": "eventos", "gender": "m"},
        "contact": {"singular": "contacto", "plural": "contactos", "gender": "m"},
        "task": {"singular": "tarea", "plural": "tareas", "gender": "f"},
        "file": {"singular": "archivo", "plural": "archivos", "gender": "m"},
        "label": {"singular": "etiqueta", "plural": "etiquetas", "gender": "f"},
    },
    "de": {
        "reminder": {"singular": "Erinnerung", "plural": "Erinnerungen"},
        "email": {"singular": "E-Mail", "plural": "E-Mails"},
        "event": {"singular": "Termin", "plural": "Termine"},
        "contact": {"singular": "Kontakt", "plural": "Kontakte"},
        "task": {"singular": "Aufgabe", "plural": "Aufgaben"},
        "file": {"singular": "Datei", "plural": "Dateien"},
        "label": {"singular": "Label", "plural": "Labels"},
    },
    "it": {
        # Italian: "promemoria", "email", "attività", "file" are invariant for number.
        "reminder": {"singular": "promemoria", "plural": "promemoria", "gender": "m"},
        "email": {"singular": "email", "plural": "email", "gender": "f"},
        "event": {"singular": "evento", "plural": "eventi", "gender": "m"},
        "contact": {"singular": "contatto", "plural": "contatti", "gender": "m"},
        "task": {"singular": "attività", "plural": "attività", "gender": "f"},
        "file": {"singular": "file", "plural": "file", "gender": "m"},
        "label": {"singular": "etichetta", "plural": "etichette", "gender": "f"},
    },
    "zh-CN": {
        # Chinese has no grammatical number; both forms hold the same string.
        "reminder": {"singular": "提醒", "plural": "提醒"},
        "email": {"singular": "邮件", "plural": "邮件"},
        "event": {"singular": "事件", "plural": "事件"},
        "contact": {"singular": "联系人", "plural": "联系人"},
        "task": {"singular": "任务", "plural": "任务"},
        "file": {"singular": "文件", "plural": "文件"},
        "label": {"singular": "标签", "plural": "标签"},
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
    },
    "en": {
        "sent": "sent",
        "deleted": "deleted",
        "created": "created",
        "updated": "updated",
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
    },
    "de": {
        "sent": "gesendet",
        "deleted": "gelöscht",
        "created": "erstellt",
        "updated": "aktualisiert",
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
    },
    "zh-CN": {
        "sent": "已发送",
        "deleted": "已删除",
        "created": "已创建",
        "updated": "已更新",
    },
}

# Header word-order template per language.
# Placeholders: {count}, {noun}, {verb}.
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
    lang = _normalize_language(language)
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

        {emoji} {Noun} : {label} - {datetime_with_day_name}

    Examples (fr):
        ``🔔 Rappel : Médecin - dimanche 17 mai 2026 à 19:00``
        ``📧 Email : Confirmation rdv jeudi - jeudi 16 mai 2026 à 14:00``
        ``📅 Événement : Réunion équipe - lundi 20 mai 2026 à 10:00``
        ``👤 Contact : Marie Dupont``

    Args:
        draft_type: Draft type identifier (e.g. ``"reminder_delete"``,
            ``"email_delete"``). For paths that only know a base domain and
            a mutation verb, the caller is responsible for synthesizing the
            ``"{domain}_{mutation}"`` candidate first and falling back to
            the bare ``domain`` if the registry has no specific entry.
        content: Item dict carrying the fields declared in the registry's
            ``item_label_fields`` and ``item_secondary_datetime_key``.
            Nested keys are resolved via :func:`resolve_nested_value`.
        language: Target language (fr/en/es/de/it/zh-CN); falls back to
            :data:`DEFAULT_LANGUAGE`.
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
        resolve_nested_value,
    )

    config = get_draft_display_config(draft_type)
    if config is None:
        return None

    lang = _normalize_language(language)
    tz = user_timezone or DEFAULT_USER_DISPLAY_TIMEZONE

    # Localized capitalized noun (e.g. "rappel" → "Rappel"). Chinese has no
    # case but ``.capitalize()`` is a no-op on it, so this is safe.
    noun_entry = DRAFT_RESULT_NOUNS.get(lang, {}).get(config.noun_key)
    noun: str = noun_entry["singular"].capitalize() if noun_entry else ""

    # Extract label using the registry's priority chain.
    label: str = ""
    for key in config.item_label_fields:
        value = resolve_nested_value(content, key) if "." in key else content.get(key)
        if value:
            label = " ".join(str(value).split())
            break

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
        recipient = _stringify_recipient(rcpt_value)
        if recipient:
            connector = DRAFT_RECIPIENT_CONNECTOR.get(
                lang, DRAFT_RECIPIENT_CONNECTOR[DEFAULT_LANGUAGE]
            )
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
            except (ValueError, TypeError):
                dt_str = ""

    # Compose: "{emoji} {Noun[ connector recipient]} : {label}" + optional date.
    head_parts: list[str] = [config.emoji]
    if noun_display and label:
        head_parts.append(f"{noun_display} : {label}")
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
        language: Target language code (fr/en/es/de/it/zh-CN); falls back
            to :data:`DEFAULT_LANGUAGE`.

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
    lang = _normalize_language(language)

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
