"""Mail accepted by SMTP can still fail to leave drafts or acquire a sent copy."""

from src.core.i18n import resolve_language
from src.core.i18n_types import Language

_KEPT: dict[Language, str] = {
    "fr": "Attention : le brouillon reste dans ta boîte mail malgré l’envoi. Ne le renvoie pas ; vérifie son état avant de le supprimer.",
    "en": "Warning: the draft remains in your mailbox despite sending. Do not send it again; check its state before deleting it.",
    "de": "Achtung: Der Entwurf bleibt trotz des Sendens im Postfach. Sende ihn nicht erneut; prüfe seinen Zustand vor dem Löschen.",
    "es": "Atención: el borrador sigue en tu buzón pese al envío. No lo envíes de nuevo; comprueba su estado antes de eliminarlo.",
    "it": "Attenzione: la bozza resta nella casella nonostante l’invio. Non inviarla di nuovo; verifica lo stato prima di eliminarla.",
    "zh-CN": "注意：邮件已发送，但草稿仍留在邮箱中。请勿再次发送；删除前请先检查当前状态。",
}

_COPY_MISSING: dict[Language, str] = {
    "fr": "La copie n’a pas pu être enregistrée dans les messages envoyés. L’envoi n’a pas été relancé ; vérifie auprès de ta boîte mail avant toute nouvelle tentative.",
    "en": "The copy could not be stored in sent messages. Sending was not retried; check with your mailbox before any new attempt.",
    "de": "Die Kopie konnte nicht unter den gesendeten Nachrichten gespeichert werden. Das Senden wurde nicht wiederholt; prüfe dein Postfach vor einem neuen Versuch.",
    "es": "No se pudo guardar la copia en enviados. No se repitió el envío; comprueba tu buzón antes de cualquier nuevo intento.",
    "it": "Non è stato possibile salvare la copia nei messaggi inviati. L’invio non è stato ripetuto; verifica la casella prima di un nuovo tentativo.",
    "zh-CN": "无法在已发送邮件中保存副本，未重试发送。再次尝试前请先在邮箱中核实。",
}


def filing_notice(language: str, *, draft_kept: bool, copy_missing: bool) -> str:
    """Say the observed filing failures, without turning missing metadata into failure."""
    lang = resolve_language(language)
    notices = []
    if draft_kept:
        notices.append(_KEPT[lang])
    if copy_missing:
        notices.append(_COPY_MISSING[lang])
    return " ".join(notices)
