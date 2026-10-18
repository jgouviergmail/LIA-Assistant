"""Closed translated vocabulary for accepted classification badges."""

from typing import Literal

from src.core.i18n import resolve_language
from src.core.i18n_types import Language

ClassificationLabel = Literal[
    "professional", "personal", "spam", "phishing_scam", "urgent", "critical"
]
_LABELS: dict[ClassificationLabel, dict[Language, str]] = {
    "professional": {
        "fr": "Professionnel",
        "en": "Professional",
        "de": "Beruflich",
        "es": "Profesional",
        "it": "Professionale",
        "zh-CN": "工作",
    },
    "personal": {
        "fr": "Personnel",
        "en": "Personal",
        "de": "Privat",
        "es": "Personal",
        "it": "Personale",
        "zh-CN": "个人",
    },
    "spam": {
        "fr": "Spam",
        "en": "Spam",
        "de": "Spam",
        "es": "Spam",
        "it": "Spam",
        "zh-CN": "垃圾邮件",
    },
    "phishing_scam": {
        "fr": "Phishing/Arnaque",
        "en": "Phishing/Scam",
        "de": "Phishing/Betrug",
        "es": "Phishing/Estafa",
        "it": "Phishing/Truffa",
        "zh-CN": "网络钓鱼/诈骗",
    },
    "urgent": {
        "fr": "Urgent",
        "en": "Urgent",
        "de": "Dringend",
        "es": "Urgente",
        "it": "Urgente",
        "zh-CN": "紧急",
    },
    "critical": {
        "fr": "Critique",
        "en": "Critical",
        "de": "Kritisch",
        "es": "Crítico",
        "it": "Critico",
        "zh-CN": "严重",
    },
}


def classification_label(key: ClassificationLabel, language: str) -> str:
    return _LABELS[key][resolve_language(language)]
