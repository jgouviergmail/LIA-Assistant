"""Central i18n of a condition routine's clock (ADR-322).

A routine that waits for something has no schedule: the system checks it. The
sentence the studio card, the hub and the chat's listing show in place of a
schedule states that clock — the interval travels as a figure the caller
supplies from settings, never written in the text (ADR-184).

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


def condition_cadence(language: str, *, minutes: int) -> str:
    """The sentence stating how often a condition routine is checked.

    Args:
        language: The reader's language, raw (normalised here).
        minutes: The effective check interval.

    Returns:
        The translated sentence, the interval in it.
    """
    return CONDITION_CADENCE[normalize_language(language)].format(minutes=minutes)
