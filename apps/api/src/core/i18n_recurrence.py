"""Central i18n for the generic recurrence component.

Data module (like the sibling ``core/i18n_*``): no domain imports, exempt from
the size ratchet.

The sentence is COMPOSED, never enumerated. The shape space is
freq × interval × selector × times × end; one key per shape would be hundreds
of entries in six languages, and the seventh consumer would add hundreds more.
Four clauses, each a key, assembled by :mod:`src.core.recurrence.display`.

Keyed on the backend-canonical language (``zh-CN``, never ``zh``), reached
through ``normalize_language`` — the single chokepoint.
"""

from __future__ import annotations

#: Every clause of a recurrence sentence, by canonical language.
#:
#: The three day sets people actually schedule get a PHRASE rather than a list:
#: measured on the migrated rows, spelling seven weekday names produced
#: "Toutes les semaines, le lundi, mardi, mercredi, jeudi, vendredi, samedi et
#: dimanche, à 09:00" where the previous engine said "Tous les jours à 09:00".
#: Only a genuinely irregular pick still enumerates.
#:
#: Placeholders: ``{n}`` a count, ``{days}`` a day list, ``{times}`` a moment
#: list, ``{from}``/``{to}`` step bounds, ``{step}`` a step, ``{date}`` a date,
#: ``{day}`` a day of month, ``{month}`` a month name, ``{weekday}`` a weekday.
#:
#: ``day_number`` is the template of ONE day of month, applied before the days
#: are joined. German marks an ordinal and Chinese appends a classifier, and
#: both belong to the NUMBER: carried by the sentence instead, they landed once
#: after a whole list — "Am 1 und 15. jedes Monats" (measured 2026-09-06).
RECURRENCE_PARTS: dict[str, dict[str, str]] = {
    "fr": {
        "once": "Une seule fois, le {date}",
        "daily": "Tous les jours",
        "daily_n": "Tous les {n} jours",
        "weekly": "Toutes les semaines, le {days}",
        "weekly_all": "Tous les jours",
        "weekly_all_n": "Tous les jours, une semaine sur {n}",
        "weekly_workdays": "En semaine",
        "weekly_workdays_n": "En semaine, une semaine sur {n}",
        "weekly_weekend": "Le week-end",
        "weekly_weekend_n": "Le week-end, une semaine sur {n}",
        "weekly_n": "Toutes les {n} semaines, le {days}",
        "monthly_day": "Le {day} de chaque mois",
        "monthly_day_n": "Le {day} tous les {n} mois",
        "monthly_last": "Le dernier jour du mois",
        "monthly_last_n": "Le dernier jour, tous les {n} mois",
        "monthly_nth": "Le {nth} {weekday} de chaque mois",
        "monthly_nth_n": "Le {nth} {weekday}, tous les {n} mois",
        "yearly": "Tous les ans, le {day} {month}",
        "yearly_n": "Tous les {n} ans, le {day} {month}",
        "day_number": "{day}",
        "at_times": "à {times}",
        "every_step": "toutes les {step}, de {from} à {to}",
        "end_on_date": "jusqu'au {date}",
        "end_after_count": "{n} fois",
        "nth_1": "1er",
        "nth_2": "2e",
        "nth_3": "3e",
        "nth_4": "4e",
        "nth_5": "5e",
        "nth_last": "dernier",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " et ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "en": {
        "once": "Once, on {date}",
        "daily": "Every day",
        "daily_n": "Every {n} days",
        "weekly": "Every week, on {days}",
        "weekly_all": "Every day",
        "weekly_all_n": "Every day, every {n} weeks",
        "weekly_workdays": "On weekdays",
        "weekly_workdays_n": "On weekdays, every {n} weeks",
        "weekly_weekend": "At the weekend",
        "weekly_weekend_n": "At the weekend, every {n} weeks",
        "weekly_n": "Every {n} weeks, on {days}",
        "monthly_day": "On the {day} of every month",
        "monthly_day_n": "On the {day}, every {n} months",
        "monthly_last": "On the last day of the month",
        "monthly_last_n": "On the last day, every {n} months",
        "monthly_nth": "On the {nth} {weekday} of every month",
        "monthly_nth_n": "On the {nth} {weekday}, every {n} months",
        "yearly": "Every year, on {month} {day}",
        "yearly_n": "Every {n} years, on {month} {day}",
        "day_number": "{day}",
        "at_times": "at {times}",
        "every_step": "every {step}, from {from} to {to}",
        "end_on_date": "until {date}",
        "end_after_count": "{n} times",
        "nth_1": "1st",
        "nth_2": "2nd",
        "nth_3": "3rd",
        "nth_4": "4th",
        "nth_5": "5th",
        "nth_last": "last",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " and ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "es": {
        "once": "Una sola vez, el {date}",
        "daily": "Todos los días",
        "daily_n": "Cada {n} días",
        "weekly": "Cada semana, el {days}",
        "weekly_all": "Todos los días",
        "weekly_all_n": "Todos los días, cada {n} semanas",
        "weekly_workdays": "Entre semana",
        "weekly_workdays_n": "Entre semana, cada {n} semanas",
        "weekly_weekend": "El fin de semana",
        "weekly_weekend_n": "El fin de semana, cada {n} semanas",
        "weekly_n": "Cada {n} semanas, el {days}",
        "monthly_day": "El {day} de cada mes",
        "monthly_day_n": "El {day}, cada {n} meses",
        "monthly_last": "El último día del mes",
        "monthly_last_n": "El último día, cada {n} meses",
        "monthly_nth": "El {nth} {weekday} de cada mes",
        "monthly_nth_n": "El {nth} {weekday}, cada {n} meses",
        "yearly": "Cada año, el {day} de {month}",
        "yearly_n": "Cada {n} años, el {day} de {month}",
        "day_number": "{day}",
        "at_times": "a las {times}",
        "every_step": "cada {step}, de {from} a {to}",
        "end_on_date": "hasta el {date}",
        "end_after_count": "{n} veces",
        "nth_1": "1.º",
        "nth_2": "2.º",
        "nth_3": "3.º",
        "nth_4": "4.º",
        "nth_5": "5.º",
        "nth_last": "último",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " y ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "de": {
        "once": "Einmalig, am {date}",
        "daily": "Täglich",
        "daily_n": "Alle {n} Tage",
        "weekly": "Wöchentlich, am {days}",
        "weekly_all": "Täglich",
        "weekly_all_n": "Täglich, alle {n} Wochen",
        "weekly_workdays": "An Werktagen",
        "weekly_workdays_n": "An Werktagen, alle {n} Wochen",
        "weekly_weekend": "Am Wochenende",
        "weekly_weekend_n": "Am Wochenende, alle {n} Wochen",
        "weekly_n": "Alle {n} Wochen, am {days}",
        "monthly_day": "Am {day} jedes Monats",
        "monthly_day_n": "Am {day}, alle {n} Monate",
        "monthly_last": "Am letzten Tag des Monats",
        "monthly_last_n": "Am letzten Tag, alle {n} Monate",
        "monthly_nth": "Am {nth} {weekday} jedes Monats",
        "monthly_nth_n": "Am {nth} {weekday}, alle {n} Monate",
        "yearly": "Jährlich, am {day} {month}",
        "yearly_n": "Alle {n} Jahre, am {day} {month}",
        "day_number": "{day}.",
        "at_times": "um {times}",
        "every_step": "alle {step}, von {from} bis {to}",
        "end_on_date": "bis zum {date}",
        "end_after_count": "{n}-mal",
        "nth_1": "1.",
        "nth_2": "2.",
        "nth_3": "3.",
        "nth_4": "4.",
        "nth_5": "5.",
        "nth_last": "letzten",
        "step_hours": "{n} Std.",
        "step_minutes": "{n} Min.",
        "list_separator": ", ",
        "list_last": " und ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "it": {
        "once": "Una sola volta, il {date}",
        "daily": "Tutti i giorni",
        "daily_n": "Ogni {n} giorni",
        "weekly": "Ogni settimana, il {days}",
        "weekly_all": "Tutti i giorni",
        "weekly_all_n": "Tutti i giorni, ogni {n} settimane",
        "weekly_workdays": "Nei giorni feriali",
        "weekly_workdays_n": "Nei giorni feriali, ogni {n} settimane",
        "weekly_weekend": "Nel fine settimana",
        "weekly_weekend_n": "Nel fine settimana, ogni {n} settimane",
        "weekly_n": "Ogni {n} settimane, il {days}",
        "monthly_day": "Il {day} di ogni mese",
        "monthly_day_n": "Il {day}, ogni {n} mesi",
        "monthly_last": "L'ultimo giorno del mese",
        "monthly_last_n": "L'ultimo giorno, ogni {n} mesi",
        "monthly_nth": "Il {nth} {weekday} di ogni mese",
        "monthly_nth_n": "Il {nth} {weekday}, ogni {n} mesi",
        "yearly": "Ogni anno, il {day} {month}",
        "yearly_n": "Ogni {n} anni, il {day} {month}",
        "day_number": "{day}",
        "at_times": "alle {times}",
        "every_step": "ogni {step}, dalle {from} alle {to}",
        "end_on_date": "fino al {date}",
        "end_after_count": "{n} volte",
        "nth_1": "1º",
        "nth_2": "2º",
        "nth_3": "3º",
        "nth_4": "4º",
        "nth_5": "5º",
        "nth_last": "ultimo",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " e ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "zh-CN": {
        "once": "仅一次，{date}",
        "daily": "每天",
        "daily_n": "每 {n} 天",
        "weekly": "每周 {days}",
        "weekly_all": "每天",
        "weekly_all_n": "每 {n} 周的每天",
        "weekly_workdays": "工作日",
        "weekly_workdays_n": "每 {n} 周的工作日",
        "weekly_weekend": "周末",
        "weekly_weekend_n": "每 {n} 周的周末",
        "weekly_n": "每 {n} 周的 {days}",
        "monthly_day": "每月 {day}",
        "monthly_day_n": "每 {n} 个月的 {day}",
        "monthly_last": "每月最后一天",
        "monthly_last_n": "每 {n} 个月的最后一天",
        "monthly_nth": "每月第 {nth} 个{weekday}",
        "monthly_nth_n": "每 {n} 个月的第 {nth} 个{weekday}",
        "yearly": "每年 {month}{day}",
        "yearly_n": "每 {n} 年的 {month}{day}",
        "day_number": "{day} 日",
        "at_times": "{times}",
        "every_step": "每 {step}，从 {from} 到 {to}",
        "end_on_date": "直到 {date}",
        "end_after_count": "共 {n} 次",
        "nth_1": "1",
        "nth_2": "2",
        "nth_3": "3",
        "nth_4": "4",
        "nth_5": "5",
        "nth_last": "最后一",
        "step_hours": "{n} 小时",
        "step_minutes": "{n} 分钟",
        "list_separator": "、",
        "list_last": "和",
        "clause_join": "，",
        "clause_join_tight": "",
    },
}


def get_recurrence_part(key: str, language: str | None) -> str:
    """One clause of a recurrence sentence, in the reader's language.

    Args:
        key: A key of :data:`RECURRENCE_PARTS`.
        language: Any raw locale — normalized through the single chokepoint.

    Returns:
        The clause, English as the last resort.
    """
    from src.core.i18n import DEFAULT_LANGUAGE, normalize_language

    canonical = normalize_language(language or DEFAULT_LANGUAGE)
    table = RECURRENCE_PARTS.get(canonical, RECURRENCE_PARTS["en"])
    return table.get(key, RECURRENCE_PARTS["en"][key])
