"""Localized strings for self-diagnostics admin notifications (6 languages).

Data module (SLOC-cap exempt family, core/i18n_*). Backend-canonical language
codes: ``zh-CN`` for Chinese; every raw variant routes through the single
``normalize_language`` chokepoint — never ad-hoc ``language[:2]`` slicing.
"""

from __future__ import annotations

from src.core.i18n import normalize_language

#: Per-language notification strings. ``body`` interpolates {severity} and
#: {title} (the incident's human title, not translated — it names the outage).
INCIDENT_NOTIFICATION_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Platform incident detected",
        "body": (
            "A {severity} incident is open on your LIA instance: {title}. "
            "Open Settings > Platform health for the diagnosis and evidence."
        ),
    },
    "fr": {
        "title": "Incident plateforme détecté",
        "body": (
            "Un incident {severity} est ouvert sur votre instance LIA : {title}. "
            "Ouvrez Réglages > Santé de la plateforme pour le diagnostic et les preuves."
        ),
    },
    "de": {
        "title": "Plattform-Vorfall erkannt",
        "body": (
            "Auf Ihrer LIA-Instanz ist ein Vorfall ({severity}) offen: {title}. "
            "Öffnen Sie Einstellungen > Plattformzustand für Diagnose und Belege."
        ),
    },
    "es": {
        "title": "Incidente de plataforma detectado",
        "body": (
            "Hay un incidente {severity} abierto en su instancia de LIA: {title}. "
            "Abra Ajustes > Salud de la plataforma para ver el diagnóstico y las evidencias."
        ),
    },
    "it": {
        "title": "Incidente della piattaforma rilevato",
        "body": (
            "È aperto un incidente {severity} sulla tua istanza LIA: {title}. "
            "Apri Impostazioni > Salute della piattaforma per la diagnosi e le evidenze."
        ),
    },
    "zh-CN": {
        "title": "检测到平台事件",
        "body": (
            "您的 LIA 实例上有一个 {severity} 级事件：{title}。"
            "请打开 设置 > 平台健康 查看诊断结果和证据。"
        ),
    },
}

_DEFAULT_LANGUAGE = "en"


def get_incident_notification(
    language: str | None,
    *,
    severity: str,
    title: str,
) -> tuple[str, str]:
    """Localized (title, body) for an incident notification.

    Args:
        language: Raw user language (any variant; routed through
            ``normalize_language``).
        severity: Incident severity token ('critical'/'warning').
        title: Incident human title (kept verbatim — it names the outage).

    Returns:
        (notification_title, notification_body) in the user's language.
    """
    normalized = normalize_language(language or _DEFAULT_LANGUAGE)
    entries = INCIDENT_NOTIFICATION_STRINGS.get(
        normalized, INCIDENT_NOTIFICATION_STRINGS[_DEFAULT_LANGUAGE]
    )
    return entries["title"], entries["body"].format(severity=severity, title=title)
