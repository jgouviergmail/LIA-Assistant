"""Every register vocabulary the journal renders must have a sentence.

The readable registers are a compliance surface: a person exercising an
Article-12 right reads them, and so does an auditor. Two of its labels are
resolved by TEMPLATED key — ``effects.journal.source.<source>`` and
``effects.journal.status.<status>`` — and neither carries a default, unlike the
treatments journal beside them. A member the locales never learnt therefore
renders as the raw i18n KEY, in all six languages, on the one screen whose
whole purpose is to be legible.

Same contract, and same failure mode, as
``workboard/test_frontend_error_keys.py``: a vocabulary the backend owns and
the frontend words is a two-table fact, and only a guard keeps the two tables
in step. This one covers the two register families that had none.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.agents.effects.models import EffectSource, EffectStatus
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

#: The six languages the repo ships, backend-canonical spelling aside: these
#: are the frontend locale DIRECTORIES, where Chinese is ``zh``.
LOCALES = ("en", "fr", "de", "es", "it", "zh")

#: Keys the journal declares that no backend member produces, with the reason.
#: Shrink-only in spirit: an entry leaves when the vocabulary grows into it.
NOT_A_BACKEND_MEMBER: dict[str, str] = {
    "all": "the filter's « any status » option, produced by the select and never by a row",
}


def _journal_table(locale: str, table: str) -> dict[str, str]:
    """One locale's table under ``effects.journal``.

    Args:
        locale: Frontend locale directory name.
        table: ``source`` or ``status``.

    Returns:
        The table, or an empty dict when the locale omits it entirely.
    """
    root = repo_root_or_skip()
    path = Path(root) / "apps" / "web" / "locales" / locale / "translation.json"
    if not path.exists():  # pragma: no cover - the frontend tree is absent
        pytest.skip("apps/web is not checked out beside apps/api")
    payload = json.loads(path.read_text(encoding="utf-8"))
    section = payload.get("effects", {}).get("journal", {}).get(table, {})
    return section if isinstance(section, dict) else {}


@pytest.mark.parametrize("locale", LOCALES)
class TestEverySourceHasASentence:
    def test_no_source_renders_as_a_raw_key(self, locale: str) -> None:
        declared = set(_journal_table(locale, "source"))
        missing = sorted(member.value for member in EffectSource if member.value not in declared)
        assert not missing, (
            f"{locale}: EffectSource members the journal cannot say: {missing} — "
            "add each under effects.journal.source, or the screen prints the key"
        )

    def test_the_locale_declares_no_source_the_backend_never_writes(self, locale: str) -> None:
        known = {member.value for member in EffectSource} | set(NOT_A_BACKEND_MEMBER)
        extra = sorted(key for key in _journal_table(locale, "source") if key not in known)
        assert not extra, f"{locale}: sources no row can carry: {extra}"


@pytest.mark.parametrize("locale", LOCALES)
class TestEveryStatusHasASentence:
    def test_no_status_renders_as_a_raw_key(self, locale: str) -> None:
        declared = set(_journal_table(locale, "status"))
        missing = sorted(member.value for member in EffectStatus if member.value not in declared)
        assert not missing, (
            f"{locale}: EffectStatus members the journal cannot say: {missing} — "
            "add each under effects.journal.status, or the screen prints the key"
        )

    def test_the_locale_declares_no_status_the_backend_never_writes(self, locale: str) -> None:
        known = {member.value for member in EffectStatus} | set(NOT_A_BACKEND_MEMBER)
        extra = sorted(key for key in _journal_table(locale, "status") if key not in known)
        assert not extra, f"{locale}: statuses no row can carry: {extra}"


def test_every_exemption_carries_a_written_reason() -> None:
    """A guard whose exemptions are unexplained is a guard nobody can audit."""
    unexplained = sorted(key for key, why in NOT_A_BACKEND_MEMBER.items() if len(why.strip()) < 20)
    assert not unexplained, f"exemptions with no reason: {unexplained}"
