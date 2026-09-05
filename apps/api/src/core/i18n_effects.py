"""Wordings of the human-readable effect register (ADR-263).

A ledger row knows a tool name, a policy and a digest. A person needs a
sentence. That sentence is stored as ``{i18n_key, values}`` at claim time and
rendered HERE, in the reader's language at the moment they read it — so a
register exported in English still reads in English about an action taken while
the interface was in French.

Data module (exempt from the size ratchet, like ``i18n_drafts``): one table per
language, the SAME key set under each, checked by
``tests/unit/domains/agents/effects/test_effect_labels.py``.

The frontend resolves the same keys from its own locales for the live card —
the API ships keys and values, never a translated sentence (``apps/web``
conventions). ``scripts/i18n/validate_effect_labels.py`` keeps the two sides in
step.
"""

from typing import Any

from src.core.i18n import normalize_language

#: The six languages every label must exist in (backend canonical codes).
SUPPORTED_LABEL_LANGUAGES: tuple[str, ...] = ("fr", "en", "de", "es", "it", "zh-CN")

#: Fallback wording when a key has no entry — a register that cannot name an
#: action still records that it happened.
UNKNOWN_LABEL_KEY = "effects.labels.generic"


#: Heading of the exported action register. Six languages, like everything else
#: a reader sees: a two-language ternary in the builder made the archive read
#: English to an Italian user.
EFFECT_REGISTER_HEADING: dict[str, str] = {
    "fr": "Journal des actions",
    "en": "Action journal",
    "de": "Aktionsprotokoll",
    "es": "Registro de acciones",
    "it": "Registro delle azioni",
    "zh-CN": "操作记录",
}


def render_effect_heading(language: str) -> str:
    """Title the exported action register in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The heading.
    """
    return EFFECT_REGISTER_HEADING.get(normalize_language(language), EFFECT_REGISTER_HEADING["en"])


#: language -> {label key -> wording}. Placeholders are the builder's values.
EFFECT_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "effects.labels.generic": "Action « {tool} » exécutée",
        "effects.labels.mcp": "Outil externe « {tool} » utilisé",
        "effects.labels.control_hue_light_tool": "Lumière « {target} » modifiée",
        "effects.labels.control_hue_room_tool": "Éclairage de la pièce « {target} » modifié",
        "effects.labels.activate_hue_scene_tool": "Scène lumineuse « {target} » activée",
        "effects.labels.apply_labels_tool": "Libellés appliqués à {count} élément(s)",
        "effects.labels.remove_labels_tool": "Libellés retirés de {count} élément(s)",
        "effects.labels.complete_task_tool": "Tâche « {target} » marquée comme faite",
        "effects.labels.toggle_scheduled_action_tool": "Action planifiée « {target} » activée ou suspendue",
        "effects.labels.browser_task_tool": "Navigation web effectuée : {target}",
        "effects.labels.activate_skill_tool": "Compétence « {target} » activée",
        "effects.labels.import_user_skill": "Compétence « {target} » ajoutée à votre bibliothèque",
        "effects.labels.set_current_item": "Élément « {target} » choisi comme référence de la conversation",
        "effects.labels.generate_image": "Image générée : {target}",
        "effects.labels.edit_image": "Image modifiée : {target}",
        "effects.labels.generate_document": "Document « {target} » généré",
        "effects.labels.run_python_tool": "Calcul exécuté dans le bac à sable",
        "effects.labels.run_skill_script": "Script de la compétence « {target} » exécuté",
        "effects.labels.draft.email": "E-mail envoyé à {recipient}",
        "effects.labels.draft.email_reply": "Réponse envoyée à {recipient}",
        "effects.labels.draft.email_forward": "E-mail transféré à {recipient}",
        "effects.labels.draft.email_delete": "E-mail supprimé : {target}",
        "effects.labels.draft.email_filter": "Filtre de messagerie créé",
        "effects.labels.draft.vacation_responder": "Réponse d'absence configurée",
        "effects.labels.draft.event": "Événement « {target} » créé",
        "effects.labels.draft.event_update": "Événement « {target} » modifié",
        "effects.labels.draft.event_delete": "Événement « {target} » supprimé",
        "effects.labels.draft.contact": "Contact « {target} » créé",
        "effects.labels.draft.contact_update": "Contact « {target} » modifié",
        "effects.labels.draft.contact_delete": "Contact « {target} » supprimé",
        "effects.labels.draft.task": "Tâche « {target} » créée",
        "effects.labels.draft.task_update": "Tâche « {target} » modifiée",
        "effects.labels.draft.task_delete": "Tâche « {target} » supprimée",
        "effects.labels.draft.reminder_delete": "Rappel « {target} » supprimé",
        "effects.labels.draft.scheduled_action": "Action planifiée « {target} » créée",
        "effects.labels.draft.file_delete": "Fichier « {target} » supprimé",
        "effects.labels.draft.label_delete": "Libellé « {target} » supprimé",
        "effects.labels.draft.document_append": "Texte ajouté au document « {target} »",
        "effects.labels.draft.spreadsheet_write": "Feuille de calcul « {target} » mise à jour",
        "effects.labels.draft.peer_message": "Message envoyé à {recipient}",
        "effects.labels.draft.phone_call": "Appel passé à {recipient}",
        "effects.labels.draft.devops_task": "Tâche d'administration exécutée sur « {target} »",
    },
    "en": {
        "effects.labels.generic": "Ran the “{tool}” action",
        "effects.labels.mcp": "Used the external tool “{tool}”",
        "effects.labels.control_hue_light_tool": "Changed the “{target}” light",
        "effects.labels.control_hue_room_tool": "Changed the lighting in “{target}”",
        "effects.labels.activate_hue_scene_tool": "Activated the “{target}” light scene",
        "effects.labels.apply_labels_tool": "Applied labels to {count} item(s)",
        "effects.labels.remove_labels_tool": "Removed labels from {count} item(s)",
        "effects.labels.complete_task_tool": "Marked the task “{target}” as done",
        "effects.labels.toggle_scheduled_action_tool": "Enabled or paused the scheduled action “{target}”",
        "effects.labels.browser_task_tool": "Browsed the web: {target}",
        "effects.labels.activate_skill_tool": "Activated the “{target}” skill",
        "effects.labels.import_user_skill": "Added the “{target}” skill to your library",
        "effects.labels.set_current_item": "Set “{target}” as the conversation's current item",
        "effects.labels.generate_image": "Generated an image: {target}",
        "effects.labels.edit_image": "Edited an image: {target}",
        "effects.labels.generate_document": "Generated the document “{target}”",
        "effects.labels.run_python_tool": "Ran a computation in the sandbox",
        "effects.labels.run_skill_script": "Ran the “{target}” skill script",
        "effects.labels.draft.email": "Sent an email to {recipient}",
        "effects.labels.draft.email_reply": "Replied to {recipient}",
        "effects.labels.draft.email_forward": "Forwarded an email to {recipient}",
        "effects.labels.draft.email_delete": "Deleted an email: {target}",
        "effects.labels.draft.email_filter": "Created a mail filter",
        "effects.labels.draft.vacation_responder": "Set the vacation responder",
        "effects.labels.draft.event": "Created the event “{target}”",
        "effects.labels.draft.event_update": "Updated the event “{target}”",
        "effects.labels.draft.event_delete": "Deleted the event “{target}”",
        "effects.labels.draft.contact": "Created the contact “{target}”",
        "effects.labels.draft.contact_update": "Updated the contact “{target}”",
        "effects.labels.draft.contact_delete": "Deleted the contact “{target}”",
        "effects.labels.draft.task": "Created the task “{target}”",
        "effects.labels.draft.task_update": "Updated the task “{target}”",
        "effects.labels.draft.task_delete": "Deleted the task “{target}”",
        "effects.labels.draft.reminder_delete": "Deleted the reminder “{target}”",
        "effects.labels.draft.scheduled_action": "Created the scheduled action “{target}”",
        "effects.labels.draft.file_delete": "Deleted the file “{target}”",
        "effects.labels.draft.label_delete": "Deleted the label “{target}”",
        "effects.labels.draft.document_append": "Appended text to the document “{target}”",
        "effects.labels.draft.spreadsheet_write": "Wrote to the spreadsheet “{target}”",
        "effects.labels.draft.peer_message": "Sent a message to {recipient}",
        "effects.labels.draft.phone_call": "Placed a call to {recipient}",
        "effects.labels.draft.devops_task": "Ran an administration task on “{target}”",
    },
    "de": {
        "effects.labels.generic": "Aktion „{tool}“ ausgeführt",
        "effects.labels.mcp": "Externes Werkzeug „{tool}“ verwendet",
        "effects.labels.control_hue_light_tool": "Licht „{target}“ geändert",
        "effects.labels.control_hue_room_tool": "Beleuchtung im Raum „{target}“ geändert",
        "effects.labels.activate_hue_scene_tool": "Lichtszene „{target}“ aktiviert",
        "effects.labels.apply_labels_tool": "Labels auf {count} Element(e) angewendet",
        "effects.labels.remove_labels_tool": "Labels von {count} Element(en) entfernt",
        "effects.labels.complete_task_tool": "Aufgabe „{target}“ als erledigt markiert",
        "effects.labels.toggle_scheduled_action_tool": "Geplante Aktion „{target}“ aktiviert oder pausiert",
        "effects.labels.browser_task_tool": "Web-Navigation ausgeführt: {target}",
        "effects.labels.activate_skill_tool": "Fähigkeit „{target}“ aktiviert",
        "effects.labels.import_user_skill": "Fähigkeit „{target}“ zu Ihrer Bibliothek hinzugefügt",
        "effects.labels.set_current_item": "„{target}“ als aktuelles Element des Gesprächs gesetzt",
        "effects.labels.generate_image": "Bild erzeugt: {target}",
        "effects.labels.edit_image": "Bild bearbeitet: {target}",
        "effects.labels.generate_document": "Dokument „{target}“ erzeugt",
        "effects.labels.run_python_tool": "Berechnung in der Sandbox ausgeführt",
        "effects.labels.run_skill_script": "Skript der Fähigkeit „{target}“ ausgeführt",
        "effects.labels.draft.email": "E-Mail an {recipient} gesendet",
        "effects.labels.draft.email_reply": "Antwort an {recipient} gesendet",
        "effects.labels.draft.email_forward": "E-Mail an {recipient} weitergeleitet",
        "effects.labels.draft.email_delete": "E-Mail gelöscht: {target}",
        "effects.labels.draft.email_filter": "E-Mail-Filter erstellt",
        "effects.labels.draft.vacation_responder": "Abwesenheitsnotiz eingerichtet",
        "effects.labels.draft.event": "Termin „{target}“ erstellt",
        "effects.labels.draft.event_update": "Termin „{target}“ geändert",
        "effects.labels.draft.event_delete": "Termin „{target}“ gelöscht",
        "effects.labels.draft.contact": "Kontakt „{target}“ erstellt",
        "effects.labels.draft.contact_update": "Kontakt „{target}“ geändert",
        "effects.labels.draft.contact_delete": "Kontakt „{target}“ gelöscht",
        "effects.labels.draft.task": "Aufgabe „{target}“ erstellt",
        "effects.labels.draft.task_update": "Aufgabe „{target}“ geändert",
        "effects.labels.draft.task_delete": "Aufgabe „{target}“ gelöscht",
        "effects.labels.draft.reminder_delete": "Erinnerung „{target}“ gelöscht",
        "effects.labels.draft.scheduled_action": "Geplante Aktion „{target}“ erstellt",
        "effects.labels.draft.file_delete": "Datei „{target}“ gelöscht",
        "effects.labels.draft.label_delete": "Label „{target}“ gelöscht",
        "effects.labels.draft.document_append": "Text an das Dokument „{target}“ angehängt",
        "effects.labels.draft.spreadsheet_write": "Tabelle „{target}“ aktualisiert",
        "effects.labels.draft.peer_message": "Nachricht an {recipient} gesendet",
        "effects.labels.draft.phone_call": "Anruf an {recipient} getätigt",
        "effects.labels.draft.devops_task": "Administrationsaufgabe auf „{target}“ ausgeführt",
    },
    "es": {
        "effects.labels.generic": "Acción «{tool}» ejecutada",
        "effects.labels.mcp": "Herramienta externa «{tool}» utilizada",
        "effects.labels.control_hue_light_tool": "Luz «{target}» modificada",
        "effects.labels.control_hue_room_tool": "Iluminación de «{target}» modificada",
        "effects.labels.activate_hue_scene_tool": "Escena de luz «{target}» activada",
        "effects.labels.apply_labels_tool": "Etiquetas aplicadas a {count} elemento(s)",
        "effects.labels.remove_labels_tool": "Etiquetas retiradas de {count} elemento(s)",
        "effects.labels.complete_task_tool": "Tarea «{target}» marcada como hecha",
        "effects.labels.toggle_scheduled_action_tool": "Acción programada «{target}» activada o pausada",
        "effects.labels.browser_task_tool": "Navegación web realizada: {target}",
        "effects.labels.activate_skill_tool": "Habilidad «{target}» activada",
        "effects.labels.import_user_skill": "Habilidad «{target}» añadida a su biblioteca",
        "effects.labels.set_current_item": "«{target}» establecido como elemento actual de la conversación",
        "effects.labels.generate_image": "Imagen generada: {target}",
        "effects.labels.edit_image": "Imagen modificada: {target}",
        "effects.labels.generate_document": "Documento «{target}» generado",
        "effects.labels.run_python_tool": "Cálculo ejecutado en el entorno aislado",
        "effects.labels.run_skill_script": "Script de la habilidad «{target}» ejecutado",
        "effects.labels.draft.email": "Correo enviado a {recipient}",
        "effects.labels.draft.email_reply": "Respuesta enviada a {recipient}",
        "effects.labels.draft.email_forward": "Correo reenviado a {recipient}",
        "effects.labels.draft.email_delete": "Correo eliminado: {target}",
        "effects.labels.draft.email_filter": "Filtro de correo creado",
        "effects.labels.draft.vacation_responder": "Respuesta de ausencia configurada",
        "effects.labels.draft.event": "Evento «{target}» creado",
        "effects.labels.draft.event_update": "Evento «{target}» modificado",
        "effects.labels.draft.event_delete": "Evento «{target}» eliminado",
        "effects.labels.draft.contact": "Contacto «{target}» creado",
        "effects.labels.draft.contact_update": "Contacto «{target}» modificado",
        "effects.labels.draft.contact_delete": "Contacto «{target}» eliminado",
        "effects.labels.draft.task": "Tarea «{target}» creada",
        "effects.labels.draft.task_update": "Tarea «{target}» modificada",
        "effects.labels.draft.task_delete": "Tarea «{target}» eliminada",
        "effects.labels.draft.reminder_delete": "Recordatorio «{target}» eliminado",
        "effects.labels.draft.scheduled_action": "Acción programada «{target}» creada",
        "effects.labels.draft.file_delete": "Archivo «{target}» eliminado",
        "effects.labels.draft.label_delete": "Etiqueta «{target}» eliminada",
        "effects.labels.draft.document_append": "Texto añadido al documento «{target}»",
        "effects.labels.draft.spreadsheet_write": "Hoja de cálculo «{target}» actualizada",
        "effects.labels.draft.peer_message": "Mensaje enviado a {recipient}",
        "effects.labels.draft.phone_call": "Llamada realizada a {recipient}",
        "effects.labels.draft.devops_task": "Tarea de administración ejecutada en «{target}»",
    },
    "it": {
        "effects.labels.generic": "Azione «{tool}» eseguita",
        "effects.labels.mcp": "Strumento esterno «{tool}» utilizzato",
        "effects.labels.control_hue_light_tool": "Luce «{target}» modificata",
        "effects.labels.control_hue_room_tool": "Illuminazione della stanza «{target}» modificata",
        "effects.labels.activate_hue_scene_tool": "Scena luminosa «{target}» attivata",
        "effects.labels.apply_labels_tool": "Etichette applicate a {count} elemento/i",
        "effects.labels.remove_labels_tool": "Etichette rimosse da {count} elemento/i",
        "effects.labels.complete_task_tool": "Attività «{target}» segnata come completata",
        "effects.labels.toggle_scheduled_action_tool": "Azione pianificata «{target}» attivata o sospesa",
        "effects.labels.browser_task_tool": "Navigazione web effettuata: {target}",
        "effects.labels.activate_skill_tool": "Competenza «{target}» attivata",
        "effects.labels.import_user_skill": "Competenza «{target}» aggiunta alla sua libreria",
        "effects.labels.set_current_item": "«{target}» impostato come elemento corrente della conversazione",
        "effects.labels.generate_image": "Immagine generata: {target}",
        "effects.labels.edit_image": "Immagine modificata: {target}",
        "effects.labels.generate_document": "Documento «{target}» generato",
        "effects.labels.run_python_tool": "Calcolo eseguito nella sandbox",
        "effects.labels.run_skill_script": "Script della competenza «{target}» eseguito",
        "effects.labels.draft.email": "E-mail inviata a {recipient}",
        "effects.labels.draft.email_reply": "Risposta inviata a {recipient}",
        "effects.labels.draft.email_forward": "E-mail inoltrata a {recipient}",
        "effects.labels.draft.email_delete": "E-mail eliminata: {target}",
        "effects.labels.draft.email_filter": "Filtro di posta creato",
        "effects.labels.draft.vacation_responder": "Risposta di assenza configurata",
        "effects.labels.draft.event": "Evento «{target}» creato",
        "effects.labels.draft.event_update": "Evento «{target}» modificato",
        "effects.labels.draft.event_delete": "Evento «{target}» eliminato",
        "effects.labels.draft.contact": "Contatto «{target}» creato",
        "effects.labels.draft.contact_update": "Contatto «{target}» modificato",
        "effects.labels.draft.contact_delete": "Contatto «{target}» eliminato",
        "effects.labels.draft.task": "Attività «{target}» creata",
        "effects.labels.draft.task_update": "Attività «{target}» modificata",
        "effects.labels.draft.task_delete": "Attività «{target}» eliminata",
        "effects.labels.draft.reminder_delete": "Promemoria «{target}» eliminato",
        "effects.labels.draft.scheduled_action": "Azione pianificata «{target}» creata",
        "effects.labels.draft.file_delete": "File «{target}» eliminato",
        "effects.labels.draft.label_delete": "Etichetta «{target}» eliminata",
        "effects.labels.draft.document_append": "Testo aggiunto al documento «{target}»",
        "effects.labels.draft.spreadsheet_write": "Foglio di calcolo «{target}» aggiornato",
        "effects.labels.draft.peer_message": "Messaggio inviato a {recipient}",
        "effects.labels.draft.phone_call": "Chiamata effettuata a {recipient}",
        "effects.labels.draft.devops_task": "Attività di amministrazione eseguita su «{target}»",
    },
    "zh-CN": {
        "effects.labels.generic": "已执行「{tool}」操作",
        "effects.labels.mcp": "已使用外部工具「{tool}」",
        "effects.labels.control_hue_light_tool": "已调整灯光「{target}」",
        "effects.labels.control_hue_room_tool": "已调整房间「{target}」的灯光",
        "effects.labels.activate_hue_scene_tool": "已启用灯光场景「{target}」",
        "effects.labels.apply_labels_tool": "已为 {count} 个项目添加标签",
        "effects.labels.remove_labels_tool": "已从 {count} 个项目移除标签",
        "effects.labels.complete_task_tool": "已将任务「{target}」标记为完成",
        "effects.labels.toggle_scheduled_action_tool": "已启用或暂停计划操作「{target}」",
        "effects.labels.browser_task_tool": "已执行网页浏览：{target}",
        "effects.labels.activate_skill_tool": "已启用技能「{target}」",
        "effects.labels.import_user_skill": "已将技能「{target}」加入您的资料库",
        "effects.labels.set_current_item": "已将「{target}」设为当前对话对象",
        "effects.labels.generate_image": "已生成图片：{target}",
        "effects.labels.edit_image": "已修改图片：{target}",
        "effects.labels.generate_document": "已生成文档「{target}」",
        "effects.labels.run_python_tool": "已在沙盒中执行计算",
        "effects.labels.run_skill_script": "已执行技能「{target}」的脚本",
        "effects.labels.draft.email": "已向 {recipient} 发送邮件",
        "effects.labels.draft.email_reply": "已回复 {recipient}",
        "effects.labels.draft.email_forward": "已将邮件转发给 {recipient}",
        "effects.labels.draft.email_delete": "已删除邮件：{target}",
        "effects.labels.draft.email_filter": "已创建邮件过滤器",
        "effects.labels.draft.vacation_responder": "已设置外出自动回复",
        "effects.labels.draft.event": "已创建日程「{target}」",
        "effects.labels.draft.event_update": "已修改日程「{target}」",
        "effects.labels.draft.event_delete": "已删除日程「{target}」",
        "effects.labels.draft.contact": "已创建联系人「{target}」",
        "effects.labels.draft.contact_update": "已修改联系人「{target}」",
        "effects.labels.draft.contact_delete": "已删除联系人「{target}」",
        "effects.labels.draft.task": "已创建任务「{target}」",
        "effects.labels.draft.task_update": "已修改任务「{target}」",
        "effects.labels.draft.task_delete": "已删除任务「{target}」",
        "effects.labels.draft.reminder_delete": "已删除提醒「{target}」",
        "effects.labels.draft.scheduled_action": "已创建计划操作「{target}」",
        "effects.labels.draft.file_delete": "已删除文件「{target}」",
        "effects.labels.draft.label_delete": "已删除标签「{target}」",
        "effects.labels.draft.document_append": "已向文档「{target}」追加内容",
        "effects.labels.draft.spreadsheet_write": "已更新电子表格「{target}」",
        "effects.labels.draft.peer_message": "已向 {recipient} 发送消息",
        "effects.labels.draft.phone_call": "已致电 {recipient}",
        "effects.labels.draft.devops_task": "已在「{target}」上执行运维任务",
    },
}


def render_effect_label(label: Any, language: str) -> str:
    """Render a stored ``{i18n_key, values}`` in the reader's language.

    Never raises: this runs while producing an export the user asked for, and a
    wording that gained a placeholder after a row was written must degrade to a
    readable line rather than fail the whole archive.

    Args:
        label: The stored label, or anything at all — malformed input is
            expected from rows written by older versions.
        language: Any locale spelling; normalised to a backend canonical code.

    Returns:
        A sentence in the requested language, always non-empty.
    """
    normalized = normalize_language(language)
    if not isinstance(label, dict):
        return _fallback(normalized, {})
    key = str(label.get("i18n_key") or UNKNOWN_LABEL_KEY)
    values = label.get("values")
    values = values if isinstance(values, dict) else {}

    table = EFFECT_LABELS.get(normalized) or EFFECT_LABELS["en"]
    wording = table.get(key)
    if wording is None:
        return _fallback(normalized, values)
    try:
        return wording.format(**values)
    except KeyError, IndexError, ValueError:
        # A newer wording expects a value an older row never stored.
        return _fallback(normalized, values)


def _fallback(language: str, values: dict[str, Any]) -> str:
    """The generic wording, filled with whatever the row does carry."""
    table = EFFECT_LABELS.get(language) or EFFECT_LABELS["en"]
    wording = table[UNKNOWN_LABEL_KEY]
    tool = values.get("tool") or values.get("target") or values.get("recipient") or "?"
    return wording.format(tool=tool)
