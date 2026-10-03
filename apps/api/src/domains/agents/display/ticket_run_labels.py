"""Deterministic run labels matching the board's six-language vocabulary."""

from src.core.i18n import resolve_language
from src.core.i18n_types import Language
from src.domains.workboard.constants import ActorKind, RunError, RunOutcome

_OUTCOMES: dict[RunOutcome, dict[Language, str]] = {
    RunOutcome.SUCCESS: {
        "en": "LIA answered",
        "fr": "LIA a répondu",
        "de": "LIA hat geantwortet",
        "es": "LIA respondió",
        "it": "LIA ha risposto",
        "zh-CN": "LIA 已回复",
    },
    RunOutcome.WAITING: {
        "en": "Waiting for you",
        "fr": "En attente de ton retour",
        "de": "Wartet auf dich",
        "es": "Espera tu respuesta",
        "it": "Attende la tua risposta",
        "zh-CN": "等待你的回复",
    },
    RunOutcome.CONFIRMING: {
        "en": "An action awaits your go-ahead",
        "fr": "Une action attend ton accord",
        "de": "Eine Aktion wartet auf dein Okay",
        "es": "Una acción espera tu visto bueno",
        "it": "Un'azione attende il tuo via libera",
        "zh-CN": "一项操作等待你的确认",
    },
    RunOutcome.FAILED: {
        "en": "Failed",
        "fr": "En échec",
        "de": "Fehlgeschlagen",
        "es": "Falló",
        "it": "Fallita",
        "zh-CN": "失败",
    },
    RunOutcome.SKIPPED_QUOTA: {
        "en": "Postponed — quota reached",
        "fr": "Reportée — quota atteint",
        "de": "Verschoben — Kontingent erreicht",
        "es": "Aplazada — cuota alcanzada",
        "it": "Rinviata — quota raggiunta",
        "zh-CN": "已推迟——配额已用完",
    },
    RunOutcome.SKIPPED_BUSY: {
        "en": "Postponed — a conversation was in progress",
        "fr": "Reportée — une conversation était en cours",
        "de": "Verschoben — ein Gespräch lief gerade",
        "es": "Aplazada — había una conversación en curso",
        "it": "Rinviata — una conversazione era in corso",
        "zh-CN": "已推迟——当时有对话进行中",
    },
}

_ERRORS: dict[RunError, dict[Language, str]] = {
    RunError.ASSIGNEE_INACTIVE: {
        "en": "The account that holds this ticket is no longer active, so LIA cannot run it.",
        "fr": "Le compte qui détient ce ticket n'est plus actif : LIA ne peut pas l'exécuter.",
        "de": "Das Konto, das dieses Ticket hält, ist nicht mehr aktiv – LIA kann es nicht ausführen.",
        "es": "La cuenta que tiene este ticket ya no está activa: LIA no puede ejecutarlo.",
        "it": "L'account che tiene questo ticket non è più attivo: LIA non può eseguirlo.",
        "zh-CN": "持有该工单的账号已停用，LIA 无法执行它。",
    },
    RunError.EMPTY_ANSWER: {
        "en": "LIA produced nothing this time — the ticket is untouched.",
        "fr": "LIA n'a rien produit cette fois — le ticket est intact.",
        "de": "LIA hat diesmal nichts erzeugt – das Ticket ist unverändert.",
        "es": "LIA no ha producido nada esta vez: el ticket queda intacto.",
        "it": "LIA non ha prodotto nulla questa volta — il ticket è intatto.",
        "zh-CN": "LIA 这次没有产出任何内容——工单保持原样。",
    },
    RunError.RUN_FAILED: {
        "en": "The run failed; LIA will not retry on its own. Use « Run now » to try again.",
        "fr": "L'exécution a échoué ; LIA ne réessaiera pas d'elle-même. Utilise « Exécuter maintenant » pour relancer.",
        "de": "Der Lauf ist fehlgeschlagen; LIA versucht es nicht von selbst erneut. Nutze „Jetzt ausführen“.",
        "es": "La ejecución ha fallado; LIA no lo reintentará sola. Usa «Ejecutar ahora» para volver a lanzarlo.",
        "it": "L'esecuzione è fallita; LIA non riproverà da sola. Usa «Esegui ora» per rilanciarla.",
        "zh-CN": "执行失败；LIA 不会自行重试。请使用「立即执行」重新发起。",
    },
    RunError.RUN_REAPED: {
        "en": "The run was interrupted and nobody saw how it ended.",
        "fr": "L'exécution a été interrompue et personne n'a vu comment elle s'est terminée.",
        "de": "Der Lauf wurde unterbrochen, und niemand hat gesehen, wie er endete.",
        "es": "La ejecución se interrumpió y nadie vio cómo terminó.",
        "it": "L'esecuzione è stata interrotta e nessuno ha visto come è finita.",
        "zh-CN": "执行被中断，没有人看到它是如何结束的。",
    },
}

_AUTHORS: dict[ActorKind, dict[Language, str]] = {
    ActorKind.USER: {"en": "You", "fr": "Toi", "de": "Du", "es": "Tú", "it": "Tu", "zh-CN": "你"},
    ActorKind.LIA: {
        "en": "LIA",
        "fr": "LIA",
        "de": "LIA",
        "es": "LIA",
        "it": "LIA",
        "zh-CN": "LIA",
    },
    ActorKind.PEER: {
        "en": "A connection",
        "fr": "Une connexion",
        "de": "Eine Verbindung",
        "es": "Una conexión",
        "it": "Una connessione",
        "zh-CN": "某个联系人",
    },
}


def ticket_outcome_label(value: str, language: str) -> str:
    return _OUTCOMES[RunOutcome(value)][resolve_language(language)] if value in RunOutcome else ""


def ticket_run_error_label(value: str, language: str) -> str:
    # Never reflect raw exception messages, credentials or stack traces into a card.
    return _ERRORS[RunError(value)][resolve_language(language)] if value in RunError else ""


def ticket_author_label(value: str, language: str) -> str:
    return _AUTHORS[ActorKind(value)][resolve_language(language)] if value in ActorKind else ""
