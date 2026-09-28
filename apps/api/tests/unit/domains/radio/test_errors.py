"""Every refusal the radio's API sends is told in the reader's words (ADR-324).

The API names a refusal with a stable ``detail.code`` and the web translates it.
A code added here without its sentence would reach a listener as a generic
« could not » in six languages at once, with every gate green — so the pair is
pinned both ways: each code has its sentence in every locale, and the start
refusals the player's banner knows are exactly the ones a start raises.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.radio import errors
from src.domains.radio.errors import START_REFUSALS, refuse
from src.domains.radio.newsroom.sources import DiscoveryOutcome

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"
_ERRORS_MODULE = _WEB / "src" / "lib" / "radio" / "errors.ts"

#: Every code the module can send (its status table is the one vocabulary).
CODES = sorted(errors._STATUSES)


def _translations(locale: str) -> dict[str, Any]:
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    return dict(json.loads(raw))


def _sentence_keys(code: str) -> list[str]:
    """The locale keys a code is told with, as ``lib/radio/errors.ts`` reads them."""
    if code == errors.SOURCE_REFUSED:
        # Told by what looking for the feed found — never « found ».
        return [
            f"radio.settings.sites.outcome.{outcome.value}"
            for outcome in DiscoveryOutcome
            if outcome is not DiscoveryOutcome.FOUND
        ]
    if code == errors.SOURCE_LIMIT:
        # Plural-aware: the sentence counts the sites.
        return [f"radio.errors.{code}_one", f"radio.errors.{code}_other"]
    return [f"radio.errors.{code}"]


def _resolve(tree: dict[str, Any], dotted: str) -> object:
    node: object = tree
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


@pytest.mark.parametrize("locale", LOCALES)
def test_every_refusal_has_its_sentence(locale: str) -> None:
    tree = _translations(locale)
    missing = [
        key
        for code in CODES
        for key in _sentence_keys(code)
        if not str(_resolve(tree, key) or "").strip()
    ]
    assert not missing, f"{locale}: refusals the API sends and nobody can read: {missing}"


def test_the_player_knows_every_start_refusal() -> None:
    """The banner tells a start refusal by its code: the web's list is the API's."""
    source = _ERRORS_MODULE.read_text(encoding="utf-8")
    block = re.search(r"RADIO_START_REFUSALS = \[(.*?)\] as const", source, re.DOTALL)
    assert block is not None, "lib/radio/errors.ts no longer declares RADIO_START_REFUSALS"
    assert set(re.findall(r"'([a-z_]+)'", block.group(1))) == set(START_REFUSALS.values())


def test_a_refusal_carries_its_code_and_the_bound_beside_it() -> None:
    with pytest.raises(BaseAPIException) as refused:
        refuse(errors.TIMER_TOO_LONG, max_minutes=240)

    assert refused.value.detail == {"code": errors.TIMER_TOO_LONG, "max_minutes": 240}
    assert refused.value.status_code == 422
