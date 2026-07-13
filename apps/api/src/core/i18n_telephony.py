"""Central i18n for the telephony feature (agentic outbound calls).

Consolidates the strings that were interim-inlined across the telephony modules
during à-blanc development (``agent_prompt.py`` disclosure, ``availability.py``
free/busy phrases, ``agents/tools/telephony_tools.py`` caller-facing phrases,
``return_synthesis.py`` delivery strings). All 6 supported languages, keyed by
ISO code (``zh`` for ``zh-CN``); the app language is normalized on lookup.

Data module (like ``core/i18n_*``): no domain imports, exempt from the size
ratchet. The domain modules import the accessors below.
"""

from __future__ import annotations

_DEFAULT = "en"


def _iso(language: str | None) -> str:
    """Normalize an app language code to the ISO key used by the tables below."""
    if not language:
        return _DEFAULT
    return language.split("-")[0].lower()


# ============================================================================
# Agent disclosure — the first message the LIA agent speaks on the call.
# Contains {{user_name}} / {{objective}} ElevenLabs dynamic-variable markers.
# ============================================================================

DISCLOSURE_FIRST_MESSAGE: dict[str, str] = {
    "fr": "Bonjour, je suis l'assistant vocal de {{user_name}}. Il m'a demandé de vous appeler au sujet de : {{objective}}.",
    "en": "Hello, I'm {{user_name}}'s voice assistant. They asked me to call you about: {{objective}}.",
    "de": "Guten Tag, ich bin der Sprachassistent von {{user_name}} und rufe Sie an wegen: {{objective}}.",
    "es": "Hola, soy el asistente de voz de {{user_name}}. Me pidió que le llamara sobre: {{objective}}.",
    "it": "Salve, sono l'assistente vocale di {{user_name}}. Mi ha chiesto di chiamarla riguardo a: {{objective}}.",
    "zh": "您好，我是{{user_name}}的语音助手，受托就以下事项致电您：{{objective}}。",
}


def get_disclosure_first_message(language: str | None) -> str:
    """First-message disclosure for the agent, in the user's language."""
    return DISCLOSURE_FIRST_MESSAGE.get(_iso(language), DISCLOSURE_FIRST_MESSAGE[_DEFAULT])


# ============================================================================
# Availability pre-fetch — structural phrases around the busy time ranges.
# ============================================================================

AVAILABILITY_PHRASES: dict[str, dict[str, str]] = {
    "fr": {
        "header": "Créneaux occupés sur la période :",
        "all_free": "Aucun créneau occupé sur la période — entièrement disponible.",
        "unavailable": "Disponibilités indisponibles (aucun agenda connecté).",
    },
    "en": {
        "header": "Busy periods in the window:",
        "all_free": "No busy periods in the window — fully available.",
        "unavailable": "Availability unavailable (no calendar connected).",
    },
    "de": {
        "header": "Belegte Zeiten im Zeitraum:",
        "all_free": "Keine belegten Zeiten im Zeitraum — vollständig verfügbar.",
        "unavailable": "Verfügbarkeit nicht abrufbar (kein Kalender verbunden).",
    },
    "es": {
        "header": "Franjas ocupadas en el periodo:",
        "all_free": "Sin franjas ocupadas en el periodo — totalmente disponible.",
        "unavailable": "Disponibilidad no disponible (sin calendario conectado).",
    },
    "it": {
        "header": "Fasce occupate nel periodo:",
        "all_free": "Nessuna fascia occupata nel periodo — completamente disponibile.",
        "unavailable": "Disponibilità non disponibile (nessun calendario connesso).",
    },
    "zh": {
        "header": "该时间段内的占用时段：",
        "all_free": "该时间段内无占用 — 完全有空。",
        "unavailable": "无法获取空闲信息（未连接日历）。",
    },
}


def get_availability_phrases(language: str | None) -> dict[str, str]:
    """Availability structural phrases (header / all_free / unavailable)."""
    return AVAILABILITY_PHRASES.get(_iso(language), AVAILABILITY_PHRASES[_DEFAULT])


# ============================================================================
# place_phone_call tool — caller-facing failure / clarification phrases.
# ============================================================================

TOOL_PHRASES: dict[str, dict[str, str]] = {
    "fr": {
        "already_active": (
            "Un appel est déjà en cours. Je n'en lance pas un second — "
            "réessaie une fois qu'il sera terminé."
        ),
        "call_failed": "Je n'ai pas pu passer l'appel pour le moment. Réessaie dans un instant.",
        "not_configured": (
            "La téléphonie n'est pas activée. Active le connecteur ElevenLabs dans "
            "Préférences → Mes connecteurs pour que je puisse passer des appels."
        ),
        "not_found": "Je n'ai trouvé aucun contact nommé « {name} ».",
        "no_phone": "J'ai trouvé « {name} » mais aucun numéro de téléphone n'est enregistré.",
        "ambiguous": (
            "Plusieurs contacts correspondent à « {name} » : {candidates}. "
            "Précise lequel (ou donne-moi directement le numéro)."
        ),
    },
    "en": {
        "already_active": (
            "A call is already in progress. I won't start a second one — "
            "try again once it's finished."
        ),
        "call_failed": "I couldn't place the call right now. Please try again in a moment.",
        "not_configured": (
            "Telephony is not enabled. Activate the ElevenLabs connector in "
            "Preferences → My connectors so I can place calls."
        ),
        "not_found": "I couldn't find a contact named “{name}”.",
        "no_phone": "I found “{name}” but no phone number is on file.",
        "ambiguous": (
            "Several contacts match “{name}”: {candidates}. "
            "Tell me which one (or give me the number directly)."
        ),
    },
    "de": {
        "already_active": (
            "Ein Anruf läuft bereits. Ich starte keinen zweiten — "
            "versuche es erneut, sobald er beendet ist."
        ),
        "call_failed": (
            "Ich konnte den Anruf gerade nicht tätigen. Bitte versuche es gleich noch einmal."
        ),
        "not_configured": (
            "Telefonie ist nicht aktiviert. Aktiviere den ElevenLabs-Connector unter "
            "Einstellungen → Meine Connectoren, damit ich anrufen kann."
        ),
        "not_found": "Ich habe keinen Kontakt namens „{name}“ gefunden.",
        "no_phone": "Ich habe „{name}“ gefunden, aber keine Telefonnummer hinterlegt.",
        "ambiguous": (
            "Mehrere Kontakte passen zu „{name}“: {candidates}. "
            "Sag mir, welcher (oder gib mir direkt die Nummer)."
        ),
    },
    "es": {
        "already_active": (
            "Ya hay una llamada en curso. No inicio una segunda; inténtalo cuando termine."
        ),
        "call_failed": "No pude realizar la llamada ahora mismo. Inténtalo de nuevo en un momento.",
        "not_configured": (
            "La telefonía no está activada. Activa el conector de ElevenLabs en "
            "Preferencias → Mis conectores para que pueda llamar."
        ),
        "not_found": "No encontré ningún contacto llamado «{name}».",
        "no_phone": "Encontré «{name}» pero no hay ningún número de teléfono registrado.",
        "ambiguous": (
            "Varios contactos coinciden con «{name}»: {candidates}. "
            "Dime cuál (o dame directamente el número)."
        ),
    },
    "it": {
        "already_active": (
            "C'è già una chiamata in corso. Non ne avvio una seconda; riprova quando è finita."
        ),
        "call_failed": "Non sono riuscito a effettuare la chiamata al momento. Riprova tra poco.",
        "not_configured": (
            "La telefonia non è attivata. Attiva il connettore ElevenLabs in "
            "Preferenze → I miei connettori così posso effettuare chiamate."
        ),
        "not_found": "Non ho trovato nessun contatto di nome «{name}».",
        "no_phone": "Ho trovato «{name}» ma non è registrato alcun numero di telefono.",
        "ambiguous": (
            "Più contatti corrispondono a «{name}»: {candidates}. "
            "Dimmi quale (o dammi direttamente il numero)."
        ),
    },
    "zh": {
        "already_active": "已有一通电话正在进行中。我不会再拨打第二通，请等它结束后再试。",
        "call_failed": "我暂时无法拨打这通电话，请稍后再试。",
        "not_configured": "电话功能未启用。请在“偏好设置 → 我的连接器”中激活 ElevenLabs 连接器，我才能拨打电话。",
        "not_found": "我没有找到名为“{name}”的联系人。",
        "no_phone": "我找到了“{name}”，但没有登记电话号码。",
        "ambiguous": "有多个联系人与“{name}”匹配：{candidates}。请告诉我是哪一个（或直接给我号码）。",
    },
}


def get_tool_phrases(language: str | None) -> dict[str, str]:
    """place_phone_call caller-facing phrases (guard / resolution failures)."""
    return TOOL_PHRASES.get(_iso(language), TOOL_PHRASES[_DEFAULT])


# ============================================================================
# Post-call return delivery — notification title + LLM-failure fallback.
# ============================================================================

RETURN_PHRASES: dict[str, dict[str, str]] = {
    "fr": {
        "title": "Retour d'appel",
        "fallback": (
            "J'ai passé ton appel mais je n'ai pas pu en tirer un résumé détaillé. "
            "Dis-moi si tu veux que je réessaie."
        ),
    },
    "en": {
        "title": "Call summary",
        "fallback": (
            "I placed your call but couldn't produce a detailed summary. "
            "Let me know if you'd like me to try again."
        ),
    },
    "de": {
        "title": "Anruf-Zusammenfassung",
        "fallback": (
            "Ich habe deinen Anruf getätigt, konnte aber keine ausführliche "
            "Zusammenfassung erstellen. Sag Bescheid, wenn ich es erneut versuchen soll."
        ),
    },
    "es": {
        "title": "Resumen de la llamada",
        "fallback": (
            "Hice tu llamada pero no pude generar un resumen detallado. "
            "Dime si quieres que lo intente de nuevo."
        ),
    },
    "it": {
        "title": "Riepilogo della chiamata",
        "fallback": (
            "Ho effettuato la tua chiamata ma non sono riuscito a produrre un "
            "riepilogo dettagliato. Dimmi se vuoi che riprovi."
        ),
    },
    "zh": {
        "title": "通话小结",
        "fallback": "我已为你拨打了电话，但无法生成详细小结。需要我再试一次的话告诉我。",
    },
}


def get_return_phrases(language: str | None) -> dict[str, str]:
    """Post-call delivery strings (title / synthesis-failure fallback)."""
    return RETURN_PHRASES.get(_iso(language), RETURN_PHRASES[_DEFAULT])
