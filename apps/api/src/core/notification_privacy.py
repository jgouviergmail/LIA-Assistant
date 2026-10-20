"""Delivery boundary for model-derived personal content."""

from enum import Enum

from src.core.i18n import normalize_language


class NotificationPrivacy(str, Enum):
    NORMAL = "normal"
    IN_APP_SENSITIVE = "in_app_sensitive"


PRIVATE_NOTIFICATION_MARKER = "sensitive_in_app_only"
_NOTICES = {
    "fr": "Un nouveau point personnel est disponible dans LIA.",
    "en": "A new personal update is available in LIA.",
    "es": "Hay una nueva actualización personal en LIA.",
    "de": "Ein neues persönliches Update ist in LIA verfügbar.",
    "it": "Un nuovo aggiornamento personale è disponibile in LIA.",
    "zh-CN": "LIA 中有新的个人动态。",
}


def notification_preview(
    privacy: NotificationPrivacy, language: str, title: str, body: str
) -> tuple[str, str]:
    if privacy is NotificationPrivacy.IN_APP_SENSITIVE:
        return "LIA", _NOTICES[normalize_language(language)]
    return title, body
