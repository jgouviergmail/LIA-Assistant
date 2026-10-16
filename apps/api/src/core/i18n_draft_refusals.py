"""Readable draft dispositions; machine codes remain in the execution result.

An uncertain completion cannot promise that nothing happened. A committed
write must stay distinguishable from a refusal, so the person checks reality
before retrying rather than repeating an action that already took effect.

Every code an owner produces on a confirmation card is either put into words
here or DECLARED generic in ``GENERIC_REFUSAL_CODES`` with the reason it names
nothing the person could act on — the census guard
(``tests/unit/domains/agents/test_draft_refusal_vocabulary_guard.py``) refuses
any other. A sentence claims « nothing was done » only where every producer of
its code refuses before any effect; elsewhere it names the cause and asks the
person to check, since a committed receipt already reads POST_COMMIT_FAILURE.
"""

from collections.abc import Mapping
from types import MappingProxyType

from src.core.i18n import resolve_language
from src.core.i18n_drafts import (
    get_draft_already_claimed_message,
    get_draft_cancel_message,
    get_draft_error_message,
)
from src.core.i18n_types import Language

_MESSAGES: dict[str, dict[Language, str]] = {
    "PARTIAL_SEND": {
        "fr": "Le serveur a accepté l’envoi pour certains destinataires et l’a refusé pour d’autres. Ne renvoie pas le message à tous : vérifie les destinataires avant une nouvelle tentative.",
        "en": "The server accepted sending to some recipients and refused others. Do not resend to everyone: check recipients before any new attempt.",
        "de": "Der Server hat das Senden an einige Empfänger angenommen und an andere abgelehnt. Sende nicht erneut an alle: Prüfe die Empfänger vor einem neuen Versuch.",
        "es": "El servidor aceptó el envío a algunos destinatarios y rechazó otros. No lo reenvíes a todos: comprueba los destinatarios antes de un nuevo intento.",
        "it": "Il server ha accettato l’invio ad alcuni destinatari e rifiutato altri. Non reinviare a tutti: verifica i destinatari prima di un nuovo tentativo.",
        "zh-CN": "服务器接受了向部分收件人发送邮件的请求，但拒绝了其他收件人。请勿向所有人重新发送；再次尝试前请先核实收件人。",
    },
    "DRAFT_CHANGED": {
        "fr": "Le brouillon a changé depuis son affichage. Aucun envoi : demande à LIA de le présenter à nouveau avant de confirmer.",
        "en": "The draft changed after it was shown. Nothing was sent: ask LIA to show it again before confirming.",
        "de": "Der Entwurf wurde seit der Anzeige geändert. Nichts wurde gesendet: Lass ihn vor der Bestätigung erneut anzeigen.",
        "es": "El borrador cambió después de mostrarse. No se envió nada: pide a LIA que lo muestre de nuevo antes de confirmar.",
        "it": "La bozza è cambiata dopo essere stata mostrata. Non è stato inviato nulla: chiedi a LIA di mostrarla di nuovo prima di confermare.",
        "zh-CN": "草稿在显示后已更改，未发送任何邮件。请让 LIA 再次显示草稿，然后确认。",
    },
    "DRAFT_GONE": {
        "fr": "Ce brouillon n’est plus disponible dans la boîte mail : il a pu être envoyé, supprimé ou déplacé. LIA n’a rien envoyé lors de cette confirmation.",
        "en": "This draft is no longer available in the mailbox: it may have been sent, deleted or moved. LIA sent nothing during this confirmation.",
        "de": "Dieser Entwurf ist nicht mehr im Postfach verfügbar: Er wurde möglicherweise gesendet, gelöscht oder verschoben. LIA hat bei dieser Bestätigung nichts gesendet.",
        "es": "Este borrador ya no está disponible: puede haberse enviado, eliminado o movido. LIA no envió nada durante esta confirmación.",
        "it": "Questa bozza non è più disponibile: potrebbe essere stata inviata, eliminata o spostata. LIA non ha inviato nulla durante questa conferma.",
        "zh-CN": "此草稿已无法在邮箱中找到，可能已发送、删除或移动。LIA 在本次确认中未发送任何邮件。",
    },
    "NO_RECIPIENT": {
        "fr": "Le brouillon confirmé ne contient aucun destinataire. Aucun envoi : ajoute un destinataire avant de confirmer à nouveau.",
        "en": "The confirmed draft has no recipient. Nothing was sent: add a recipient before confirming again.",
        "de": "Der bestätigte Entwurf hat keinen Empfänger. Nichts wurde gesendet: Füge vor einer erneuten Bestätigung einen Empfänger hinzu.",
        "es": "El borrador confirmado no tiene destinatario. No se envió nada: añade uno antes de volver a confirmar.",
        "it": "La bozza confermata non ha destinatari. Non è stato inviato nulla: aggiungi un destinatario prima di confermare di nuovo.",
        "zh-CN": "已确认的草稿没有收件人，未发送任何邮件。请添加收件人后再次确认。",
    },
    "SCHEMA_CHANGED": {
        "fr": "Les paramètres de cette action ont changé. Demande une nouvelle confirmation avec les valeurs actuelles.",
        "en": "The parameters of this action changed. Request a new confirmation with the current values.",
        "de": "Die Parameter dieser Aktion haben sich geändert. Fordere eine neue Bestätigung mit den aktuellen Werten an.",
        "es": "Los parámetros de esta acción cambiaron. Solicita una nueva confirmación con los valores actuales.",
        "it": "I parametri di questa azione sono cambiati. Richiedi una nuova conferma con i valori attuali.",
        "zh-CN": "此操作的参数已更改。请按当前值重新请求确认。",
    },
    "POST_COMMIT_FAILURE": {
        "fr": "Les modifications sont enregistrées, mais LIA n’a pas pu confirmer la fin du traitement. Vérifie leur état avant de réessayer.",
        "en": "The changes were saved, but LIA could not confirm that processing finished. Check their state before trying again.",
        "de": "Die Änderungen wurden gespeichert, aber LIA konnte den Abschluss nicht bestätigen. Prüfe ihren Zustand, bevor du es erneut versuchst.",
        "es": "Los cambios se guardaron, pero LIA no pudo confirmar el final del proceso. Comprueba su estado antes de volver a intentarlo.",
        "it": "Le modifiche sono state salvate, ma LIA non ha potuto confermare la fine del processo. Verifica il loro stato prima di riprovare.",
        "zh-CN": "更改已保存，但 LIA 无法确认处理是否完成。请先检查当前状态，再考虑重试。",
    },
    "COMPLETION_UNKNOWN": {
        "fr": "LIA n’a pas pu confirmer le résultat de cette action. Vérifie son état avant de réessayer : elle a pu prendre effet.",
        "en": "LIA could not confirm this action’s result. Check its state before trying again: it may have taken effect.",
        "de": "LIA konnte das Ergebnis dieser Aktion nicht bestätigen. Prüfe den Zustand vor einem erneuten Versuch: Sie könnte bereits wirksam sein.",
        "es": "LIA no pudo confirmar el resultado de esta acción. Comprueba su estado antes de reintentar: puede haber surtido efecto.",
        "it": "LIA non ha potuto confermare il risultato di questa azione. Verifica lo stato prima di riprovare: potrebbe aver avuto effetto.",
        "zh-CN": "LIA 无法确认此操作的结果，操作可能已生效。请先检查当前状态，再考虑重试。",
    },
    # The effect gate refuses before any claim or effect, and so does the
    # command service's own approval check.
    "CONFIRMATION_MISSING": {
        "fr": "Cette confirmation n’a pas pu être rattachée à ce qui t’a été présenté : rien n’a été exécuté. Redemande l’action pour la confirmer.",
        "en": "This confirmation could not be matched to what you were shown: nothing was done. Ask for the action again to confirm it.",
        "de": "Diese Bestätigung ließ sich dem Angezeigten nicht zuordnen: Es wurde nichts ausgeführt. Fordere die Aktion erneut an, um sie zu bestätigen.",
        "es": "Esta confirmación no se pudo asociar a lo que se te mostró: no se hizo nada. Vuelve a pedir la acción para confirmarla.",
        "it": "Questa conferma non è stata ricondotta a ciò che ti è stato mostrato: non è stato fatto nulla. Richiedi di nuovo l’azione per confermarla.",
        "zh-CN": "无法将此确认与向你展示的内容对应，未执行任何操作。请重新发起该操作并确认。",
    },
    # A claim, a database or a provider that did not answer: nothing was
    # committed, so a new attempt cannot do it twice.
    "DEPENDENCY_ERROR": {
        "fr": "Un service dont cette action a besoin ne répond pas pour le moment : elle n’a pas abouti. Réessaie dans un instant.",
        "en": "A service this action needs is not responding right now: it did not go through. Try again in a moment.",
        "de": "Ein Dienst, den diese Aktion braucht, antwortet gerade nicht: Sie wurde nicht abgeschlossen. Versuche es gleich noch einmal.",
        "es": "Un servicio que necesita esta acción no responde por ahora: no se completó. Inténtalo de nuevo en un momento.",
        "it": "Un servizio necessario a questa azione non risponde al momento: non è stata completata. Riprova tra un istante.",
        "zh-CN": "此操作依赖的服务暂时无响应，操作未完成。请稍后重试。",
    },
    "EXPIRED": {
        "fr": "Le délai prévu pour cette action a expiré : redemande-la si tu le souhaites toujours.",
        "en": "The time allowed for this action has run out: ask for it again if you still want it.",
        "de": "Die vorgesehene Frist für diese Aktion ist abgelaufen: Fordere sie erneut an, wenn du sie noch möchtest.",
        "es": "El plazo previsto para esta acción ha vencido: vuelve a pedirla si todavía la quieres.",
        "it": "Il tempo previsto per questa azione è scaduto: richiedila di nuovo se la vuoi ancora.",
        "zh-CN": "此操作的有效时间已过。如仍需要，请重新发起。",
    },
    "STALE_STATE": {
        "fr": "Ce que tu avais confirmé a changé depuis : vérifie l’état actuel avant de redemander l’action.",
        "en": "What you confirmed has changed since: check the current state before asking for the action again.",
        "de": "Was du bestätigt hattest, hat sich inzwischen geändert: Prüfe den aktuellen Stand, bevor du die Aktion erneut anforderst.",
        "es": "Lo que confirmaste ha cambiado desde entonces: comprueba el estado actual antes de volver a pedir la acción.",
        "it": "Ciò che avevi confermato è cambiato nel frattempo: verifica lo stato attuale prima di richiedere di nuovo l’azione.",
        "zh-CN": "你确认的内容此后已发生变化。请先查看当前状态，再重新发起该操作。",
    },
    "FORBIDDEN": {
        "fr": "Cette action n’est pas autorisée pour ton compte, ou ne l’est plus.",
        "en": "This action is not allowed for your account, or no longer is.",
        "de": "Diese Aktion ist für dein Konto nicht oder nicht mehr erlaubt.",
        "es": "Esta acción no está permitida para tu cuenta, o ya no lo está.",
        "it": "Questa azione non è consentita per il tuo account, o non lo è più.",
        "zh-CN": "你的账户不允许（或已不再允许）执行此操作。",
    },
    "NOT_FOUND_OR_UNAUTHORIZED": {
        "fr": "L’élément concerné est introuvable ou ne t’est plus accessible.",
        "en": "The item concerned cannot be found or is no longer available to you.",
        "de": "Das betroffene Element ist nicht auffindbar oder für dich nicht mehr zugänglich.",
        "es": "No se encuentra el elemento en cuestión o ya no tienes acceso a él.",
        "it": "L’elemento interessato non si trova o non ti è più accessibile.",
        "zh-CN": "找不到相关项目，或你已无权访问。",
    },
    "CAPABILITY_DISABLED": {
        "fr": "Cette fonction est désactivée sur cette instance.",
        "en": "This feature is switched off on this instance.",
        "de": "Diese Funktion ist auf dieser Instanz deaktiviert.",
        "es": "Esta función está desactivada en esta instancia.",
        "it": "Questa funzione è disattivata su questa istanza.",
        "zh-CN": "此功能在当前实例上已停用。",
    },
    "BUSY": {
        "fr": "L’élément concerné est en cours de traitement : réessaie dans un instant.",
        "en": "The item concerned is still being processed: try again in a moment.",
        "de": "Das betroffene Element wird gerade verarbeitet: Versuche es gleich noch einmal.",
        "es": "El elemento en cuestión todavía se está procesando: inténtalo de nuevo en un momento.",
        "it": "L’elemento interessato è ancora in elaborazione: riprova tra un istante.",
        "zh-CN": "相关项目仍在处理中，请稍后重试。",
    },
    "RATE_LIMIT_EXCEEDED": {
        "fr": "Trop de demandes en peu de temps : réessaie dans un instant.",
        "en": "Too many requests in a short time: try again in a moment.",
        "de": "Zu viele Anfragen in kurzer Zeit: Versuche es gleich noch einmal.",
        "es": "Demasiadas solicitudes en poco tiempo: inténtalo de nuevo en un momento.",
        "it": "Troppe richieste in poco tempo: riprova tra un istante.",
        "zh-CN": "短时间内请求过多，请稍后重试。",
    },
    "USAGE_LIMIT_EXCEEDED": {
        "fr": "Ta limite d’utilisation est atteinte pour le moment.",
        "en": "Your usage limit has been reached for now.",
        "de": "Dein Nutzungslimit ist vorerst erreicht.",
        "es": "Has alcanzado tu límite de uso por ahora.",
        "it": "Hai raggiunto il tuo limite di utilizzo per ora.",
        "zh-CN": "你目前已达到使用上限。",
    },
    # ``INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE``: the instance's own pause,
    # carried by ``UsageLimitExceededError.error_code``.
    "instance_budget_exhausted": {
        "fr": "Le budget du jour de cette instance est atteint : réessaie plus tard.",
        "en": "This instance’s daily budget has been reached: try again later.",
        "de": "Das Tagesbudget dieser Instanz ist ausgeschöpft: Versuche es später erneut.",
        "es": "Se ha agotado el presupuesto diario de esta instancia: inténtalo más tarde.",
        "it": "Il budget giornaliero di questa istanza è esaurito: riprova più tardi.",
        "zh-CN": "本实例的每日预算已用尽，请稍后再试。",
    },
    "TIMEOUT": {
        "fr": "Le service n’a pas répondu à temps : vérifie l’état actuel avant de réessayer.",
        "en": "The service did not answer in time: check the current state before trying again.",
        "de": "Der Dienst hat nicht rechtzeitig geantwortet: Prüfe den aktuellen Stand, bevor du es erneut versuchst.",
        "es": "El servicio no respondió a tiempo: comprueba el estado actual antes de volver a intentarlo.",
        "it": "Il servizio non ha risposto in tempo: verifica lo stato attuale prima di riprovare.",
        "zh-CN": "服务未能及时响应。请先查看当前状态，再决定是否重试。",
    },
    "CONSTRAINT_VIOLATION": {
        "fr": "Cette action ne respecte pas une règle ou une limite de l’application.",
        "en": "This action breaks one of the application’s rules or limits.",
        "de": "Diese Aktion verstößt gegen eine Regel oder Grenze der Anwendung.",
        "es": "Esta acción no respeta una regla o un límite de la aplicación.",
        "it": "Questa azione non rispetta una regola o un limite dell’applicazione.",
        "zh-CN": "此操作不符合应用的某项规则或限制。",
    },
    "INVALID_INPUT": {
        "fr": "Cette action n’est pas valide en l’état : redemande-la en précisant ce que tu veux.",
        "en": "This action is not valid as it stands: ask for it again, saying what you want.",
        "de": "Diese Aktion ist so nicht gültig: Fordere sie erneut an und sag genau, was du möchtest.",
        "es": "Esta acción no es válida tal como está: vuelve a pedirla precisando lo que quieres.",
        "it": "Questa azione non è valida così com’è: richiedila di nuovo precisando cosa vuoi.",
        "zh-CN": "此操作目前无效。请重新发起，并说明你想要的内容。",
    },
    # A personal MCP server's authorization failed: its credentials were never
    # staged, so no connection exists.
    "OAUTH_FAILED": {
        "fr": "L’autorisation auprès du service a échoué : la connexion n’a pas été établie. Relance-la si tu le souhaites.",
        "en": "Authorization with the service failed: the connection was not made. Start it again if you wish.",
        "de": "Die Autorisierung beim Dienst ist fehlgeschlagen: Die Verbindung wurde nicht hergestellt. Starte sie erneut, wenn du möchtest.",
        "es": "La autorización con el servicio falló: no se estableció la conexión. Vuelve a iniciarla si quieres.",
        "it": "L’autorizzazione presso il servizio non è riuscita: la connessione non è stata stabilita. Riavviala se vuoi.",
        "zh-CN": "向该服务授权失败，未建立连接。如有需要，请重新发起。",
    },
    # A command that was no longer pending could not be withdrawn: it may be
    # running or done, so the card never says « cancelled ».
    "CANCELLATION_UNAVAILABLE": {
        "fr": "Cette action n’a pas pu être annulée : elle a peut-être déjà commencé. Vérifie son état.",
        "en": "This action could not be cancelled: it may already have started. Check its state.",
        "de": "Diese Aktion konnte nicht abgebrochen werden: Sie hat möglicherweise schon begonnen. Prüfe ihren Stand.",
        "es": "No se pudo cancelar esta acción: puede que ya haya empezado. Comprueba su estado.",
        "it": "Non è stato possibile annullare questa azione: potrebbe essere già iniziata. Verificane lo stato.",
        "zh-CN": "无法取消此操作，它可能已经开始执行。请查看其当前状态。",
    },
}

#: Codes that name the same cause as another: one cause, one wording.
_SAME_AS: Mapping[str, str] = MappingProxyType(
    {
        "STALE_SELECTION": "STALE_STATE",
        "RESOURCE_BUSY": "BUSY",
        "INTERACTION_EXPIRED": "EXPIRED",
        "NOT_FOUND": "NOT_FOUND_OR_UNAUTHORIZED",
        "EXTERNAL_API_ERROR": "DEPENDENCY_ERROR",
    }
)

#: Every code the card reads as a sentence of its own.
WORDED_REFUSAL_CODES: frozenset[str] = (
    frozenset(_MESSAGES) | frozenset(_SAME_AS) | frozenset({"ALREADY_CLAIMED", "CANCELLED"})
)

#: Codes the card reads as the generic sentence ON PURPOSE, each with why.
GENERIC_REFUSAL_CODES: Mapping[str, str] = MappingProxyType(
    {
        "EXECUTION_FAILED": "An unexpected failure with no finite cause; its type is in the log.",
        "ADVISORY_CLEANUP_FAILED": (
            "Raised once the forgetting committed, so the committed receipt already reads "
            "POST_COMMIT_FAILURE."
        ),
        "INVALID_DRAFT": "A stored command the service cannot read back: an internal fault.",
        "INVALID_RESPONSE_FORMAT": "A provider or a source answered something unreadable.",
        "UNKNOWN_OPERATION": "An operation the code no longer declares: an internal fault.",
        "SOURCE_UNAVAILABLE": (
            "A skill-library source re-read at execution is blocked or conflicting; no wording "
            "verified against its producers yet."
        ),
        "DEVICE_UNAVAILABLE": (
            "A secure continuation's routing condition (ADR-339); no wording verified against "
            "its producers yet."
        ),
        "SESSION_UNAVAILABLE": (
            "A secure continuation's routing condition (ADR-339); no wording verified against "
            "its producers yet."
        ),
    }
)


def get_draft_refusal_message(
    code: str | None, language: str | None, *, committed: bool = False
) -> str:
    """The translated known disposition, without exposing an internal code.

    A committed receipt takes precedence even if closing the command failed.
    Unknown codes remain available to diagnostics in the result, while the
    card reads the existing generic sentence rather than inventing a reason.
    """
    lang = resolve_language(language)
    if committed:
        code = "POST_COMMIT_FAILURE"
    if code == "ALREADY_CLAIMED":
        return get_draft_already_claimed_message(lang)
    if code == "CANCELLED":
        return get_draft_cancel_message("application_action", lang)
    cause = code or ""
    messages = _MESSAGES.get(_SAME_AS.get(cause, cause))
    return messages[lang] if messages is not None else get_draft_error_message(lang)
