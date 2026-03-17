"""
Internationalization (i18n) for HITL interactions.

Centralized translations for all Human-In-The-Loop interaction types:
- Clarification: Semantic validation clarification questions
- Draft Critique: Draft review before execution (email, event, contact, task)
- Plan Approval: Plan-level approval questions
- Tool Confirmation: Tool-level confirmation questions

All 6 supported languages: fr, en, es, de, it, zh-CN

Usage:
    from src.core.i18n_hitl import HitlMessages

    # Get fallback message
    msg = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "fr")

    # Get action label
    label = HitlMessages.get_action_label("confirm", "de")

    # Get action prompt
    prompt = HitlMessages.get_action_prompt("fr")

    # Get draft summary template
    summary = HitlMessages.get_draft_summary("email", "it", to="jean@ex.com", subject="RDV")

    # Get clarification header
    header = HitlMessages.get_clarification_header("zh-CN")

Created: 2025-12-06
"""

from enum import Enum
from typing import Any

from src.core.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Language


class HitlMessageType(str, Enum):
    """HITL interaction message types."""

    CLARIFICATION = "clarification"
    DRAFT_CRITIQUE = "draft_critique"
    PLAN_APPROVAL = "plan_approval"
    TOOL_CONFIRMATION = "tool_confirmation"
    ENTITY_DISAMBIGUATION = "entity_disambiguation"
    DESTRUCTIVE_CONFIRM = "destructive_confirm"
    FOR_EACH_CONFIRMATION = "for_each_confirmation"  # Bulk mutation confirmation


# =============================================================================
# FALLBACK MESSAGES - Static messages when LLM streaming fails
# =============================================================================

_FALLBACK_MESSAGES: dict[HitlMessageType, dict[str, str]] = {
    HitlMessageType.CLARIFICATION: {
        "fr": "J'ai besoin de clarifications pour mieux comprendre ta demande. Peux-tu préciser ?",
        "en": "I need clarification to better understand your request. Can you provide more details?",
        "es": "Necesito aclaraciones para entender mejor su solicitud. ¿Puede proporcionar más detalles?",
        "de": "Ich benötige Klarstellungen, um Ihre Anfrage besser zu verstehen. Können Sie genauer werden?",
        "it": "Ho bisogno di chiarimenti per capire meglio la tua richiesta. Puoi fornire più dettagli?",
        "zh-CN": "我需要更多信息来理解您的请求。您能提供更多细节吗？",
    },
    HitlMessageType.DRAFT_CRITIQUE: {
        "fr": "J'ai préparé une action qui nécessite ta validation. Veux-tu confirmer, modifier ou annuler ?",
        "en": "I've prepared an action that requires your approval. Would you like to confirm, edit, or cancel?",
        "es": "He preparado una acción que requiere tu aprobación. ¿Quieres confirmar, modificar o cancelar?",
        "de": "Ich habe eine Aktion vorbereitet, die deine Genehmigung erfordert. Möchtest du bestätigen, bearbeiten oder abbrechen?",
        "it": "Ho preparato un'azione che richiede la tua approvazione. Vuoi confermare, modificare o annullare?",
        "zh-CN": "我准备了一个需要您确认的操作。您想确认、修改还是取消？",
    },
    HitlMessageType.PLAN_APPROVAL: {
        "fr": "Ce plan nécessite ton approbation. Valides-tu pour continuer ?",
        "en": "This plan requires your approval. Do you confirm to proceed?",
        "es": "Este plan requiere tu aprobación. ¿Confirmas para continuar?",
        "de": "Dieser Plan erfordert deine Genehmigung. Bestätigst du, um fortzufahren?",
        "it": "Questo piano richiede la tua approvazione. Confermi per procedere?",
        "zh-CN": "此计划需要您的批准。您确认继续吗？",
    },
    HitlMessageType.TOOL_CONFIRMATION: {
        "fr": "Cette action nécessite ta confirmation. Dois-je continuer ?",
        "en": "This action requires your confirmation. Should I proceed?",
        "es": "Esta acción requiere tu confirmación. ¿Debo continuar?",
        "de": "Diese Aktion erfordert deine Bestätigung. Soll ich fortfahren?",
        "it": "Questa azione richiede la tua conferma. Devo procedere?",
        "zh-CN": "此操作需要您的确认。我应该继续吗？",
    },
    HitlMessageType.ENTITY_DISAMBIGUATION: {
        "fr": "J'ai trouvé plusieurs correspondances. Peux-tu préciser laquelle tu souhaites ?",
        "en": "I found multiple matches. Can you specify which one you want?",
        "es": "Encontré varias coincidencias. ¿Puedes especificar cuál quieres?",
        "de": "Ich habe mehrere Treffer gefunden. Kannst du angeben, welchen du möchtest?",
        "it": "Ho trovato più corrispondenze. Puoi specificare quale vuoi?",
        "zh-CN": "我找到了多个匹配项。你能指定你想要哪一个吗？",
    },
    HitlMessageType.DESTRUCTIVE_CONFIRM: {
        "fr": "Cette opération affecte plusieurs éléments. Confirmes-tu ?",
        "en": "This operation affects multiple items. Do you confirm?",
        "es": "Esta operación afecta a varios elementos. ¿Confirmas?",
        "de": "Diese Operation betrifft mehrere Elemente. Bestätigen Sie?",
        "it": "Questa operazione interessa più elementi. Confermi?",
        "zh-CN": "此操作会影响多个项目。确认吗？",
    },
    HitlMessageType.FOR_EACH_CONFIRMATION: {
        "fr": "Cette action va s'appliquer à plusieurs éléments. Confirmes-tu l'exécution ?",
        "en": "This action will apply to multiple items. Do you confirm execution?",
        "es": "Esta acción se aplicará a varios elementos. ¿Confirmas la ejecución?",
        "de": "Diese Aktion wird auf mehrere Elemente angewendet. Bestätigen Sie die Ausführung?",
        "it": "Questa azione verrà applicata a più elementi. Confermi l'esecuzione?",
        "zh-CN": "此操作将应用于多个项目。确认执行吗？",
    },
}

# =============================================================================
# ACTION LABELS - Button labels for draft actions
# =============================================================================

_ACTION_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "confirm": "Confirmer",
        "edit": "Modifier",
        "cancel": "Annuler",
    },
    "en": {
        "confirm": "Confirm",
        "edit": "Edit",
        "cancel": "Cancel",
    },
    "es": {
        "confirm": "Confirmar",
        "edit": "Modificar",
        "cancel": "Cancelar",
    },
    "de": {
        "confirm": "Bestätigen",
        "edit": "Bearbeiten",
        "cancel": "Abbrechen",
    },
    "it": {
        "confirm": "Conferma",
        "edit": "Modifica",
        "cancel": "Annulla",
    },
    "zh-CN": {
        "confirm": "确认",
        "edit": "编辑",
        "cancel": "取消",
    },
}

# =============================================================================
# ACTION PROMPTS - "What would you like to do?" in each language
# =============================================================================

_ACTION_PROMPTS: dict[str, str] = {
    "fr": "<br/>Que veux-tu faire ?",
    "en": "<br/>What would you like to do?",
    "es": "<br/>¿Qué quieres hacer?",
    "de": "<br/>Was möchtest du tun?",
    "it": "<br/>Cosa vuoi fare?",
    "zh-CN": "<br/>你想怎么做？",
}

# =============================================================================
# CLARIFICATION HEADERS - Multi-question headers
# =============================================================================

_CLARIFICATION_HEADERS: dict[str, str] = {
    "fr": "J'ai besoin de clarifications sur les points suivants :<br/><br/>",
    "en": "I need clarification on the following points:<br/><br/>",
    "es": "Necesito aclaraciones sobre los siguientes puntos:<br/><br/>",
    "de": "Ich benötige Klarstellungen zu folgenden Punkten:<br/><br/>",
    "it": "Ho bisogno di chiarimenti sui seguenti punti:<br/><br/>",
    "zh-CN": "我需要以下几点的澄清：<br/><br/>",
}

# =============================================================================
# DISAMBIGUATION TEMPLATES - Entity resolution messages
# =============================================================================

# Headers for multiple entities disambiguation
_DISAMBIGUATION_MULTIPLE_ENTITIES: dict[str, str] = {
    "fr": 'J\'ai trouvé plusieurs "{query}" :',
    "en": 'I found multiple matches for "{query}":',
    "es": 'Encontré varias coincidencias para "{query}":',
    "de": 'Ich habe mehrere Treffer für "{query}" gefunden:',
    "it": 'Ho trovato più corrispondenze per "{query}":',
    "zh-CN": '我找到了多个"{query}"的匹配项：',
}

# Headers for multiple fields disambiguation (e.g., multiple emails for one contact)
_DISAMBIGUATION_MULTIPLE_FIELDS: dict[str, str] = {
    "fr": "{name} a plusieurs {field_type}s. Lequel veux-tu utiliser ?",
    "en": "{name} has multiple {field_type}s. Which one would you like to use?",
    "es": "{name} tiene varios {field_type}s. ¿Cuál quieres usar?",
    "de": "{name} hat mehrere {field_type}s. Welche möchtest du verwenden?",
    "it": "{name} ha più {field_type}. Quale vuoi usare?",
    "zh-CN": "{name}有多个{field_type}。你想用哪个？",
}

# Footer asking for selection
_DISAMBIGUATION_CHOICE_PROMPT: dict[str, str] = {
    "fr": "\n\nIndique le numéro de ton choix (ex: 1, 2...):",
    "en": "\n\nPlease indicate your choice by number (e.g., 1, 2...):",
    "es": "\n\nIndica el número de tu elección (ej: 1, 2...):",
    "de": "\n\nBitte gib die Nummer deiner Wahl an (z.B. 1, 2...):",
    "it": "\n\nIndica il numero della tua scelta (es: 1, 2...):",
    "zh-CN": "\n\n请指出你的选择编号（例如：1, 2...）：",
}

# Domain-specific labels
_DOMAIN_LABELS: dict[str, dict[str, str]] = {
    "contacts": {
        "fr": "contact",
        "en": "contact",
        "es": "contacto",
        "de": "Kontakt",
        "it": "contatto",
        "zh-CN": "联系人",
    },
    "emails": {
        "fr": "email",
        "en": "email",
        "es": "correo",
        "de": "E-Mail",
        "it": "email",
        "zh-CN": "邮件",
    },
    "events": {
        "fr": "événement",
        "en": "event",
        "es": "evento",
        "de": "Termin",
        "it": "evento",
        "zh-CN": "活动",
    },
    "tasks": {
        "fr": "tâche",
        "en": "task",
        "es": "tarea",
        "de": "Aufgabe",
        "it": "attività",
        "zh-CN": "任务",
    },
    "files": {
        "fr": "fichier",
        "en": "file",
        "es": "archivo",
        "de": "Datei",
        "it": "file",
        "zh-CN": "文件",
    },
    "labels": {
        "fr": "label",
        "en": "label",
        "es": "etiqueta",
        "de": "Label",
        "it": "etichetta",
        "zh-CN": "标签",
    },
}

# Field type labels for multiple fields disambiguation
_FIELD_TYPE_LABELS: dict[str, dict[str, str]] = {
    "email": {
        "fr": "adresse email",
        "en": "email address",
        "es": "dirección de correo",
        "de": "E-Mail-Adresse",
        "it": "indirizzo email",
        "zh-CN": "电子邮件地址",
    },
    "phone": {
        "fr": "numéro de téléphone",
        "en": "phone number",
        "es": "número de teléfono",
        "de": "Telefonnummer",
        "it": "numero di telefono",
        "zh-CN": "电话号码",
    },
    "address": {
        "fr": "adresse",
        "en": "address",
        "es": "dirección",
        "de": "Adresse",
        "it": "indirizzo",
        "zh-CN": "地址",
    },
}

# =============================================================================
# FOR_EACH CONFIRM - UI labels for bulk iteration operations
# =============================================================================
# Format: "{operation_prefix} {mutation_verb} **{count}** {items_suffix}"
# E.g. FR: "Cette action va envoyer **10** emails" / EN: "This action will send **10** emails"

_FOR_EACH_CONFIRM_UI: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Confirmation d'opération en masse",
        "operation_prefix": "Cette action va",
        "items_suffix": "éléments",
        "confirm_question": "Veux-tu continuer ?",
        "mutation_send": "envoyer",
        "mutation_create": "créer",
        "mutation_update": "modifier",
        "mutation_delete": "supprimer",
        "mutation_default": "affecter",
        "operations_header": "Opérations",
        "more_suffix": "de plus",
        "affected_items": "Éléments concernés",
        "and_more": "et {count} autre(s)...",
        "item_date_connector": "le",  # "test le 06 février 2026"
    },
    "en": {
        "title": "Bulk Operation Confirmation",
        "operation_prefix": "This action will",
        "items_suffix": "items",
        "confirm_question": "Do you want to continue?",
        "mutation_send": "send",
        "mutation_create": "create",
        "mutation_update": "update",
        "mutation_delete": "delete",
        "mutation_default": "affect",
        "operations_header": "Operations",
        "more_suffix": "more",
        "affected_items": "Affected items",
        "and_more": "and {count} more...",
        "item_date_connector": "on",  # "test on February 6, 2026"
    },
    "es": {
        "title": "Confirmación de operación masiva",
        "operation_prefix": "Esta acción va a",
        "items_suffix": "elementos",
        "confirm_question": "¿Quieres continuar?",
        "mutation_send": "enviar",
        "mutation_create": "crear",
        "mutation_update": "actualizar",
        "mutation_delete": "eliminar",
        "mutation_default": "afectar",
        "operations_header": "Operaciones",
        "more_suffix": "más",
        "affected_items": "Elementos afectados",
        "and_more": "y {count} más...",
        "item_date_connector": "el",  # "test el 6 de febrero de 2026"
    },
    "de": {
        "title": "Bestätigung der Massenoperation",
        "operation_prefix": "Diese Aktion wird",
        "items_suffix": "Elemente",
        "confirm_question": "Möchtest du fortfahren?",
        "mutation_send": "senden",
        "mutation_create": "erstellen",
        "mutation_update": "aktualisieren",
        "mutation_delete": "löschen",
        "mutation_default": "betreffen",
        "operations_header": "Operationen",
        "more_suffix": "weitere",
        "affected_items": "Betroffene Elemente",
        "and_more": "und {count} weitere...",
        "item_date_connector": "am",  # "test am 6. Februar 2026"
    },
    "it": {
        "title": "Conferma operazione in blocco",
        "operation_prefix": "Questa azione",
        "items_suffix": "elementi",
        "confirm_question": "Vuoi continuare?",
        "mutation_send": "invierà",
        "mutation_create": "creerà",
        "mutation_update": "aggiornerà",
        "mutation_delete": "eliminerà",
        "mutation_default": "modificherà",
        "operations_header": "Operazioni",
        "more_suffix": "altri",
        "affected_items": "Elementi interessati",
        "and_more": "e {count} altri...",
        "item_date_connector": "il",  # "test il 6 febbraio 2026"
    },
    "zh-CN": {
        "title": "批量操作确认",
        "operation_prefix": "此操作将",
        "items_suffix": "个项目",
        "confirm_question": "是否继续？",
        "mutation_send": "发送",
        "mutation_create": "创建",
        "mutation_update": "更新",
        "mutation_delete": "删除",
        "mutation_default": "影响",
        "operations_header": "操作",
        "more_suffix": "更多",
        "affected_items": "受影响的项目",
        "and_more": "以及其他 {count} 项...",
        "item_date_connector": "",  # Chinese uses no connector: "test 2026年2月6日"
    },
}

# =============================================================================
# FOR_EACH EDIT - Messages for item exclusion during bulk confirmation
# =============================================================================
# Used when user wants to exclude specific items from the list
# Example: "remove emails from Guy Savoy" → filters out matching items

_FOR_EACH_EDIT_UI: dict[str, dict[str, str]] = {
    "fr": {
        "exclude_action": "Modifier la liste",
        "items_excluded": "**{count}** élément(s) retiré(s) de la liste.",
        "all_items_excluded": "Tous les éléments ont été retirés. Opération annulée.",
        "filtered_list_header": "Liste mise à jour ({count} éléments restants) :",
        "filter_instruction": "Tu peux retirer des éléments en décrivant lesquels exclure.",
        "no_criteria": "Je n'ai pas compris quels éléments retirer. Peux-tu préciser ?",
    },
    "en": {
        "exclude_action": "Modify list",
        "items_excluded": "**{count}** item(s) removed from the list.",
        "all_items_excluded": "All items have been removed. Operation cancelled.",
        "filtered_list_header": "Updated list ({count} items remaining):",
        "filter_instruction": "You can remove items by describing which ones to exclude.",
        "no_criteria": "I didn't understand which items to remove. Can you clarify?",
    },
    "es": {
        "exclude_action": "Modificar lista",
        "items_excluded": "**{count}** elemento(s) eliminado(s) de la lista.",
        "all_items_excluded": "Todos los elementos han sido eliminados. Operación cancelada.",
        "filtered_list_header": "Lista actualizada ({count} elementos restantes):",
        "filter_instruction": "Puedes eliminar elementos describiendo cuáles excluir.",
        "no_criteria": "No entendí qué elementos eliminar. ¿Puedes aclarar?",
    },
    "de": {
        "exclude_action": "Liste ändern",
        "items_excluded": "**{count}** Element(e) aus der Liste entfernt.",
        "all_items_excluded": "Alle Elemente wurden entfernt. Operation abgebrochen.",
        "filtered_list_header": "Aktualisierte Liste ({count} Elemente verbleibend):",
        "filter_instruction": "Du kannst Elemente entfernen, indem du beschreibst, welche ausgeschlossen werden sollen.",
        "no_criteria": "Ich habe nicht verstanden, welche Elemente entfernt werden sollen. Kannst du das präzisieren?",
    },
    "it": {
        "exclude_action": "Modifica lista",
        "items_excluded": "**{count}** elemento/i rimosso/i dalla lista.",
        "all_items_excluded": "Tutti gli elementi sono stati rimossi. Operazione annullata.",
        "filtered_list_header": "Lista aggiornata ({count} elementi rimanenti):",
        "filter_instruction": "Puoi rimuovere elementi descrivendo quali escludere.",
        "no_criteria": "Non ho capito quali elementi rimuovere. Puoi chiarire?",
    },
    "zh-CN": {
        "exclude_action": "修改列表",
        "items_excluded": "已从列表中移除 **{count}** 个项目。",
        "all_items_excluded": "所有项目已被移除。操作已取消。",
        "filtered_list_header": "更新后的列表（剩余 {count} 个项目）：",
        "filter_instruction": "您可以通过描述要排除的项目来移除它们。",
        "no_criteria": "我不明白要移除哪些项目。您能说明吗？",
    },
}

# =============================================================================
# DESTRUCTIVE CONFIRM - UI labels for destructive operations
# =============================================================================

_DESTRUCTIVE_CONFIRM_UI: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Confirmation requise",
        "affected_items": "Éléments concernés",
        "and_more": "et {count} autre(s)...",
        "default_warning": "Cette action est irréversible.",
        "confirm_question": "Confirmes-tu cette suppression ?",
    },
    "en": {
        "title": "Confirmation required",
        "affected_items": "Affected items",
        "and_more": "and {count} more...",
        "default_warning": "This action cannot be undone.",
        "confirm_question": "Do you confirm this deletion?",
    },
    "es": {
        "title": "Confirmación requerida",
        "affected_items": "Elementos afectados",
        "and_more": "y {count} más...",
        "default_warning": "Esta acción es irreversible.",
        "confirm_question": "¿Confirmas esta eliminación?",
    },
    "de": {
        "title": "Bestätigung erforderlich",
        "affected_items": "Betroffene Elemente",
        "and_more": "und {count} weitere...",
        "default_warning": "Diese Aktion kann nicht rückgängig gemacht werden.",
        "confirm_question": "Bestätigst du diese Löschung?",
    },
    "it": {
        "title": "Conferma richiesta",
        "affected_items": "Elementi interessati",
        "and_more": "e altri {count}...",
        "default_warning": "Questa azione è irreversibile.",
        "confirm_question": "Confermi questa eliminazione?",
    },
    "zh-CN": {
        "title": "需要确认",
        "affected_items": "受影响的项目",
        "and_more": "以及其他 {count} 项...",
        "default_warning": "此操作无法撤销。",
        "confirm_question": "确认删除吗？",
    },
}

# Operation descriptions for destructive confirm
_DESTRUCTIVE_OPERATION_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "fr": {
        "delete_emails": "Tu es sur le point de supprimer **{count} email(s)**.",
        "delete_contacts": "Tu es sur le point de supprimer **{count} contact(s)**.",
        "delete_events": "Tu es sur le point de supprimer **{count} événement(s)**.",
        "delete_tasks": "Tu es sur le point de supprimer **{count} tâche(s)**.",
        "delete_files": "Tu es sur le point de supprimer **{count} fichier(s)**.",
        "delete_labels": "Tu es sur le point de supprimer **{count} label(s)**.",
        "unknown": "Tu es sur le point d'effectuer une opération sur **{count} élément(s)**.",
    },
    "en": {
        "delete_emails": "You are about to delete **{count} email(s)**.",
        "delete_contacts": "You are about to delete **{count} contact(s)**.",
        "delete_events": "You are about to delete **{count} event(s)**.",
        "delete_tasks": "You are about to delete **{count} task(s)**.",
        "delete_files": "You are about to delete **{count} file(s)**.",
        "delete_labels": "You are about to delete **{count} label(s)**.",
        "unknown": "You are about to perform an operation on **{count} item(s)**.",
    },
    "es": {
        "delete_emails": "Estás a punto de eliminar **{count} email(s)**.",
        "delete_contacts": "Estás a punto de eliminar **{count} contacto(s)**.",
        "delete_events": "Estás a punto de eliminar **{count} evento(s)**.",
        "delete_tasks": "Estás a punto de eliminar **{count} tarea(s)**.",
        "delete_files": "Estás a punto de eliminar **{count} archivo(s)**.",
        "delete_labels": "Estás a punto de eliminar **{count} etiqueta(s)**.",
        "unknown": "Estás a punto de realizar una operación en **{count} elemento(s)**.",
    },
    "de": {
        "delete_emails": "Du bist dabei, **{count} E-Mail(s)** zu löschen.",
        "delete_contacts": "Du bist dabei, **{count} Kontakt(e)** zu löschen.",
        "delete_events": "Du bist dabei, **{count} Termin(e)** zu löschen.",
        "delete_tasks": "Du bist dabei, **{count} Aufgabe(n)** zu löschen.",
        "delete_files": "Du bist dabei, **{count} Datei(en)** zu löschen.",
        "delete_labels": "Du bist dabei, **{count} Label(s)** zu löschen.",
        "unknown": "Du bist dabei, eine Operation an **{count} Element(en)** durchzuführen.",
    },
    "it": {
        "delete_emails": "Stai per eliminare **{count} email**.",
        "delete_contacts": "Stai per eliminare **{count} contatto/i**.",
        "delete_events": "Stai per eliminare **{count} evento/i**.",
        "delete_tasks": "Stai per eliminare **{count} attività**.",
        "delete_files": "Stai per eliminare **{count} file**.",
        "delete_labels": "Stai per eliminare **{count} etichetta/e**.",
        "unknown": "Stai per eseguire un'operazione su **{count} elemento/i**.",
    },
    "zh-CN": {
        "delete_emails": "您即将删除 **{count} 封邮件**。",
        "delete_contacts": "您即将删除 **{count} 个联系人**。",
        "delete_events": "您即将删除 **{count} 个日程**。",
        "delete_tasks": "您即将删除 **{count} 个任务**。",
        "delete_files": "您即将删除 **{count} 个文件**。",
        "delete_labels": "您即将删除 **{count} 个标签**。",
        "unknown": "您即将对 **{count} 个项目** 执行操作。",
    },
}

# =============================================================================
# INSUFFICIENT CONTENT - Clarification questions when content is missing
# =============================================================================

# Questions per domain when content is insufficient
_INSUFFICIENT_CONTENT_QUESTIONS: dict[str, dict[str, str]] = {
    "email": {
        "fr": "Que souhaites-tu écrire dans cet email ?",
        "en": "What would you like to write in this email?",
        "es": "¿Qué quieres escribir en este email?",
        "de": "Was möchtest du in diese E-Mail schreiben?",
        "it": "Cosa vuoi scrivere in questa email?",
        "zh-CN": "您想在这封邮件中写什么？",
    },
    "email_subject": {
        "fr": "Quel est le sujet de cet email ?",
        "en": "What is the subject of this email?",
        "es": "¿Cuál es el asunto de este email?",
        "de": "Was ist der Betreff dieser E-Mail?",
        "it": "Qual è l'oggetto di questa email?",
        "zh-CN": "这封邮件的主题是什么？",
    },
    "event": {
        "fr": "De quoi s'agit-il pour cet événement ? (titre, description...)",
        "en": "What is this event about? (title, description...)",
        "es": "¿De qué trata este evento? (título, descripción...)",
        "de": "Worum geht es bei diesem Termin? (Titel, Beschreibung...)",
        "it": "Di cosa tratta questo evento? (titolo, descrizione...)",
        "zh-CN": "这个活动是关于什么的？（标题、描述...）",
    },
    "task": {
        "fr": "Quelle est cette tâche ? (titre, description...)",
        "en": "What is this task about? (title, description...)",
        "es": "¿De qué trata esta tarea? (título, descripción...)",
        "de": "Was ist diese Aufgabe? (Titel, Beschreibung...)",
        "it": "Di cosa tratta questa attività? (titolo, descrizione...)",
        "zh-CN": "这个任务是关于什么的？（标题、描述...）",
    },
    "contact": {
        "fr": "Quelles informations veux-tu ajouter pour ce contact ?",
        "en": "What information would you like to add for this contact?",
        "es": "¿Qué información quieres añadir para este contacto?",
        "de": "Welche Informationen möchtest du für diesen Kontakt hinzufügen?",
        "it": "Quali informazioni vuoi aggiungere per questo contatto?",
        "zh-CN": "您想为这个联系人添加什么信息？",
    },
}

# Generic fallback for unknown domains
_INSUFFICIENT_CONTENT_GENERIC: dict[str, str] = {
    "fr": "Peux-tu me donner plus de détails sur ce que tu souhaites faire ?",
    "en": "Can you give me more details about what you want to do?",
    "es": "¿Puedes darme más detalles sobre lo que quieres hacer?",
    "de": "Kannst du mir mehr Details geben, was du tun möchtest?",
    "it": "Puoi darmi più dettagli su cosa vuoi fare?",
    "zh-CN": "你能告诉我更多关于你想做什么的细节吗？",
}

# =============================================================================
# INSUFFICIENT CONTENT FIELD-SPECIFIC QUESTIONS
# =============================================================================
# Questions for each specific field, used in multi-turn clarification flow.
# Format: "{domain}.{field}": {language: question}
# Fields are asked in priority order defined in constants.INSUFFICIENT_CONTENT_REQUIRED_FIELDS

_INSUFFICIENT_CONTENT_FIELD_QUESTIONS: dict[str, dict[str, str]] = {
    # Email fields (priority: recipient > subject > body)
    "email.recipient": {
        "fr": "À qui veux-tu envoyer cet email ?",
        "en": "Who do you want to send this email to?",
        "es": "¿A quién quieres enviar este email?",
        "de": "An wen möchtest du diese E-Mail senden?",
        "it": "A chi vuoi inviare questa email?",
        "zh-CN": "您想把这封邮件发给谁？",
    },
    "email.subject": {
        "fr": "Quel est le sujet de cet email ?",
        "en": "What is the subject of this email?",
        "es": "¿Cuál es el asunto de este email?",
        "de": "Was ist der Betreff dieser E-Mail?",
        "it": "Qual è l'oggetto di questa email?",
        "zh-CN": "这封邮件的主题是什么？",
    },
    "email.body": {
        "fr": "Que souhaites-tu écrire dans cet email ?",
        "en": "What would you like to write in this email?",
        "es": "¿Qué quieres escribir en este email?",
        "de": "Was möchtest du in diese E-Mail schreiben?",
        "it": "Cosa vuoi scrivere in questa email?",
        "zh-CN": "您想在这封邮件中写什么？",
    },
    # Event fields (priority: title > start_datetime > end_or_duration)
    "event.title": {
        "fr": "Quel est le titre de cet événement ?",
        "en": "What is the title of this event?",
        "es": "¿Cuál es el título de este evento?",
        "de": "Was ist der Titel dieses Termins?",
        "it": "Qual è il titolo di questo evento?",
        "zh-CN": "这个活动的标题是什么？",
    },
    "event.start_datetime": {
        "fr": "Quand commence cet événement ?",
        "en": "When does this event start?",
        "es": "¿Cuándo empieza este evento?",
        "de": "Wann beginnt dieser Termin?",
        "it": "Quando inizia questo evento?",
        "zh-CN": "这个活动什么时候开始？",
    },
    "event.end_or_duration": {
        "fr": "Quelle est la durée ou l'heure de fin ?",
        "en": "What is the duration or end time?",
        "es": "¿Cuál es la duración o la hora de fin?",
        "de": "Wie lange dauert es oder wann endet es?",
        "it": "Qual è la durata o l'ora di fine?",
        "zh-CN": "持续多长时间或结束时间是什么？",
    },
    # Task fields (priority: title > priority > due_date)
    "task.title": {
        "fr": "Quel est le titre de cette tâche ?",
        "en": "What is the title of this task?",
        "es": "¿Cuál es el título de esta tarea?",
        "de": "Was ist der Titel dieser Aufgabe?",
        "it": "Qual è il titolo di questa attività?",
        "zh-CN": "这个任务的标题是什么？",
    },
    "task.priority": {
        "fr": "Quelle est la priorité de cette tâche ?",
        "en": "What is the priority of this task?",
        "es": "¿Cuál es la prioridad de esta tarea?",
        "de": "Welche Priorität hat diese Aufgabe?",
        "it": "Qual è la priorità di questa attività?",
        "zh-CN": "这个任务的优先级是什么？",
    },
    "task.due_date": {
        "fr": "Pour quand est cette tâche ?",
        "en": "When is this task due?",
        "es": "¿Para cuándo es esta tarea?",
        "de": "Bis wann ist diese Aufgabe fällig?",
        "it": "Per quando è questa attività?",
        "zh-CN": "这个任务的截止日期是什么时候？",
    },
    # Contact fields (priority: name > email > phone)
    "contact.name": {
        "fr": "Quel est le nom complet de ce contact ?",
        "en": "What is the full name of this contact?",
        "es": "¿Cuál es el nombre completo de este contacto?",
        "de": "Wie ist der vollständige Name dieses Kontakts?",
        "it": "Qual è il nome completo di questo contatto?",
        "zh-CN": "这个联系人的全名是什么？",
    },
    "contact.email": {
        "fr": "Quelle est l'adresse email de ce contact ?",
        "en": "What is the email address of this contact?",
        "es": "¿Cuál es el email de este contacto?",
        "de": "Wie ist die E-Mail-Adresse dieses Kontakts?",
        "it": "Qual è l'email di questo contatto?",
        "zh-CN": "这个联系人的电子邮件地址是什么？",
    },
    "contact.phone": {
        "fr": "Quel est le numéro de téléphone de ce contact ?",
        "en": "What is the phone number of this contact?",
        "es": "¿Cuál es el teléfono de este contacto?",
        "de": "Wie ist die Telefonnummer dieses Kontakts?",
        "it": "Qual è il numero di telefono di questo contatto?",
        "zh-CN": "这个联系人的电话号码是什么？",
    },
}

# =============================================================================
# ENUMERATED FIELD OPTIONS WITH I18N LABELS
# =============================================================================
# For fields with predefined options (like priority), provide translated labels.
# Format: "{domain}.{field}": {option_value: {language: label}}

_FIELD_OPTION_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "task.priority": {
        "high": {
            "fr": "Haute",
            "en": "High",
            "es": "Alta",
            "de": "Hoch",
            "it": "Alta",
            "zh-CN": "高",
        },
        "medium": {
            "fr": "Moyenne",
            "en": "Medium",
            "es": "Media",
            "de": "Mittel",
            "it": "Media",
            "zh-CN": "中",
        },
        "low": {
            "fr": "Basse",
            "en": "Low",
            "es": "Baja",
            "de": "Niedrig",
            "it": "Bassa",
            "zh-CN": "低",
        },
    },
}

# =============================================================================
# INSUFFICIENT CONTENT DETECTION PATTERNS (per language)
# =============================================================================
# Patterns that indicate a mutation request WITHOUT content.
# Used to detect if user needs clarification before planning.
# These are "trigger patterns" - if query matches and has little remaining text,
# we ask for clarification.
#
# Format: {domain: [list of trigger patterns per language]}
# The detector removes these patterns and checks remaining content length.

_INSUFFICIENT_CONTENT_PATTERNS: dict[str, list[str]] = {
    # Email send patterns - detect "send email to X" without content
    "email": [
        # French
        "envoie un email à",
        "envoie un mail à",
        "envoie email à",
        "envoie mail à",
        "envoyer un email à",
        "envoyer un mail à",
        "email à",
        "mail à",
        "écris un email à",
        "écris un mail à",
        # English
        "send an email to",
        "send email to",
        "send a mail to",
        "send mail to",
        "write an email to",
        "write email to",
        "email to",
        "mail to",
        # Spanish
        "envía un email a",
        "envía un correo a",
        "enviar un email a",
        "enviar un correo a",
        "escribe un email a",
        "escribe un correo a",
        # German
        "schicke eine email an",
        "schicke eine e-mail an",
        "sende eine email an",
        "sende eine e-mail an",
        "email an",
        "e-mail an",
        "schreibe eine email an",
        # Italian
        "invia una email a",
        "invia un'email a",
        "invia una mail a",
        "manda una email a",
        "manda una mail a",
        "scrivi una email a",
        # Chinese
        "发邮件给",
        "发送邮件给",
        "给发邮件",
        "写邮件给",
    ],
    # Event creation patterns - detect "create event with X" without details
    "event": [
        # French
        "crée un événement avec",
        "crée un rdv avec",
        "créer un événement avec",
        "créer un rdv avec",
        "planifie un rdv avec",
        "programme un rdv avec",
        "ajoute un événement avec",
        # English
        "create an event with",
        "create event with",
        "schedule a meeting with",
        "schedule meeting with",
        "plan a meeting with",
        "add an event with",
        # Spanish
        "crea un evento con",
        "crear un evento con",
        "programa una reunión con",
        "planifica una cita con",
        # German
        "erstelle einen termin mit",
        "erstelle ein ereignis mit",
        "plane ein treffen mit",
        "termin mit",
        # Italian
        "crea un evento con",
        "creare un evento con",
        "pianifica un incontro con",
        "programma un appuntamento con",
        # Chinese
        "创建活动与",
        "安排会议与",
        "预约与",
    ],
    # Task creation patterns
    "task": [
        # French
        "crée une tâche",
        "créer une tâche",
        "ajoute une tâche",
        "nouvelle tâche",
        # English
        "create a task",
        "create task",
        "add a task",
        "new task",
        # Spanish
        "crea una tarea",
        "crear una tarea",
        "añade una tarea",
        "nueva tarea",
        # German
        "erstelle eine aufgabe",
        "neue aufgabe",
        "aufgabe hinzufügen",
        # Italian
        "crea un'attività",
        "creare un'attività",
        "aggiungi un'attività",
        "nuova attività",
        # Chinese
        "创建任务",
        "新建任务",
        "添加任务",
    ],
    # Contact creation patterns
    "contact": [
        # French
        "crée un contact",
        "créer un contact",
        "ajoute un contact",
        "nouveau contact",
        # English
        "create a contact",
        "create contact",
        "add a contact",
        "new contact",
        # Spanish
        "crea un contacto",
        "crear un contacto",
        "añade un contacto",
        "nuevo contacto",
        # German
        "erstelle einen kontakt",
        "neuer kontakt",
        "kontakt hinzufügen",
        # Italian
        "crea un contatto",
        "creare un contatto",
        "aggiungi un contatto",
        "nuovo contatto",
        # Chinese
        "创建联系人",
        "新建联系人",
        "添加联系人",
    ],
}

# =============================================================================
# EARLY RECIPIENT DETECTION - Pre-planner recipient presence check
# =============================================================================
# Patterns to detect if a recipient is mentioned in the (English) request.
# Used by detect_early_insufficient_content() after Semantic Pivot (English).
#
# Note: These patterns check the ENGLISH version of the request since
# the Semantic Pivot translates to English before this detection runs.
# =============================================================================

EARLY_RECIPIENT_PATTERNS: list[str] = [" to ", " for "]

# =============================================================================
# DRAFT TYPE EMOJIS - Visual icons for draft types
# =============================================================================

DRAFT_TYPE_EMOJIS: dict[str, str] = {
    # Email
    "email": "✉️",
    # Calendar events
    "event": "📅",
    "event_update": "📝📅",
    "event_delete": "🗑️📅",
    # Contacts
    "contact": "👤",
    "contact_update": "📝👤",
    "contact_delete": "🗑️👤",
    # Tasks
    "task": "✅",
    "task_update": "📝✅",
    "task_delete": "🗑️✅",
    # Drive files
    "file_delete": "🗑️📁",
    # Labels
    "label_delete": "🗑️🏷️",
    # Future
    "note": "📝",
}

# =============================================================================
# DRAFT SUMMARIES - Templates for draft type summaries
# =============================================================================

# Format: {draft_type: {language: template_string}}
# Templates use Python format strings with named placeholders
_DRAFT_SUMMARIES: dict[str, dict[str, str]] = {
    "email": {
        "fr": 'Email pour {to}, sujet: "{subject}"',
        "en": 'Email to {to}, subject: "{subject}"',
        "es": 'Email para {to}, asunto: "{subject}"',
        "de": 'E-Mail an {to}, Betreff: "{subject}"',
        "it": 'Email a {to}, oggetto: "{subject}"',
        "zh-CN": '发送邮件给 {to}，主题："{subject}"',
    },
    "event": {
        "fr": 'Événement "{summary}" le {start}',
        "en": 'Event "{summary}" on {start}',
        "es": 'Evento "{summary}" el {start}',
        "de": 'Termin "{summary}" am {start}',
        "it": 'Evento "{summary}" il {start}',
        "zh-CN": '活动"{summary}"于 {start}',
    },
    "event_update": {
        "fr": 'Modification événement: "{summary}"',
        "en": 'Update event: "{summary}"',
        "es": 'Modificación evento: "{summary}"',
        "de": 'Termin aktualisieren: "{summary}"',
        "it": 'Modifica evento: "{summary}"',
        "zh-CN": '更新活动："{summary}"',
    },
    "event_delete": {
        "fr": 'Suppression événement: "{summary}"',
        "en": 'Delete event: "{summary}"',
        "es": 'Eliminación evento: "{summary}"',
        "de": 'Termin löschen: "{summary}"',
        "it": 'Elimina evento: "{summary}"',
        "zh-CN": '删除活动："{summary}"',
    },
    "contact": {
        "fr": "Contact: {name}{email_part}",
        "en": "Contact: {name}{email_part}",
        "es": "Contacto: {name}{email_part}",
        "de": "Kontakt: {name}{email_part}",
        "it": "Contatto: {name}{email_part}",
        "zh-CN": "联系人：{name}{email_part}",
    },
    "contact_update": {
        "fr": "Modification contact: {name}",
        "en": "Update contact: {name}",
        "es": "Modificación contacto: {name}",
        "de": "Kontakt aktualisieren: {name}",
        "it": "Modifica contatto: {name}",
        "zh-CN": "更新联系人：{name}",
    },
    "contact_delete": {
        "fr": "Suppression contact: {name}",
        "en": "Delete contact: {name}",
        "es": "Eliminación contacto: {name}",
        "de": "Kontakt löschen: {name}",
        "it": "Elimina contatto: {name}",
        "zh-CN": "删除联系人：{name}",
    },
    "task": {
        "fr": 'Tâche: "{title}"',
        "en": 'Task: "{title}"',
        "es": 'Tarea: "{title}"',
        "de": 'Aufgabe: "{title}"',
        "it": 'Attività: "{title}"',
        "zh-CN": '任务："{title}"',
    },
    "task_update": {
        "fr": 'Modification tâche: "{title}"',
        "en": 'Update task: "{title}"',
        "es": 'Modificación tarea: "{title}"',
        "de": 'Aufgabe aktualisieren: "{title}"',
        "it": 'Modifica attività: "{title}"',
        "zh-CN": '更新任务："{title}"',
    },
    "task_delete": {
        "fr": 'Suppression tâche: "{title}"',
        "en": 'Delete task: "{title}"',
        "es": 'Eliminación tarea: "{title}"',
        "de": 'Aufgabe löschen: "{title}"',
        "it": 'Elimina attività: "{title}"',
        "zh-CN": '删除任务："{title}"',
    },
    "file_delete": {
        "fr": 'Suppression fichier: "{name}"',
        "en": 'Delete file: "{name}"',
        "es": 'Eliminación archivo: "{name}"',
        "de": 'Datei löschen: "{name}"',
        "it": 'Elimina file: "{name}"',
        "zh-CN": '删除文件："{name}"',
    },
    "label_delete": {
        "fr": 'Suppression label: "{name}"',
        "en": 'Delete label: "{name}"',
        "es": 'Eliminación etiqueta: "{name}"',
        "de": 'Label löschen: "{name}"',
        "it": 'Elimina etichetta: "{name}"',
        "zh-CN": '删除标签："{name}"',
    },
}

# =============================================================================
# ACTION DESCRIPTIONS - Extended descriptions for action buttons
# =============================================================================

_ACTION_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "fr": {
        "confirm": "exécuter maintenant",
        "edit": "modifier le contenu",
        "cancel": "abandonner",
    },
    "en": {
        "confirm": "execute now",
        "edit": "modify content",
        "cancel": "abort",
    },
    "es": {
        "confirm": "ejecutar ahora",
        "edit": "modificar contenido",
        "cancel": "abandonar",
    },
    "de": {
        "confirm": "jetzt ausführen",
        "edit": "Inhalt bearbeiten",
        "cancel": "abbrechen",
    },
    "it": {
        "confirm": "esegui ora",
        "edit": "modifica contenuto",
        "cancel": "annulla",
    },
    "zh-CN": {
        "confirm": "立即执行",
        "edit": "修改内容",
        "cancel": "放弃",
    },
}

# =============================================================================
# DEFAULT PERSONALITY INSTRUCTIONS
# =============================================================================
# Fallback personality instructions for LLM when no custom personality is provided.
# Used in HITL question generators to maintain consistent assistant behavior.

_DEFAULT_PERSONALITY: dict[str, str] = {
    "fr": """Tu es un assistant équilibré et professionnel.
- Réponds de manière claire et concise.
- Adapte ton ton au contexte de la conversation.
- Sois utile sans être excessif.""",
    "en": """You are a balanced and professional assistant.
- Respond in a clear and concise manner.
- Adapt your tone to the context of the conversation.
- Be helpful without being excessive.""",
    "es": """Eres un asistente equilibrado y profesional.
- Responde de manera clara y concisa.
- Adapta tu tono al contexto de la conversación.
- Sé útil sin ser excesivo.""",
    "de": """Du bist ein ausgewogener und professioneller Assistent.
- Antworte klar und prägnant.
- Passe deinen Ton dem Kontext des Gesprächs an.
- Sei hilfreich, ohne übertrieben zu sein.""",
    "it": """Sei un assistente equilibrato e professionale.
- Rispondi in modo chiaro e conciso.
- Adatta il tuo tono al contesto della conversazione.
- Sii utile senza essere eccessivo.""",
    "zh-CN": """你是一个平衡且专业的助手。
- 以清晰简洁的方式回答。
- 根据对话的上下文调整你的语气。
- 提供帮助但不要过度。""",
}


class HitlMessages:
    """
    Centralized HITL message provider.

    Provides all translated strings for HITL interactions across all 6 languages.
    Falls back to English if requested language is not available.

    Example:
        >>> HitlMessages.get_fallback(HitlMessageType.PLAN_APPROVAL, "de")
        "Dieser Plan erfordert deine Genehmigung. Bestätigst du, um fortzufahren?"

        >>> HitlMessages.get_action_label("confirm", "it")
        "Conferma"
    """

    @staticmethod
    def _normalize_language(language: str) -> str:
        """
        Normalize language code to supported format.

        Handles variations like 'zh', 'zh_CN', 'zh-cn' -> 'zh-CN'

        Args:
            language: Input language code

        Returns:
            Normalized language code
        """
        if not language:
            return DEFAULT_LANGUAGE

        lang_lower = language.lower().replace("_", "-")

        # Handle Chinese variants
        if lang_lower.startswith("zh"):
            return "zh-CN"

        # Extract base language code
        base_lang = lang_lower.split("-")[0]

        # Check if it's a supported language (uses centralized SUPPORTED_LANGUAGES)
        if base_lang in SUPPORTED_LANGUAGES:
            return base_lang

        return DEFAULT_LANGUAGE

    @staticmethod
    def get_fallback(message_type: HitlMessageType, language: str) -> str:
        """
        Get fallback message for HITL interaction type.

        Args:
            message_type: Type of HITL interaction
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Fallback message in requested language
        """
        lang = HitlMessages._normalize_language(language)
        messages = _FALLBACK_MESSAGES.get(message_type, {})
        return messages.get(lang, messages.get("en", ""))

    @staticmethod
    def get_action_label(action: str, language: str) -> str:
        """
        Get action button label.

        Args:
            action: Action name (confirm, edit, cancel)
            language: Language code

        Returns:
            Translated action label
        """
        lang = HitlMessages._normalize_language(language)
        labels = _ACTION_LABELS.get(lang, _ACTION_LABELS["en"])
        return labels.get(action, action)

    @staticmethod
    def get_action_labels(language: str) -> dict[str, str]:
        """
        Get all action labels for a language.

        Args:
            language: Language code

        Returns:
            Dict with confirm, edit, cancel labels
        """
        lang = HitlMessages._normalize_language(language)
        return _ACTION_LABELS.get(lang, _ACTION_LABELS["en"])

    @staticmethod
    def get_action_prompt(language: str) -> str:
        """
        Get action prompt ("What would you like to do?").

        Args:
            language: Language code

        Returns:
            Translated action prompt
        """
        lang = HitlMessages._normalize_language(language)
        return _ACTION_PROMPTS.get(lang, _ACTION_PROMPTS["en"])

    @staticmethod
    def get_action_description(action: str, language: str) -> str:
        """
        Get action description for extended button text.

        Args:
            action: Action name (confirm, edit, cancel)
            language: Language code

        Returns:
            Translated action description
        """
        lang = HitlMessages._normalize_language(language)
        descriptions = _ACTION_DESCRIPTIONS.get(lang, _ACTION_DESCRIPTIONS["en"])
        return descriptions.get(action, "")

    @staticmethod
    def get_clarification_header(language: str) -> str:
        """
        Get clarification multi-question header.

        Args:
            language: Language code

        Returns:
            Translated header for multiple clarification questions
        """
        lang = HitlMessages._normalize_language(language)
        return _CLARIFICATION_HEADERS.get(lang, _CLARIFICATION_HEADERS["en"])

    @staticmethod
    def get_draft_emoji(draft_type: str) -> str:
        """
        Get emoji for draft type.

        Args:
            draft_type: Type of draft (email, event, contact, etc.)

        Returns:
            Emoji string for the draft type
        """
        return DRAFT_TYPE_EMOJIS.get(draft_type, "")

    @staticmethod
    def get_draft_summary(
        draft_type: str,
        language: str,
        **kwargs: Any,
    ) -> str:
        """
        Get formatted draft summary.

        Args:
            draft_type: Type of draft (email, event, contact, etc.)
            language: Language code
            **kwargs: Template variables (to, subject, name, summary, etc.)

        Returns:
            Formatted draft summary string

        Example:
            >>> HitlMessages.get_draft_summary("email", "fr", to="jean@ex.com", subject="RDV")
            'Email pour jean@ex.com, sujet: "RDV"'
        """
        lang = HitlMessages._normalize_language(language)

        templates = _DRAFT_SUMMARIES.get(draft_type, {})
        template = templates.get(lang, templates.get("en", ""))

        if not template:
            # Fallback to generic message
            return HitlMessages.get_fallback(HitlMessageType.DRAFT_CRITIQUE, language)

        # Handle optional email_part for contacts
        if "email_part" not in kwargs and "email" in kwargs:
            email = kwargs.pop("email", "")
            kwargs["email_part"] = f" ({email})" if email else ""
        elif "email_part" not in kwargs:
            kwargs["email_part"] = ""

        try:
            return template.format(**kwargs)
        except KeyError:
            # If template variables missing, return template as-is
            return template

    @staticmethod
    def format_draft_critique_actions(
        language: str,
        include_descriptions: bool = True,
    ) -> str:
        """
        Format the action buttons section for draft critique.

        Args:
            language: Language code
            include_descriptions: Whether to include action descriptions

        Returns:
            Formatted HTML string with action buttons
        """
        lang = HitlMessages._normalize_language(language)
        labels = HitlMessages.get_action_labels(lang)
        prompt = HitlMessages.get_action_prompt(lang)

        if include_descriptions:
            descriptions = _ACTION_DESCRIPTIONS.get(lang, _ACTION_DESCRIPTIONS["en"])
            return f"""
{prompt}<br/>
- ✅ **{labels["confirm"]}** : {descriptions["confirm"]}<br/>
- ✏️ **{labels["edit"]}** : {descriptions["edit"]}<br/>
- 🚫 **{labels["cancel"]}** : {descriptions["cancel"]}<br/>"""
        else:
            return f"""
{prompt}<br/>
- ✅ **{labels["confirm"]}**<br/>
- ✏️ **{labels["edit"]}**<br/>
- 🚫 **{labels["cancel"]}**<br/>"""

    @staticmethod
    def format_clarification_questions(
        questions: list[str],
        language: str,
    ) -> str:
        """
        Format multiple clarification questions into a single message.

        Args:
            questions: List of clarification questions
            language: Language code

        Returns:
            Formatted question string with numbered list
        """
        if not questions:
            return HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, language)

        if len(questions) == 1:
            return questions[0]

        # Multiple questions: Format as numbered list
        header = HitlMessages.get_clarification_header(language)
        formatted_questions = "<br/>".join([f"{i + 1}. {q}" for i, q in enumerate(questions)])

        return header + formatted_questions

    @staticmethod
    def format_disambiguation_question(
        disambiguation_type: str,
        domain: str,
        original_query: str,
        intended_action: str,
        candidates: list[dict[str, Any]],
        target_field: str,
        language: str,
    ) -> str:
        """
        Format disambiguation question with numbered choices.

        Creates a user-friendly question with clear numbered options for entity
        or field disambiguation scenarios.

        Args:
            disambiguation_type: "multiple_entities" or "multiple_fields"
            domain: Entity domain (contacts, emails, events, tasks, files)
            original_query: User's original search term
            intended_action: What action the user wants to perform (send_email, etc.)
            candidates: List of candidate items with display info
            target_field: For multiple_fields, which field type (email, phone, address)
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Formatted question string with numbered choices

        Example output (fr, multiple_entities):
            J'ai trouvé plusieurs "Jean Dupont" :

            1. Jean Dupont (jean@work.com)
            2. Jean-Pierre Dupont (jp@home.com)

            Indique le numéro de ton choix (ex: 1, 2...):

        Example output (fr, multiple_fields):
            Jean Dupont a plusieurs adresse emails. Lequel veux-tu utiliser ?

            1. jean@work.com
            2. jean.dupont@personal.com

            Indique le numéro de ton choix (ex: 1, 2...):
        """
        lang = HitlMessages._normalize_language(language)

        if not candidates:
            return HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, language)

        # Build header based on disambiguation type
        if disambiguation_type == "multiple_fields":
            # Multiple fields for one entity (e.g., multiple emails)
            contact_name = (
                candidates[0].get("parent_name", original_query) if candidates else original_query
            )
            field_type_labels = _FIELD_TYPE_LABELS.get(target_field, {})
            field_type_label = field_type_labels.get(lang, target_field)

            header_template = _DISAMBIGUATION_MULTIPLE_FIELDS.get(
                lang, _DISAMBIGUATION_MULTIPLE_FIELDS["en"]
            )
            header = header_template.format(name=contact_name, field_type=field_type_label)
        else:
            # Multiple entities (default)
            header_template = _DISAMBIGUATION_MULTIPLE_ENTITIES.get(
                lang, _DISAMBIGUATION_MULTIPLE_ENTITIES["en"]
            )
            header = header_template.format(query=original_query)

        # Build numbered choices
        choices = []
        for i, candidate in enumerate(candidates, 1):
            choice_line = HitlMessages._format_candidate_line(candidate, i, domain, lang)
            choices.append(choice_line)

        choices_text = "\n".join(choices)

        # Add selection prompt
        prompt = _DISAMBIGUATION_CHOICE_PROMPT.get(lang, _DISAMBIGUATION_CHOICE_PROMPT["en"])

        return f"{header}\n\n{choices_text}{prompt}"

    @staticmethod
    def _format_candidate_line(
        candidate: dict[str, Any],
        index: int,
        domain: str,
        language: str,
    ) -> str:
        """
        Format a single candidate line for disambiguation display.

        Args:
            candidate: Candidate item dict with display info
            index: 1-based index for display
            domain: Entity domain for formatting
            language: Language code

        Returns:
            Formatted candidate line (e.g., "1. Jean Dupont (jean@work.com)")
        """
        # Extract display fields based on domain and available data
        name = candidate.get("name") or candidate.get("display_name") or candidate.get("value", "")

        # Build detail parts (email, phone, etc.)
        details = []

        # For contacts domain, show email/phone if available
        if domain == "contacts":
            email = candidate.get("email") or candidate.get("primary_email", "")
            if email:
                details.append(email)
            phone = candidate.get("phone") or candidate.get("primary_phone", "")
            if phone and not email:
                details.append(phone)

        # For emails domain, show subject/from
        elif domain == "emails":
            subject = candidate.get("subject", "")
            if subject:
                # Truncate long subjects
                if len(subject) > 40:
                    subject = subject[:37] + "..."
                details.append(f'"{subject}"')
            sender = candidate.get("from") or candidate.get("sender", "")
            if sender:
                details.append(f"de {sender}")

        # For events domain, show date/time
        elif domain == "events":
            start = candidate.get("start") or candidate.get("start_time", "")
            if start:
                details.append(start)

        # For tasks domain, show due date
        elif domain == "tasks":
            due = candidate.get("due") or candidate.get("due_date", "")
            if due:
                details.append(f"due: {due}")

        # For field disambiguation (multiple emails/phones), name IS the value
        if not name and candidate.get("value"):
            name = candidate.get("value", "")

        # Format the line
        if details:
            details_str = ", ".join(details)
            return f"**{index}.** {name} ({details_str})"
        else:
            return f"**{index}.** {name}"

    @staticmethod
    def get_domain_label(domain: str, language: str) -> str:
        """
        Get translated domain label.

        Args:
            domain: Domain identifier (contacts, emails, events, tasks, files)
            language: Language code

        Returns:
            Translated domain label
        """
        lang = HitlMessages._normalize_language(language)
        domain_labels = _DOMAIN_LABELS.get(domain, {})
        return domain_labels.get(lang, domain)

    @staticmethod
    def get_field_type_label(field_type: str, language: str) -> str:
        """
        Get translated field type label.

        Args:
            field_type: Field type identifier (email, phone, address)
            language: Language code

        Returns:
            Translated field type label
        """
        lang = HitlMessages._normalize_language(language)
        field_labels = _FIELD_TYPE_LABELS.get(field_type, {})
        return field_labels.get(lang, field_type)

    # =========================================================================
    # INSUFFICIENT CONTENT METHODS
    # =========================================================================

    @staticmethod
    def get_insufficient_content_question(domain: str, language: str) -> str:
        """
        Get clarification question for insufficient content.

        Used when a mutation tool is called without sufficient content parameters
        (e.g., "send email to marie" without body/subject).

        Args:
            domain: Domain identifier (email, event, task, contact)
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Translated clarification question

        Example:
            >>> HitlMessages.get_insufficient_content_question("email", "fr")
            "Que souhaites-tu écrire dans cet email ?"
        """
        lang = HitlMessages._normalize_language(language)

        # Check domain-specific questions
        domain_questions = _INSUFFICIENT_CONTENT_QUESTIONS.get(domain, {})
        if domain_questions:
            return domain_questions.get(lang, domain_questions.get("en", ""))

        # Fallback to generic question
        return _INSUFFICIENT_CONTENT_GENERIC.get(lang, _INSUFFICIENT_CONTENT_GENERIC["en"])

    @staticmethod
    def get_insufficient_content_patterns(domain: str) -> list[str]:
        """
        Get detection patterns for insufficient content by domain.

        These patterns help detect when a user request lacks content.
        All supported languages are included in the pattern list.

        Args:
            domain: Domain identifier (email, event, task, contact)

        Returns:
            List of detection patterns across all languages

        Example:
            >>> patterns = HitlMessages.get_insufficient_content_patterns("email")
            >>> "envoie un email à" in patterns
            True
            >>> "send email to" in patterns
            True
        """
        return _INSUFFICIENT_CONTENT_PATTERNS.get(domain, [])

    @staticmethod
    def get_field_question(domain: str, field: str, language: str) -> str:
        """
        Get field-specific clarification question.

        Used in multi-turn clarification flow to ask for specific missing fields
        in priority order.

        Args:
            domain: Domain identifier (email, event, task, contact)
            field: Field identifier (recipient, subject, body, title, etc.)
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Translated field-specific question

        Example:
            >>> HitlMessages.get_field_question("email", "recipient", "fr")
            "À qui veux-tu envoyer cet email ?"
            >>> HitlMessages.get_field_question("task", "priority", "en")
            "What is the priority of this task?"
        """
        lang = HitlMessages._normalize_language(language)
        key = f"{domain}.{field}"

        field_questions = _INSUFFICIENT_CONTENT_FIELD_QUESTIONS.get(key, {})
        if field_questions:
            return field_questions.get(lang, field_questions.get("en", ""))

        # Fallback to domain-level question
        return HitlMessages.get_insufficient_content_question(domain, language)

    @staticmethod
    def get_field_options(
        domain: str,
        field: str,
        language: str,
    ) -> list[dict[str, str]] | None:
        """
        Get enumerated options for a field with i18n labels.

        For fields with predefined values (like priority), returns the available
        options with translated labels for display.

        Args:
            domain: Domain identifier (email, event, task, contact)
            field: Field identifier (priority, etc.)
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            List of {value, label} dicts if field has options, None otherwise

        Example:
            >>> HitlMessages.get_field_options("task", "priority", "fr")
            [
                {"value": "high", "label": "Haute"},
                {"value": "medium", "label": "Moyenne"},
                {"value": "low", "label": "Basse"},
            ]
            >>> HitlMessages.get_field_options("email", "recipient", "fr")
            None
        """
        lang = HitlMessages._normalize_language(language)
        key = f"{domain}.{field}"

        field_options = _FIELD_OPTION_LABELS.get(key)
        if not field_options:
            return None

        result = []
        for value, labels in field_options.items():
            label = labels.get(lang, labels.get("en", value))
            result.append({"value": value, "label": label})

        return result

    @staticmethod
    def format_field_question_with_options(
        domain: str,
        field: str,
        language: str,
    ) -> str:
        """
        Format field question with options if applicable.

        For fields with enumerated options, appends the available choices
        to the question for better UX.

        Args:
            domain: Domain identifier
            field: Field identifier
            language: Language code

        Returns:
            Formatted question string, with options appended if applicable

        Example:
            >>> HitlMessages.format_field_question_with_options("task", "priority", "fr")
            "Quelle est la priorité de cette tâche ? (Haute, Moyenne, Basse)"
        """
        question = HitlMessages.get_field_question(domain, field, language)
        options = HitlMessages.get_field_options(domain, field, language)

        if options:
            labels = [opt["label"] for opt in options]
            options_str = ", ".join(labels)
            # Remove trailing punctuation and add options
            question = question.rstrip("?").rstrip() + f" ? ({options_str})"

        return question

    # =========================================================================
    # FOR_EACH CONFIRM METHODS
    # =========================================================================

    @staticmethod
    def get_for_each_confirm_translations(language: str) -> dict[str, str]:
        """
        Get UI translations for for_each bulk operation confirmation dialog.

        Args:
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Dict with keys: title, operation_prefix, items_suffix, confirm_question,
                          mutation_send, mutation_create, mutation_update,
                          mutation_delete, mutation_default
        """
        lang = HitlMessages._normalize_language(language)
        return _FOR_EACH_CONFIRM_UI.get(lang, _FOR_EACH_CONFIRM_UI["en"])

    @staticmethod
    def get_for_each_edit_translations(language: str) -> dict[str, str]:
        """
        Get UI translations for for_each item exclusion during bulk confirmation.

        Used when user wants to exclude specific items from the bulk operation list
        (e.g., "retire les emails de Guy Savoy").

        Args:
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Dict with keys: exclude_action, items_excluded, all_items_excluded,
                          filtered_list_header, filter_instruction, no_criteria

        Example:
            >>> HitlMessages.get_for_each_edit_translations("fr")
            {
                "exclude_action": "Modifier la liste",
                "items_excluded": "**{count}** élément(s) retiré(s) de la liste.",
                ...
            }
        """
        lang = HitlMessages._normalize_language(language)
        return _FOR_EACH_EDIT_UI.get(lang, _FOR_EACH_EDIT_UI["en"])

    @staticmethod
    def format_for_each_items_excluded(count: int, language: str) -> str:
        """
        Format the 'items excluded' message with count.

        Args:
            count: Number of items excluded
            language: Language code

        Returns:
            Formatted message (e.g., "**3** élément(s) retiré(s) de la liste.")
        """
        translations = HitlMessages.get_for_each_edit_translations(language)
        template = translations.get("items_excluded", "**{count}** item(s) removed.")
        return template.format(count=count)

    @staticmethod
    def format_for_each_filtered_header(count: int, language: str) -> str:
        """
        Format the filtered list header with remaining count.

        Args:
            count: Number of items remaining after filter
            language: Language code

        Returns:
            Formatted header (e.g., "Liste mise à jour (5 éléments restants) :")
        """
        translations = HitlMessages.get_for_each_edit_translations(language)
        template = translations.get(
            "filtered_list_header", "Updated list ({count} items remaining):"
        )
        return template.format(count=count)

    # =========================================================================
    # DESTRUCTIVE CONFIRM METHODS
    # =========================================================================

    @staticmethod
    def get_destructive_confirm_translations(language: str) -> dict[str, str]:
        """
        Get UI translations for destructive confirmation dialog.

        Args:
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Dict with keys: title, affected_items, and_more, default_warning, confirm_question
        """
        lang = HitlMessages._normalize_language(language)
        return _DESTRUCTIVE_CONFIRM_UI.get(lang, _DESTRUCTIVE_CONFIRM_UI["en"])

    @staticmethod
    def get_destructive_operation_description(
        operation_type: str,
        count: int,
        language: str,
    ) -> str:
        """
        Get localized operation description for destructive confirm.

        Args:
            operation_type: Operation type (delete_emails, delete_contacts, etc.)
            count: Number of affected items
            language: Language code

        Returns:
            Formatted operation description string
        """
        lang = HitlMessages._normalize_language(language)
        descriptions = _DESTRUCTIVE_OPERATION_DESCRIPTIONS.get(
            lang, _DESTRUCTIVE_OPERATION_DESCRIPTIONS["en"]
        )
        template = descriptions.get(operation_type, descriptions["unknown"])
        return template.format(count=count)

    @staticmethod
    def get_default_personality(language: str) -> str:
        """
        Get default personality instruction for LLM in the user's language.

        Used as fallback when no custom personality is provided in HITL
        question generators.

        Args:
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Default personality instruction text in the specified language

        Example:
            >>> HitlMessages.get_default_personality("en")
            "You are a balanced and professional assistant..."
        """
        lang = HitlMessages._normalize_language(language)
        return _DEFAULT_PERSONALITY.get(lang, _DEFAULT_PERSONALITY["en"])


# =============================================================================
# UTILITY FUNCTION - Get user language with proper fallback
# =============================================================================


def get_user_language(
    user_language: str | None = None,
    accept_language_header: str | None = None,
    default: Language = DEFAULT_LANGUAGE,
) -> Language:
    """
    Get user language with proper fallback chain.

    Priority:
    1. User's stored language preference (from database)
    2. Accept-Language header (from browser)
    3. Default language (fr)

    Args:
        user_language: User's stored language preference
        accept_language_header: HTTP Accept-Language header
        default: Default language to use as fallback

    Returns:
        Resolved language code

    Example:
        >>> get_user_language(user_language="de")
        "de"
        >>> get_user_language(user_language=None, accept_language_header="en-US,en;q=0.9")
        "en"
        >>> get_user_language()
        "fr"
    """
    from src.core.i18n import SUPPORTED_LANGUAGES, get_language_from_header

    # Priority 1: User's stored preference
    if user_language:
        normalized = HitlMessages._normalize_language(user_language)
        if normalized in SUPPORTED_LANGUAGES:
            return normalized  # type: ignore[return-value]

    # Priority 2: Accept-Language header
    if accept_language_header:
        return get_language_from_header(accept_language_header)

    # Priority 3: Default
    return default
