"""The words of a fired reminder's postponement (ADR-268 amendment 2026-11-16).

Read where the SERVER writes them: the two actions a web push draws (a service
worker has no translation of its own) and Telegram's buttons and the answers to
their presses. The chat bubble draws the same words from the web's locales.

Every table holds exactly the six canonical languages (guarded); a duration is
said in whole hours when it is one, in minutes otherwise.
"""

from __future__ import annotations

from src.core.i18n import resolve_language
from src.core.i18n_types import Language

#: « In N min » and « In N h », the two delays a notification offers.
_IN_MINUTES: dict[Language, str] = {
    "fr": "Dans {n} min",
    "en": "In {n} min",
    "es": "En {n} min",
    "de": "In {n} Min.",
    "it": "Tra {n} min",
    "zh-CN": "{n} 分钟后",
}
_IN_HOURS: dict[Language, str] = {
    "fr": "Dans {n} h",
    "en": "In {n} h",
    "es": "En {n} h",
    "de": "In {n} Std.",
    "it": "Tra {n} h",
    "zh-CN": "{n} 小时后",
}

#: The two buttons that are not a duration.
_BUTTONS: dict[str, dict[Language, str]] = {
    "morning": {
        "fr": "Demain matin",
        "en": "Tomorrow morning",
        "es": "Mañana por la mañana",
        "de": "Morgen früh",
        "it": "Domani mattina",
        "zh-CN": "明天早上",
    },
    "stop": {
        "fr": "Arrêter ce rappel",
        "en": "Stop this reminder",
        "es": "Detener este recordatorio",
        "de": "Erinnerung beenden",
        "it": "Interrompi il promemoria",
        "zh-CN": "停止此提醒",
    },
}

#: What a press did, said above the Telegram chat. ``{when}`` is a stamp in the
#: person's zone (``format_short_stamp``: « le 16/11 à 15:40 »).
_ANSWERS: dict[str, dict[Language, str]] = {
    "snoozed": {
        "fr": "C'est noté : je te le rappelle {when}.",
        "en": "Noted: I'll remind you {when}.",
        "es": "Anotado: te lo recuerdo {when}.",
        "de": "Notiert: Ich erinnere dich {when}.",
        "it": "Fatto: te lo ricordo {when}.",
        "zh-CN": "好的：我会在{when}再提醒你。",
    },
    "already_snoozed": {
        "fr": "Déjà reporté : je te le rappelle {when}.",
        "en": "Already postponed: I'll remind you {when}.",
        "es": "Ya aplazado: te lo recuerdo {when}.",
        "de": "Schon verschoben: Ich erinnere dich {when}.",
        "it": "Già rimandato: te lo ricordo {when}.",
        "zh-CN": "已经推迟：我会在{when}再提醒你。",
    },
    "expired": {
        "fr": "Trop tard pour le reporter : demande-moi un nouveau rappel.",
        "en": "Too late to postpone it: ask me for a new reminder.",
        "es": "Demasiado tarde para aplazarlo: pídeme un nuevo recordatorio.",
        "de": "Zu spät zum Verschieben: Bitte mich um eine neue Erinnerung.",
        "it": "Troppo tardi per rimandarlo: chiedimi un nuovo promemoria.",
        "zh-CN": "已无法推迟：请让我设置一个新的提醒。",
    },
    "collides": {
        "fr": "Ce rappel revient déjà {when} : choisis un report plus court.",
        "en": "This reminder already comes back {when}: choose a shorter delay.",
        "es": "Este recordatorio ya vuelve {when}: elige un aplazamiento más corto.",
        "de": "Diese Erinnerung kommt schon {when} wieder: Wähle eine kürzere Verschiebung.",
        "it": "Questo promemoria torna già {when}: scegli un rinvio più breve.",
        "zh-CN": "这个提醒会在{when}再次出现：请选择更短的推迟时间。",
    },
    "stopped": {
        "fr": "Rappel arrêté : ses prochaines dates sont supprimées.",
        "en": "Reminder stopped: its upcoming dates are removed.",
        "es": "Recordatorio detenido: se eliminan sus próximas fechas.",
        "de": "Erinnerung beendet: Ihre künftigen Termine sind entfernt.",
        "it": "Promemoria interrotto: le sue prossime date sono rimosse.",
        "zh-CN": "提醒已停止：之后的日期已删除。",
    },
    "already_stopped": {
        "fr": "Ce rappel n'a déjà plus de prochaine date.",
        "en": "This reminder already has no upcoming date.",
        "es": "Este recordatorio ya no tiene próximas fechas.",
        "de": "Diese Erinnerung hat schon keine künftigen Termine mehr.",
        "it": "Questo promemoria non ha già più date future.",
        "zh-CN": "这个提醒已经没有之后的日期了。",
    },
    "gone": {
        "fr": "Ce rappel n'est plus disponible.",
        "en": "This reminder is no longer available.",
        "es": "Este recordatorio ya no está disponible.",
        "de": "Diese Erinnerung ist nicht mehr verfügbar.",
        "it": "Questo promemoria non è più disponibile.",
        "zh-CN": "这个提醒已不可用。",
    },
}


def snooze_delay_label(minutes: int, language: str | None) -> str:
    """« In 10 min », « In 1 h »: a delay as a button says it.

    Args:
        minutes: The delay.
        language: The reader's language, any spelling (the declared one if None).

    Returns:
        The label, in whole hours when the delay is one.
    """
    code = resolve_language(language)
    if minutes % 60 == 0:
        return _IN_HOURS[code].format(n=minutes // 60)
    return _IN_MINUTES[code].format(n=minutes)


def snooze_button_label(button: str, language: str | None) -> str:
    """The label of « tomorrow morning » (``morning``) or « stop » (``stop``).

    Raises:
        KeyError: A button no surface draws.
    """
    return _BUTTONS[button][resolve_language(language)]


def snooze_press_answer(outcome: str, language: str | None, *, when: str = "") -> str:
    """What a press did, as a sentence.

    Args:
        outcome: A ``SnoozeOutcome`` or ``StopOutcome`` value, or ``gone``.
        language: The reader's language.
        when: The stamp the sentence names, for the outcomes that carry one.

    Raises:
        KeyError: An outcome no press produces.
    """
    return _ANSWERS[outcome][resolve_language(language)].format(when=when)


__all__ = ["snooze_button_label", "snooze_delay_label", "snooze_press_answer"]
