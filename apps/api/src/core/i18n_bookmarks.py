"""Central i18n of the « Kept answers » knowledge space (part A, 2026-09-16 design).

Strings the BACKEND writes into artefacts the person keeps: the name and the
description of the auto-created knowledge space every bookmark is projected
into, and the header lines of the Markdown document that projection renders
(its title, the label of the quoted request, the line that replaces it when a
notification answered no request, the answered-on label).

Six supported languages, keyed by the backend-canonical code (``zh-CN``);
``normalize_language`` from ``core.i18n`` is the only entry point for raw
locale strings. Data module (like the other ``core/i18n_*``): no domain
imports, exempt from the size ratchet.
"""

from __future__ import annotations

from src.core.i18n import normalize_language

_DEFAULT = "en"

#: Default name of the auto-created knowledge space. The person may rename it;
#: the bookmarks domain finds it by ``kind``.
SPACE_NAME: dict[str, str] = {
    "en": "Kept answers",
    "fr": "Réponses conservées",
    "de": "Aufbewahrte Antworten",
    "es": "Respuestas guardadas",
    "it": "Risposte conservate",
    "zh-CN": "收藏的回答",
}

#: Default description — it says what the space holds, because the retrieval
#: block names the space and a reader should know these are LIA's own words.
SPACE_DESCRIPTION: dict[str, str] = {
    "en": (
        "The answers you kept with the bookmark button, indexed so LIA can find "
        "them again when a question recalls one."
    ),
    "fr": (
        "Les réponses que vous avez conservées avec le bouton signet, indexées "
        "pour que LIA les retrouve quand une question les rappelle."
    ),
    "de": (
        "Die Antworten, die Sie mit der Lesezeichen-Schaltfläche aufbewahrt haben, "
        "indexiert, damit LIA sie wiederfindet, wenn eine Frage daran erinnert."
    ),
    "es": (
        "Las respuestas que guardaste con el botón de marcador, indexadas para "
        "que LIA las encuentre cuando una pregunta las evoque."
    ),
    "it": (
        "Le risposte che hai conservato con il pulsante segnalibro, indicizzate "
        "perché LIA le ritrovi quando una domanda le richiama."
    ),
    "zh-CN": "您用书签按钮收藏的回答，已建立索引，当提问涉及时 LIA 可以再次找到它们。",
}

#: Header lines of the rendered document. ``name`` opens the display name;
#: ``title`` carries the local date; ``request`` labels the quoted request;
#: ``no_request`` replaces it for a notification LIA sent on its own
#: initiative; ``answered_on`` labels the answer's date.
DOCUMENT_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "name": "Kept answer",
        "title": "Kept answer of {date}",
        "request": "Request",
        "no_request": "Kept from a notification LIA sent on its own initiative (no request).",
        "answered_on": "Answered on",
    },
    "fr": {
        "name": "Réponse conservée",
        "title": "Réponse conservée du {date}",
        "request": "Demande",
        "no_request": (
            "Conservée depuis une notification envoyée par LIA de sa propre initiative "
            "(aucune demande)."
        ),
        "answered_on": "Répondu le",
    },
    "de": {
        "name": "Aufbewahrte Antwort",
        "title": "Aufbewahrte Antwort vom {date}",
        "request": "Anfrage",
        "no_request": (
            "Aufbewahrt aus einer Benachrichtigung, die LIA von sich aus gesendet hat "
            "(keine Anfrage)."
        ),
        "answered_on": "Beantwortet am",
    },
    "es": {
        "name": "Respuesta guardada",
        "title": "Respuesta guardada del {date}",
        "request": "Solicitud",
        "no_request": (
            "Guardada desde una notificación que LIA envió por iniciativa propia "
            "(sin solicitud)."
        ),
        "answered_on": "Respondida el",
    },
    "it": {
        "name": "Risposta conservata",
        "title": "Risposta conservata del {date}",
        "request": "Richiesta",
        "no_request": (
            "Conservata da una notifica inviata da LIA di propria iniziativa "
            "(nessuna richiesta)."
        ),
        "answered_on": "Risposta del",
    },
    "zh-CN": {
        "name": "收藏的回答",
        "title": "{date} 收藏的回答",
        "request": "请求",
        "no_request": "收藏自 LIA 主动发送的通知（没有对应请求）。",
        "answered_on": "回答日期",
    },
}


def _lang(language: str | None) -> str:
    """Resolve a raw locale to a table key through the single chokepoint."""
    code = normalize_language(language or "")
    return code if code in SPACE_NAME else _DEFAULT


def get_space_name(language: str | None) -> str:
    """Default name of the auto-created « Kept answers » knowledge space."""
    return SPACE_NAME.get(_lang(language), SPACE_NAME[_DEFAULT])


def get_space_description(language: str | None) -> str:
    """Default description of the auto-created knowledge space."""
    return SPACE_DESCRIPTION.get(_lang(language), SPACE_DESCRIPTION[_DEFAULT])


def get_document_labels(language: str | None) -> dict[str, str]:
    """Header labels of the rendered document, in the person's language."""
    return DOCUMENT_LABELS.get(_lang(language), DOCUMENT_LABELS[_DEFAULT])


__all__ = [
    "DOCUMENT_LABELS",
    "SPACE_DESCRIPTION",
    "SPACE_NAME",
    "get_document_labels",
    "get_space_description",
    "get_space_name",
]
