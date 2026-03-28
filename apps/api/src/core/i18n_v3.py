"""
Internationalization (i18n) for Architecture v3 components.

Centralized translations for:
- AutonomousExecutor: Recovery messages, proactive suggestions
- RelevanceEngine: Filter explanations
- Display: Warm intro patterns, proactive outro suggestions

All 6 supported languages: fr, en, es, de, it, zh-CN

Usage:
    from src.core.i18n_v3 import V3Messages

    # Get recovery message
    msg = V3Messages.get_partial_success_message("fr", has_results=True, error="timeout")

    # Get proactive suggestion
    suggestion = V3Messages.get_proactive_suggestion("send_message", "de")

    # Get filter explanation
    explanation = V3Messages.get_filter_explanation("fr", total=10, shown=5)

    # Get warm intro
    intro = V3Messages.get_warm_intro("fr", context="found_many", count=5)

Created: 2025-12-30
Architecture v3 - Intelligence, Autonomy, Relevance
"""

from typing import Any

from src.core.i18n import DEFAULT_LANGUAGE

# =============================================================================
# RECOVERY MESSAGES - AutonomousExecutor partial success messages
# =============================================================================

_PARTIAL_SUCCESS_WITH_RESULTS: dict[str, str] = {
    "fr": "J'ai pu récupérer des informations partielles, mais l'étape '{tool_name}' a échoué: {error}. Voici ce que j'ai trouvé jusqu'ici...",
    "en": "I was able to retrieve partial information, but the '{tool_name}' step failed: {error}. Here's what I found so far...",
    "es": "Pude recuperar información parcial, pero el paso '{tool_name}' falló: {error}. Esto es lo que encontré hasta ahora...",
    "de": "Ich konnte teilweise Informationen abrufen, aber der Schritt '{tool_name}' ist fehlgeschlagen: {error}. Hier ist, was ich bisher gefunden habe...",
    "it": "Ho recuperato informazioni parziali, ma il passaggio '{tool_name}' è fallito: {error}. Ecco cosa ho trovato finora...",
    "zh-CN": "我获取了部分信息，但'{tool_name}'步骤失败了：{error}。以下是我目前找到的内容...",
}

_PARTIAL_SUCCESS_NO_RESULTS: dict[str, str] = {
    "fr": "Je n'ai pas pu exécuter cette demande ({error}). Suggestions: vérifiez l'orthographe, essayez avec moins de détails, ou reformulez votre demande.",
    "en": "I couldn't execute this request ({error}). Suggestions: check the spelling, try with fewer details, or rephrase your request.",
    "es": "No pude ejecutar esta solicitud ({error}). Sugerencias: verifica la ortografía, intenta con menos detalles o reformula tu solicitud.",
    "de": "Ich konnte diese Anfrage nicht ausführen ({error}). Vorschläge: Überprüfen Sie die Rechtschreibung, versuchen Sie es mit weniger Details oder formulieren Sie Ihre Anfrage um.",
    "it": "Non ho potuto eseguire questa richiesta ({error}). Suggerimenti: controlla l'ortografia, prova con meno dettagli o riformula la richiesta.",
    "zh-CN": "我无法执行此请求（{error}）。建议：检查拼写，尝试减少细节，或重新表述您的请求。",
}

_EXECUTION_STOPPED: dict[str, str] = {
    "fr": "Exécution arrêtée: {reason}",
    "en": "Execution stopped: {reason}",
    "es": "Ejecución detenida: {reason}",
    "de": "Ausführung gestoppt: {reason}",
    "it": "Esecuzione interrotta: {reason}",
    "zh-CN": "执行已停止：{reason}",
}

_RECOVERY_STOPPED: dict[str, str] = {
    "fr": "Récupération arrêtée: {reason}",
    "en": "Recovery stopped: {reason}",
    "es": "Recuperación detenida: {reason}",
    "de": "Wiederherstellung gestoppt: {reason}",
    "it": "Recupero interrotto: {reason}",
    "zh-CN": "恢复已停止：{reason}",
}

# =============================================================================
# PROACTIVE SUGGESTIONS - AutonomousExecutor suggestions
# =============================================================================

_PROACTIVE_SUGGESTIONS: dict[str, dict[str, str]] = {
    "send_message": {
        "fr": "Envoyer un message",
        "en": "Send a message",
        "es": "Enviar un mensaje",
        "de": "Nachricht senden",
        "it": "Invia un messaggio",
        "zh-CN": "发送消息",
    },
    "get_contact_info": {
        "fr": "Voir les coordonnées",
        "en": "View contact details",
        "es": "Ver datos de contacto",
        "de": "Kontaktdaten anzeigen",
        "it": "Visualizza i contatti",
        "zh-CN": "查看联系方式",
    },
    "modify_event": {
        "fr": "Modifier l'événement",
        "en": "Modify the event",
        "es": "Modificar el evento",
        "de": "Termin bearbeiten",
        "it": "Modifica l'evento",
        "zh-CN": "修改活动",
    },
    "reply_email": {
        "fr": "Répondre à l'email",
        "en": "Reply to the email",
        "es": "Responder al correo",
        "de": "Auf E-Mail antworten",
        "it": "Rispondi all'email",
        "zh-CN": "回复邮件",
    },
    "create_event": {
        "fr": "Créer un événement",
        "en": "Create an event",
        "es": "Crear un evento",
        "de": "Termin erstellen",
        "it": "Crea un evento",
        "zh-CN": "创建活动",
    },
    "create_task": {
        "fr": "Créer une tâche",
        "en": "Create a task",
        "es": "Crear una tarea",
        "de": "Aufgabe erstellen",
        "it": "Crea un'attività",
        "zh-CN": "创建任务",
    },
    "forward_email": {
        "fr": "Transférer l'email",
        "en": "Forward the email",
        "es": "Reenviar el correo",
        "de": "E-Mail weiterleiten",
        "it": "Inoltra l'email",
        "zh-CN": "转发邮件",
    },
    "call_contact": {
        "fr": "Appeler le contact",
        "en": "Call the contact",
        "es": "Llamar al contacto",
        "de": "Kontakt anrufen",
        "it": "Chiama il contatto",
        "zh-CN": "呼叫联系人",
    },
}

# =============================================================================
# FILTER EXPLANATIONS - RelevanceEngine explanations
# =============================================================================

_FILTER_NO_RESULTS: dict[str, str] = {
    "fr": "Aucun résultat trouvé",
    "en": "No results found",
    "es": "No se encontraron resultados",
    "de": "Keine Ergebnisse gefunden",
    "it": "Nessun risultato trovato",
    "zh-CN": "未找到结果",
}

_FILTER_ONE_RESULT: dict[str, str] = {
    "fr": "1 résultat trouvé",
    "en": "1 result found",
    "es": "1 resultado encontrado",
    "de": "1 Ergebnis gefunden",
    "it": "1 risultato trovato",
    "zh-CN": "找到1个结果",
}

_FILTER_ALL_SHOWN: dict[str, str] = {
    "fr": "Tous les {total} résultats affichés",
    "en": "All {total} results shown",
    "es": "Los {total} resultados mostrados",
    "de": "Alle {total} Ergebnisse angezeigt",
    "it": "Tutti i {total} risultati mostrati",
    "zh-CN": "显示全部{total}个结果",
}

_FILTER_MOST_RELEVANT: dict[str, str] = {
    "fr": "Résultat le plus pertinent",
    "en": "Most relevant result",
    "es": "Resultado más relevante",
    "de": "Relevantestes Ergebnis",
    "it": "Risultato più rilevante",
    "zh-CN": "最相关的结果",
}

_FILTER_TOP_N: dict[str, str] = {
    "fr": "Top {shown} sur {total} résultats, triés par pertinence",
    "en": "Top {shown} of {total} results, sorted by relevance",
    "es": "Top {shown} de {total} resultados, ordenados por relevancia",
    "de": "Top {shown} von {total} Ergebnissen, sortiert nach Relevanz",
    "it": "Top {shown} di {total} risultati, ordinati per rilevanza",
    "zh-CN": "按相关性排序的{total}个结果中的前{shown}个",
}

# =============================================================================
# RELEVANCE REASONS - RelevanceEngine scoring reasons
# =============================================================================

_RELEVANCE_REASONS: dict[str, dict[str, str]] = {
    "matches_terms": {
        "fr": "Correspond à {count} terme(s)",
        "en": "Matches {count} term(s)",
        "es": "Coincide con {count} término(s)",
        "de": "Stimmt mit {count} Begriff(en) überein",
        "it": "Corrisponde a {count} termine/i",
        "zh-CN": "匹配{count}个词条",
    },
    "recent": {
        "fr": "Récent",
        "en": "Recent",
        "es": "Reciente",
        "de": "Aktuell",
        "it": "Recente",
        "zh-CN": "最近",
    },
    "today": {
        "fr": "Aujourd'hui",
        "en": "Today",
        "es": "Hoy",
        "de": "Heute",
        "it": "Oggi",
        "zh-CN": "今天",
    },
    "complete_data": {
        "fr": "Données complètes",
        "en": "Complete data",
        "es": "Datos completos",
        "de": "Vollständige Daten",
        "it": "Dati completi",
        "zh-CN": "完整数据",
    },
    "has_contact_info": {
        "fr": "A des coordonnées",
        "en": "Has contact info",
        "es": "Tiene información de contacto",
        "de": "Hat Kontaktdaten",
        "it": "Ha informazioni di contatto",
        "zh-CN": "有联系方式",
    },
    "has_location_time": {
        "fr": "A lieu/horaire",
        "en": "Has location/time",
        "es": "Tiene lugar/hora",
        "de": "Hat Ort/Zeit",
        "it": "Ha luogo/orario",
        "zh-CN": "有地点/时间",
    },
    "nearby": {
        "fr": "Proche de {location}",
        "en": "Near {location}",
        "es": "Cerca de {location}",
        "de": "In der Nähe von {location}",
        "it": "Vicino a {location}",
        "zh-CN": "靠近{location}",
    },
    "same_city": {
        "fr": "Même ville",
        "en": "Same city",
        "es": "Misma ciudad",
        "de": "Gleiche Stadt",
        "it": "Stessa città",
        "zh-CN": "同一城市",
    },
    "near_work": {
        "fr": "Proche du travail",
        "en": "Near work",
        "es": "Cerca del trabajo",
        "de": "In der Nähe der Arbeit",
        "it": "Vicino al lavoro",
        "zh-CN": "靠近工作地点",
    },
    "frequent_contact": {
        "fr": "Contact fréquent",
        "en": "Frequent contact",
        "es": "Contacto frecuente",
        "de": "Häufiger Kontakt",
        "it": "Contatto frequente",
        "zh-CN": "常用联系人",
    },
    "already_contacted": {
        "fr": "Déjà contacté",
        "en": "Already contacted",
        "es": "Ya contactado",
        "de": "Bereits kontaktiert",
        "it": "Già contattato",
        "zh-CN": "已联系过",
    },
    "favorite_place_type": {
        "fr": "Type de lieu favori",
        "en": "Favorite place type",
        "es": "Tipo de lugar favorito",
        "de": "Bevorzugter Ortstyp",
        "it": "Tipo di luogo preferito",
        "zh-CN": "常用地点类型",
    },
    "unknown_format": {
        "fr": "Format inconnu",
        "en": "Unknown format",
        "es": "Formato desconocido",
        "de": "Unbekanntes Format",
        "it": "Formato sconosciuto",
        "zh-CN": "未知格式",
    },
}

# =============================================================================
# WARM INTROS - Display warm introduction patterns
# =============================================================================

_WARM_INTROS: dict[str, dict[str, list[str]]] = {
    "found_many": {
        "fr": [
            "Voici ce que j'ai trouvé !",
            "J'ai trouvé plusieurs résultats.",
            "Voilà les résultats de ta recherche.",
        ],
        "en": [
            "Here's what I found!",
            "I found several results.",
            "Here are your search results.",
        ],
        "es": [
            "¡Esto es lo que encontré!",
            "Encontré varios resultados.",
            "Aquí están los resultados de tu búsqueda.",
        ],
        "de": [
            "Das habe ich gefunden!",
            "Ich habe mehrere Ergebnisse gefunden.",
            "Hier sind deine Suchergebnisse.",
        ],
        "it": [
            "Ecco cosa ho trovato!",
            "Ho trovato diversi risultati.",
            "Ecco i risultati della tua ricerca.",
        ],
        "zh-CN": [
            "这是我找到的内容！",
            "我找到了几个结果。",
            "以下是您的搜索结果。",
        ],
    },
    "found_one": {
        "fr": [
            "J'ai trouvé exactement ce que tu cherchais.",
            "Voici le résultat.",
            "Trouvé !",
        ],
        "en": [
            "I found exactly what you're looking for.",
            "Here's the result.",
            "Found it!",
        ],
        "es": [
            "Encontré exactamente lo que buscabas.",
            "Aquí está el resultado.",
            "¡Encontrado!",
        ],
        "de": [
            "Ich habe genau das gefunden, was du suchst.",
            "Hier ist das Ergebnis.",
            "Gefunden!",
        ],
        "it": [
            "Ho trovato esattamente quello che cercavi.",
            "Ecco il risultato.",
            "Trovato!",
        ],
        "zh-CN": [
            "我找到了你要找的内容。",
            "这是结果。",
            "找到了！",
        ],
    },
    "contacts": {
        "fr": [
            "Voici les contacts correspondants.",
            "J'ai trouvé ces contacts pour toi.",
        ],
        "en": [
            "Here are the matching contacts.",
            "I found these contacts for you.",
        ],
        "es": [
            "Aquí están los contactos correspondientes.",
            "Encontré estos contactos para ti.",
        ],
        "de": [
            "Hier sind die passenden Kontakte.",
            "Ich habe diese Kontakte für dich gefunden.",
        ],
        "it": [
            "Ecco i contatti corrispondenti.",
            "Ho trovato questi contatti per te.",
        ],
        "zh-CN": [
            "这是匹配的联系人。",
            "我为你找到了这些联系人。",
        ],
    },
    "calendar": {
        "fr": [
            "Voici ton agenda.",
            "Voilà tes événements à venir.",
        ],
        "en": [
            "Here's your calendar.",
            "Here are your upcoming events.",
        ],
        "es": [
            "Aquí está tu calendario.",
            "Aquí están tus próximos eventos.",
        ],
        "de": [
            "Hier ist dein Kalender.",
            "Hier sind deine bevorstehenden Termine.",
        ],
        "it": [
            "Ecco il tuo calendario.",
            "Ecco i tuoi prossimi eventi.",
        ],
        "zh-CN": [
            "这是你的日历。",
            "这是你即将到来的活动。",
        ],
    },
    "emails": {
        "fr": [
            "Voici tes emails.",
            "J'ai trouvé ces messages.",
        ],
        "en": [
            "Here are your emails.",
            "I found these messages.",
        ],
        "es": [
            "Aquí están tus correos.",
            "Encontré estos mensajes.",
        ],
        "de": [
            "Hier sind deine E-Mails.",
            "Ich habe diese Nachrichten gefunden.",
        ],
        "it": [
            "Ecco le tue email.",
            "Ho trovato questi messaggi.",
        ],
        "zh-CN": [
            "这是你的邮件。",
            "我找到了这些消息。",
        ],
    },
    "no_results": {
        "fr": [
            "Je n'ai rien trouvé correspondant à ta recherche.",
            "Aucun résultat pour cette recherche.",
            "Désolé, pas de résultat.",
        ],
        "en": [
            "I didn't find anything matching your search.",
            "No results for this search.",
            "Sorry, no results.",
        ],
        "es": [
            "No encontré nada que coincida con tu búsqueda.",
            "Sin resultados para esta búsqueda.",
            "Lo siento, sin resultados.",
        ],
        "de": [
            "Ich habe nichts Passendes gefunden.",
            "Keine Ergebnisse für diese Suche.",
            "Leider keine Ergebnisse.",
        ],
        "it": [
            "Non ho trovato nulla che corrisponda alla tua ricerca.",
            "Nessun risultato per questa ricerca.",
            "Mi dispiace, nessun risultato.",
        ],
        "zh-CN": [
            "我没有找到与您搜索匹配的内容。",
            "此搜索没有结果。",
            "抱歉，没有结果。",
        ],
    },
    "multi_domain": {
        "fr": [
            "Pas mal de choses à te montrer !",
            "Voici un résumé complet.",
            "J'ai trouvé des infos dans plusieurs domaines.",
        ],
        "en": [
            "Lots of things to show you!",
            "Here's a complete summary.",
            "I found info across multiple domains.",
        ],
        "es": [
            "¡Muchas cosas que mostrarte!",
            "Aquí tienes un resumen completo.",
            "Encontré información en varios dominios.",
        ],
        "de": [
            "Einiges zu zeigen!",
            "Hier ist eine vollständige Zusammenfassung.",
            "Ich habe Infos aus mehreren Bereichen gefunden.",
        ],
        "it": [
            "Tante cose da mostrarti!",
            "Ecco un riepilogo completo.",
            "Ho trovato informazioni in più domini.",
        ],
        "zh-CN": [
            "有很多东西要给你看！",
            "这是完整的摘要。",
            "我在多个领域找到了信息。",
        ],
    },
}

# =============================================================================
# PROACTIVE OUTROS - Display proactive suggestions
# =============================================================================

_PROACTIVE_OUTROS: dict[str, dict[str, list[str]]] = {
    "contacts": {
        "fr": [
            "Veux-tu envoyer un message à ce contact ?",
            "Besoin de plus de détails ?",
            "Veux-tu l'ajouter à un événement ?",
        ],
        "en": [
            "Would you like to send a message to this contact?",
            "Need more details?",
            "Would you like to add them to an event?",
        ],
        "es": [
            "¿Quieres enviar un mensaje a este contacto?",
            "¿Necesitas más detalles?",
            "¿Quieres agregarlo a un evento?",
        ],
        "de": [
            "Möchtest du diesem Kontakt eine Nachricht senden?",
            "Mehr Details benötigt?",
            "Möchtest du ihn zu einem Termin hinzufügen?",
        ],
        "it": [
            "Vuoi inviare un messaggio a questo contatto?",
            "Hai bisogno di più dettagli?",
            "Vuoi aggiungerlo a un evento?",
        ],
        "zh-CN": [
            "你想给这个联系人发消息吗？",
            "需要更多详情吗？",
            "你想把他们添加到活动中吗？",
        ],
    },
    "calendar": {
        "fr": [
            "Veux-tu modifier cet événement ?",
            "Besoin de plus de détails sur cet événement ?",
            "Veux-tu voir la météo pour ce jour ?",
        ],
        "en": [
            "Would you like to modify this event?",
            "Need more details about this event?",
            "Would you like to see the weather for that day?",
        ],
        "es": [
            "¿Quieres modificar este evento?",
            "¿Necesitas más detalles sobre este evento?",
            "¿Quieres ver el clima para ese día?",
        ],
        "de": [
            "Möchtest du diesen Termin bearbeiten?",
            "Mehr Details zu diesem Termin benötigt?",
            "Möchtest du das Wetter für diesen Tag sehen?",
        ],
        "it": [
            "Vuoi modificare questo evento?",
            "Hai bisogno di più dettagli su questo evento?",
            "Vuoi vedere il meteo per quel giorno?",
        ],
        "zh-CN": [
            "你想修改这个活动吗？",
            "需要这个活动的更多详情吗？",
            "你想看看那天的天气吗？",
        ],
    },
    "emails": {
        "fr": [
            "Veux-tu répondre à cet email ?",
            "Veux-tu le transférer ?",
            "Besoin de créer une tâche à partir de cet email ?",
        ],
        "en": [
            "Would you like to reply to this email?",
            "Would you like to forward it?",
            "Need to create a task from this email?",
        ],
        "es": [
            "¿Quieres responder a este correo?",
            "¿Quieres reenviarlo?",
            "¿Necesitas crear una tarea a partir de este correo?",
        ],
        "de": [
            "Möchtest du auf diese E-Mail antworten?",
            "Möchtest du sie weiterleiten?",
            "Eine Aufgabe aus dieser E-Mail erstellen?",
        ],
        "it": [
            "Vuoi rispondere a questa email?",
            "Vuoi inoltrarla?",
            "Devi creare un'attività da questa email?",
        ],
        "zh-CN": [
            "你想回复这封邮件吗？",
            "你想转发它吗？",
            "需要从这封邮件创建任务吗？",
        ],
    },
    "general": {
        "fr": [
            "Autre chose que je peux faire pour toi ?",
            "Besoin d'aide pour autre chose ?",
        ],
        "en": [
            "Anything else I can do for you?",
            "Need help with anything else?",
        ],
        "es": [
            "¿Algo más en lo que pueda ayudarte?",
            "¿Necesitas ayuda con algo más?",
        ],
        "de": [
            "Kann ich noch etwas für dich tun?",
            "Brauchst du Hilfe bei etwas anderem?",
        ],
        "it": [
            "Posso fare qualcos'altro per te?",
            "Hai bisogno di aiuto per qualcos'altro?",
        ],
        "zh-CN": [
            "还有什么我可以帮你的吗？",
            "还需要其他帮助吗？",
        ],
    },
}


# =============================================================================
# FORMATTER STRINGS - ResponseFormatter display strings
# =============================================================================

_FORMATTER_NO_RESULTS: dict[str, str] = {
    "fr": "Aucun résultat.",
    "en": "No results.",
    "es": "Sin resultados.",
    "de": "Keine Ergebnisse.",
    "it": "Nessun risultato.",
    "zh-CN": "没有结果。",
}

_FORMATTER_ONE_RESULT: dict[str, str] = {
    "fr": "1 résultat trouvé.",
    "en": "1 result found.",
    "es": "1 resultado encontrado.",
    "de": "1 Ergebnis gefunden.",
    "it": "1 risultato trovato.",
    "zh-CN": "找到1个结果。",
}

_FORMATTER_N_RESULTS: dict[str, str] = {
    "fr": "{count} résultats trouvés.",
    "en": "{count} results found.",
    "es": "{count} resultados encontrados.",
    "de": "{count} Ergebnisse gefunden.",
    "it": "{count} risultati trovati.",
    "zh-CN": "找到{count}个结果。",
}

_FORMATTER_NO_NAME: dict[str, str] = {
    "fr": "Sans nom",
    "en": "No name",
    "es": "Sin nombre",
    "de": "Ohne Namen",
    "it": "Senza nome",
    "zh-CN": "无名称",
}

_FORMATTER_NO_TITLE: dict[str, str] = {
    "fr": "Sans titre",
    "en": "No title",
    "es": "Sin título",
    "de": "Ohne Titel",
    "it": "Senza titolo",
    "zh-CN": "无标题",
}

_FORMATTER_NO_SUBJECT: dict[str, str] = {
    "fr": "Sans sujet",
    "en": "No subject",
    "es": "Sin asunto",
    "de": "Ohne Betreff",
    "it": "Senza oggetto",
    "zh-CN": "无主题",
}

_FORMATTER_DATE_NOT_SPECIFIED: dict[str, str] = {
    "fr": "Date non spécifiée",
    "en": "Date not specified",
    "es": "Fecha no especificada",
    "de": "Datum nicht angegeben",
    "it": "Data non specificata",
    "zh-CN": "日期未指定",
}

_FORMATTER_TIME_NOT_SPECIFIED: dict[str, str] = {
    "fr": "Heure non spécifiée",
    "en": "Time not specified",
    "es": "Hora no especificada",
    "de": "Uhrzeit nicht angegeben",
    "it": "Ora non specificata",
    "zh-CN": "时间未指定",
}

_FORMATTER_YESTERDAY: dict[str, str] = {
    "fr": "hier",
    "en": "yesterday",
    "es": "ayer",
    "de": "gestern",
    "it": "ieri",
    "zh-CN": "昨天",
}

_FORMATTER_TODAY: dict[str, str] = {
    "fr": "Aujourd'hui",
    "en": "Today",
    "es": "Hoy",
    "de": "Heute",
    "it": "Oggi",
    "zh-CN": "今天",
}

_FORMATTER_TOMORROW: dict[str, str] = {
    "fr": "Demain",
    "en": "Tomorrow",
    "es": "Mañana",
    "de": "Morgen",
    "it": "Domani",
    "zh-CN": "明天",
}

_FORMATTER_UNREAD: dict[str, str] = {
    "fr": "non lu",
    "en": "unread",
    "es": "no leído",
    "de": "ungelesen",
    "it": "non letto",
    "zh-CN": "未读",
}

# =============================================================================
# DISPLAY COMPONENT STRINGS - UI labels for display components
# =============================================================================

_DISPLAY_SHARED: dict[str, str] = {
    "fr": "Partagé",
    "en": "Shared",
    "es": "Compartido",
    "de": "Geteilt",
    "it": "Condiviso",
    "zh-CN": "已共享",
}

_DISPLAY_MODIFIED: dict[str, str] = {
    "fr": "Modifié",
    "en": "Modified",
    "es": "Modificado",
    "de": "Geändert",
    "it": "Modificato",
    "zh-CN": "已修改",
}

_DISPLAY_CREATED: dict[str, str] = {
    "fr": "Créé",
    "en": "Created",
    "es": "Creado",
    "de": "Erstellt",
    "it": "Creato",
    "zh-CN": "已创建",
}

_DISPLAY_COMPLETED: dict[str, str] = {
    "fr": "Terminé",
    "en": "Completed",
    "es": "Completado",
    "de": "Erledigt",
    "it": "Completato",
    "zh-CN": "已完成",
}

_DISPLAY_FEELS_LIKE: dict[str, str] = {
    "fr": "Ressenti",
    "en": "Feels like",
    "es": "Sensación",
    "de": "Gefühlt",
    "it": "Percepito",
    "zh-CN": "体感温度",
}

_DISPLAY_TEMP_RANGE: dict[str, str] = {
    "fr": "Températures",
    "en": "Temperatures",
    "es": "Temperaturas",
    "de": "Temperaturen",
    "it": "Temperature",
    "zh-CN": "温度",
}

_DISPLAY_HUMIDITY: dict[str, str] = {
    "fr": "Humidité",
    "en": "Humidity",
    "es": "Humedad",
    "de": "Luftfeuchtigkeit",
    "it": "Umidità",
    "zh-CN": "湿度",
}

_DISPLAY_WIND: dict[str, str] = {
    "fr": "Vent",
    "en": "Wind",
    "es": "Viento",
    "de": "Wind",
    "it": "Vento",
    "zh-CN": "风",
}

_DISPLAY_FORECAST: dict[str, str] = {
    "fr": "Prévisions",
    "en": "Forecast",
    "es": "Pronóstico",
    "de": "Vorhersage",
    "it": "Previsioni",
    "zh-CN": "预报",
}

_DISPLAY_HOURLY: dict[str, str] = {
    "fr": "Heure par heure",
    "en": "Hourly",
    "es": "Por hora",
    "de": "Stündlich",
    "it": "Ogni ora",
    "zh-CN": "逐小时",
}

# Weather extended details labels (v3.1)
_DISPLAY_UV_INDEX: dict[str, str] = {
    "fr": "Indice UV",
    "en": "UV Index",
    "es": "Índice UV",
    "de": "UV-Index",
    "it": "Indice UV",
    "zh-CN": "紫外线指数",
}

_DISPLAY_PRESSURE: dict[str, str] = {
    "fr": "Pression",
    "en": "Pressure",
    "es": "Presión",
    "de": "Luftdruck",
    "it": "Pressione",
    "zh-CN": "气压",
}

_DISPLAY_VISIBILITY: dict[str, str] = {
    "fr": "Visibilité",
    "en": "Visibility",
    "es": "Visibilidad",
    "de": "Sichtweite",
    "it": "Visibilità",
    "zh-CN": "能见度",
}

_DISPLAY_CLOUD_COVER: dict[str, str] = {
    "fr": "Couverture nuageuse",
    "en": "Cloud cover",
    "es": "Nubosidad",
    "de": "Bewölkung",
    "it": "Copertura nuvolosa",
    "zh-CN": "云量",
}

_DISPLAY_AIR_QUALITY: dict[str, str] = {
    "fr": "Qualité de l'air",
    "en": "Air Quality",
    "es": "Calidad del aire",
    "de": "Luftqualität",
    "it": "Qualità dell'aria",
    "zh-CN": "空气质量",
}

_DISPLAY_PRECIPITATION: dict[str, str] = {
    "fr": "Précipitations",
    "en": "Precipitation",
    "es": "Precipitación",
    "de": "Niederschlag",
    "it": "Precipitazioni",
    "zh-CN": "降水概率",
}

# Weather forecast limit message
_WEATHER_FORECAST_BEYOND_LIMIT: dict[str, str] = {
    "fr": "Les prévisions météo ne sont disponibles que pour les {max_days} prochains jours. La date demandée est dans {offset} jours.",
    "en": "Weather forecast is only available for the next {max_days} days. The requested date is {offset} days from now.",
    "es": "El pronóstico del tiempo solo está disponible para los próximos {max_days} días. La fecha solicitada es dentro de {offset} días.",
    "de": "Die Wettervorhersage ist nur für die nächsten {max_days} Tage verfügbar. Das angeforderte Datum liegt {offset} Tage in der Zukunft.",
    "it": "Le previsioni meteo sono disponibili solo per i prossimi {max_days} giorni. La data richiesta è tra {offset} giorni.",
    "zh-CN": "天气预报仅适用于未来 {max_days} 天。请求的日期是 {offset} 天后。",
}

_DISPLAY_ATTACHMENTS: dict[str, str] = {
    "fr": "Pièces jointes",
    "en": "Attachments",
    "es": "Adjuntos",
    "de": "Anhänge",
    "it": "Allegati",
    "zh-CN": "附件",
}

_DISPLAY_READ_MORE: dict[str, str] = {
    "fr": "Lire la suite sur Gmail",
    "en": "Read more on Gmail",
    "es": "Leer más en Gmail",
    "de": "Weiterlesen auf Gmail",
    "it": "Leggi di più su Gmail",
    "zh-CN": "在Gmail上阅读更多",
}

_DISPLAY_READ_MORE_OUTLOOK: dict[str, str] = {
    "fr": "Lire la suite sur Outlook",
    "en": "Read more on Outlook",
    "es": "Leer más en Outlook",
    "de": "Weiterlesen auf Outlook",
    "it": "Leggi di più su Outlook",
    "zh-CN": "在Outlook上阅读更多",
}

# Email action buttons (v3.0) - Short labels for mobile
_DISPLAY_REPLY: dict[str, str] = {
    "fr": "Rép.",
    "en": "Reply",
    "es": "Resp.",
    "de": "Antw.",
    "it": "Risp.",
    "zh-CN": "回复",
}

_DISPLAY_FORWARD: dict[str, str] = {
    "fr": "Transf.",
    "en": "Fwd",
    "es": "Reenv.",
    "de": "Weit.",
    "it": "Inol.",
    "zh-CN": "转发",
}

_DISPLAY_ARCHIVE: dict[str, str] = {
    "fr": "Supp.",
    "en": "Delete",
    "es": "Elim.",
    "de": "Lösch.",
    "it": "Elim.",
    "zh-CN": "删除",
}

_DISPLAY_SEE_MORE: dict[str, str] = {
    "fr": "Voir plus",
    "en": "See more",
    "es": "Ver más",
    "de": "Mehr anzeigen",
    "it": "Vedi altro",
    "zh-CN": "查看更多",
}

# "See N attachment(s)" for collapsible (singular)
_DISPLAY_SEE_ATTACHMENT: dict[str, str] = {
    "fr": "Voir {count} pièce jointe",
    "en": "See {count} attachment",
    "es": "Ver {count} adjunto",
    "de": "{count} Anhang anzeigen",
    "it": "Vedi {count} allegato",
    "zh-CN": "查看{count}个附件",
}

# "See N attachment(s)" for collapsible (plural)
_DISPLAY_SEE_ATTACHMENTS: dict[str, str] = {
    "fr": "Voir {count} pièces jointes",
    "en": "See {count} attachments",
    "es": "Ver {count} adjuntos",
    "de": "{count} Anhänge anzeigen",
    "it": "Vedi {count} allegati",
    "zh-CN": "查看{count}个附件",
}

_DISPLAY_SHARED_WITH_N: dict[str, str] = {
    "fr": "Partagé avec {count} personne",
    "en": "Shared with {count} person",
    "es": "Compartido con {count} persona",
    "de": "Geteilt mit {count} Person",
    "it": "Condiviso con {count} persona",
    "zh-CN": "与{count}人共享",
}

_DISPLAY_SHARED_WITH_N_PLURAL: dict[str, str] = {
    "fr": "Partagé avec {count} personnes",
    "en": "Shared with {count} people",
    "es": "Compartido con {count} personas",
    "de": "Geteilt mit {count} Personen",
    "it": "Condiviso con {count} persone",
    "zh-CN": "与{count}人共享",
}

_DISPLAY_IN_FOLDER: dict[str, str] = {
    "fr": "Dans",
    "en": "In",
    "es": "En",
    "de": "In",
    "it": "In",
    "zh-CN": "位于",
}

_DISPLAY_SUBTASK_OF: dict[str, str] = {
    "fr": "Sous-tâche de",
    "en": "Subtask of",
    "es": "Subtarea de",
    "de": "Unteraufgabe von",
    "it": "Sottotask di",
    "zh-CN": "子任务属于",
}

_DISPLAY_LINKS: dict[str, str] = {
    "fr": "Liens",
    "en": "Links",
    "es": "Enlaces",
    "de": "Links",
    "it": "Link",
    "zh-CN": "链接",
}

_DISPLAY_LINK: dict[str, str] = {
    "fr": "Lien",
    "en": "Link",
    "es": "Enlace",
    "de": "Link",
    "it": "Link",
    "zh-CN": "链接",
}

_DISPLAY_SUBTASKS: dict[str, str] = {
    "fr": "Sous-tâches",
    "en": "Subtasks",
    "es": "Subtareas",
    "de": "Unteraufgaben",
    "it": "Sottotask",
    "zh-CN": "子任务",
}

_DISPLAY_LIST: dict[str, str] = {
    "fr": "Liste",
    "en": "List",
    "es": "Lista",
    "de": "Liste",
    "it": "Lista",
    "zh-CN": "列表",
}

_DISPLAY_PRIORITY_HIGH: dict[str, str] = {
    "fr": "Haute",
    "en": "High",
    "es": "Alta",
    "de": "Hoch",
    "it": "Alta",
    "zh-CN": "高",
}

_DISPLAY_PRIORITY_MEDIUM: dict[str, str] = {
    "fr": "Moyenne",
    "en": "Medium",
    "es": "Media",
    "de": "Mittel",
    "it": "Media",
    "zh-CN": "中",
}

_DISPLAY_PRIORITY_LOW: dict[str, str] = {
    "fr": "Basse",
    "en": "Low",
    "es": "Baja",
    "de": "Niedrig",
    "it": "Bassa",
    "zh-CN": "低",
}

_DISPLAY_FAVORITE: dict[str, str] = {
    "fr": "Favori",
    "en": "Favorite",
    "es": "Favorito",
    "de": "Favorit",
    "it": "Preferito",
    "zh-CN": "收藏",
}

_DISPLAY_READ_FULL_ARTICLE: dict[str, str] = {
    "fr": "Lire l'article complet",
    "en": "Read full article",
    "es": "Leer artículo completo",
    "de": "Vollständigen Artikel lesen",
    "it": "Leggi l'articolo completo",
    "zh-CN": "阅读全文",
}

_DISPLAY_READ_MORE_ON_WIKIPEDIA: dict[str, str] = {
    "fr": "voir la suite sur Wikipedia",
    "en": "read more on Wikipedia",
    "es": "leer más en Wikipedia",
    "de": "mehr auf Wikipedia lesen",
    "it": "leggi di più su Wikipedia",
    "zh-CN": "在维基百科上阅读更多",
}

# Email-specific labels
_DISPLAY_NEW: dict[str, str] = {
    "fr": "Nouveau",
    "en": "New",
    "es": "Nuevo",
    "de": "Neu",
    "it": "Nuovo",
    "zh-CN": "新",
}

_DISPLAY_IMPORTANT: dict[str, str] = {
    "fr": "Important",
    "en": "Important",
    "es": "Importante",
    "de": "Wichtig",
    "it": "Importante",
    "zh-CN": "重要",
}

_DISPLAY_FROM: dict[str, str] = {
    "fr": "De",
    "en": "From",
    "es": "De",
    "de": "Von",
    "it": "Da",
    "zh-CN": "发件人",
}

_DISPLAY_TO: dict[str, str] = {
    "fr": "Destinataires",
    "en": "Recipients",
    "es": "Destinatarios",
    "de": "Empfänger",
    "it": "Destinatari",
    "zh-CN": "收件人",
}

_DISPLAY_CC: dict[str, str] = {
    "fr": "Destinataires CC",
    "en": "CC Recipients",
    "es": "Destinatarios CC",
    "de": "CC-Empfänger",
    "it": "Destinatari CC",
    "zh-CN": "抄送",
}

_DISPLAY_EMAIL_CONTENT: dict[str, str] = {
    "fr": "Contenu du mail",
    "en": "Email content",
    "es": "Contenido del correo",
    "de": "E-Mail-Inhalt",
    "it": "Contenuto email",
    "zh-CN": "邮件内容",
}

_DISPLAY_ATTACHMENT: dict[str, str] = {
    "fr": "pièce jointe",
    "en": "attachment",
    "es": "adjunto",
    "de": "Anhang",
    "it": "allegato",
    "zh-CN": "附件",
}

# Size unit labels
_DISPLAY_SIZE_BYTES: dict[str, str] = {
    "fr": "o",
    "en": "B",
    "es": "B",
    "de": "B",
    "it": "B",
    "zh-CN": "B",
}

_DISPLAY_SIZE_KB: dict[str, str] = {
    "fr": "Ko",
    "en": "KB",
    "es": "KB",
    "de": "KB",
    "it": "KB",
    "zh-CN": "KB",
}

_DISPLAY_SIZE_MB: dict[str, str] = {
    "fr": "Mo",
    "en": "MB",
    "es": "MB",
    "de": "MB",
    "it": "MB",
    "zh-CN": "MB",
}

_DISPLAY_SIZE_GB: dict[str, str] = {
    "fr": "Go",
    "en": "GB",
    "es": "GB",
    "de": "GB",
    "it": "GB",
    "zh-CN": "GB",
}

# =============================================================================
# CONTACT COMPONENT STRINGS
# =============================================================================

# Month names (for birthday formatting)
_DISPLAY_MONTHS: dict[int, dict[str, str]] = {
    1: {
        "fr": "janvier",
        "en": "January",
        "es": "enero",
        "de": "Januar",
        "it": "gennaio",
        "zh-CN": "一月",
    },
    2: {
        "fr": "février",
        "en": "February",
        "es": "febrero",
        "de": "Februar",
        "it": "febbraio",
        "zh-CN": "二月",
    },
    3: {"fr": "mars", "en": "March", "es": "marzo", "de": "März", "it": "marzo", "zh-CN": "三月"},
    4: {
        "fr": "avril",
        "en": "April",
        "es": "abril",
        "de": "April",
        "it": "aprile",
        "zh-CN": "四月",
    },
    5: {"fr": "mai", "en": "May", "es": "mayo", "de": "Mai", "it": "maggio", "zh-CN": "五月"},
    6: {"fr": "juin", "en": "June", "es": "junio", "de": "Juni", "it": "giugno", "zh-CN": "六月"},
    7: {
        "fr": "juillet",
        "en": "July",
        "es": "julio",
        "de": "Juli",
        "it": "luglio",
        "zh-CN": "七月",
    },
    8: {
        "fr": "août",
        "en": "August",
        "es": "agosto",
        "de": "August",
        "it": "agosto",
        "zh-CN": "八月",
    },
    9: {
        "fr": "septembre",
        "en": "September",
        "es": "septiembre",
        "de": "September",
        "it": "settembre",
        "zh-CN": "九月",
    },
    10: {
        "fr": "octobre",
        "en": "October",
        "es": "octubre",
        "de": "Oktober",
        "it": "ottobre",
        "zh-CN": "十月",
    },
    11: {
        "fr": "novembre",
        "en": "November",
        "es": "noviembre",
        "de": "November",
        "it": "novembre",
        "zh-CN": "十一月",
    },
    12: {
        "fr": "décembre",
        "en": "December",
        "es": "diciembre",
        "de": "Dezember",
        "it": "dicembre",
        "zh-CN": "十二月",
    },
}

_DISPLAY_YEARS_OLD: dict[str, str] = {
    "fr": "ans",
    "en": "years old",
    "es": "años",
    "de": "Jahre",
    "it": "anni",
    "zh-CN": "岁",
}

_DISPLAY_NICKNAMES: dict[str, str] = {
    "fr": "Surnoms",
    "en": "Nicknames",
    "es": "Apodos",
    "de": "Spitznamen",
    "it": "Soprannomi",
    "zh-CN": "昵称",
}

_DISPLAY_RELATIONS: dict[str, str] = {
    "fr": "Relations",
    "en": "Relations",
    "es": "Relaciones",
    "de": "Beziehungen",
    "it": "Relazioni",
    "zh-CN": "关系",
}

# Relation types (Google Contacts API values)
_RELATION_TYPES: dict[str, dict[str, str]] = {
    "spouse": {
        "fr": "Époux/Épouse",
        "en": "Spouse",
        "es": "Cónyuge",
        "de": "Ehepartner",
        "it": "Coniuge",
        "zh-CN": "配偶",
    },
    "child": {
        "fr": "Enfant",
        "en": "Child",
        "es": "Hijo/a",
        "de": "Kind",
        "it": "Figlio/a",
        "zh-CN": "子女",
    },
    "parent": {
        "fr": "Parent",
        "en": "Parent",
        "es": "Padre/Madre",
        "de": "Elternteil",
        "it": "Genitore",
        "zh-CN": "父母",
    },
    "sibling": {
        "fr": "Frère/Sœur",
        "en": "Sibling",
        "es": "Hermano/a",
        "de": "Geschwister",
        "it": "Fratello/Sorella",
        "zh-CN": "兄弟姐妹",
    },
    "friend": {
        "fr": "Ami(e)",
        "en": "Friend",
        "es": "Amigo/a",
        "de": "Freund/in",
        "it": "Amico/a",
        "zh-CN": "朋友",
    },
    "relative": {
        "fr": "Famille",
        "en": "Relative",
        "es": "Familiar",
        "de": "Verwandter",
        "it": "Parente",
        "zh-CN": "亲戚",
    },
    "partner": {
        "fr": "Partenaire",
        "en": "Partner",
        "es": "Pareja",
        "de": "Partner/in",
        "it": "Partner",
        "zh-CN": "伴侣",
    },
    "assistant": {
        "fr": "Assistant(e)",
        "en": "Assistant",
        "es": "Asistente",
        "de": "Assistent/in",
        "it": "Assistente",
        "zh-CN": "助理",
    },
    "manager": {
        "fr": "Responsable",
        "en": "Manager",
        "es": "Gerente",
        "de": "Vorgesetzter",
        "it": "Responsabile",
        "zh-CN": "经理",
    },
    "domesticPartner": {
        "fr": "Partenaire",
        "en": "Domestic Partner",
        "es": "Pareja doméstica",
        "de": "Lebenspartner",
        "it": "Convivente",
        "zh-CN": "同居伴侣",
    },
    "mother": {
        "fr": "Mère",
        "en": "Mother",
        "es": "Madre",
        "de": "Mutter",
        "it": "Madre",
        "zh-CN": "母亲",
    },
    "father": {
        "fr": "Père",
        "en": "Father",
        "es": "Padre",
        "de": "Vater",
        "it": "Padre",
        "zh-CN": "父亲",
    },
    "son": {"fr": "Fils", "en": "Son", "es": "Hijo", "de": "Sohn", "it": "Figlio", "zh-CN": "儿子"},
    "daughter": {
        "fr": "Fille",
        "en": "Daughter",
        "es": "Hija",
        "de": "Tochter",
        "it": "Figlia",
        "zh-CN": "女儿",
    },
    "brother": {
        "fr": "Frère",
        "en": "Brother",
        "es": "Hermano",
        "de": "Bruder",
        "it": "Fratello",
        "zh-CN": "兄弟",
    },
    "sister": {
        "fr": "Sœur",
        "en": "Sister",
        "es": "Hermana",
        "de": "Schwester",
        "it": "Sorella",
        "zh-CN": "姐妹",
    },
}

# Data types for contact info (email, phone, address types from Google Contacts API)
_DATA_TYPES: dict[str, dict[str, str]] = {
    "home": {
        "fr": "Domicile",
        "en": "Home",
        "es": "Casa",
        "de": "Privat",
        "it": "Casa",
        "zh-CN": "住宅",
    },
    "work": {
        "fr": "Travail",
        "en": "Work",
        "es": "Trabajo",
        "de": "Arbeit",
        "it": "Lavoro",
        "zh-CN": "工作",
    },
    "mobile": {
        "fr": "Mobile",
        "en": "Mobile",
        "es": "Móvil",
        "de": "Mobil",
        "it": "Cellulare",
        "zh-CN": "手机",
    },
    "main": {
        "fr": "Principal",
        "en": "Main",
        "es": "Principal",
        "de": "Haupt",
        "it": "Principale",
        "zh-CN": "主要",
    },
    "other": {
        "fr": "Autre",
        "en": "Other",
        "es": "Otro",
        "de": "Andere",
        "it": "Altro",
        "zh-CN": "其他",
    },
    "homefax": {
        "fr": "Fax domicile",
        "en": "Home Fax",
        "es": "Fax casa",
        "de": "Fax privat",
        "it": "Fax casa",
        "zh-CN": "住宅传真",
    },
    "workfax": {
        "fr": "Fax travail",
        "en": "Work Fax",
        "es": "Fax trabajo",
        "de": "Fax arbeit",
        "it": "Fax lavoro",
        "zh-CN": "工作传真",
    },
    "pager": {
        "fr": "Pager",
        "en": "Pager",
        "es": "Buscapersonas",
        "de": "Pager",
        "it": "Cercapersone",
        "zh-CN": "寻呼机",
    },
    "car": {
        "fr": "Voiture",
        "en": "Car",
        "es": "Coche",
        "de": "Auto",
        "it": "Auto",
        "zh-CN": "汽车",
    },
    "isdn": {"fr": "ISDN", "en": "ISDN", "es": "ISDN", "de": "ISDN", "it": "ISDN", "zh-CN": "ISDN"},
    "callback": {
        "fr": "Rappel",
        "en": "Callback",
        "es": "Devolver llamada",
        "de": "Rückruf",
        "it": "Richiamata",
        "zh-CN": "回拨",
    },
    "personal": {
        "fr": "Personnel",
        "en": "Personal",
        "es": "Personal",
        "de": "Persönlich",
        "it": "Personale",
        "zh-CN": "个人",
    },
}

_DISPLAY_SKILLS: dict[str, str] = {
    "fr": "Compétences",
    "en": "Skills",
    "es": "Habilidades",
    "de": "Fähigkeiten",
    "it": "Competenze",
    "zh-CN": "技能",
}

_DISPLAY_INTERESTS: dict[str, str] = {
    "fr": "Intérêts",
    "en": "Interests",
    "es": "Intereses",
    "de": "Interessen",
    "it": "Interessi",
    "zh-CN": "兴趣",
}

_DISPLAY_OCCUPATION: dict[str, str] = {
    "fr": "Profession",
    "en": "Occupation",
    "es": "Profesión",
    "de": "Beruf",
    "it": "Professione",
    "zh-CN": "职业",
}

_DISPLAY_EVENTS: dict[str, str] = {
    "fr": "Événements",
    "en": "Events",
    "es": "Eventos",
    "de": "Ereignisse",
    "it": "Eventi",
    "zh-CN": "事件",
}

_DISPLAY_LOCATIONS: dict[str, str] = {
    "fr": "Lieux",
    "en": "Locations",
    "es": "Ubicaciones",
    "de": "Standorte",
    "it": "Luoghi",
    "zh-CN": "位置",
}

_DISPLAY_CALENDAR: dict[str, str] = {
    "fr": "Calendrier",
    "en": "Calendar",
    "es": "Calendario",
    "de": "Kalender",
    "it": "Calendario",
    "zh-CN": "日历",
}

# =============================================================================
# DOMAIN SECTION LABELS (for multi-domain display)
# Used by html_renderer._get_domain_label() for section titles
# =============================================================================

_DOMAIN_SECTION_LABELS: dict[str, dict[str, str]] = {
    "contacts": {
        "fr": "Contacts",
        "en": "Contacts",
        "es": "Contactos",
        "de": "Kontakte",
        "it": "Contatti",
        "zh-CN": "联系人",
    },
    "emails": {
        "fr": "Emails",
        "en": "Emails",
        "es": "Correos",
        "de": "E-Mails",
        "it": "Email",
        "zh-CN": "邮件",
    },
    "calendar": {
        "fr": "Événements",
        "en": "Events",
        "es": "Eventos",
        "de": "Termine",
        "it": "Eventi",
        "zh-CN": "活动",
    },
    "events": {
        "fr": "Événements",
        "en": "Events",
        "es": "Eventos",
        "de": "Termine",
        "it": "Eventi",
        "zh-CN": "活动",
    },
    "tasks": {
        "fr": "Tâches",
        "en": "Tasks",
        "es": "Tareas",
        "de": "Aufgaben",
        "it": "Attività",
        "zh-CN": "任务",
    },
    "places": {
        "fr": "Lieux",
        "en": "Places",
        "es": "Lugares",
        "de": "Orte",
        "it": "Luoghi",
        "zh-CN": "地点",
    },
    "weather": {
        "fr": "Météo",
        "en": "Weather",
        "es": "Clima",
        "de": "Wetter",
        "it": "Meteo",
        "zh-CN": "天气",
    },
    "weathers": {
        "fr": "Météo",
        "en": "Weather",
        "es": "Clima",
        "de": "Wetter",
        "it": "Meteo",
        "zh-CN": "天气",
    },
    "drive": {
        "fr": "Fichiers",
        "en": "Files",
        "es": "Archivos",
        "de": "Dateien",
        "it": "File",
        "zh-CN": "文件",
    },
    "files": {
        "fr": "Fichiers",
        "en": "Files",
        "es": "Archivos",
        "de": "Dateien",
        "it": "File",
        "zh-CN": "文件",
    },
    "wikipedia": {
        "fr": "Articles",
        "en": "Articles",
        "es": "Artículos",
        "de": "Artikel",
        "it": "Articoli",
        "zh-CN": "文章",
    },
    "wikipedias": {
        "fr": "Articles",
        "en": "Articles",
        "es": "Artículos",
        "de": "Artikel",
        "it": "Articoli",
        "zh-CN": "文章",
    },
    "articles": {
        "fr": "Articles",
        "en": "Articles",
        "es": "Artículos",
        "de": "Artikel",
        "it": "Articoli",
        "zh-CN": "文章",
    },
    "perplexity": {
        "fr": "Recherche",
        "en": "Search",
        "es": "Búsqueda",
        "de": "Suche",
        "it": "Ricerca",
        "zh-CN": "搜索",
    },
    "perplexitys": {
        "fr": "Recherche",
        "en": "Search",
        "es": "Búsqueda",
        "de": "Suche",
        "it": "Ricerca",
        "zh-CN": "搜索",
    },
    "search": {
        "fr": "Recherche",
        "en": "Search",
        "es": "Búsqueda",
        "de": "Suche",
        "it": "Ricerca",
        "zh-CN": "搜索",
    },
    "reminders": {
        "fr": "Rappels",
        "en": "Reminders",
        "es": "Recordatorios",
        "de": "Erinnerungen",
        "it": "Promemoria",
        "zh-CN": "提醒",
    },
    "routes": {
        "fr": "Itinéraire",
        "en": "Route",
        "es": "Ruta",
        "de": "Route",
        "it": "Percorso",
        "zh-CN": "路线",
    },
    "braves": {
        "fr": "Recherche Brave",
        "en": "Brave Search",
        "es": "Búsqueda Brave",
        "de": "Brave Suche",
        "it": "Ricerca Brave",
        "zh-CN": "Brave搜索",
    },
    "web_search": {
        "fr": "Recherche web",
        "en": "Web Search",
        "es": "Búsqueda web",
        "de": "Websuche",
        "it": "Ricerca web",
        "zh-CN": "网页搜索",
    },
    "web_searchs": {
        "fr": "Recherche web",
        "en": "Web Search",
        "es": "Búsqueda web",
        "de": "Websuche",
        "it": "Ricerca web",
        "zh-CN": "网页搜索",
    },
    "mcps": {
        "fr": "Résultats MCP",
        "en": "MCP Results",
        "es": "Resultados MCP",
        "de": "MCP-Ergebnisse",
        "it": "Risultati MCP",
        "zh-CN": "MCP结果",
    },
    "mcp_apps": {
        "fr": "Application MCP",
        "en": "MCP Application",
        "es": "Aplicación MCP",
        "de": "MCP-Anwendung",
        "it": "Applicazione MCP",
        "zh-CN": "MCP应用",
    },
}

# =============================================================================
# EVENT COMPONENT STRINGS
# =============================================================================

_DISPLAY_TENTATIVE: dict[str, str] = {
    "fr": "Provisoire",
    "en": "Tentative",
    "es": "Provisional",
    "de": "Vorläufig",
    "it": "Provvisorio",
    "zh-CN": "暂定",
}

_DISPLAY_CANCELLED: dict[str, str] = {
    "fr": "Annulé",
    "en": "Cancelled",
    "es": "Cancelado",
    "de": "Abgesagt",
    "it": "Annullato",
    "zh-CN": "已取消",
}

_DISPLAY_ALL_DAY: dict[str, str] = {
    "fr": "Journée",
    "en": "All day",
    "es": "Todo el día",
    "de": "Ganztägig",
    "it": "Tutto il giorno",
    "zh-CN": "全天",
}

_DISPLAY_ALL_DAY_LONG: dict[str, str] = {
    "fr": "Toute la journée",
    "en": "All day",
    "es": "Todo el día",
    "de": "Ganztägig",
    "it": "Tutto il giorno",
    "zh-CN": "全天",
}

_DISPLAY_PARTICIPANT: dict[str, str] = {
    "fr": "participant",
    "en": "participant",
    "es": "participante",
    "de": "Teilnehmer",
    "it": "partecipante",
    "zh-CN": "参与者",
}

_DISPLAY_PARTICIPANTS: dict[str, str] = {
    "fr": "Participants",
    "en": "Participants",
    "es": "Participantes",
    "de": "Teilnehmer",
    "it": "Partecipanti",
    "zh-CN": "参与者",
}

_DISPLAY_ORGANIZED_BY: dict[str, str] = {
    "fr": "Organisé par",
    "en": "Organized by",
    "es": "Organizado por",
    "de": "Organisiert von",
    "it": "Organizzato da",
    "zh-CN": "由...组织",
}

_DISPLAY_JOIN_MEET: dict[str, str] = {
    "fr": "Visio",
    "en": "Video",
    "es": "Video",
    "de": "Video",
    "it": "Video",
    "zh-CN": "视频",
}

_DISPLAY_RECURRING_EVENT: dict[str, str] = {
    "fr": "Événement récurrent",
    "en": "Recurring event",
    "es": "Evento recurrente",
    "de": "Wiederkehrendes Ereignis",
    "it": "Evento ricorrente",
    "zh-CN": "重复事件",
}

_DISPLAY_DEFAULT_REMINDER: dict[str, str] = {
    "fr": "Rappel par défaut",
    "en": "Default reminder",
    "es": "Recordatorio predeterminado",
    "de": "Standarderinnerung",
    "it": "Promemoria predefinito",
    "zh-CN": "默认提醒",
}

_DISPLAY_REMINDERS: dict[str, str] = {
    "fr": "Rappels",
    "en": "Reminders",
    "es": "Recordatorios",
    "de": "Erinnerungen",
    "it": "Promemoria",
    "zh-CN": "提醒",
}

# Time expressions for reminders
_DISPLAY_AT_EVENT_TIME: dict[str, str] = {
    "fr": "À l'heure de l'événement",
    "en": "At event time",
    "es": "A la hora del evento",
    "de": "Zur Ereigniszeit",
    "it": "All'ora dell'evento",
    "zh-CN": "在事件时间",
}

_DISPLAY_MINUTES_BEFORE: dict[str, str] = {
    "fr": "{count} minutes avant",
    "en": "{count} minutes before",
    "es": "{count} minutos antes",
    "de": "{count} Minuten vorher",
    "it": "{count} minuti prima",
    "zh-CN": "{count}分钟前",
}

_DISPLAY_HOUR_BEFORE: dict[str, str] = {
    "fr": "1 heure avant",
    "en": "1 hour before",
    "es": "1 hora antes",
    "de": "1 Stunde vorher",
    "it": "1 ora prima",
    "zh-CN": "1小时前",
}

_DISPLAY_HOURS_BEFORE: dict[str, str] = {
    "fr": "{count} heures avant",
    "en": "{count} hours before",
    "es": "{count} horas antes",
    "de": "{count} Stunden vorher",
    "it": "{count} ore prima",
    "zh-CN": "{count}小时前",
}

_DISPLAY_DAY_BEFORE: dict[str, str] = {
    "fr": "1 jour avant",
    "en": "1 day before",
    "es": "1 día antes",
    "de": "1 Tag vorher",
    "it": "1 giorno prima",
    "zh-CN": "1天前",
}

_DISPLAY_DAYS_BEFORE: dict[str, str] = {
    "fr": "{count} jours avant",
    "en": "{count} days before",
    "es": "{count} días antes",
    "de": "{count} Tage vorher",
    "it": "{count} giorni prima",
    "zh-CN": "{count}天前",
}

_DISPLAY_WEEK_BEFORE: dict[str, str] = {
    "fr": "1 semaine avant",
    "en": "1 week before",
    "es": "1 semana antes",
    "de": "1 Woche vorher",
    "it": "1 settimana prima",
    "zh-CN": "1周前",
}

_DISPLAY_WEEKS_BEFORE: dict[str, str] = {
    "fr": "{count} semaines avant",
    "en": "{count} weeks before",
    "es": "{count} semanas antes",
    "de": "{count} Wochen vorher",
    "it": "{count} settimane prima",
    "zh-CN": "{count}周前",
}

# =============================================================================
# PLACE COMPONENT STRINGS
# =============================================================================

_DISPLAY_OPEN: dict[str, str] = {
    "fr": "Ouvert",
    "en": "Open",
    "es": "Abierto",
    "de": "Geöffnet",
    "it": "Aperto",
    "zh-CN": "营业中",
}

_DISPLAY_CLOSED: dict[str, str] = {
    "fr": "Fermé",
    "en": "Closed",
    "es": "Cerrado",
    "de": "Geschlossen",
    "it": "Chiuso",
    "zh-CN": "已关闭",
}

_DISPLAY_OPEN_NOW: dict[str, str] = {
    "fr": "Ouvert maintenant",
    "en": "Open now",
    "es": "Abierto ahora",
    "de": "Jetzt geöffnet",
    "it": "Aperto ora",
}

_DISPLAY_OPENS_AT: dict[str, str] = {
    "fr": "Ouvre à",
    "en": "Opens at",
    "es": "Abre a las",
    "de": "Öffnet um",
    "it": "Apre alle",
    "zh-CN": "开门时间",
}

_DISPLAY_REVIEWS: dict[str, str] = {
    "fr": "avis",
    "en": "reviews",
    "es": "reseñas",
    "de": "Bewertungen",
    "it": "recensioni",
    "zh-CN": "评论",
}

_DISPLAY_FREE: dict[str, str] = {
    "fr": "Gratuit",
    "en": "Free",
    "es": "Gratis",
    "de": "Kostenlos",
    "it": "Gratuito",
    "zh-CN": "免费",
}

_DISPLAY_WEBSITE: dict[str, str] = {
    "fr": "Site",
    "en": "Site",
    "es": "Sitio",
    "de": "Seite",
    "it": "Sito",
    "zh-CN": "网站",
}

_DISPLAY_DIRECTIONS: dict[str, str] = {
    "fr": "Itinéraire",
    "en": "Directions",
    "es": "Indicaciones",
    "de": "Wegbeschreibung",
    "it": "Indicazioni",
    "zh-CN": "路线",
}

_DISPLAY_SERVICES_AMENITIES: dict[str, str] = {
    "fr": "Services & équipements",
    "en": "Services & amenities",
    "es": "Servicios y comodidades",
    "de": "Services & Ausstattung",
    "it": "Servizi e comfort",
    "zh-CN": "服务和设施",
}

_DISPLAY_DESCRIPTION: dict[str, str] = {
    "fr": "Description",
    "en": "Description",
    "es": "Descripción",
    "de": "Beschreibung",
    "it": "Descrizione",
    "zh-CN": "描述",
}

_DISPLAY_OPENING_HOURS: dict[str, str] = {
    "fr": "Horaires d'ouverture",
    "en": "Opening hours",
    "es": "Horarios de apertura",
    "de": "Öffnungszeiten",
    "it": "Orari di apertura",
    "zh-CN": "营业时间",
}

# Place types
_DISPLAY_PLACE_TYPES: dict[str, dict[str, str]] = {
    "restaurant": {
        "fr": "🍽️ Restaurant",
        "en": "🍽️ Restaurant",
        "es": "🍽️ Restaurante",
        "de": "🍽️ Restaurant",
        "it": "🍽️ Ristorante",
        "zh-CN": "🍽️ 餐厅",
    },
    "cafe": {
        "fr": "☕ Café",
        "en": "☕ Café",
        "es": "☕ Café",
        "de": "☕ Café",
        "it": "☕ Caffè",
        "zh-CN": "☕ 咖啡馆",
    },
    "bar": {
        "fr": "🍸 Bar",
        "en": "🍸 Bar",
        "es": "🍸 Bar",
        "de": "🍸 Bar",
        "it": "🍸 Bar",
        "zh-CN": "🍸 酒吧",
    },
    "bakery": {
        "fr": "🥐 Boulangerie",
        "en": "🥐 Bakery",
        "es": "🥐 Panadería",
        "de": "🥐 Bäckerei",
        "it": "🥐 Panetteria",
        "zh-CN": "🥐 面包店",
    },
    "hotel": {
        "fr": "🏨 Hôtel",
        "en": "🏨 Hotel",
        "es": "🏨 Hotel",
        "de": "🏨 Hotel",
        "it": "🏨 Hotel",
        "zh-CN": "🏨 酒店",
    },
    "store": {
        "fr": "🏪 Magasin",
        "en": "🏪 Store",
        "es": "🏪 Tienda",
        "de": "🏪 Geschäft",
        "it": "🏪 Negozio",
        "zh-CN": "🏪 商店",
    },
    "pharmacy": {
        "fr": "💊 Pharmacie",
        "en": "💊 Pharmacy",
        "es": "💊 Farmacia",
        "de": "💊 Apotheke",
        "it": "💊 Farmacia",
        "zh-CN": "💊 药店",
    },
    "hospital": {
        "fr": "🏥 Hôpital",
        "en": "🏥 Hospital",
        "es": "🏥 Hospital",
        "de": "🏥 Krankenhaus",
        "it": "🏥 Ospedale",
        "zh-CN": "🏥 医院",
    },
    "gym": {
        "fr": "💪 Salle de sport",
        "en": "💪 Gym",
        "es": "💪 Gimnasio",
        "de": "💪 Fitnessstudio",
        "it": "💪 Palestra",
        "zh-CN": "💪 健身房",
    },
    "park": {
        "fr": "🌳 Parc",
        "en": "🌳 Park",
        "es": "🌳 Parque",
        "de": "🌳 Park",
        "it": "🌳 Parco",
        "zh-CN": "🌳 公园",
    },
    "museum": {
        "fr": "🏛️ Musée",
        "en": "🏛️ Museum",
        "es": "🏛️ Museo",
        "de": "🏛️ Museum",
        "it": "🏛️ Museo",
        "zh-CN": "🏛️ 博物馆",
    },
    "movie_theater": {
        "fr": "🎬 Cinéma",
        "en": "🎬 Cinema",
        "es": "🎬 Cine",
        "de": "🎬 Kino",
        "it": "🎬 Cinema",
        "zh-CN": "🎬 电影院",
    },
}

# Place features
_DISPLAY_PLACE_FEATURES: dict[str, dict[str, str]] = {
    # Dining
    "dine_in": {
        "fr": "🍽️ Sur place",
        "en": "🍽️ Dine-in",
        "es": "🍽️ En el local",
        "de": "🍽️ Vor Ort",
        "it": "🍽️ Sul posto",
        "zh-CN": "🍽️ 堂食",
    },
    "delivery": {
        "fr": "🛵 Livraison",
        "en": "🛵 Delivery",
        "es": "🛵 Entrega",
        "de": "🛵 Lieferung",
        "it": "🛵 Consegna",
        "zh-CN": "🛵 外卖",
    },
    "takeout": {
        "fr": "🥡 À emporter",
        "en": "🥡 Takeout",
        "es": "🥡 Para llevar",
        "de": "🥡 Zum Mitnehmen",
        "it": "🥡 Da asporto",
        "zh-CN": "🥡 外带",
    },
    "outdoor_seating": {
        "fr": "☀️ Terrasse",
        "en": "☀️ Outdoor seating",
        "es": "☀️ Terraza",
        "de": "☀️ Außenbereich",
        "it": "☀️ Terrazza",
        "zh-CN": "☀️ 户外座位",
    },
    "curbside_pickup": {
        "fr": "🚗 Retrait",
        "en": "🚗 Curbside pickup",
        "es": "🚗 Recogida",
        "de": "🚗 Abholung",
        "it": "🚗 Ritiro",
        "zh-CN": "🚗 路边取餐",
    },
    # Meals
    "serves_breakfast": {
        "fr": "🌅 Petit-déjeuner",
        "en": "🌅 Breakfast",
        "es": "🌅 Desayuno",
        "de": "🌅 Frühstück",
        "it": "🌅 Colazione",
        "zh-CN": "🌅 早餐",
    },
    "serves_lunch": {
        "fr": "🌞 Déjeuner",
        "en": "🌞 Lunch",
        "es": "🌞 Almuerzo",
        "de": "🌞 Mittagessen",
        "it": "🌞 Pranzo",
        "zh-CN": "🌞 午餐",
    },
    "serves_dinner": {
        "fr": "🌙 Dîner",
        "en": "🌙 Dinner",
        "es": "🌙 Cena",
        "de": "🌙 Abendessen",
        "it": "🌙 Cena",
        "zh-CN": "🌙 晚餐",
    },
    "serves_brunch": {
        "fr": "🥂 Brunch",
        "en": "🥂 Brunch",
        "es": "🥂 Brunch",
        "de": "🥂 Brunch",
        "it": "🥂 Brunch",
        "zh-CN": "🥂 早午餐",
    },
    # Drinks
    "serves_wine": {
        "fr": "🍷 Vin",
        "en": "🍷 Wine",
        "es": "🍷 Vino",
        "de": "🍷 Wein",
        "it": "🍷 Vino",
        "zh-CN": "🍷 葡萄酒",
    },
    "serves_beer": {
        "fr": "🍺 Bière",
        "en": "🍺 Beer",
        "es": "🍺 Cerveza",
        "de": "🍺 Bier",
        "it": "🍺 Birra",
        "zh-CN": "🍺 啤酒",
    },
    "serves_coffee": {
        "fr": "☕ Café",
        "en": "☕ Coffee",
        "es": "☕ Café",
        "de": "☕ Kaffee",
        "it": "☕ Caffè",
        "zh-CN": "☕ 咖啡",
    },
    "serves_cocktails": {
        "fr": "🍹 Cocktails",
        "en": "🍹 Cocktails",
        "es": "🍹 Cócteles",
        "de": "🍹 Cocktails",
        "it": "🍹 Cocktail",
        "zh-CN": "🍹 鸡尾酒",
    },
    # Amenities
    "reservable": {
        "fr": "📅 Réservation",
        "en": "📅 Reservations",
        "es": "📅 Reservas",
        "de": "📅 Reservierung",
        "it": "📅 Prenotazioni",
        "zh-CN": "📅 可预订",
    },
    "good_for_groups": {
        "fr": "👥 Groupes",
        "en": "👥 Groups",
        "es": "👥 Grupos",
        "de": "👥 Gruppen",
        "it": "👥 Gruppi",
        "zh-CN": "👥 适合团体",
    },
    "good_for_children": {
        "fr": "👶 Enfants",
        "en": "👶 Kids",
        "es": "👶 Niños",
        "de": "👶 Kinder",
        "it": "👶 Bambini",
        "zh-CN": "👶 适合儿童",
    },
    "live_music": {
        "fr": "🎵 Musique live",
        "en": "🎵 Live music",
        "es": "🎵 Música en vivo",
        "de": "🎵 Live-Musik",
        "it": "🎵 Musica dal vivo",
        "zh-CN": "🎵 现场音乐",
    },
    "free_wifi": {
        "fr": "📶 Wifi gratuit",
        "en": "📶 Free WiFi",
        "es": "📶 WiFi gratis",
        "de": "📶 Gratis WLAN",
        "it": "📶 WiFi gratuito",
        "zh-CN": "📶 免费WiFi",
    },
    "parking": {
        "fr": "🅿️ Parking",
        "en": "🅿️ Parking",
        "es": "🅿️ Aparcamiento",
        "de": "🅿️ Parkplatz",
        "it": "🅿️ Parcheggio",
        "zh-CN": "🅿️ 停车场",
    },
}

# Accessibility labels
_DISPLAY_ACCESSIBILITY: dict[str, dict[str, str]] = {
    "wheelchair_entrance": {
        "fr": "♿ Entrée accessible",
        "en": "♿ Wheelchair accessible entrance",
        "es": "♿ Entrada accesible",
        "de": "♿ Barrierefreier Eingang",
        "it": "♿ Ingresso accessibile",
        "zh-CN": "♿ 无障碍入口",
    },
    "wheelchair_parking": {
        "fr": "♿ Parking accessible",
        "en": "♿ Wheelchair accessible parking",
        "es": "♿ Estacionamiento accesible",
        "de": "♿ Barrierefreier Parkplatz",
        "it": "♿ Parcheggio accessibile",
        "zh-CN": "♿ 无障碍停车",
    },
    "wheelchair_seating": {
        "fr": "♿ Places assises accessibles",
        "en": "♿ Wheelchair accessible seating",
        "es": "♿ Asientos accesibles",
        "de": "♿ Barrierefreie Sitzplätze",
        "it": "♿ Posti a sedere accessibili",
        "zh-CN": "♿ 无障碍座位",
    },
    "wheelchair_restroom": {
        "fr": "♿ Toilettes accessibles",
        "en": "♿ Wheelchair accessible restroom",
        "es": "♿ Baños accesibles",
        "de": "♿ Barrierefreie Toiletten",
        "it": "♿ Bagni accessibili",
        "zh-CN": "♿ 无障碍洗手间",
    },
}

# Payment labels
_DISPLAY_PAYMENT: dict[str, dict[str, str]] = {
    "credit_cards": {
        "fr": "💳 Cartes acceptées",
        "en": "💳 Credit cards accepted",
        "es": "💳 Tarjetas aceptadas",
        "de": "💳 Karten akzeptiert",
        "it": "💳 Carte accettate",
        "zh-CN": "💳 接受信用卡",
    },
    "cash_only": {
        "fr": "💵 Espèces uniquement",
        "en": "💵 Cash only",
        "es": "💵 Solo efectivo",
        "de": "💵 Nur Bargeld",
        "it": "💵 Solo contanti",
        "zh-CN": "💵 仅限现金",
    },
    "contactless": {
        "fr": "📱 Paiement sans contact",
        "en": "📱 Contactless payment",
        "es": "📱 Pago sin contacto",
        "de": "📱 Kontaktloses Bezahlen",
        "it": "📱 Pagamento contactless",
        "zh-CN": "📱 无接触支付",
    },
}

# =============================================================================
# SEARCH RESULT COMPONENT STRINGS
# =============================================================================

_DISPLAY_SOURCES: dict[str, str] = {
    "fr": "Sources",
    "en": "Sources",
    "es": "Fuentes",
    "de": "Quellen",
    "it": "Fonti",
    "zh-CN": "来源",
}

_DISPLAY_RELATED_QUESTIONS: dict[str, str] = {
    "fr": "Questions connexes",
    "en": "Related questions",
    "es": "Preguntas relacionadas",
    "de": "Verwandte Fragen",
    "it": "Domande correlate",
    "zh-CN": "相关问题",
}

_DISPLAY_SEARCH: dict[str, str] = {
    "fr": "Recherche",
    "en": "Search",
    "es": "Búsqueda",
    "de": "Suche",
    "it": "Ricerca",
    "zh-CN": "搜索",
}

_DISPLAY_INTERNET: dict[str, str] = {
    "fr": "Internet",
    "en": "Internet",
    "es": "Internet",
    "de": "Internet",
    "it": "Internet",
    "zh-CN": "互联网",
}

_DISPLAY_AI_SYNTHESIS: dict[str, str] = {
    "fr": "Synthèse IA",
    "en": "AI Synthesis",
    "es": "Síntesis IA",
    "de": "KI-Synthese",
    "it": "Sintesi IA",
    "zh-CN": "AI综合",
}

_DISPLAY_WEB_RESULTS: dict[str, str] = {
    "fr": "Résultats web",
    "en": "Web results",
    "es": "Resultados web",
    "de": "Webergebnisse",
    "it": "Risultati web",
    "zh-CN": "网络结果",
}

_DISPLAY_EDIT: dict[str, str] = {
    "fr": "Modifier",
    "en": "Edit",
    "es": "Editar",
    "de": "Bearbeiten",
    "it": "Modifica",
    "zh-CN": "编辑",
}

_DISPLAY_DELETE: dict[str, str] = {
    "fr": "Supprimer",
    "en": "Delete",
    "es": "Eliminar",
    "de": "Löschen",
    "it": "Elimina",
    "zh-CN": "删除",
}

_DISPLAY_CALL: dict[str, str] = {
    "fr": "Appeler",
    "en": "Call",
    "es": "Llamar",
    "de": "Anrufen",
    "it": "Chiama",
    "zh-CN": "拨打",
}

_DISPLAY_EMAIL: dict[str, str] = {
    "fr": "Email",
    "en": "Email",
    "es": "Email",
    "de": "Email",
    "it": "Email",
    "zh-CN": "邮件",
}

_DISPLAY_VIEW_DETAILS: dict[str, str] = {
    "fr": "Voir",
    "en": "View",
    "es": "Ver",
    "de": "Ansehen",
    "it": "Vedi",
    "zh-CN": "查看",
}

# =============================================================================
# FILE TYPE LABELS
# =============================================================================

# File type labels
_DISPLAY_FILE_TYPES: dict[str, dict[str, str]] = {
    "document": {
        "fr": "Document",
        "en": "Document",
        "es": "Documento",
        "de": "Dokument",
        "it": "Documento",
        "zh-CN": "文档",
    },
    "spreadsheet": {
        "fr": "Tableur",
        "en": "Spreadsheet",
        "es": "Hoja de cálculo",
        "de": "Tabelle",
        "it": "Foglio di calcolo",
        "zh-CN": "电子表格",
    },
    "presentation": {
        "fr": "Présentation",
        "en": "Presentation",
        "es": "Presentación",
        "de": "Präsentation",
        "it": "Presentazione",
        "zh-CN": "演示文稿",
    },
    "folder": {
        "fr": "Dossier",
        "en": "Folder",
        "es": "Carpeta",
        "de": "Ordner",
        "it": "Cartella",
        "zh-CN": "文件夹",
    },
    "form": {
        "fr": "Formulaire",
        "en": "Form",
        "es": "Formulario",
        "de": "Formular",
        "it": "Modulo",
        "zh-CN": "表单",
    },
    "pdf": {
        "fr": "PDF",
        "en": "PDF",
        "es": "PDF",
        "de": "PDF",
        "it": "PDF",
        "zh-CN": "PDF",
    },
    "word": {
        "fr": "Word",
        "en": "Word",
        "es": "Word",
        "de": "Word",
        "it": "Word",
        "zh-CN": "Word",
    },
    "excel": {
        "fr": "Excel",
        "en": "Excel",
        "es": "Excel",
        "de": "Excel",
        "it": "Excel",
        "zh-CN": "Excel",
    },
    "powerpoint": {
        "fr": "PowerPoint",
        "en": "PowerPoint",
        "es": "PowerPoint",
        "de": "PowerPoint",
        "it": "PowerPoint",
        "zh-CN": "PowerPoint",
    },
    "image": {
        "fr": "Image",
        "en": "Image",
        "es": "Imagen",
        "de": "Bild",
        "it": "Immagine",
        "zh-CN": "图片",
    },
    "video": {
        "fr": "Vidéo",
        "en": "Video",
        "es": "Vídeo",
        "de": "Video",
        "it": "Video",
        "zh-CN": "视频",
    },
    "audio": {
        "fr": "Audio",
        "en": "Audio",
        "es": "Audio",
        "de": "Audio",
        "it": "Audio",
        "zh-CN": "音频",
    },
    "text": {
        "fr": "Texte",
        "en": "Text",
        "es": "Texto",
        "de": "Text",
        "it": "Testo",
        "zh-CN": "文本",
    },
    "archive": {
        "fr": "Archive",
        "en": "Archive",
        "es": "Archivo",
        "de": "Archiv",
        "it": "Archivio",
        "zh-CN": "压缩包",
    },
    "file": {
        "fr": "Fichier",
        "en": "File",
        "es": "Archivo",
        "de": "Datei",
        "it": "File",
        "zh-CN": "文件",
    },
}

# =============================================================================
# ROUTE COMPONENT STRINGS
# =============================================================================

_ROUTE_TRAVEL_MODES: dict[str, dict[str, str]] = {
    "DRIVE": {
        "fr": "En voiture",
        "en": "By car",
        "es": "En coche",
        "de": "Mit dem Auto",
        "it": "In auto",
        "zh-CN": "驾车",
    },
    "WALK": {
        "fr": "À pied",
        "en": "On foot",
        "es": "A pie",
        "de": "Zu Fuß",
        "it": "A piedi",
        "zh-CN": "步行",
    },
    "BICYCLE": {
        "fr": "À vélo",
        "en": "By bike",
        "es": "En bicicleta",
        "de": "Mit dem Fahrrad",
        "it": "In bici",
        "zh-CN": "骑车",
    },
    "TRANSIT": {
        "fr": "En transports",
        "en": "By transit",
        "es": "En transporte",
        "de": "Mit ÖPNV",
        "it": "Con mezzi",
        "zh-CN": "公交",
    },
    "TWO_WHEELER": {
        "fr": "En deux-roues",
        "en": "By motorcycle",
        "es": "En moto",
        "de": "Mit Motorrad",
        "it": "In moto",
        "zh-CN": "摩托车",
    },
}

_ROUTE_TRAFFIC_CONDITIONS: dict[str, dict[str, str]] = {
    "NORMAL": {
        "fr": "Fluide",
        "en": "Normal",
        "es": "Fluido",
        "de": "Normal",
        "it": "Normale",
        "zh-CN": "正常",
    },
    "LIGHT": {
        "fr": "Très fluide",
        "en": "Very light",
        "es": "Muy fluido",
        "de": "Sehr flüssig",
        "it": "Molto scorrevole",
        "zh-CN": "非常畅通",
    },
    "MODERATE": {
        "fr": "Modéré",
        "en": "Moderate",
        "es": "Moderado",
        "de": "Mäßig",
        "it": "Moderato",
        "zh-CN": "一般",
    },
    "HEAVY": {
        "fr": "Dense",
        "en": "Heavy",
        "es": "Denso",
        "de": "Stark",
        "it": "Intenso",
        "zh-CN": "拥堵",
    },
}

_ROUTE_AVOIDANCES: dict[str, dict[str, str]] = {
    "tolls": {
        "fr": "Évite les péages",
        "en": "Avoids tolls",
        "es": "Evita peajes",
        "de": "Maut vermeiden",
        "it": "Evita pedaggi",
        "zh-CN": "避开收费",
    },
    "highways": {
        "fr": "Évite les autoroutes",
        "en": "Avoids highways",
        "es": "Evita autopistas",
        "de": "Autobahnen vermeiden",
        "it": "Evita autostrade",
        "zh-CN": "避开高速",
    },
    "ferries": {
        "fr": "Évite les ferries",
        "en": "Avoids ferries",
        "es": "Evita ferries",
        "de": "Fähren vermeiden",
        "it": "Evita traghetti",
        "zh-CN": "避开渡轮",
    },
}

_DISPLAY_DISTANCE: dict[str, str] = {
    "fr": "Distance",
    "en": "Distance",
    "es": "Distancia",
    "de": "Entfernung",
    "it": "Distanza",
    "zh-CN": "距离",
}

_DISPLAY_DURATION: dict[str, str] = {
    "fr": "Durée",
    "en": "Duration",
    "es": "Duración",
    "de": "Dauer",
    "it": "Durata",
    "zh-CN": "时长",
}

_DISPLAY_TRAFFIC: dict[str, str] = {
    "fr": "Trafic",
    "en": "Traffic",
    "es": "Tráfico",
    "de": "Verkehr",
    "it": "Traffico",
    "zh-CN": "路况",
}

_DISPLAY_WITH_TRAFFIC: dict[str, str] = {
    "fr": "avec trafic",
    "en": "with traffic",
    "es": "con tráfico",
    "de": "mit Verkehr",
    "it": "con traffico",
    "zh-CN": "含路况",
}

_DISPLAY_TOLL_LABEL: dict[str, str] = {
    "fr": "Péages",
    "en": "Tolls",
    "es": "Peajes",
    "de": "Maut",
    "it": "Pedaggi",
    "zh-CN": "通行费",
}

_DISPLAY_ARRIVAL_TIME: dict[str, str] = {
    "fr": "Arrivée",
    "en": "Arrival",
    "es": "Llegada",
    "de": "Ankunft",
    "it": "Arrivo",
    "zh-CN": "到达",
}

_DISPLAY_SUGGESTED_DEPARTURE: dict[str, str] = {
    "fr": "Départ conseillé",
    "en": "Suggested departure",
    "es": "Salida sugerida",
    "de": "Empfohlene Abfahrt",
    "it": "Partenza consigliata",
    "zh-CN": "建议出发",
}

_DISPLAY_TO_ARRIVE_BY: dict[str, str] = {
    "fr": "Pour arriver à {time}, partez à {departure}",
    "en": "To arrive by {time}, leave at {departure}",
    "es": "Para llegar a las {time}, salga a las {departure}",
    "de": "Um {time} anzukommen, fahren Sie um {departure} los",
    "it": "Per arrivare alle {time}, partire alle {departure}",
    "zh-CN": "要在{time}到达，请在{departure}出发",
}

_DISPLAY_OPEN_IN_MAPS: dict[str, str] = {
    "fr": "Ouvrir dans Maps",
    "en": "Open in Maps",
    "es": "Abrir en Maps",
    "de": "In Maps öffnen",
    "it": "Apri in Maps",
    "zh-CN": "在地图中打开",
}

_DISPLAY_ROUTE: dict[str, str] = {
    "fr": "Itinéraire",
    "en": "Route",
    "es": "Ruta",
    "de": "Route",
    "it": "Percorso",
    "zh-CN": "路线",
}

_DISPLAY_ROUTE_STEPS: dict[str, str] = {
    "fr": "Étapes",
    "en": "Steps",
    "es": "Pasos",
    "de": "Schritte",
    "it": "Tappe",
    "zh-CN": "步骤",
}

_DISPLAY_VIA: dict[str, str] = {
    "fr": "via",
    "en": "via",
    "es": "vía",
    "de": "über",
    "it": "via",
    "zh-CN": "经由",
}

_DISPLAY_ORIGIN: dict[str, str] = {
    "fr": "Départ",
    "en": "From",
    "es": "Origen",
    "de": "Start",
    "it": "Partenza",
    "zh-CN": "出发",
}

_DISPLAY_DESTINATION: dict[str, str] = {
    "fr": "Arrivée",
    "en": "To",
    "es": "Destino",
    "de": "Ziel",
    "it": "Arrivo",
    "zh-CN": "到达",
}

_DISPLAY_MY_LOCATION: dict[str, str] = {
    "fr": "Ma position",
    "en": "My location",
    "es": "Mi ubicación",
    "de": "Mein Standort",
    "it": "La mia posizione",
    "zh-CN": "我的位置",
}

_DISPLAY_MORE_STEPS: dict[str, str] = {
    "fr": "+{count} étapes de plus...",
    "en": "+{count} more steps...",
    "es": "+{count} pasos más...",
    "de": "+{count} weitere Schritte...",
    "it": "+{count} tappe in più...",
    "zh-CN": "还有{count}个步骤...",
}

_DISPLAY_TRANSIT_STOPS: dict[str, str] = {
    "fr": "{count} arrêts",
    "en": "{count} stops",
    "es": "{count} paradas",
    "de": "{count} Haltestellen",
    "it": "{count} fermate",
    "zh-CN": "{count}站",
}

_DISPLAY_TRANSIT_STOP_SINGLE: dict[str, str] = {
    "fr": "1 arrêt",
    "en": "1 stop",
    "es": "1 parada",
    "de": "1 Haltestelle",
    "it": "1 fermata",
    "zh-CN": "1站",
}

_DISPLAY_MCP_APP_LOADING: dict[str, str] = {
    "fr": "Chargement de l'application\u2026",
    "en": "Loading application\u2026",
    "es": "Cargando aplicaci\u00f3n\u2026",
    "de": "Anwendung wird geladen\u2026",
    "it": "Caricamento applicazione\u2026",
    "zh-CN": "\u52a0\u8f7d\u5e94\u7528\u7a0b\u5e8f\u2026",
}


class V3Messages:
    """
    Centralized v3 architecture message provider.

    Provides all translated strings for v3 components across all 6 languages.
    Falls back to English if requested language is not available.
    """

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        """Normalize language code to supported format."""
        if not language:
            return DEFAULT_LANGUAGE

        lang_lower = language.lower().replace("_", "-")

        # Handle Chinese variants
        if lang_lower.startswith("zh"):
            return "zh-CN"

        # Extract base language code
        base_lang = lang_lower.split("-")[0]

        # Check if it's a supported language
        if base_lang in ("fr", "en", "es", "de", "it"):
            return base_lang

        return DEFAULT_LANGUAGE

    # =========================================================================
    # RECOVERY MESSAGES
    # =========================================================================

    @staticmethod
    def get_partial_success_message(
        language: str,
        has_results: bool,
        tool_name: str = "",
        error: str = "",
    ) -> str:
        """Get partial success message for AutonomousExecutor."""
        lang = V3Messages._normalize_language(language)

        if has_results:
            template = _PARTIAL_SUCCESS_WITH_RESULTS.get(lang, _PARTIAL_SUCCESS_WITH_RESULTS["en"])
            return template.format(tool_name=tool_name, error=error)
        else:
            template = _PARTIAL_SUCCESS_NO_RESULTS.get(lang, _PARTIAL_SUCCESS_NO_RESULTS["en"])
            return template.format(error=error)

    @staticmethod
    def get_execution_stopped_message(language: str, reason: str) -> str:
        """Get execution stopped message."""
        lang = V3Messages._normalize_language(language)
        template = _EXECUTION_STOPPED.get(lang, _EXECUTION_STOPPED["en"])
        return template.format(reason=reason)

    @staticmethod
    def get_recovery_stopped_message(language: str, reason: str) -> str:
        """Get recovery stopped message."""
        lang = V3Messages._normalize_language(language)
        template = _RECOVERY_STOPPED.get(lang, _RECOVERY_STOPPED["en"])
        return template.format(reason=reason)

    # =========================================================================
    # PROACTIVE SUGGESTIONS
    # =========================================================================

    @staticmethod
    def get_proactive_suggestion(intent: str, language: str) -> str:
        """Get proactive suggestion for a given intent."""
        lang = V3Messages._normalize_language(language)

        suggestions = _PROACTIVE_SUGGESTIONS.get(intent, {})
        return suggestions.get(lang, suggestions.get("en", intent))

    @staticmethod
    def get_all_proactive_suggestions(language: str) -> dict[str, str]:
        """Get all proactive suggestions for a language."""
        lang = V3Messages._normalize_language(language)

        return {
            intent: msgs.get(lang, msgs.get("en", intent))
            for intent, msgs in _PROACTIVE_SUGGESTIONS.items()
        }

    # =========================================================================
    # FILTER EXPLANATIONS
    # =========================================================================

    @staticmethod
    def get_filter_explanation(
        language: str,
        total: int,
        shown: int,
        intent: str = "",
    ) -> str:
        """Get filter explanation for RelevanceEngine."""
        lang = V3Messages._normalize_language(language)

        if total == 0:
            return _FILTER_NO_RESULTS.get(lang, _FILTER_NO_RESULTS["en"])

        if total == 1:
            return _FILTER_ONE_RESULT.get(lang, _FILTER_ONE_RESULT["en"])

        if total == shown:
            template = _FILTER_ALL_SHOWN.get(lang, _FILTER_ALL_SHOWN["en"])
            return template.format(total=total)

        # NOTE: "detail" intent removed (2026-01), now using "search"
        # Show "most relevant" when displaying 1 result from many
        if shown == 1 and intent == "search":
            return _FILTER_MOST_RELEVANT.get(lang, _FILTER_MOST_RELEVANT["en"])

        template = _FILTER_TOP_N.get(lang, _FILTER_TOP_N["en"])
        return template.format(shown=shown, total=total)

    # =========================================================================
    # RELEVANCE REASONS
    # =========================================================================

    @staticmethod
    def get_relevance_reason(
        reason_key: str,
        language: str,
        **kwargs: Any,
    ) -> str:
        """Get translated relevance reason."""
        lang = V3Messages._normalize_language(language)

        reasons = _RELEVANCE_REASONS.get(reason_key, {})
        template = reasons.get(lang, reasons.get("en", reason_key))

        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    # =========================================================================
    # WARM INTROS
    # =========================================================================

    @staticmethod
    def get_warm_intro(
        language: str,
        context: str = "found_many",
        index: int = 0,
    ) -> str:
        """
        Get warm introduction message.

        Args:
            language: Language code
            context: Context type (found_many, found_one, contacts, calendar, etc.)
            index: Index of the pattern to use (cycles through available patterns)

        Returns:
            Warm introduction message
        """
        lang = V3Messages._normalize_language(language)

        intros = _WARM_INTROS.get(context, _WARM_INTROS["found_many"])
        patterns = intros.get(lang, intros.get("en", ["Here's what I found"]))

        if not patterns:
            return ""

        return patterns[index % len(patterns)]

    @staticmethod
    def get_warm_intro_patterns(language: str, context: str = "found_many") -> list[str]:
        """Get all warm intro patterns for a context."""
        lang = V3Messages._normalize_language(language)

        intros = _WARM_INTROS.get(context, _WARM_INTROS["found_many"])
        return intros.get(lang, intros.get("en", []))

    # =========================================================================
    # PROACTIVE OUTROS
    # =========================================================================

    @staticmethod
    def get_proactive_outro(
        language: str,
        domain: str = "general",
        index: int = 0,
    ) -> str:
        """
        Get proactive outro suggestion.

        Args:
            language: Language code
            domain: Domain type (contacts, calendar, emails, general)
            index: Index of the suggestion to use

        Returns:
            Proactive outro suggestion
        """
        lang = V3Messages._normalize_language(language)

        outros = _PROACTIVE_OUTROS.get(domain, _PROACTIVE_OUTROS["general"])
        patterns = outros.get(lang, outros.get("en", ["Anything else?"]))

        if not patterns:
            return ""

        return patterns[index % len(patterns)]

    @staticmethod
    def get_proactive_outro_patterns(language: str, domain: str = "general") -> list[str]:
        """Get all proactive outro patterns for a domain."""
        lang = V3Messages._normalize_language(language)

        outros = _PROACTIVE_OUTROS.get(domain, _PROACTIVE_OUTROS["general"])
        return outros.get(lang, outros.get("en", []))

    # =========================================================================
    # FORMATTER STRINGS
    # =========================================================================

    @staticmethod
    def get_no_results(language: str) -> str:
        """Get 'no results' message."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_NO_RESULTS.get(lang, _FORMATTER_NO_RESULTS["en"])

    @staticmethod
    def get_one_result(language: str) -> str:
        """Get '1 result found' message."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_ONE_RESULT.get(lang, _FORMATTER_ONE_RESULT["en"])

    @staticmethod
    def get_n_results(language: str, count: int) -> str:
        """Get 'N results found' message."""
        lang = V3Messages._normalize_language(language)
        template = _FORMATTER_N_RESULTS.get(lang, _FORMATTER_N_RESULTS["en"])
        return template.format(count=count)

    @staticmethod
    def get_no_name(language: str) -> str:
        """Get 'no name' placeholder."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_NO_NAME.get(lang, _FORMATTER_NO_NAME["en"])

    @staticmethod
    def get_no_title(language: str) -> str:
        """Get 'no title' placeholder."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_NO_TITLE.get(lang, _FORMATTER_NO_TITLE["en"])

    @staticmethod
    def get_no_subject(language: str) -> str:
        """Get 'no subject' placeholder."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_NO_SUBJECT.get(lang, _FORMATTER_NO_SUBJECT["en"])

    @staticmethod
    def get_date_not_specified(language: str) -> str:
        """Get 'date not specified' message."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_DATE_NOT_SPECIFIED.get(lang, _FORMATTER_DATE_NOT_SPECIFIED["en"])

    @staticmethod
    def get_time_not_specified(language: str) -> str:
        """Get 'time not specified' message."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_TIME_NOT_SPECIFIED.get(lang, _FORMATTER_TIME_NOT_SPECIFIED["en"])

    @staticmethod
    def get_yesterday(language: str) -> str:
        """Get 'yesterday' word."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_YESTERDAY.get(lang, _FORMATTER_YESTERDAY["en"])

    @staticmethod
    def get_today(language: str) -> str:
        """Get 'today' word."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_TODAY.get(lang, _FORMATTER_TODAY["en"])

    @staticmethod
    def get_tomorrow(language: str) -> str:
        """Get 'tomorrow' word."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_TOMORROW.get(lang, _FORMATTER_TOMORROW["en"])

    @staticmethod
    def get_unread(language: str) -> str:
        """Get 'unread' word."""
        lang = V3Messages._normalize_language(language)
        return _FORMATTER_UNREAD.get(lang, _FORMATTER_UNREAD["en"])

    # =========================================================================
    # DISPLAY COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_shared(language: str) -> str:
        """Get 'shared' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SHARED.get(lang, _DISPLAY_SHARED["en"])

    @staticmethod
    def get_modified(language: str) -> str:
        """Get 'modified' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_MODIFIED.get(lang, _DISPLAY_MODIFIED["en"])

    @staticmethod
    def get_created(language: str) -> str:
        """Get 'created' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CREATED.get(lang, _DISPLAY_CREATED["en"])

    @staticmethod
    def get_completed(language: str) -> str:
        """Get 'completed' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_COMPLETED.get(lang, _DISPLAY_COMPLETED["en"])

    @staticmethod
    def get_feels_like(language: str) -> str:
        """Get 'feels like' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FEELS_LIKE.get(lang, _DISPLAY_FEELS_LIKE["en"])

    @staticmethod
    def get_humidity(language: str) -> str:
        """Get 'humidity' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_HUMIDITY.get(lang, _DISPLAY_HUMIDITY["en"])

    @staticmethod
    def get_temp_range(language: str) -> str:
        """Get 'low / high' temperature range label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_TEMP_RANGE.get(lang, _DISPLAY_TEMP_RANGE["en"])

    @staticmethod
    def get_wind(language: str) -> str:
        """Get 'wind' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_WIND.get(lang, _DISPLAY_WIND["en"])

    @staticmethod
    def get_forecast(language: str) -> str:
        """Get 'forecast' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FORECAST.get(lang, _DISPLAY_FORECAST["en"])

    @staticmethod
    def get_hourly(language: str) -> str:
        """Get 'hourly' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_HOURLY.get(lang, _DISPLAY_HOURLY["en"])

    @staticmethod
    def get_forecast_beyond_limit(language: str, max_days: int, offset: int) -> str:
        """Get forecast beyond limit error message."""
        lang = V3Messages._normalize_language(language)
        template = _WEATHER_FORECAST_BEYOND_LIMIT.get(lang, _WEATHER_FORECAST_BEYOND_LIMIT["en"])
        return template.format(max_days=max_days, offset=offset)

    @staticmethod
    def get_uv_index(language: str) -> str:
        """Get 'UV Index' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_UV_INDEX.get(lang, _DISPLAY_UV_INDEX["en"])

    @staticmethod
    def get_pressure(language: str) -> str:
        """Get 'Pressure' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_PRESSURE.get(lang, _DISPLAY_PRESSURE["en"])

    @staticmethod
    def get_visibility(language: str) -> str:
        """Get 'Visibility' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_VISIBILITY.get(lang, _DISPLAY_VISIBILITY["en"])

    @staticmethod
    def get_cloud_cover(language: str) -> str:
        """Get 'Cloud cover' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CLOUD_COVER.get(lang, _DISPLAY_CLOUD_COVER["en"])

    @staticmethod
    def get_air_quality(language: str) -> str:
        """Get 'Air Quality' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_AIR_QUALITY.get(lang, _DISPLAY_AIR_QUALITY["en"])

    @staticmethod
    def get_precipitation(language: str) -> str:
        """Get 'Precipitation' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_PRECIPITATION.get(lang, _DISPLAY_PRECIPITATION["en"])

    @staticmethod
    def get_attachments(language: str) -> str:
        """Get 'attachments' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ATTACHMENTS.get(lang, _DISPLAY_ATTACHMENTS["en"])

    @staticmethod
    def get_read_more(language: str, provider: str = "") -> str:
        """Get 'read more on <provider>' label (provider-aware)."""
        lang = V3Messages._normalize_language(language)
        if provider == "microsoft":
            return _DISPLAY_READ_MORE_OUTLOOK.get(lang, _DISPLAY_READ_MORE_OUTLOOK["en"])
        # Default: Gmail (Google or unspecified)
        return _DISPLAY_READ_MORE.get(lang, _DISPLAY_READ_MORE["en"])

    @staticmethod
    def get_reply(language: str) -> str:
        """Get 'reply' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_REPLY.get(lang, _DISPLAY_REPLY["en"])

    @staticmethod
    def get_forward(language: str) -> str:
        """Get 'forward' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FORWARD.get(lang, _DISPLAY_FORWARD["en"])

    @staticmethod
    def get_archive(language: str) -> str:
        """Get 'archive' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ARCHIVE.get(lang, _DISPLAY_ARCHIVE["en"])

    @staticmethod
    def get_see_more(language: str) -> str:
        """Get 'see more' collapsible trigger label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SEE_MORE.get(lang, _DISPLAY_SEE_MORE["en"])

    @staticmethod
    def get_see_attachments(language: str, count: int) -> str:
        """Get 'see N attachment(s)' collapsible trigger label."""
        lang = V3Messages._normalize_language(language)
        if count == 1:
            template = _DISPLAY_SEE_ATTACHMENT.get(lang, _DISPLAY_SEE_ATTACHMENT["en"])
        else:
            template = _DISPLAY_SEE_ATTACHMENTS.get(lang, _DISPLAY_SEE_ATTACHMENTS["en"])
        return template.format(count=count)

    @staticmethod
    def get_shared_with(language: str, count: int) -> str:
        """Get 'shared with N people' label."""
        lang = V3Messages._normalize_language(language)
        if count == 1:
            template = _DISPLAY_SHARED_WITH_N.get(lang, _DISPLAY_SHARED_WITH_N["en"])
        else:
            template = _DISPLAY_SHARED_WITH_N_PLURAL.get(lang, _DISPLAY_SHARED_WITH_N_PLURAL["en"])
        return template.format(count=count)

    @staticmethod
    def get_in_folder(language: str) -> str:
        """Get 'in folder' prefix."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_IN_FOLDER.get(lang, _DISPLAY_IN_FOLDER["en"])

    @staticmethod
    def get_subtask_of(language: str) -> str:
        """Get 'subtask of' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SUBTASK_OF.get(lang, _DISPLAY_SUBTASK_OF["en"])

    @staticmethod
    def get_links(language: str) -> str:
        """Get 'links' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_LINKS.get(lang, _DISPLAY_LINKS["en"])

    @staticmethod
    def get_link(language: str) -> str:
        """Get 'link' singular label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_LINK.get(lang, _DISPLAY_LINK["en"])

    @staticmethod
    def get_subtasks(language: str) -> str:
        """Get 'subtasks' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SUBTASKS.get(lang, _DISPLAY_SUBTASKS["en"])

    @staticmethod
    def get_list(language: str) -> str:
        """Get 'list' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_LIST.get(lang, _DISPLAY_LIST["en"])

    @staticmethod
    def get_priority(language: str, level: str) -> str:
        """Get priority level label (high, medium, low)."""
        lang = V3Messages._normalize_language(language)
        level_lower = level.lower()
        if level_lower == "high":
            return _DISPLAY_PRIORITY_HIGH.get(lang, _DISPLAY_PRIORITY_HIGH["en"])
        elif level_lower == "medium":
            return _DISPLAY_PRIORITY_MEDIUM.get(lang, _DISPLAY_PRIORITY_MEDIUM["en"])
        elif level_lower == "low":
            return _DISPLAY_PRIORITY_LOW.get(lang, _DISPLAY_PRIORITY_LOW["en"])
        return level

    @staticmethod
    def get_favorite(language: str) -> str:
        """Get 'favorite' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FAVORITE.get(lang, _DISPLAY_FAVORITE["en"])

    @staticmethod
    def get_read_full_article(language: str) -> str:
        """Get 'read full article' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_READ_FULL_ARTICLE.get(lang, _DISPLAY_READ_FULL_ARTICLE["en"])

    @staticmethod
    def get_read_more_on_wikipedia(language: str) -> str:
        """Get 'read more on Wikipedia' label for truncated articles."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_READ_MORE_ON_WIKIPEDIA.get(lang, _DISPLAY_READ_MORE_ON_WIKIPEDIA["en"])

    # =========================================================================
    # EMAIL COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_new(language: str) -> str:
        """Get 'new' label (for unread emails badge)."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_NEW.get(lang, _DISPLAY_NEW["en"])

    @staticmethod
    def get_important(language: str) -> str:
        """Get 'important' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_IMPORTANT.get(lang, _DISPLAY_IMPORTANT["en"])

    @staticmethod
    def get_from(language: str) -> str:
        """Get 'from' label for email sender."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FROM.get(lang, _DISPLAY_FROM["en"])

    @staticmethod
    def get_to(language: str) -> str:
        """Get 'to' label for email recipients."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_TO.get(lang, _DISPLAY_TO["en"])

    @staticmethod
    def get_cc(language: str) -> str:
        """Get 'cc' label for email copy recipients."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CC.get(lang, _DISPLAY_CC["en"])

    @staticmethod
    def get_email_content(language: str) -> str:
        """Get 'Email content' label for email body section."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_EMAIL_CONTENT.get(lang, _DISPLAY_EMAIL_CONTENT["en"])

    @staticmethod
    def get_attachment(language: str) -> str:
        """Get 'attachment' singular label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ATTACHMENT.get(lang, _DISPLAY_ATTACHMENT["en"])

    @staticmethod
    def get_size_unit(language: str, unit: str) -> str:
        """Get localized size unit (bytes, KB, MB, GB)."""
        lang = V3Messages._normalize_language(language)
        unit_lower = unit.lower()
        if unit_lower in ("b", "bytes", "o"):
            return _DISPLAY_SIZE_BYTES.get(lang, _DISPLAY_SIZE_BYTES["en"])
        elif unit_lower in ("kb", "ko"):
            return _DISPLAY_SIZE_KB.get(lang, _DISPLAY_SIZE_KB["en"])
        elif unit_lower in ("mb", "mo"):
            return _DISPLAY_SIZE_MB.get(lang, _DISPLAY_SIZE_MB["en"])
        elif unit_lower in ("gb", "go"):
            return _DISPLAY_SIZE_GB.get(lang, _DISPLAY_SIZE_GB["en"])
        return unit

    @staticmethod
    def get_file_type(language: str, type_key: str) -> str:
        """Get localized file type label."""
        lang = V3Messages._normalize_language(language)
        type_dict = _DISPLAY_FILE_TYPES.get(type_key.lower(), _DISPLAY_FILE_TYPES["file"])
        return type_dict.get(lang, type_dict.get("en", type_key))

    # =========================================================================
    # CONTACT COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_month_name(language: str, month: int) -> str:
        """Get localized month name (1-12)."""
        lang = V3Messages._normalize_language(language)
        month_dict = _DISPLAY_MONTHS.get(month, {})
        return month_dict.get(lang, month_dict.get("en", str(month)))

    @staticmethod
    def get_years_old(language: str) -> str:
        """Get 'years old' suffix for age."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_YEARS_OLD.get(lang, _DISPLAY_YEARS_OLD["en"])

    @staticmethod
    def get_nicknames(language: str) -> str:
        """Get 'nicknames' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_NICKNAMES.get(lang, _DISPLAY_NICKNAMES["en"])

    @staticmethod
    def get_relations(language: str) -> str:
        """Get 'relations' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_RELATIONS.get(lang, _DISPLAY_RELATIONS["en"])

    @staticmethod
    def get_relation_type(language: str, relation_type: str) -> str:
        """Get translated relation type (spouse, child, parent, etc.)."""
        lang = V3Messages._normalize_language(language)
        type_lower = relation_type.lower() if relation_type else ""
        if type_lower in _RELATION_TYPES:
            return _RELATION_TYPES[type_lower].get(lang, _RELATION_TYPES[type_lower]["en"])
        # Fallback: return original type with capitalization
        return relation_type.capitalize() if relation_type else ""

    @staticmethod
    def get_data_type(language: str, data_type: str) -> str:
        """
        Get translated data type for contact info (home, work, mobile, etc.).

        Used for email types, phone types, address types from Google Contacts API.

        Args:
            language: Language code
            data_type: Data type key (e.g., 'home', 'work', 'mobile')

        Returns:
            Localized data type label
        """
        lang = V3Messages._normalize_language(language)
        type_lower = data_type.lower() if data_type else ""
        if type_lower in _DATA_TYPES:
            return _DATA_TYPES[type_lower].get(lang, _DATA_TYPES[type_lower]["en"])
        # Fallback: return original type with capitalization
        return data_type.capitalize() if data_type else ""

    @staticmethod
    def get_skills(language: str) -> str:
        """Get 'skills' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SKILLS.get(lang, _DISPLAY_SKILLS["en"])

    @staticmethod
    def get_interests(language: str) -> str:
        """Get 'interests' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_INTERESTS.get(lang, _DISPLAY_INTERESTS["en"])

    @staticmethod
    def get_occupation(language: str) -> str:
        """Get 'occupation/profession' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OCCUPATION.get(lang, _DISPLAY_OCCUPATION["en"])

    @staticmethod
    def get_events(language: str) -> str:
        """Get 'events' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_EVENTS.get(lang, _DISPLAY_EVENTS["en"])

    @staticmethod
    def get_locations(language: str) -> str:
        """Get 'locations' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_LOCATIONS.get(lang, _DISPLAY_LOCATIONS["en"])

    @staticmethod
    def get_calendar(language: str) -> str:
        """Get 'calendar' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CALENDAR.get(lang, _DISPLAY_CALENDAR["en"])

    # =========================================================================
    # EVENT COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_tentative(language: str) -> str:
        """Get 'tentative' status label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_TENTATIVE.get(lang, _DISPLAY_TENTATIVE["en"])

    @staticmethod
    def get_cancelled(language: str) -> str:
        """Get 'cancelled' status label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CANCELLED.get(lang, _DISPLAY_CANCELLED["en"])

    @staticmethod
    def get_all_day(language: str, long_form: bool = False) -> str:
        """Get 'all day' label."""
        lang = V3Messages._normalize_language(language)
        if long_form:
            return _DISPLAY_ALL_DAY_LONG.get(lang, _DISPLAY_ALL_DAY_LONG["en"])
        return _DISPLAY_ALL_DAY.get(lang, _DISPLAY_ALL_DAY["en"])

    @staticmethod
    def get_participant(language: str, count: int = 1) -> str:
        """Get 'participant(s)' label."""
        lang = V3Messages._normalize_language(language)
        if count == 1:
            return _DISPLAY_PARTICIPANT.get(lang, _DISPLAY_PARTICIPANT["en"])
        return _DISPLAY_PARTICIPANTS.get(lang, _DISPLAY_PARTICIPANTS["en"])

    @staticmethod
    def get_participants(language: str) -> str:
        """Get 'Participants' label (capitalized)."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_PARTICIPANTS.get(lang, _DISPLAY_PARTICIPANTS["en"])

    @staticmethod
    def get_organized_by(language: str) -> str:
        """Get 'organized by' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ORGANIZED_BY.get(lang, _DISPLAY_ORGANIZED_BY["en"])

    @staticmethod
    def get_join_meet(language: str) -> str:
        """Get 'Join Google Meet' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_JOIN_MEET.get(lang, _DISPLAY_JOIN_MEET["en"])

    @staticmethod
    def get_recurring_event(language: str) -> str:
        """Get 'recurring event' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_RECURRING_EVENT.get(lang, _DISPLAY_RECURRING_EVENT["en"])

    @staticmethod
    def get_default_reminder(language: str) -> str:
        """Get 'default reminder' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DEFAULT_REMINDER.get(lang, _DISPLAY_DEFAULT_REMINDER["en"])

    @staticmethod
    def get_reminders(language: str) -> str:
        """Get 'reminders' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_REMINDERS.get(lang, _DISPLAY_REMINDERS["en"])

    @staticmethod
    def get_reminder_time(language: str, minutes: int) -> str:
        """Get formatted reminder time string."""
        lang = V3Messages._normalize_language(language)

        if minutes == 0:
            return _DISPLAY_AT_EVENT_TIME.get(lang, _DISPLAY_AT_EVENT_TIME["en"])
        elif minutes < 60:
            template = _DISPLAY_MINUTES_BEFORE.get(lang, _DISPLAY_MINUTES_BEFORE["en"])
            return template.format(count=minutes)
        elif minutes == 60:
            return _DISPLAY_HOUR_BEFORE.get(lang, _DISPLAY_HOUR_BEFORE["en"])
        elif minutes < 1440:  # Less than a day
            hours = minutes // 60
            template = _DISPLAY_HOURS_BEFORE.get(lang, _DISPLAY_HOURS_BEFORE["en"])
            return template.format(count=hours)
        elif minutes == 1440:
            return _DISPLAY_DAY_BEFORE.get(lang, _DISPLAY_DAY_BEFORE["en"])
        elif minutes < 10080:  # Less than a week
            days = minutes // 1440
            template = _DISPLAY_DAYS_BEFORE.get(lang, _DISPLAY_DAYS_BEFORE["en"])
            return template.format(count=days)
        elif minutes == 10080:
            return _DISPLAY_WEEK_BEFORE.get(lang, _DISPLAY_WEEK_BEFORE["en"])
        else:
            weeks = minutes // 10080
            template = _DISPLAY_WEEKS_BEFORE.get(lang, _DISPLAY_WEEKS_BEFORE["en"])
            return template.format(count=weeks)

    # =========================================================================
    # PLACE COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_open(language: str) -> str:
        """Get 'open' status label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OPEN.get(lang, _DISPLAY_OPEN["en"])

    @staticmethod
    def get_closed(language: str) -> str:
        """Get 'closed' status label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CLOSED.get(lang, _DISPLAY_CLOSED["en"])

    @staticmethod
    def get_open_now(language: str) -> str:
        """Get 'open now' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OPEN_NOW.get(lang, _DISPLAY_OPEN_NOW["en"])

    @staticmethod
    def get_opens_at(language: str) -> str:
        """Get 'opens at' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OPENS_AT.get(lang, _DISPLAY_OPENS_AT["en"])

    @staticmethod
    def get_reviews(language: str) -> str:
        """Get 'reviews' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_REVIEWS.get(lang, _DISPLAY_REVIEWS["en"])

    @staticmethod
    def get_free(language: str) -> str:
        """Get 'free' price label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_FREE.get(lang, _DISPLAY_FREE["en"])

    @staticmethod
    def get_website(language: str) -> str:
        """Get 'website' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_WEBSITE.get(lang, _DISPLAY_WEBSITE["en"])

    @staticmethod
    def get_directions(language: str) -> str:
        """Get 'directions' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DIRECTIONS.get(lang, _DISPLAY_DIRECTIONS["en"])

    @staticmethod
    def get_services_amenities(language: str) -> str:
        """Get 'services & amenities' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SERVICES_AMENITIES.get(lang, _DISPLAY_SERVICES_AMENITIES["en"])

    @staticmethod
    def get_description(language: str) -> str:
        """Get 'description' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DESCRIPTION.get(lang, _DISPLAY_DESCRIPTION["en"])

    @staticmethod
    def get_opening_hours(language: str) -> str:
        """Get 'opening hours' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OPENING_HOURS.get(lang, _DISPLAY_OPENING_HOURS["en"])

    @staticmethod
    def get_place_type(language: str, type_key: str) -> str:
        """Get localized place type label with emoji."""
        lang = V3Messages._normalize_language(language)
        type_dict = _DISPLAY_PLACE_TYPES.get(type_key.lower(), {})
        return type_dict.get(lang, type_dict.get("en", ""))

    @staticmethod
    def get_place_feature(language: str, feature_key: str) -> str:
        """Get localized place feature label with emoji."""
        lang = V3Messages._normalize_language(language)
        feature_dict = _DISPLAY_PLACE_FEATURES.get(feature_key.lower(), {})
        return feature_dict.get(lang, feature_dict.get("en", ""))

    @staticmethod
    def get_accessibility(language: str, key: str) -> str:
        """Get localized accessibility label."""
        lang = V3Messages._normalize_language(language)
        acc_dict = _DISPLAY_ACCESSIBILITY.get(key, {})
        return acc_dict.get(lang, acc_dict.get("en", ""))

    @staticmethod
    def get_payment(language: str, key: str) -> str:
        """Get localized payment option label."""
        lang = V3Messages._normalize_language(language)
        pay_dict = _DISPLAY_PAYMENT.get(key, {})
        return pay_dict.get(lang, pay_dict.get("en", ""))

    @staticmethod
    def get_accessibility_title(language: str) -> str:
        """Get 'Accessibility' section title."""
        lang = V3Messages._normalize_language(language)
        titles = {
            "fr": "Accessibilité",
            "en": "Accessibility",
            "de": "Barrierefreiheit",
            "es": "Accesibilidad",
            "it": "Accessibilità",
            "zh-CN": "无障碍设施",
        }
        return titles.get(lang, titles["en"])

    @staticmethod
    def get_payment_title(language: str) -> str:
        """Get 'Payment options' section title."""
        lang = V3Messages._normalize_language(language)
        titles = {
            "fr": "Paiements",
            "en": "Payment",
            "de": "Zahlungsmethoden",
            "es": "Pagos",
            "it": "Pagamenti",
            "zh-CN": "支付方式",
        }
        return titles.get(lang, titles["en"])

    # =========================================================================
    # SEARCH RESULT COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_sources(language: str) -> str:
        """Get 'sources' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SOURCES.get(lang, _DISPLAY_SOURCES["en"])

    @staticmethod
    def get_related_questions(language: str) -> str:
        """Get 'related questions' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_RELATED_QUESTIONS.get(lang, _DISPLAY_RELATED_QUESTIONS["en"])

    @staticmethod
    def get_search(language: str) -> str:
        """Get 'search' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SEARCH.get(lang, _DISPLAY_SEARCH["en"])

    @staticmethod
    def get_internet(language: str) -> str:
        """Get 'internet' label for web search badge."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_INTERNET.get(lang, _DISPLAY_INTERNET["en"])

    @staticmethod
    def get_ai_synthesis(language: str) -> str:
        """Get 'AI synthesis' label for web search."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_AI_SYNTHESIS.get(lang, _DISPLAY_AI_SYNTHESIS["en"])

    @staticmethod
    def get_web_results(language: str) -> str:
        """Get 'web results' label for web search."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_WEB_RESULTS.get(lang, _DISPLAY_WEB_RESULTS["en"])

    @staticmethod
    def get(key: str, language: str, default: str = "") -> str:
        """Generic get method for any label by key name."""
        # Map key names to corresponding methods
        method_map = {
            "ai_synthesis": V3Messages.get_ai_synthesis,
            "web_results": V3Messages.get_web_results,
            "sources": V3Messages.get_sources,
            "related_questions": V3Messages.get_related_questions,
            "internet": V3Messages.get_internet,
            "search": V3Messages.get_search,
        }
        if key in method_map:
            return method_map[key](language)
        return default

    @staticmethod
    def get_edit(language: str) -> str:
        """Get 'edit' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_EDIT.get(lang, _DISPLAY_EDIT["en"])

    @staticmethod
    def get_delete(language: str) -> str:
        """Get 'delete' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DELETE.get(lang, _DISPLAY_DELETE["en"])

    @staticmethod
    def get_call(language: str) -> str:
        """Get 'call' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_CALL.get(lang, _DISPLAY_CALL["en"])

    @staticmethod
    def get_email_action(language: str) -> str:
        """Get 'send email' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_EMAIL.get(lang, _DISPLAY_EMAIL["en"])

    @staticmethod
    def get_view_details(language: str) -> str:
        """Get 'view details' action label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_VIEW_DETAILS.get(lang, _DISPLAY_VIEW_DETAILS["en"])

    # =========================================================================
    # ROUTE COMPONENT STRINGS
    # =========================================================================

    @staticmethod
    def get_travel_mode(language: str, mode: str) -> str:
        """Get localized travel mode label."""
        lang = V3Messages._normalize_language(language)
        mode_dict = _ROUTE_TRAVEL_MODES.get(mode.upper(), _ROUTE_TRAVEL_MODES.get("DRIVE", {}))
        return mode_dict.get(lang, mode_dict.get("en", mode))

    @staticmethod
    def get_traffic_condition(language: str, condition: str) -> str:
        """Get localized traffic condition label."""
        lang = V3Messages._normalize_language(language)
        cond_dict = _ROUTE_TRAFFIC_CONDITIONS.get(condition.upper(), {})
        return cond_dict.get(lang, cond_dict.get("en", condition))

    @staticmethod
    def get_route_avoidance(language: str, avoidance: str) -> str:
        """Get localized route avoidance label."""
        lang = V3Messages._normalize_language(language)
        avoid_dict = _ROUTE_AVOIDANCES.get(avoidance.lower(), {})
        return avoid_dict.get(lang, avoid_dict.get("en", avoidance))

    @staticmethod
    def get_distance_label(language: str) -> str:
        """Get 'distance' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DISTANCE.get(lang, _DISPLAY_DISTANCE["en"])

    @staticmethod
    def get_duration_label(language: str) -> str:
        """Get 'duration' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DURATION.get(lang, _DISPLAY_DURATION["en"])

    @staticmethod
    def get_traffic_label(language: str) -> str:
        """Get 'traffic' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_TRAFFIC.get(lang, _DISPLAY_TRAFFIC["en"])

    @staticmethod
    def get_with_traffic(language: str) -> str:
        """Get 'with traffic' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_WITH_TRAFFIC.get(lang, _DISPLAY_WITH_TRAFFIC["en"])

    @staticmethod
    def get_toll_label(language: str) -> str:
        """Get 'tolls' label for route cost."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_TOLL_LABEL.get(lang, _DISPLAY_TOLL_LABEL["en"])

    @staticmethod
    def get_arrival_time(language: str) -> str:
        """Get 'arrival' label for ETA."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ARRIVAL_TIME.get(lang, _DISPLAY_ARRIVAL_TIME["en"])

    @staticmethod
    def get_suggested_departure(language: str) -> str:
        """Get 'suggested departure' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_SUGGESTED_DEPARTURE.get(lang, _DISPLAY_SUGGESTED_DEPARTURE["en"])

    @staticmethod
    def get_to_arrive_by(language: str, time: str, departure: str) -> str:
        """Get formatted 'to arrive by X, leave at Y' message."""
        lang = V3Messages._normalize_language(language)
        template = _DISPLAY_TO_ARRIVE_BY.get(lang, _DISPLAY_TO_ARRIVE_BY["en"])
        return template.format(time=time, departure=departure)

    @staticmethod
    def get_open_in_maps(language: str) -> str:
        """Get 'open in maps' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_OPEN_IN_MAPS.get(lang, _DISPLAY_OPEN_IN_MAPS["en"])

    @staticmethod
    def get_route_label(language: str) -> str:
        """Get 'route' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ROUTE.get(lang, _DISPLAY_ROUTE["en"])

    @staticmethod
    def get_route_steps(language: str) -> str:
        """Get 'steps' label for route."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ROUTE_STEPS.get(lang, _DISPLAY_ROUTE_STEPS["en"])

    @staticmethod
    def get_via(language: str) -> str:
        """Get 'via' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_VIA.get(lang, _DISPLAY_VIA["en"])

    @staticmethod
    def get_origin(language: str) -> str:
        """Get 'origin/from' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_ORIGIN.get(lang, _DISPLAY_ORIGIN["en"])

    @staticmethod
    def get_destination_label(language: str) -> str:
        """Get 'destination/to' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_DESTINATION.get(lang, _DISPLAY_DESTINATION["en"])

    @staticmethod
    def get_my_location(language: str) -> str:
        """Get 'my location' / 'current location' label."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_MY_LOCATION.get(lang, _DISPLAY_MY_LOCATION["en"])

    @staticmethod
    def get_more_steps(language: str, count: int) -> str:
        """Get '+N more steps...' label for truncated step list."""
        lang = V3Messages._normalize_language(language)
        template = _DISPLAY_MORE_STEPS.get(lang, _DISPLAY_MORE_STEPS["en"])
        return template.format(count=count)

    @staticmethod
    def get_transit_stops(language: str, count: int) -> str:
        """Get 'N stops' / 'N arrêts' label for transit steps."""
        lang = V3Messages._normalize_language(language)
        if count == 1:
            return _DISPLAY_TRANSIT_STOP_SINGLE.get(lang, _DISPLAY_TRANSIT_STOP_SINGLE["en"])
        template = _DISPLAY_TRANSIT_STOPS.get(lang, _DISPLAY_TRANSIT_STOPS["en"])
        return template.format(count=count)

    # =========================================================================
    # DOMAIN SECTION LABELS (multi-domain display)
    # =========================================================================

    @staticmethod
    def get_domain_section_label(domain: str, language: str) -> str:
        """
        Get translated section label for a domain.

        Used by html_renderer for multi-domain display section titles.

        Args:
            domain: Domain key (e.g., "contacts", "events", "routes")
            language: Language code (e.g., "fr", "en")

        Returns:
            Translated section title (e.g., "Contacts", "Événements", "Itinéraire")
        """
        lang = V3Messages._normalize_language(language)
        domain_labels = _DOMAIN_SECTION_LABELS.get(domain, {})
        return domain_labels.get(lang, domain_labels.get("en", domain.capitalize()))

    # =========================================================================
    # MCP APPS (interactive widget placeholders)
    # =========================================================================

    @staticmethod
    def get_mcp_app_loading(language: str) -> str:
        """Get MCP Apps loading placeholder text."""
        lang = V3Messages._normalize_language(language)
        return _DISPLAY_MCP_APP_LOADING.get(lang, _DISPLAY_MCP_APP_LOADING["en"])
