"""What a live session's model costs, read from the tariff table (ADR-300 wave 3).

The live mode runs on the PERSON's own key, so the platform records, accounts
and bills nothing of it (`cost_bearers`) — but a person watching a session
still deserves to see what it is costing THEM. The browser counts the
provider's own usage reports and multiplies them by the rates published here:
the tariff the administrator declared under « LLM pricing », the one authority
the platform has on what a model costs. Indicative by construction, never
persisted.

Two consequences, both the owner's rule (2026-09-19): the models a person may
pick in the Live settings are those DECLARED in the tariff table (a discovered
name with no tariff is named as such, never offered in silence), and a session
on an undeclared model is refused with the same word. « Declared » means the
tariff can price a live session: a time-billed unit, or a token-billed tariff
WITH its audio pair — the text rates alone would leave every turn's cost
unavailable and a spend ceiling unenforceable.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domains.live.schemas import LiveRates
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    get_cached_model_price,
    get_cached_usd_eur_rate,
)

__all__ = ["is_priced", "rates_for", "split_priced"]


def _prices_a_live_session(price: CachedModelPrice) -> bool:
    """Whether a tariff can price a live session: audio is billed, or the unit is time.

    A token-billed tariff without its audio pair could only price the text
    half of a speech-to-speech session — a meter fed by it would under-report
    or say « unavailable » on every turn, and a ceiling set on it could never
    be enforced. Such a model is not DECLARED for the live mode; the
    administrator adds the pair under LLM pricing.
    """
    if price.pricing_unit != "per_1m_tokens":
        return True
    return price.audio_input_unit_price is not None and price.audio_output_unit_price is not None


def rates_for(model: str) -> LiveRates | None:
    """The published rates of a live model, or None when it has no live tariff.

    Args:
        model: The provider model id the session opens on.

    Returns:
        The tariff's rates with the cached USD→EUR rate, or None when the
        pricing cache is cold, the model undeclared, or its tariff unable to
        price a live session (a token-billed tariff without its audio pair).
    """
    price = get_cached_model_price(model)
    if price is None or not _prices_a_live_session(price):
        return None
    return LiveRates(
        pricing_unit=price.pricing_unit,
        input_unit_price=price.input_unit_price,
        output_unit_price=price.output_unit_price,
        audio_input_unit_price=price.audio_input_unit_price,
        audio_output_unit_price=price.audio_output_unit_price,
        usd_eur_rate=get_cached_usd_eur_rate(),
    )


def is_priced(model: str) -> bool:
    """Whether the tariff table declares this model FOR THE LIVE MODE (exact name, else normalised)."""
    return rates_for(model) is not None


def split_priced(names: Iterable[str]) -> tuple[list[str], list[str]]:
    """Partition discovered model names into the declared and the undeclared.

    Args:
        names: What the person's key discovers.

    Returns:
        ``(priced, unpriced)``, each in the input's order.
    """
    priced: list[str] = []
    unpriced: list[str] = []
    for name in names:
        (priced if is_priced(name) else unpriced).append(name)
    return priced, unpriced
