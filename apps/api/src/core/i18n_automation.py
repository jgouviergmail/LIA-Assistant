"""Central i18n for the automation feature (ADR-140).

Data module (like ``core/i18n_*``): no domain imports, exempt from the size
ratchet. Currently carries the recurrence-suggestion text injected into the
response prompt directive when the deterministic detector fires (P12).
"""

from __future__ import annotations

_DEFAULT = "en"

# Keyed by ISO base code (``zh`` for ``zh-CN``); normalized on lookup like
# the sibling i18n modules.
#: Compact day-set wordings for a routine's schedule.
#:
#: The three sets a weekly schedule falls into often enough to deserve a
#: phrase rather than an enumeration. Anything else is listed day by day using
#: the central ``i18n_dates`` abbreviations, so no day name is ever declared
#: twice in the codebase.
#:
#: Keyed on the backend-canonical language (``zh-CN``, never ``zh``).
SCHEDULE_DAY_SETS: dict[str, dict[str, str]] = {
    "fr": {"every_day": "Tous les jours", "weekdays": "Lun-Ven", "weekend": "Sam-Dim"},
    "en": {"every_day": "Every day", "weekdays": "Mon-Fri", "weekend": "Sat-Sun"},
    "es": {"every_day": "Todos los días", "weekdays": "Lun-Vie", "weekend": "Sáb-Dom"},
    "de": {"every_day": "Täglich", "weekdays": "Mo-Fr", "weekend": "Sa-So"},
    "it": {"every_day": "Tutti i giorni", "weekdays": "Lun-Ven", "weekend": "Sab-Dom"},
    "zh-CN": {"every_day": "每天", "weekdays": "周一至周五", "weekend": "周末"},
}


def get_schedule_day_set(kind: str, language: str | None) -> str:
    """Localized wording for a recognised day set.

    Args:
        kind: ``every_day`` | ``weekdays`` | ``weekend``.
        language: Any raw locale — normalized through the single chokepoint.

    Returns:
        The wording in the user's language, English as the last resort.
    """
    from src.core.i18n import DEFAULT_LANGUAGE, normalize_language

    canonical = normalize_language(language or DEFAULT_LANGUAGE)
    table = SCHEDULE_DAY_SETS.get(canonical, SCHEDULE_DAY_SETS["en"])
    return table[kind]


RECURRENCE_SUGGESTION_TEXT: dict[str, str] = {
    "fr": (
        "Tu me demandes régulièrement ce genre de chose au même moment de la "
        "journée — veux-tu que j'en fasse une automatisation récurrente ? "
        "Je peux l'exécuter pour toi automatiquement au jour et à l'heure de ton choix."
    ),
    "en": (
        "You ask me this kind of thing regularly at the same time of day — "
        "want me to turn it into a recurring automation? I can run it for you "
        "automatically on the days and time you choose."
    ),
    "de": (
        "Du fragst mich so etwas regelmäßig zur gleichen Tageszeit — soll ich "
        "daraus eine wiederkehrende Automatisierung machen? Ich kann sie "
        "automatisch an den Tagen und zur Uhrzeit deiner Wahl ausführen."
    ),
    "es": (
        "Me pides este tipo de cosas con regularidad a la misma hora del día — "
        "¿quieres que lo convierta en una automatización recurrente? Puedo "
        "ejecutarla automáticamente los días y a la hora que elijas."
    ),
    "it": (
        "Mi chiedi regolarmente questo genere di cose alla stessa ora del "
        "giorno — vuoi che ne faccia un'automazione ricorrente? Posso "
        "eseguirla automaticamente nei giorni e all'ora che scegli."
    ),
    "zh": (
        "你经常在一天中的同一时间向我提出这类请求——要不要我把它变成一个定期自动化任务？"
        "我可以在你选择的日期和时间自动为你执行。"
    ),
}


def get_recurrence_suggestion_text(language: str | None) -> str:
    """Localized recurrence→automation suggestion, normalized lookup."""
    key = (language or _DEFAULT).split("-")[0].lower()
    return RECURRENCE_SUGGESTION_TEXT.get(key, RECURRENCE_SUGGESTION_TEXT[_DEFAULT])
