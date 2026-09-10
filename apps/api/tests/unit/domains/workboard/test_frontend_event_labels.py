"""Every history event kind the board writes has a name on screen.

The panel renders ``t('workboard.events.<kind>')`` and i18next falls back to
the key itself, so a kind added on the backend alone would show a raw
``workboard.events.something`` to every reader in every language, with the
i18n parity gate green — parity proves the six locales agree with each other,
never that a key exists.

Six wordings are DERIVED rather than kinds: the release path and a run's
hand-back both write an ``assigned`` event, and the panel tells a hand-over
from the three ways a ticket comes back — a peer returns it, LIA's run returns
it, a connection ends — from the payload (``eventLabelKey`` in
``lib/workboard/display.ts``), as it tells the three answers to a
confirmation (lot 7). They are declared here so the orphan check knows them,
and a wording nobody derives any more cannot survive as a string nobody can
read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.workboard.constants import TicketEventKind

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
WEB_LOCALES = Path(__file__).resolve().parents[5] / "web" / "locales"

#: Wordings the panel derives from an event's payload: the three ways a ticket
#: comes back to its owner (a peer, LIA's run — lot 15 —, a connection that
#: ended), and the three answers to a confirmation (lot 7).
DERIVED_WORDINGS = frozenset(
    {"returned", "returned_by_run", "released", "approved", "amended", "refused"}
)


def _events_block(language: str) -> dict[str, str]:
    path = WEB_LOCALES / language / "translation.json"
    return json.loads(path.read_text(encoding="utf-8"))["workboard"]["events"]


class TestTheFrontendCanNameEveryEvent:
    def test_the_locale_files_are_where_this_test_thinks(self) -> None:
        assert (WEB_LOCALES / "en" / "translation.json").is_file()

    @pytest.mark.parametrize("language", LOCALES)
    def test_every_kind_has_a_wording(self, language: str) -> None:
        block = _events_block(language)
        missing = sorted(
            kind.value for kind in TicketEventKind if not block.get(kind.value, "").strip()
        )

        assert (
            not missing
        ), f"{language}: event kinds the panel would show by their raw key: {missing}"

    @pytest.mark.parametrize("language", LOCALES)
    def test_every_derived_wording_exists(self, language: str) -> None:
        block = _events_block(language)
        missing = sorted(key for key in DERIVED_WORDINGS if not block.get(key, "").strip())

        assert (
            not missing
        ), f"{language}: derived wordings the panel resolves to a raw key: {missing}"

    def test_no_wording_survives_a_kind_that_left(self) -> None:
        known = {kind.value for kind in TicketEventKind} | DERIVED_WORDINGS
        orphans = sorted(key for key in _events_block("en") if key not in known)

        assert not orphans, f"wordings for events the board never writes: {orphans}"
