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
# Agent greeting — the first message spoken the instant the call connects.
# ============================================================================
# DELIBERATELY SHORT (identity only, no objective): it plays instantly at
# pickup, so the line is never silent while the agent LLM composes its first
# real turn (an EMPTY first_message caused a multi-second standoff at call
# start — the agent waited for speech, the callee waited for the caller). The
# old long disclosure (identity + objective) caused the opposite bug: the
# agent considered its opening done and stalled. Why + first question come
# from the LLM at the person's first response (prompt's Opening mandate).
# Contains the {{user_name}} ElevenLabs dynamic-variable marker.

GREETING_FIRST_MESSAGE: dict[str, str] = {
    "fr": "Bonjour, je suis l'assistant vocal de {{user_name}}.",
    "en": "Hello, this is {{user_name}}'s voice assistant speaking.",
    "de": "Guten Tag, hier spricht der Sprachassistent von {{user_name}}.",
    "es": "Hola, soy el asistente de voz de {{user_name}}.",
    "it": "Salve, sono l'assistente vocale di {{user_name}}.",
    "zh": "您好，我是{{user_name}}的语音助手。",
}


def get_greeting_first_message(language: str | None) -> str:
    """Instant-pickup greeting for the agent, in the user's language."""
    return GREETING_FIRST_MESSAGE.get(_iso(language), GREETING_FIRST_MESSAGE[_DEFAULT])


# ============================================================================
# Owner and verification mandates (phone-as-a-channel, lot 2) — greetings.
# ============================================================================
# Rendered SERVER-SIDE with ``str.format`` (``{name}``, the i18n convention),
# never left to the vendor's ``{{...}}`` substitution: they travel in a per-call
# override, and what leaves LIA is the exact sentence the person hears.

SELF_GREETING_FIRST_MESSAGE: dict[str, str] = {
    "fr": "Bonjour, c'est ton assistant LIA. Je suis bien avec {name} ?",
    "en": "Hello, this is your assistant LIA. Am I speaking with {name}?",
    "de": "Hallo, hier ist dein Assistent LIA. Spreche ich mit {name}?",
    "es": "Hola, soy tu asistente LIA. ¿Hablo con {name}?",
    "it": "Ciao, sono il tuo assistente LIA. Parlo con {name}?",
    "zh": "你好，我是你的助手 LIA。请问是{name}吗？",
}

VERIFICATION_GREETING_FIRST_MESSAGE: dict[str, str] = {
    "fr": "Bonjour, c'est l'assistant LIA de {name}. Je vous appelle pour vérifier ce numéro.",
    "en": "Hello, this is {name}'s assistant LIA. I am calling to verify this number.",
    "de": "Hallo, hier ist der Assistent LIA von {name}. Ich rufe an, um diese Nummer zu bestätigen.",
    "es": "Hola, soy el asistente LIA de {name}. Llamo para verificar este número.",
    "it": "Salve, sono l'assistente LIA di {name}. La chiamo per verificare questo numero.",
    "zh": "您好，我是{name}的助手 LIA。我来电是为了验证这个号码。",
}


def get_self_greeting(language: str | None, *, name: str) -> str:
    """Greeting of an owner call, rendered with the person's name."""
    template = SELF_GREETING_FIRST_MESSAGE.get(
        _iso(language), SELF_GREETING_FIRST_MESSAGE[_DEFAULT]
    )
    return template.format(name=name)


def get_verification_greeting(language: str | None, *, name: str) -> str:
    """Greeting of a number-verification call, rendered with the person's name."""
    table = VERIFICATION_GREETING_FIRST_MESSAGE
    return table.get(_iso(language), table[_DEFAULT]).format(name=name)


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
        "call_rejected": (
            "Le service de téléphonie a refusé l'appel : sa configuration doit être corrigée (numéro émetteur non vérifié, crédit épuisé…). Réessayer n'y changera rien tant que ce n'est pas réglé côté fournisseur."
        ),
        "call_failed": "Je n'ai pas pu passer l'appel pour le moment. Réessaie dans un instant.",
        "auth_failed": (
            "Le service de téléphonie a rejeté la clé API enregistrée : elle n'est plus valide. "
            "Reconnecte ElevenLabs dans Préférences → Mes connecteurs avec une clé API valide "
            "(elle commence par « sk_ ») — réessayer sans cela ne servira à rien."
        ),
        "number_not_verified": (
            "Ton numéro n'est pas encore vérifié. Déclare-le et vérifie-le dans Préférences → Téléphonie → Mon identité, puis redemande-moi de t'appeler."
        ),
        "calling_you": (
            "Je t'appelle maintenant sur ton numéro. Tout ce qu'on se dira arrivera ici dès la fin de l'appel."
        ),
        "agent_sync_failed": (
            "Je n'ai pas pu préparer l'agent vocal pour cet appel (le service de téléphonie n'a pas accepté la mise à jour). Réessaie dans un instant."
        ),
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
        "call_rejected": (
            "The telephony provider declined the call: its configuration needs fixing (source number not verified, credit exhausted…). Retrying will not help until that is sorted out on the provider side."
        ),
        "call_failed": "I couldn't place the call right now. Please try again in a moment.",
        "auth_failed": (
            "The telephony provider rejected the stored API key: it is no longer valid. "
            "Reconnect ElevenLabs in Preferences → My connectors with a valid API key "
            "(it starts with “sk_”) — retrying without that will not help."
        ),
        "number_not_verified": (
            "Your number is not verified yet. Declare and verify it in Preferences → Telephony → My identity, then ask me to call you again."
        ),
        "calling_you": (
            "I'm calling you now on your number. Everything we say will land here as soon as the call ends."
        ),
        "agent_sync_failed": (
            "I could not prepare the voice agent for this call (the telephony service refused the update). Try again in a moment."
        ),
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
        "call_rejected": (
            "Der Telefonie-Dienst hat den Anruf abgelehnt: seine Konfiguration muss korrigiert werden (Absendernummer nicht verifiziert, Guthaben aufgebraucht …). Ein erneuter Versuch hilft erst danach."
        ),
        "call_failed": (
            "Ich konnte den Anruf gerade nicht tätigen. Bitte versuche es gleich noch einmal."
        ),
        "auth_failed": (
            "Der Telefonie-Dienst hat den gespeicherten API-Schlüssel abgelehnt: er ist nicht "
            "mehr gültig. Verbinde ElevenLabs unter Einstellungen → Meine Connectoren neu mit "
            "einem gültigen API-Schlüssel (er beginnt mit „sk_“) — ein erneuter Versuch ohne "
            "das hilft nicht."
        ),
        "number_not_verified": (
            "Deine Nummer ist noch nicht bestätigt. Hinterlege und bestätige sie unter Einstellungen → Telefonie → Meine Identität und bitte mich dann erneut, dich anzurufen."
        ),
        "calling_you": (
            "Ich rufe dich jetzt auf deiner Nummer an. Alles, was wir besprechen, erscheint hier, sobald das Gespräch beendet ist."
        ),
        "agent_sync_failed": (
            "Ich konnte den Sprachagenten für diesen Anruf nicht vorbereiten (der Telefoniedienst hat die Aktualisierung abgelehnt). Versuche es gleich noch einmal."
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
        "call_rejected": (
            "El servicio de telefonía rechazó la llamada: su configuración debe corregirse (número emisor no verificado, crédito agotado…). Reintentar no servirá de nada hasta que se resuelva en el proveedor."
        ),
        "call_failed": "No pude realizar la llamada ahora mismo. Inténtalo de nuevo en un momento.",
        "auth_failed": (
            "El servicio de telefonía rechazó la clave API guardada: ya no es válida. "
            "Vuelve a conectar ElevenLabs en Preferencias → Mis conectores con una clave API "
            "válida (empieza por «sk_»); reintentar sin eso no servirá de nada."
        ),
        "number_not_verified": (
            "Tu número aún no está verificado. Decláralo y verifícalo en Preferencias → Telefonía → Mi identidad, y vuelve a pedirme que te llame."
        ),
        "calling_you": (
            "Te llamo ahora a tu número. Todo lo que hablemos llegará aquí en cuanto termine la llamada."
        ),
        "agent_sync_failed": (
            "No he podido preparar el agente de voz para esta llamada (el servicio de telefonía rechazó la actualización). Inténtalo de nuevo en un momento."
        ),
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
        "call_rejected": (
            "Il servizio di telefonia ha rifiutato la chiamata: la sua configurazione va corretta (numero mittente non verificato, credito esaurito…). Riprovare non servirà finché non è risolto lato fornitore."
        ),
        "call_failed": "Non sono riuscito a effettuare la chiamata al momento. Riprova tra poco.",
        "auth_failed": (
            "Il servizio di telefonia ha rifiutato la chiave API salvata: non è più valida. "
            "Ricollega ElevenLabs in Preferenze → I miei connettori con una chiave API valida "
            "(inizia con «sk_»); riprovare senza questo non servirà a nulla."
        ),
        "number_not_verified": (
            "Il tuo numero non è ancora verificato. Dichiaralo e verificalo in Preferenze → Telefonia → La mia identità, poi chiedimi di nuovo di chiamarti."
        ),
        "calling_you": (
            "Ti chiamo adesso sul tuo numero. Tutto quello che ci diremo arriverà qui appena finita la chiamata."
        ),
        "agent_sync_failed": (
            "Non sono riuscito a preparare l'agente vocale per questa chiamata (il servizio di telefonia ha rifiutato l'aggiornamento). Riprova tra un istante."
        ),
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
        "call_rejected": (
            "电话服务拒绝了这次通话：其配置需要修正（主叫号码未验证、余额不足等）。在服务商侧解决之前，重试不会有帮助。"
        ),
        "call_failed": "我暂时无法拨打这通电话，请稍后再试。",
        "auth_failed": (
            "电话服务拒绝了已保存的 API 密钥：它已失效。请在“偏好设置 → 我的连接器”中"
            "用有效的 API 密钥（以“sk_”开头）重新连接 ElevenLabs——在此之前重试没有用。"
        ),
        "number_not_verified": (
            "你的号码尚未验证。请在“偏好设置 → 电话 → 我的身份”中登记并验证，然后再让我给你打电话。"
        ),
        "calling_you": ("我现在就拨打你的号码。通话结束后，我们聊的内容都会出现在这里。"),
        "agent_sync_failed": ("我无法为本次通话准备语音助手（电话服务拒绝了更新）。请稍后再试。"),
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
        "appointment_suggestion": (
            "📅 Rendez-vous convenu : {datetime_local}{location_part}. "
            "Veux-tu que je l'ajoute à ton agenda ?"
        ),
        "appointment_location_part": " ({location})",
        "self_call_title": ("Notre appel"),
        "relay_drafts_waiting": ("Notre appel a laissé des brouillons à confirmer dans le chat."),
        "relay_answered": (
            "J'ai fait ce que tu m'as demandé au téléphone : ma réponse est dans le chat."
        ),
        "relay_empty": ("Notre appel n'a rien laissé à faire : je n'ai rien relayé dans le chat."),
        "relay_not_owner": (
            "Quelqu'un d'autre a répondu à mon appel ; je n'ai rien partagé et je n'ai rien relayé. Redemande-moi de t'appeler quand tu veux."
        ),
        "relay_unanswered": (
            "Tu n'as pas répondu à mon appel (ou c'est ta messagerie qui a décroché) ; je n'ai rien relayé. Redemande-moi de t'appeler quand tu veux."
        ),
        "relay_call_failed": (
            "Mon appel n'a pas abouti : la ligne a échoué avant que nous parlions. Je n'ai rien relayé ; redemande-moi de t'appeler quand tu veux."
        ),
        "relay_pending_question": (
            "Je n'ai pas relayé notre appel dans le chat : une question y attend encore ta réponse. Réponds-y, puis dis-moi si je dois reprendre ce que tu m'as demandé."
        ),
        "relay_busy": (
            "Je n'ai pas relayé notre appel dans le chat : une autre conversation y était en cours. Dis-moi si je dois reprendre ce que tu m'as demandé."
        ),
        "relay_quota_blocked": (
            "Je n'ai pas pu relayer notre appel dans le chat : le plafond d'utilisation est atteint pour le moment. Redis-le-moi quand il sera levé."
        ),
        "relay_failed": (
            "Je n'ai pas pu relayer notre appel dans le chat. Voici ce que j'en retiens ; redis-moi ce que tu veux que je fasse."
        ),
    },
    "en": {
        "title": "Call summary",
        "fallback": (
            "I placed your call but couldn't produce a detailed summary. "
            "Let me know if you'd like me to try again."
        ),
        "appointment_suggestion": (
            "📅 Appointment agreed: {datetime_local}{location_part}. "
            "Want me to add it to your calendar?"
        ),
        "appointment_location_part": " ({location})",
        "self_call_title": ("Our call"),
        "relay_drafts_waiting": ("Our call left drafts to confirm in the chat."),
        "relay_answered": ("I did what you asked me on the phone: my answer is in the chat."),
        "relay_empty": ("Our call left nothing to do: I relayed nothing into the chat."),
        "relay_not_owner": (
            "Someone else answered my call; I shared nothing and relayed nothing. Ask me to call you again whenever you like."
        ),
        "relay_unanswered": (
            "You did not pick up my call (or I reached your voicemail); I relayed nothing. Ask me to call you again whenever you like."
        ),
        "relay_call_failed": (
            "My call did not go through: the line failed before we spoke. I relayed nothing; ask me to call you again whenever you like."
        ),
        "relay_pending_question": (
            "I did not relay our call into the chat: a question there is still waiting for your answer. Answer it, then tell me whether to pick up what you asked for."
        ),
        "relay_busy": (
            "I did not relay our call into the chat: another conversation was running there. Tell me whether to pick up what you asked for."
        ),
        "relay_quota_blocked": (
            "I could not relay our call into the chat: the usage ceiling is reached for now. Tell me again once it lifts."
        ),
        "relay_failed": (
            "I could not relay our call into the chat. Here is what I keep from it; tell me again what you want done."
        ),
    },
    "de": {
        "title": "Anruf-Zusammenfassung",
        "fallback": (
            "Ich habe deinen Anruf getätigt, konnte aber keine ausführliche "
            "Zusammenfassung erstellen. Sag Bescheid, wenn ich es erneut versuchen soll."
        ),
        "appointment_suggestion": (
            "📅 Termin vereinbart: {datetime_local}{location_part}. "
            "Soll ich ihn in deinen Kalender eintragen?"
        ),
        "appointment_location_part": " ({location})",
        "self_call_title": ("Unser Anruf"),
        "relay_drafts_waiting": (
            "Unser Anruf hat Entwürfe hinterlassen, die im Chat zu bestätigen sind."
        ),
        "relay_answered": (
            "Ich habe erledigt, worum du mich am Telefon gebeten hast: meine Antwort steht im Chat."
        ),
        "relay_empty": (
            "Unser Anruf hat nichts zu tun hinterlassen: ich habe nichts in den Chat übernommen."
        ),
        "relay_not_owner": (
            "Jemand anderes hat meinen Anruf entgegengenommen; ich habe nichts geteilt und nichts übernommen. Bitte mich jederzeit erneut, dich anzurufen."
        ),
        "relay_unanswered": (
            "Du hast meinen Anruf nicht angenommen (oder ich habe deine Mailbox erreicht); ich habe nichts übernommen. Bitte mich jederzeit erneut, dich anzurufen."
        ),
        "relay_call_failed": (
            "Mein Anruf ist nicht zustande gekommen: die Leitung ist ausgefallen, bevor wir gesprochen haben. Ich habe nichts übernommen; bitte mich jederzeit erneut, dich anzurufen."
        ),
        "relay_pending_question": (
            "Ich habe unseren Anruf nicht in den Chat übernommen: dort wartet noch eine Frage auf deine Antwort. Beantworte sie und sag mir dann, ob ich deine Bitten aufgreifen soll."
        ),
        "relay_busy": (
            "Ich habe unseren Anruf nicht in den Chat übernommen: dort lief gerade ein anderes Gespräch. Sag mir, ob ich deine Bitten aufgreifen soll."
        ),
        "relay_quota_blocked": (
            "Ich konnte unseren Anruf nicht in den Chat übernehmen: das Nutzungslimit ist vorerst erreicht. Sag es mir erneut, sobald es aufgehoben ist."
        ),
        "relay_failed": (
            "Ich konnte unseren Anruf nicht in den Chat übernehmen. Das behalte ich davon; sag mir erneut, was ich tun soll."
        ),
    },
    "es": {
        "title": "Resumen de la llamada",
        "fallback": (
            "Hice tu llamada pero no pude generar un resumen detallado. "
            "Dime si quieres que lo intente de nuevo."
        ),
        "appointment_suggestion": (
            "📅 Cita acordada: {datetime_local}{location_part}. "
            "¿Quieres que la añada a tu calendario?"
        ),
        "appointment_location_part": " ({location})",
        "self_call_title": ("Nuestra llamada"),
        "relay_drafts_waiting": ("Nuestra llamada dejó borradores por confirmar en el chat."),
        "relay_answered": ("Hice lo que me pediste por teléfono: mi respuesta está en el chat."),
        "relay_empty": ("Nuestra llamada no dejó nada por hacer: no he trasladado nada al chat."),
        "relay_not_owner": (
            "Otra persona contestó a mi llamada; no compartí nada ni trasladé nada. Pídeme que te llame de nuevo cuando quieras."
        ),
        "relay_unanswered": (
            "No contestaste a mi llamada (o me saltó tu buzón de voz); no trasladé nada. Pídeme que te llame de nuevo cuando quieras."
        ),
        "relay_call_failed": (
            "Mi llamada no llegó a establecerse: la línea falló antes de que habláramos. No trasladé nada; pídeme que te llame de nuevo cuando quieras."
        ),
        "relay_pending_question": (
            "No he trasladado nuestra llamada al chat: allí sigue esperando una pregunta tu respuesta. Respóndela y luego dime si retomo lo que me pediste."
        ),
        "relay_busy": (
            "No he trasladado nuestra llamada al chat: había otra conversación en curso. Dime si retomo lo que me pediste."
        ),
        "relay_quota_blocked": (
            "No he podido trasladar nuestra llamada al chat: el límite de uso está alcanzado por ahora. Vuelve a decírmelo cuando se levante."
        ),
        "relay_failed": (
            "No he podido trasladar nuestra llamada al chat. Esto es lo que retengo; vuelve a decirme qué quieres que haga."
        ),
    },
    "it": {
        "title": "Riepilogo della chiamata",
        "fallback": (
            "Ho effettuato la tua chiamata ma non sono riuscito a produrre un "
            "riepilogo dettagliato. Dimmi se vuoi che riprovi."
        ),
        "appointment_suggestion": (
            "📅 Appuntamento concordato: {datetime_local}{location_part}. "
            "Vuoi che lo aggiunga al tuo calendario?"
        ),
        "appointment_location_part": " ({location})",
        "self_call_title": ("La nostra chiamata"),
        "relay_drafts_waiting": (
            "La nostra chiamata ha lasciato delle bozze da confermare nella chat."
        ),
        "relay_answered": (
            "Ho fatto quello che mi hai chiesto al telefono: la mia risposta è nella chat."
        ),
        "relay_empty": (
            "La nostra chiamata non ha lasciato nulla da fare: non ho riportato nulla nella chat."
        ),
        "relay_not_owner": (
            "Qualcun altro ha risposto alla mia chiamata; non ho condiviso né riportato nulla. Chiedimi di richiamarti quando vuoi."
        ),
        "relay_unanswered": (
            "Non hai risposto alla mia chiamata (o ho trovato la tua segreteria); non ho riportato nulla. Chiedimi di richiamarti quando vuoi."
        ),
        "relay_call_failed": (
            "La mia chiamata non è andata a buon fine: la linea è caduta prima che parlassimo. Non ho riportato nulla; chiedimi di richiamarti quando vuoi."
        ),
        "relay_pending_question": (
            "Non ho riportato la nostra chiamata nella chat: una domanda lì attende ancora la tua risposta. Rispondi, poi dimmi se devo riprendere ciò che mi hai chiesto."
        ),
        "relay_busy": (
            "Non ho riportato la nostra chiamata nella chat: c'era un'altra conversazione in corso. Dimmi se devo riprendere ciò che mi hai chiesto."
        ),
        "relay_quota_blocked": (
            "Non ho potuto riportare la nostra chiamata nella chat: il limite di utilizzo è raggiunto per ora. Ridimmelo quando sarà tolto."
        ),
        "relay_failed": (
            "Non ho potuto riportare la nostra chiamata nella chat. Ecco cosa ne trattengo; ridimmi cosa vuoi che faccia."
        ),
    },
    "zh": {
        "title": "通话小结",
        "fallback": "我已为你拨打了电话，但无法生成详细小结。需要我再试一次的话告诉我。",
        "appointment_suggestion": "📅 已约定时间：{datetime_local}{location_part}。要我帮你加到日历里吗？",
        "appointment_location_part": "（{location}）",
        "self_call_title": ("我们的通话"),
        "relay_drafts_waiting": ("我们的通话留下了待在聊天中确认的草稿。"),
        "relay_answered": ("我已经完成了你在电话里交代的事：我的回复在聊天中。"),
        "relay_empty": ("我们的通话没有留下要办的事：我没有向聊天转达任何内容。"),
        "relay_not_owner": (
            "接听我电话的是其他人；我没有分享也没有转达任何内容。想要的话随时让我再打给你。"
        ),
        "relay_unanswered": (
            "你没有接听我的电话（或者转到了语音信箱）；我没有转达任何内容。想要的话随时让我再打给你。"
        ),
        "relay_call_failed": (
            "我的电话没有接通：线路在我们通话前就中断了。我没有转达任何内容；想要的话随时让我再打给你。"
        ),
        "relay_pending_question": (
            "我没有把我们的通话转达到聊天：那里还有一个问题等你回答。先回答它，再告诉我是否要接着处理你提的事。"
        ),
        "relay_busy": (
            "我没有把我们的通话转达到聊天：那里当时有另一段对话在进行。告诉我是否要接着处理你提的事。"
        ),
        "relay_quota_blocked": (
            "我无法把我们的通话转达到聊天：目前已达到使用上限。上限解除后再告诉我一次。"
        ),
        "relay_failed": (
            "我无法把我们的通话转达到聊天。以下是我记下的内容；请再告诉我你要我做什么。"
        ),
    },
}


# ============================================================================
# Owner call — headings of the context block the voice agent receives (lot 4).
# ============================================================================
# ``more_not_shown`` carries a ``{count}`` placeholder rendered by the builder.

CONTEXT_HEADINGS: dict[str, dict[str, str]] = {
    "fr": {
        "memories": "Ce que je sais de toi",
        "agenda": "Ton agenda (36 prochaines heures)",
        "reminders": "Tes rappels en attente",
        "open_loops": "Tes fils en suspens",
        "recent_exchanges": "Nos derniers échanges",
        "more_not_shown": "(… {count} de plus, non affichés)",
    },
    "en": {
        "memories": "What I know about you",
        "agenda": "Your agenda (next 36 hours)",
        "reminders": "Your pending reminders",
        "open_loops": "Your open threads",
        "recent_exchanges": "Our latest exchanges",
        "more_not_shown": "(… {count} more not shown)",
    },
    "de": {
        "memories": "Was ich über dich weiß",
        "agenda": "Dein Kalender (nächste 36 Stunden)",
        "reminders": "Deine offenen Erinnerungen",
        "open_loops": "Deine offenen Fäden",
        "recent_exchanges": "Unsere letzten Gespräche",
        "more_not_shown": "(… {count} weitere, nicht angezeigt)",
    },
    "es": {
        "memories": "Lo que sé de ti",
        "agenda": "Tu agenda (próximas 36 horas)",
        "reminders": "Tus recordatorios pendientes",
        "open_loops": "Tus asuntos abiertos",
        "recent_exchanges": "Nuestros últimos intercambios",
        "more_not_shown": "(… {count} más, no mostrados)",
    },
    "it": {
        "memories": "Quello che so di te",
        "agenda": "La tua agenda (prossime 36 ore)",
        "reminders": "I tuoi promemoria in sospeso",
        "open_loops": "Le tue questioni aperte",
        "recent_exchanges": "I nostri ultimi scambi",
        "more_not_shown": "(… altri {count}, non mostrati)",
    },
    "zh": {
        "memories": "我对你的了解",
        "agenda": "你的日程（未来 36 小时）",
        "reminders": "你的待办提醒",
        "open_loops": "你的未决事项",
        "recent_exchanges": "我们最近的对话",
        "more_not_shown": "（……还有 {count} 条未显示）",
    },
}


def get_context_headings(language: str | None) -> dict[str, str]:
    """Headings of the owner-call context block, in the user's language."""
    return CONTEXT_HEADINGS.get(_iso(language), CONTEXT_HEADINGS[_DEFAULT])


def get_return_phrases(language: str | None) -> dict[str, str]:
    """Post-call delivery strings (title / synthesis-failure fallback)."""
    return RETURN_PHRASES.get(_iso(language), RETURN_PHRASES[_DEFAULT])
