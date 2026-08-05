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


# v2 (ADR-214): the suggestion carries the LEARNED schedule so the assistant
# can propose a prefilled automation. ``{schedule}`` is built from the shape
# (day-set wording or weekday name from the central i18n_dates module — no
# day name is ever declared twice) and ``{time}``/connector when an hour was
# locked. Keyed by ISO base code (``zh`` for ``zh-CN``), like the sibling tables.
RECURRENCE_SCHEDULE_SUGGESTION_TEXT: dict[str, str] = {
    "fr": (
        "Je remarque que tu me demandes ce genre de chose {schedule} — veux-tu "
        "que j'en fasse une automatisation récurrente programmée {schedule} ? "
        "Dis-le-moi et je la crée avec ces réglages, que tu pourras ajuster."
    ),
    "en": (
        "I notice you ask me this kind of thing {schedule} — want me to turn "
        "it into a recurring automation scheduled {schedule}? Say the word and "
        "I'll create it with these settings, which you can adjust."
    ),
    "de": (
        "Mir fällt auf, dass du mich {schedule} um so etwas bittest — soll ich "
        "daraus eine wiederkehrende Automatisierung machen, geplant {schedule}? "
        "Sag Bescheid und ich lege sie mit diesen Einstellungen an, die du "
        "anpassen kannst."
    ),
    "es": (
        "He notado que me pides este tipo de cosas {schedule} — ¿quieres que lo "
        "convierta en una automatización recurrente programada {schedule}? "
        "Dímelo y la creo con estos ajustes, que podrás modificar."
    ),
    "it": (
        "Noto che mi chiedi questo genere di cose {schedule} — vuoi che ne "
        "faccia un'automazione ricorrente programmata {schedule}? Dimmelo e la "
        "creo con queste impostazioni, che potrai modificare."
    ),
    "zh": (
        "我注意到你{schedule}会向我提出这类请求——要不要我把它变成一个定期自动化任务"
        "（{schedule}执行）？告诉我一声，我就按这些设置创建，你随时可以调整。"
    ),
}

# Per-shape schedule wording. ``{days}`` is the day-set wording or weekday
# name; ``{connector}`` and ``{time}`` are appended only when an hour was
# locked. "weekly" prefixes come from here (the day NAME comes from
# i18n_dates.get_day_name — never redeclared).
_SCHEDULE_SHAPE_WORDING: dict[str, dict[str, str]] = {
    "fr": {"with_time": "{days} vers {time}", "no_time": "{days}", "weekly_prefix": "chaque "},
    "en": {"with_time": "{days} around {time}", "no_time": "{days}", "weekly_prefix": "every "},
    "de": {"with_time": "{days} gegen {time}", "no_time": "{days}", "weekly_prefix": "jeden "},
    "es": {"with_time": "{days} hacia las {time}", "no_time": "{days}", "weekly_prefix": "cada "},
    "it": {"with_time": "{days} verso le {time}", "no_time": "{days}", "weekly_prefix": "ogni "},
    "zh": {"with_time": "{days}{time}左右", "no_time": "{days}", "weekly_prefix": "每"},
}


def get_recurrence_schedule_suggestion_text(language: str | None, lock: object) -> str:
    """Localized suggestion carrying the learned schedule (v2, ADR-214).

    Args:
        language: Any raw locale (normalized like the sibling lookups).
        lock: A ``RecurrenceLock``-shaped object (``shape``, ``trigger_hour``,
            ``modal_weekday`` attributes) — typed as object to keep this data
            module free of domain imports.

    Returns:
        The suggestion text with the schedule spliced in, in the user's
        language (English as the last resort).
    """
    from src.core.i18n_dates import format_half_hour_label, get_day_name

    key = (language or _DEFAULT).split("-")[0].lower()
    template = RECURRENCE_SCHEDULE_SUGGESTION_TEXT.get(
        key, RECURRENCE_SCHEDULE_SUGGESTION_TEXT[_DEFAULT]
    )
    wording = _SCHEDULE_SHAPE_WORDING.get(key, _SCHEDULE_SHAPE_WORDING[_DEFAULT])

    shape = getattr(lock, "shape", "daily")
    trigger_hour = getattr(lock, "trigger_hour", None)
    modal_weekday = getattr(lock, "modal_weekday", None)

    if shape == "weekly" and modal_weekday is not None:
        days = wording["weekly_prefix"] + get_day_name(modal_weekday, language or _DEFAULT)
    elif shape == "workdays":
        days = get_schedule_day_set("weekdays", language)
    else:
        days = get_schedule_day_set("every_day", language)

    if trigger_hour is not None:
        schedule = wording["with_time"].format(days=days, time=format_half_hour_label(trigger_hour))
    else:
        schedule = wording["no_time"].format(days=days)
    return template.format(schedule=schedule)
