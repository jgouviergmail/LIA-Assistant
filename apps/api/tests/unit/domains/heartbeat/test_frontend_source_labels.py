"""Every heartbeat source the API publishes has a name on screen.

The i18n gate proves the six locales agree with each other; it cannot know
that a key exists at all. The panel renders ``t('heartbeat.source_<key>')`` for
whatever ``HEARTBEAT_SOURCE_ORDER`` publishes, and i18next falls back to the
key itself — so a source added on the backend alone puts a raw
``heartbeat.source_workboard`` in front of a reader, in every language at once,
with every gate green.

Same shape as the workboard's own vocabulary guard (lot 4): the backend owns
the vocabulary, so the backend is where the frontend is held to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_ORDER

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
WEB_LOCALES = Path(__file__).resolve().parents[5] / "web" / "locales"


def _heartbeat_block(language: str) -> dict[str, str]:
    path = WEB_LOCALES / language / "translation.json"
    return json.loads(path.read_text(encoding="utf-8"))["heartbeat"]


class TestTheFrontendCanNameEverySource:
    def test_the_locale_files_are_where_this_test_thinks(self) -> None:
        """A guard reading nothing passes for the wrong reason."""
        assert (WEB_LOCALES / "en" / "translation.json").is_file()

    @pytest.mark.parametrize("language", LOCALES)
    def test_every_published_source_has_a_label(self, language: str) -> None:
        labels = _heartbeat_block(language)
        missing = sorted(
            key for key in HEARTBEAT_SOURCE_ORDER if not labels.get(f"source_{key}", "").strip()
        )

        assert (
            not missing
        ), f"{language}: sources the settings panel would name by their raw key: {missing}"

    def test_no_label_survives_a_source_that_left(self) -> None:
        """Shrink-only in the other direction: a label with no source is a
        string nobody can ever read, and the next reader takes it for a
        feature."""
        published = {f"source_{key}" for key in HEARTBEAT_SOURCE_ORDER}
        # Only the per-source labels are compared; the panel's own wordings
        # (`source_not_connected`, `source_requires`) are not sources.
        orphans = sorted(
            key
            for key in _heartbeat_block("en")
            if key.startswith("source_")
            and key not in published
            and key not in {"source_not_connected", "source_requires"}
        )

        assert not orphans, f"labels for sources the API never publishes: {orphans}"
