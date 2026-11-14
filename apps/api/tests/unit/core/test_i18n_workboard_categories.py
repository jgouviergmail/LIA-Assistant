"""A person is sent to their categories in the words their own screen shows (ADR-276).

``list_ticket_categories_tool`` tells the model WHERE categories are created,
renamed, reordered and deleted: a page of the application's menu and a button
of that page. The web draws both labels from its locale files; the backend
restates them under its own canonical codes, because a tool cannot read a
frontend file at run time. A label renamed on one side only would send the
person looking for a button their screen does not show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.core.config import settings
from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_workboard_categories import (
    WORKBOARD_CATEGORY_PLACES,
    workboard_category_place,
)

pytestmark = pytest.mark.unit

#: The web's locale codes (``zh`` there, ``zh-CN`` in the backend).
WEB_LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[4] / "web"

#: The key each label is drawn from, and the source file that draws it. A
#: guard comparing against a key the screen stopped using would stay green
#: while the person reads another word.
_PAGE_KEY = "navigation.workboard"
_BUTTON_KEY = "workboard.categories.manage"
_DRAWN_BY = {
    _PAGE_KEY: ("src/lib/dashboard-nav.ts", f"labelKey: '{_PAGE_KEY}'"),
    _BUTTON_KEY: ("src/components/workboard/WorkboardPage.tsx", f"t('{_BUTTON_KEY}')"),
}


def _web_label(locale: str, key: str) -> str:
    node: Any = json.loads(
        (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    )
    for part in key.split("."):
        node = node[part]
    return str(node)


@pytest.mark.parametrize("locale", WEB_LOCALES)
def test_the_page_is_named_as_the_menu_names_it(locale: str) -> None:
    assert workboard_category_place(locale).page == _web_label(locale, _PAGE_KEY)


@pytest.mark.parametrize("locale", WEB_LOCALES)
def test_the_button_is_named_as_the_board_labels_it(locale: str) -> None:
    assert workboard_category_place(locale).button == _web_label(locale, _BUTTON_KEY)


@pytest.mark.parametrize("key", sorted(_DRAWN_BY))
def test_the_screen_still_draws_the_label_from_the_key_compared(key: str) -> None:
    source, call = _DRAWN_BY[key]

    assert call in (_WEB / source).read_text(encoding="utf-8"), (
        f"{source} no longer draws {key}: find the key the screen draws now, "
        "and hold the backend's table to that one"
    )


def test_the_table_speaks_the_backend_vocabulary() -> None:
    assert set(WORKBOARD_CATEGORY_PLACES) == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("spelling", ["zh", "zh-CN", "zh_CN", "ZH-cn"])
def test_any_spelling_of_chinese_reads_the_one_place(spelling: str) -> None:
    """A stored language goes through ``normalize_language``: a ``zh`` account
    must not fall off the table (ADR-323)."""
    assert workboard_category_place(spelling) == WORKBOARD_CATEGORY_PLACES["zh-CN"]


@pytest.mark.parametrize("language", [None, "", "pt-BR"])
def test_an_absent_or_unsupported_language_reads_the_instance_default(
    language: str | None,
) -> None:
    """Never an error: the tool that asks runs inside a turn."""
    assert (
        workboard_category_place(language) == WORKBOARD_CATEGORY_PLACES[settings.default_language]
    )


def test_no_label_is_left_empty() -> None:
    """An empty label would make the sentence point at « the '' button »."""
    assert all(
        place.page.strip() and place.button.strip() for place in WORKBOARD_CATEGORY_PLACES.values()
    )
