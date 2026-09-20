"""Central i18n for the live voice mode (ADR-299).

Six languages keyed by the backend canonical code (``zh-CN`` for Chinese);
a raw locale is routed through ``normalize_language`` on lookup. ``summary_body`` is a ``str.format`` template with
``minutes``, ``delegations``, ``voice_turns`` and ``cost`` (euros, already
formatted) — the chat meter's vocabulary, never the provider's;
``summary_body_direct`` takes ``minutes``, ``cost`` and ``relay`` — the fate of
the relay of a DIRECT session's words into the chat (ADR-301: ``relay_*``,
the ``RelayOutcome`` vocabulary plus ``scheduled``), a direct session
archiving no exchange it could count (ADR-300 wave 4).
``provider_refused`` carries ``{detail}``: the provider's own words.

Data module (like ``core/i18n_*``): no domain imports, exempt from the size
ratchet. The domain modules import the accessor below.
"""

from __future__ import annotations

from src.core.i18n import DEFAULT_LANGUAGE, normalize_language

LIVE_PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "connector_missing": "Activate a Live connector before starting a voice session.",
        "session_in_progress": "A live session is already open on this account.",
        "instance_busy": (
            "Too many live sessions are open on this instance right now; try again in a moment."
        ),
        "mint_rate_limited": "Too many requests in a short time; wait a minute.",
        "voice_sample": "Hello, I am LIA. This is how I sound.",
        "session_not_found": "This live session does not exist or has ended.",
        "session_expired": "This live session reached its limit before the extension; start a new one.",
        "credential_invalid": "This connection credential was already used or has expired; reconnect to get a fresh one.",
        "summary_extended": "extended ×{count}",
        "provider_refused": "The provider refused this model: {detail}",
        "voice_unknown": "The voice {voice} is not one the provider offers; pick one from the list.",
        "model_unpriced": "The model {model} has no live tariff declared under LLM pricing (text AND audio rates, or a per-minute price); an administrator declares it, or pick another model in the Live settings.",
        "mode_unsupported": "This model cannot hold a direct session; start a live session, or pick a model that can in the Live settings.",
        "thinking_level_unknown": "The thinking level {level} is not one this model offers; pick one from the list.",
        "summary_title": "Live session",
        "summary_body": (
            "{minutes} min · {delegations} request(s) to LIA · {voice_turns} voice "
            "exchange(s) · LIA's cost {cost} €"
        ),
        "summary_body_direct": "{minutes} min · direct session · {relay} · LIA's cost {cost} €",
        "relay_scheduled": "your words are being relayed to the chat",
        "relay_answered": "your words were relayed to the chat and LIA answered",
        "relay_waiting": "your words were relayed to the chat; LIA has a question for you",
        "relay_empty": "nothing to relay to the chat",
        "relay_pending_question": "not relayed: a question of LIA is still waiting in the chat",
        "relay_busy": "not relayed: the chat was busy",
        "relay_quota_blocked": "not relayed: the spend ceiling refused it",
        "relay_failed": "the relay to the chat failed",
        "relay_not_owner": "not relayed: the account holder was not the one speaking",
        "relay_unanswered": "not relayed: nobody answered",
        "relay_call_failed": "not relayed: the line failed",
        "summary_recap": "recap: {recap}",
        "outcome_ended": "ended by you",
        "outcome_expired": "reached the session limit",
        "outcome_idle_timeout": "ended after a long silence",
        "outcome_hidden": "ended when the page went to the background",
        "outcome_provider_closed": "closed by the provider",
        "outcome_resumption_failed": "could not be resumed after a disconnection",
        "outcome_error": "ended on an error",
        "outcome_mic_denied": "could not start: microphone refused",
        "outcome_superseded": "replaced by a new session",
        "outcome_budget_reached": "ended at the spend ceiling you set",
    },
    "fr": {
        "connector_missing": "Active un connecteur Live avant d'ouvrir une session vocale.",
        "session_in_progress": "Une session live est déjà ouverte sur ce compte.",
        "instance_busy": (
            "Trop de sessions live sont ouvertes sur cette instance pour l'instant ; "
            "réessaie dans un moment."
        ),
        "mint_rate_limited": "Trop de demandes en peu de temps ; attends une minute.",
        "voice_sample": "Bonjour, je suis LIA. Voici ma voix.",
        "session_not_found": "Cette session live n'existe pas ou est terminée.",
        "session_expired": "Cette session live a atteint sa limite avant la prolongation ; ouvre-en une nouvelle.",
        "credential_invalid": "Cette clé de connexion a déjà servi ou a expiré ; reconnecte-toi pour en obtenir une nouvelle.",
        "summary_extended": "prolongée ×{count}",
        "provider_refused": "Le fournisseur a refusé ce modèle : {detail}",
        "voice_unknown": "La voix {voice} n'est pas proposée par le fournisseur ; choisis-en une dans la liste.",
        "model_unpriced": "Le modèle {model} n'a pas de tarif live déclaré dans la tarification LLM (tarifs texte ET audio, ou un prix à la minute) ; un administrateur le déclare, ou choisis un autre modèle dans les réglages Live.",
        "mode_unsupported": "Ce modèle ne peut pas tenir une session directe ; ouvre une session live, ou choisis dans les réglages Live un modèle qui le peut.",
        "thinking_level_unknown": "Le niveau de réflexion {level} n'est pas proposé par ce modèle ; choisis-en un dans la liste.",
        "summary_title": "Session live",
        "summary_body": (
            "{minutes} min · {delegations} demande(s) à LIA · {voice_turns} échange(s) "
            "vocal(aux) · coût LIA {cost} €"
        ),
        "summary_body_direct": "{minutes} min · session directe · {relay} · coût LIA {cost} €",
        "relay_scheduled": "tes mots sont en cours de relais dans le chat",
        "relay_answered": "tes mots ont été relayés dans le chat et LIA a répondu",
        "relay_waiting": "tes mots ont été relayés dans le chat ; LIA a une question pour toi",
        "relay_empty": "rien à relayer dans le chat",
        "relay_pending_question": "non relayé : une question de LIA attend encore dans le chat",
        "relay_busy": "non relayé : le chat était occupé",
        "relay_quota_blocked": "non relayé : le plafond de dépense l'a refusé",
        "relay_failed": "le relais dans le chat a échoué",
        "relay_not_owner": "non relayé : ce n'était pas le titulaire du compte qui parlait",
        "relay_unanswered": "non relayé : personne n'a répondu",
        "relay_call_failed": "non relayé : la ligne a échoué",
        "summary_recap": "résumé : {recap}",
        "outcome_ended": "terminée par toi",
        "outcome_expired": "arrivée à la limite de durée",
        "outcome_idle_timeout": "terminée après un long silence",
        "outcome_hidden": "terminée quand la page est passée en arrière-plan",
        "outcome_provider_closed": "fermée par le fournisseur",
        "outcome_resumption_failed": "impossible à reprendre après une coupure",
        "outcome_error": "terminée sur une erreur",
        "outcome_mic_denied": "impossible à démarrer : micro refusé",
        "outcome_superseded": "remplacée par une nouvelle session",
        "outcome_budget_reached": "arrêtée au plafond de dépense que tu as fixé",
    },
    "de": {
        "connector_missing": (
            "Aktivieren Sie einen Live-Connector, bevor Sie eine Sprachsitzung starten."
        ),
        "session_in_progress": "Auf diesem Konto ist bereits eine Live-Sitzung geöffnet.",
        "instance_busy": (
            "Auf dieser Instanz sind gerade zu viele Live-Sitzungen geöffnet; versuchen Sie "
            "es gleich noch einmal."
        ),
        "mint_rate_limited": "Zu viele Anfragen in kurzer Zeit; warten Sie eine Minute.",
        "voice_sample": "Hallo, ich bin LIA. So klinge ich.",
        "session_not_found": "Diese Live-Sitzung existiert nicht oder ist beendet.",
        "session_expired": "Diese Live-Sitzung hat ihr Limit vor der Verlängerung erreicht; starte eine neue.",
        "credential_invalid": "Dieser Verbindungsschlüssel wurde bereits verwendet oder ist abgelaufen; verbinden Sie sich erneut, um einen neuen zu erhalten.",
        "summary_extended": "verlängert ×{count}",
        "provider_refused": "Der Anbieter hat dieses Modell abgelehnt: {detail}",
        "voice_unknown": "Die Stimme {voice} bietet der Anbieter nicht an; wählen Sie eine aus der Liste.",
        "model_unpriced": "Für das Modell {model} ist unter LLM-Preise kein Live-Tarif hinterlegt (Text- UND Audio-Tarif, oder ein Minutenpreis); ein Administrator hinterlegt ihn, oder wählen Sie in den Live-Einstellungen ein anderes Modell.",
        "mode_unsupported": "Dieses Modell kann keine direkte Sitzung führen; starten Sie eine Live-Sitzung oder wählen Sie in den Live-Einstellungen ein Modell, das es kann.",
        "thinking_level_unknown": "Die Denkstufe {level} bietet dieses Modell nicht an; wählen Sie eine aus der Liste.",
        "summary_title": "Live-Sitzung",
        "summary_body": (
            "{minutes} Min · {delegations} Anfrage(n) an LIA · {voice_turns} "
            "Sprachwechsel · Kosten LIA {cost} €"
        ),
        "summary_body_direct": "{minutes} Min · direkte Sitzung · {relay} · Kosten LIA {cost} €",
        "relay_scheduled": "deine Worte werden gerade in den Chat übertragen",
        "relay_answered": "deine Worte wurden in den Chat übertragen und LIA hat geantwortet",
        "relay_waiting": "deine Worte wurden in den Chat übertragen; LIA hat eine Frage an dich",
        "relay_empty": "nichts in den Chat zu übertragen",
        "relay_pending_question": "nicht übertragen: eine Frage von LIA wartet noch im Chat",
        "relay_busy": "nicht übertragen: der Chat war beschäftigt",
        "relay_quota_blocked": "nicht übertragen: die Ausgabengrenze hat es abgelehnt",
        "relay_failed": "die Übertragung in den Chat ist fehlgeschlagen",
        "relay_not_owner": "nicht übertragen: nicht der Kontoinhaber hat gesprochen",
        "relay_unanswered": "nicht übertragen: niemand hat geantwortet",
        "relay_call_failed": "nicht übertragen: die Leitung ist ausgefallen",
        "summary_recap": "Zusammenfassung: {recap}",
        "outcome_ended": "von Ihnen beendet",
        "outcome_expired": "hat das Sitzungslimit erreicht",
        "outcome_idle_timeout": "nach langer Stille beendet",
        "outcome_hidden": "beendet, als die Seite in den Hintergrund ging",
        "outcome_provider_closed": "vom Anbieter geschlossen",
        "outcome_resumption_failed": "nach einer Unterbrechung nicht wiederaufnehmbar",
        "outcome_error": "mit einem Fehler beendet",
        "outcome_mic_denied": "konnte nicht starten: Mikrofon verweigert",
        "outcome_superseded": "durch eine neue Sitzung ersetzt",
        "outcome_budget_reached": "beim von Ihnen festgelegten Ausgabenlimit beendet",
    },
    "es": {
        "connector_missing": "Activa un conector Live antes de abrir una sesión de voz.",
        "session_in_progress": "Ya hay una sesión live abierta en esta cuenta.",
        "instance_busy": (
            "Hay demasiadas sesiones live abiertas en esta instancia ahora mismo; "
            "inténtalo de nuevo en un momento."
        ),
        "mint_rate_limited": "Demasiadas solicitudes en poco tiempo; espera un minuto.",
        "voice_sample": "Hola, soy LIA. Así suena mi voz.",
        "session_not_found": "Esta sesión live no existe o ha terminado.",
        "session_expired": "Esta sesión live alcanzó su límite antes de la prórroga; inicia una nueva.",
        "credential_invalid": "Esta credencial de conexión ya se usó o ha caducado; vuelve a conectarte para obtener una nueva.",
        "summary_extended": "prolongada ×{count}",
        "provider_refused": "El proveedor rechazó este modelo: {detail}",
        "voice_unknown": "La voz {voice} no la ofrece el proveedor; elige una de la lista.",
        "model_unpriced": "El modelo {model} no tiene tarifa live declarada en la tarificación LLM (tarifas de texto Y de audio, o un precio por minuto); un administrador la declara, o elige otro modelo en los ajustes Live.",
        "mode_unsupported": "Este modelo no puede mantener una sesión directa; inicia una sesión live, o elige en los ajustes Live un modelo que sí pueda.",
        "thinking_level_unknown": "El nivel de razonamiento {level} no lo ofrece este modelo; elige uno de la lista.",
        "summary_title": "Sesión live",
        "summary_body": (
            "{minutes} min · {delegations} petición(es) a LIA · {voice_turns} "
            "intercambio(s) de voz · coste LIA {cost} €"
        ),
        "summary_body_direct": "{minutes} min · sesión directa · {relay} · coste LIA {cost} €",
        "relay_scheduled": "tus palabras se están transmitiendo al chat",
        "relay_answered": "tus palabras se transmitieron al chat y LIA respondió",
        "relay_waiting": "tus palabras se transmitieron al chat; LIA tiene una pregunta para ti",
        "relay_empty": "nada que transmitir al chat",
        "relay_pending_question": "no transmitido: una pregunta de LIA sigue esperando en el chat",
        "relay_busy": "no transmitido: el chat estaba ocupado",
        "relay_quota_blocked": "no transmitido: el límite de gasto lo rechazó",
        "relay_failed": "la transmisión al chat falló",
        "relay_not_owner": "no transmitido: no era el titular de la cuenta quien hablaba",
        "relay_unanswered": "no transmitido: nadie contestó",
        "relay_call_failed": "no transmitido: la línea falló",
        "summary_recap": "resumen: {recap}",
        "outcome_ended": "terminada por ti",
        "outcome_expired": "alcanzó el límite de duración",
        "outcome_idle_timeout": "terminada tras un largo silencio",
        "outcome_hidden": "terminada cuando la página pasó a segundo plano",
        "outcome_provider_closed": "cerrada por el proveedor",
        "outcome_resumption_failed": "no se pudo reanudar tras un corte",
        "outcome_error": "terminada por un error",
        "outcome_mic_denied": "no pudo iniciarse: micrófono rechazado",
        "outcome_superseded": "sustituida por una nueva sesión",
        "outcome_budget_reached": "finalizada al alcanzar el límite de gasto que fijaste",
    },
    "it": {
        "connector_missing": "Attiva un connettore Live prima di aprire una sessione vocale.",
        "session_in_progress": "Una sessione live è già aperta su questo account.",
        "instance_busy": (
            "Troppe sessioni live sono aperte su questa istanza in questo momento; "
            "riprova tra poco."
        ),
        "mint_rate_limited": "Troppe richieste in poco tempo; attendi un minuto.",
        "voice_sample": "Ciao, sono LIA. Questa è la mia voce.",
        "session_not_found": "Questa sessione live non esiste o è terminata.",
        "session_expired": "Questa sessione live ha raggiunto il limite prima della proroga; avviane una nuova.",
        "credential_invalid": "Questa credenziale di connessione è già stata usata o è scaduta; riconnettiti per ottenerne una nuova.",
        "summary_extended": "prolungata ×{count}",
        "provider_refused": "Il fornitore ha rifiutato questo modello: {detail}",
        "voice_unknown": "La voce {voice} non è offerta dal fornitore; scegline una dall'elenco.",
        "model_unpriced": "Il modello {model} non ha una tariffa live dichiarata nella tariffazione LLM (tariffe testo E audio, oppure un prezzo al minuto); un amministratore la dichiara, oppure scegli un altro modello nelle impostazioni Live.",
        "mode_unsupported": "Questo modello non può tenere una sessione diretta; avvia una sessione live, oppure scegli nelle impostazioni Live un modello che lo possa.",
        "thinking_level_unknown": "Il livello di ragionamento {level} non è offerto da questo modello; scegline uno dall'elenco.",
        "summary_title": "Sessione live",
        "summary_body": (
            "{minutes} min · {delegations} richiesta/e a LIA · {voice_turns} "
            "scambio/i vocale/i · costo LIA {cost} €"
        ),
        "summary_body_direct": "{minutes} min · sessione diretta · {relay} · costo LIA {cost} €",
        "relay_scheduled": "le tue parole vengono trasmesse alla chat",
        "relay_answered": "le tue parole sono state trasmesse alla chat e LIA ha risposto",
        "relay_waiting": "le tue parole sono state trasmesse alla chat; LIA ha una domanda per te",
        "relay_empty": "niente da trasmettere alla chat",
        "relay_pending_question": "non trasmesso: una domanda di LIA è ancora in attesa nella chat",
        "relay_busy": "non trasmesso: la chat era occupata",
        "relay_quota_blocked": "non trasmesso: il tetto di spesa lo ha rifiutato",
        "relay_failed": "la trasmissione alla chat non è riuscita",
        "relay_not_owner": "non trasmesso: non era il titolare dell'account a parlare",
        "relay_unanswered": "non trasmesso: nessuno ha risposto",
        "relay_call_failed": "non trasmesso: la linea non ha funzionato",
        "summary_recap": "riepilogo: {recap}",
        "outcome_ended": "terminata da te",
        "outcome_expired": "ha raggiunto il limite di durata",
        "outcome_idle_timeout": "terminata dopo un lungo silenzio",
        "outcome_hidden": "terminata quando la pagina è passata in secondo piano",
        "outcome_provider_closed": "chiusa dal fornitore",
        "outcome_resumption_failed": "impossibile riprenderla dopo un'interruzione",
        "outcome_error": "terminata per un errore",
        "outcome_mic_denied": "impossibile avviarla: microfono rifiutato",
        "outcome_superseded": "sostituita da una nuova sessione",
        "outcome_budget_reached": "terminata al tetto di spesa che hai fissato",
    },
    "zh-CN": {
        "connector_missing": "请先激活一个 Live 连接器，再开始语音会话。",
        "session_in_progress": "此账户已有一个正在进行的实时会话。",
        "instance_busy": "此实例当前打开的实时会话过多，请稍后再试。",
        "mint_rate_limited": "短时间内请求过多，请等待一分钟。",
        "voice_sample": "你好，我是 LIA。这是我的声音。",
        "session_not_found": "此实时会话不存在或已结束。",
        "session_expired": "此实时会话在延长前已达上限；请开始新的会话。",
        "credential_invalid": "此连接凭证已使用或已过期；请重新连接以获取新的凭证。",
        "summary_extended": "已延长 {count} 次",
        "provider_refused": "服务商拒绝了该模型：{detail}",
        "voice_unknown": "服务商不提供语音 {voice}，请从列表中选择。",
        "model_unpriced": "模型 {model} 未在 LLM 计价中声明 Live 费率（文本和音频费率，或按分钟计价）；请由管理员声明，或在 Live 设置中选择其他模型。",
        "mode_unsupported": "此模型无法进行直接会话；请开始一个 Live 会话，或在 Live 设置中选择支持它的模型。",
        "thinking_level_unknown": "该模型不提供思考深度 {level}，请从列表中选择。",
        "summary_title": "实时会话",
        "summary_body": (
            "{minutes} 分钟 · 向 LIA 发出 {delegations} 次请求 · {voice_turns} 次语音交流 · "
            "LIA 费用 {cost} €"
        ),
        "summary_body_direct": "{minutes} 分钟 · 直接会话 · {relay} · LIA 费用 {cost} €",
        "relay_scheduled": "你的话正在转入对话",
        "relay_answered": "你的话已转入对话，LIA 已回复",
        "relay_waiting": "你的话已转入对话；LIA 有一个问题要问你",
        "relay_empty": "没有可转入对话的内容",
        "relay_pending_question": "未转入：LIA 的一个问题仍在对话中等待",
        "relay_busy": "未转入：对话正忙",
        "relay_quota_blocked": "未转入：费用上限拒绝了它",
        "relay_failed": "转入对话失败",
        "relay_not_owner": "未转入：说话的不是账户持有人",
        "relay_unanswered": "未转入：无人接听",
        "relay_call_failed": "未转入：线路故障",
        "summary_recap": "摘要：{recap}",
        "outcome_ended": "由您结束",
        "outcome_expired": "已达到会话时长上限",
        "outcome_idle_timeout": "长时间静默后结束",
        "outcome_hidden": "页面切换到后台时结束",
        "outcome_provider_closed": "由服务商关闭",
        "outcome_resumption_failed": "断线后无法恢复",
        "outcome_error": "因错误结束",
        "outcome_mic_denied": "无法开始：麦克风被拒绝",
        "outcome_superseded": "已被新会话取代",
        "outcome_budget_reached": "已在你设定的消费上限处结束",
    },
}


def get_live_phrases(language: str | None) -> dict[str, str]:
    """The live phrases of a language (the default language when unknown)."""
    key = normalize_language(language) if language else DEFAULT_LANGUAGE
    return LIVE_PHRASES.get(key, LIVE_PHRASES[DEFAULT_LANGUAGE])


__all__ = ["LIVE_PHRASES", "get_live_phrases"]
