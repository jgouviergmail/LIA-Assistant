"""
Internationalized draft execution messages.

Provides centralized translations for draft success and cancellation messages.
Used by DraftExecutionResult to display localized messages.

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n_types import DEFAULT_LANGUAGE, Language

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
# HELPER FUNCTIONS
# ============================================================================


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

    # Handle Chinese variants
    lang_lower = language.lower()
    if lang_lower in ("zh", "zh-cn", "zh_cn"):
        return "zh-CN"

    # Extract base language (e.g., "fr-FR" -> "fr")
    base_lang = lang_lower.split("-")[0].split("_")[0]

    # Check if supported
    if base_lang in DRAFT_SUCCESS_MESSAGES:
        return base_lang  # type: ignore[return-value]

    return DEFAULT_LANGUAGE


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
