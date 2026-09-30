"""Every refusal of a skill proposal's card is told in the reader's words (ADR-327).

The API names a refusal with a stable ``detail.code`` and the card translates it
(``lib/skill-proposals/errors.ts``). A code added here without its sentence would
reach the reader as the card's generic sentence in six languages at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.skills.proposal_errors import STATUSES

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_refusal_has_its_sentence(locale: str) -> None:
    tree = json.loads((_WEB / "locales" / locale / "translation.json").read_text("utf-8"))
    errors = tree["chat"]["skill_proposal"]["errors"]
    missing = [code for code in sorted(STATUSES) if not str(errors.get(code) or "").strip()]
    assert not missing, f"{locale}: refusals the API sends and nobody can read: {missing}"
    extra = sorted(set(errors) - set(STATUSES))
    assert not extra, f"{locale}: sentences for codes the API never sends: {extra}"


def test_the_web_reads_exactly_the_codes_the_api_sends() -> None:
    module = (_WEB / "src" / "lib" / "skill-proposals" / "errors.ts").read_text("utf-8")
    unread = [code for code in STATUSES if f"'{code}'" not in module]
    assert not unread, f"codes the web does not map: {unread}"
