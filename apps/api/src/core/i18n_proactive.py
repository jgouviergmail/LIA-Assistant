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
        # Used by the reminder scheduler, which kept its OWN inline table keyed
        # "zh" — the third occurrence of the very bug this module exists for.
        # It sends both the FCM title and the external-channel title, so a
        # Chinese user was getting "Reminder" in English on every reminder.
        "reminder": {
            "fr": "Rappel",
            "en": "Reminder",
            "es": "Recordatorio",
            "de": "Erinnerung",
            "it": "Promemoria",
            "zh-CN": "提醒",
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

    # N-07 propose-first mode: the tick notifies instead of executing; the
    # markdown link carries the routine's prompt as a chat ?intent= (ADR-173),
    # so the actual run flows through the normal pipeline + HITL.
    _ROUTINE_APPROVAL_BODIES: dict[str, str] = {
        "fr": "Ta routine « {title} » est prête à s'exécuter. [Lancer maintenant]({intent_url})",
        "en": "Your routine “{title}” is ready to run. [Run it now]({intent_url})",
        "es": "Tu rutina «{title}» está lista para ejecutarse. [Ejecutarla ahora]({intent_url})",
        "de": "Deine Routine „{title}“ ist bereit zur Ausführung. [Jetzt ausführen]({intent_url})",
        "it": "La tua routine «{title}» è pronta per essere eseguita. [Eseguila ora]({intent_url})",
        "zh-CN": "您的例行任务“{title}”已准备好执行。[立即执行]({intent_url})",
    }

    @staticmethod
    def notification_title(task_type: str, language: str) -> str:
        """Localized push/chat title for a proactive task type.

        The code is normalized through the single chokepoint before keying the
        table: callers hold raw locales of every spelling (``zh`` from the
        frontend, ``fr-FR`` from a header, ``zh_CN`` from a legacy row), and
        keying on a raw locale is precisely the defect this module was created
        to fix. Normalizing here makes every call site safe by construction
        rather than by discipline.

        Args:
            task_type: Proactive task type (interest, birthday, ...).
            language: Any locale spelling; normalized internally.

        Returns:
            The localized title; English fallback per task type, then a
            generic "Notification" for unknown task types.
        """
        from src.core.i18n import normalize_language

        task_titles = ProactiveMessages._TITLES.get(task_type, {})
        return task_titles.get(normalize_language(language), task_titles.get("en", "Notification"))

    @staticmethod
    def routine_approval_body(title: str, intent_url: str, language: str) -> str:
        """Localized propose-first body for a routine awaiting approval (N-07).

        Args:
            title: The routine's user-facing title.
            intent_url: Absolute chat deep link carrying the routine prompt
                as ``?intent=`` (ADR-173).
            language: Any locale spelling; normalized internally.

        Returns:
            The localized markdown body (English fallback).
        """
        from src.core.i18n import normalize_language

        template = ProactiveMessages._ROUTINE_APPROVAL_BODIES.get(
            normalize_language(language), ProactiveMessages._ROUTINE_APPROVAL_BODIES["en"]
        )
        return template.format(title=title, intent_url=intent_url)

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
