"""Central i18n of the clocks a routine runs on when it has no schedule.

A routine that waits for something has no schedule: the system checks it
(ADR-322). The sentence the studio card, the hub and the chat's listing show in
place of a schedule states that clock — the interval travels as a figure the
caller supplies from settings, never written in the text (ADR-184). A routine
another system starts has no schedule either: its sentence says so (ADR-386).

Six supported languages, keyed by the backend-canonical code (``zh-CN``);
``normalize_language`` from ``core.i18n`` is the only entry point for raw
locale strings. Data module (like the other ``core/i18n_*``): no domain
imports, exempt from the size ratchet.
"""

from __future__ import annotations

from src.core.i18n import normalize_language
from src.core.i18n_types import Language

#: ``{minutes}`` is the effective check interval. Keyed by EVERY canonical
#: code (a test holds the keys equal to ``Language``), so the lookup needs no
#: fallback: ``normalize_language`` always answers one of them.
CONDITION_CADENCE: dict[Language, str] = {
    "en": "Checked about every {minutes} min",
    "fr": "Vérifiée environ toutes les {minutes} min",
    "de": "Etwa alle {minutes} Min. geprüft",
    "es": "Se comprueba cada {minutes} min aprox.",
    "it": "Verificata circa ogni {minutes} min",
    "zh-CN": "约每 {minutes} 分钟检查一次",
}


#: What starts a webhook routine (ADR-386): no schedule, no check — a call.
WEBHOOK_TRIGGER: dict[Language, str] = {
    "en": "Started by a signed call to its address",
    "fr": "Démarrée par un appel signé à son adresse",
    "de": "Durch einen signierten Aufruf ihrer Adresse gestartet",
    "es": "Se inicia con una llamada firmada a su dirección",
    "it": "Avviata da una chiamata firmata al suo indirizzo",
    "zh-CN": "由对其地址的签名调用启动",
}


def webhook_trigger(language: str) -> str:
    """The sentence stating what starts a webhook routine.

    Args:
        language: The reader's language, raw (normalised here).

    Returns:
        The translated sentence.
    """
    return WEBHOOK_TRIGGER[normalize_language(language)]


def condition_cadence(language: str, *, minutes: int) -> str:
    """The sentence stating how often a condition routine is checked.

    Args:
        language: The reader's language, raw (normalised here).
        minutes: The effective check interval.

    Returns:
        The translated sentence, the interval in it.
    """
    return CONDITION_CADENCE[normalize_language(language)].format(minutes=minutes)
