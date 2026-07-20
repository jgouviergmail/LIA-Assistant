"""Centralized i18n for proactive notification surface strings (ADR-131).

Replaces the inline titles table that lived in
infrastructure/proactive/notification.py — which was keyed "zh" while
User.language is backend-canonical "zh-CN", silently sending English
titles to Chinese users.

Supported languages: fr, en, es, de, it, zh-CN (systemic i18n rule).
"""


class ProactiveMessages:
    """Factory for proactive notification strings, 6 languages.

    Same pattern as APIMessages: dict-based translations keyed by the
    backend-canonical language code, English fallback.
    """

    _TITLES: dict[str, dict[str, str]] = {
        "interest": {
            "fr": "Pour toi",
            "en": "For you",
            "es": "Para ti",
            "de": "Für dich",
            "it": "Per te",
            "zh-CN": "为你推荐",
        },
        "birthday": {
            "fr": "Anniversaire",
            "en": "Birthday",
            "es": "Cumpleaños",
            "de": "Geburtstag",
            "it": "Compleanno",
            "zh-CN": "生日",
        },
        "event": {
            "fr": "Événement",
            "en": "Event",
            "es": "Evento",
            "de": "Ereignis",
            "it": "Evento",
            "zh-CN": "活动",
        },
        "summary": {
            "fr": "Résumé",
            "en": "Summary",
            "es": "Resumen",
            "de": "Zusammenfassung",
            "it": "Riepilogo",
            "zh-CN": "摘要",
        },
        "heartbeat": {
            "fr": "Notification proactive",
            "en": "Proactive notification",
            "es": "Notificación proactiva",
            "de": "Proaktive Benachrichtigung",
            "it": "Notifica proattiva",
            "zh-CN": "主动通知",
        },
        # Used by the scheduled-action executor, which kept its own inline
        # table keyed "zh" — reproducing here the exact bug this module was
        # created to fix (User.language is backend-canonical "zh-CN", so
        # Chinese users silently received the English title).
        "scheduled_action": {
            "fr": "Action planifiée",
            "en": "Scheduled action",
            "es": "Acción programada",
            "de": "Geplante Aktion",
            "it": "Azione pianificata",
            "zh-CN": "计划操作",
        },
    }

    _SOURCES_LABEL: dict[str, str] = {
        "fr": "Sources",
        "en": "Sources",
        "es": "Fuentes",
        "de": "Quellen",
        "it": "Fonti",
        "zh-CN": "来源",
    }

    @staticmethod
    def notification_title(task_type: str, language: str) -> str:
        """Localized push/chat title for a proactive task type.

        Args:
            task_type: Proactive task type (interest, birthday, ...).
            language: Backend-canonical language code (e.g. "fr", "zh-CN").

        Returns:
            The localized title; English fallback per task type, then a
            generic "Notification" for unknown task types.
        """
        task_titles = ProactiveMessages._TITLES.get(task_type, {})
        return task_titles.get(language, task_titles.get("en", "Notification"))

    @staticmethod
    def sources_label(language: str) -> str:
        """Localized label prefixing the source links block.

        Args:
            language: Backend-canonical language code.

        Returns:
            The localized "Sources" label (English fallback).
        """
        return ProactiveMessages._SOURCES_LABEL.get(
            language, ProactiveMessages._SOURCES_LABEL["en"]
        )
