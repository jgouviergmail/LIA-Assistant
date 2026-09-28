"""The destructive confirmation's item list closes on its language's own words."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.services.hitl.interactions.destructive_confirm import (
    DestructiveConfirmInteraction,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
def test_items_past_five_close_on_the_language_s_own_and_more(language: str) -> None:
    """The line read « - ... and 2 more… »: two ellipses, the first in ASCII."""
    interaction = DestructiveConfirmInteraction(question_generator=Mock())

    message = interaction._build_warning_message(
        operation_type="delete_emails",
        affected_count=7,
        affected_items=[{"subject": f"Mail {i}"} for i in range(7)],
        custom_warning=None,
        user_language=language,
    )

    and_more = HitlMessages.get_destructive_confirm_translations(language)["and_more"]
    assert f"- {and_more.format(count=2)}\n" in message
    assert "..." not in message
    # The five it shows are the first five, each on its own line.
    for index in range(5):
        assert f"- Mail {index}\n" in message
    assert "Mail 5" not in message


@pytest.mark.parametrize(
    ("language", "unnamed"),
    [
        ("fr", "élément sans nom"),
        ("en", "unnamed item"),
        ("es", "elemento sin nombre"),
        ("de", "Element ohne Namen"),
        ("it", "elemento senza nome"),
        ("zh-CN", "未命名项目"),
    ],
)
def test_an_item_with_nothing_readable_is_named_in_the_reader_s_language(
    language: str, unnamed: str
) -> None:
    """It read its id cut at 50 characters, or « item » in every language."""
    interaction = DestructiveConfirmInteraction(question_generator=Mock())

    preview = interaction._format_item_preview({"id": "x" * 80}, user_language=language)

    assert preview == unnamed


@pytest.mark.parametrize(
    ("item", "named"),
    [
        ({"subject": None, "name": "Budget"}, "Budget"),
        ({"subject": "   ", "title": "Relance"}, "Relance"),
        ({"subject": None}, "unnamed item"),
    ],
    ids=["none_then_name", "blank_then_title", "none_alone"],
)
def test_a_field_that_says_nothing_names_nothing(item: dict[str, object], named: str) -> None:
    """A readable key present with None read « None », in English, in six languages."""
    interaction = DestructiveConfirmInteraction(question_generator=Mock())

    assert interaction._format_item_preview(item, user_language="en") == named


@pytest.mark.parametrize("empty", [[], {}, False, 0], ids=["list", "dict", "false", "zero"])
def test_an_empty_value_names_nothing(empty: object) -> None:
    """« [] », « False », « 0 » read as a name — « False » in English, in six languages."""
    interaction = DestructiveConfirmInteraction(question_generator=Mock())

    item = {"subject": empty, "name": "Bob"}
    assert interaction._format_item_preview(item, user_language="en") == "Bob"


@pytest.mark.parametrize(
    ("item", "named"),
    [
        ({"subject": "Facture", "name": "Budget"}, "Facture"),
        ({"name": "Budget", "summary": "Point"}, "Budget"),
        ({"summary": "Point", "title": "Relance"}, "Point"),
        ({"title": "Relance", "displayName": "Ada"}, "Relance"),
        ({"displayName": "Ada"}, "Ada"),
    ],
    ids=["subject_first", "then_name", "then_summary", "then_title", "then_display_name"],
)
def test_an_item_is_named_by_its_first_readable_field(item: dict[str, object], named: str) -> None:
    interaction = DestructiveConfirmInteraction(question_generator=Mock())

    assert interaction._format_item_preview(item, user_language="en") == named
