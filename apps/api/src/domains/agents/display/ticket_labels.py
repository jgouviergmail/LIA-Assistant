"""Workboard columns in deterministic cards, matching the board vocabulary."""

from src.core.i18n import resolve_language
from src.core.i18n_types import Language
from src.domains.workboard.constants import TicketStatus

_LABELS: dict[TicketStatus, dict[Language, str]] = {
    TicketStatus.IDEA: {
        "en": "Idea",
        "fr": "Idée",
        "de": "Idee",
        "es": "Idea",
        "it": "Idea",
        "zh-CN": "想法",
    },
    TicketStatus.TODO: {
        "en": "To do",
        "fr": "À faire",
        "de": "Zu erledigen",
        "es": "Por hacer",
        "it": "Da fare",
        "zh-CN": "待办",
    },
    TicketStatus.IN_PROGRESS: {
        "en": "In progress",
        "fr": "En cours",
        "de": "In Arbeit",
        "es": "En curso",
        "it": "In corso",
        "zh-CN": "进行中",
    },
    TicketStatus.WAITING: {
        "en": "Waiting",
        "fr": "En attente",
        "de": "Wartet",
        "es": "En espera",
        "it": "In attesa",
        "zh-CN": "等待中",
    },
    TicketStatus.CONFIRMING: {
        "en": "To confirm",
        "fr": "À confirmer",
        "de": "Zu bestätigen",
        "es": "Por confirmar",
        "it": "Da confermare",
        "zh-CN": "待确认",
    },
    TicketStatus.VALIDATING: {
        "en": "To validate",
        "fr": "En validation",
        "de": "Zu prüfen",
        "es": "Por validar",
        "it": "Da validare",
        "zh-CN": "待确认",
    },
    TicketStatus.DONE: {
        "en": "Done",
        "fr": "Terminé",
        "de": "Erledigt",
        "es": "Terminado",
        "it": "Completato",
        "zh-CN": "已完成",
    },
}


def ticket_status_label(status: TicketStatus, language: str) -> str:
    return _LABELS[status][resolve_language(language)]
