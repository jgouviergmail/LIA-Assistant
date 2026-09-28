"""A binary Drive file's card names it in its reader's language (ADR-323).

The Drive tool used to write a SENTENCE into the item's ``content`` — French for
everyone, then English for everyone — and the card showed it as the file's
preview. The payload now carries ``content_type="binary"`` alone, and the card
writes the line from the type, in the language it renders in.
"""

from __future__ import annotations

import pytest

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.file_item import FileItem

pytestmark = pytest.mark.unit

_BINARY = {"name": "scan.pdf", "mimeType": "application/pdf", "content_type": "binary"}


@pytest.mark.parametrize("language", ["fr", "de", "zh-CN"])
def test_a_binary_file_is_named_in_the_readers_language(language: str) -> None:
    html = FileItem().render(_BINARY, RenderContext(language=language), with_wrapper=False)

    assert escape_html(V3Messages.get_binary_content(language)) in html
    assert "Binary content" not in html


def test_a_text_file_still_shows_its_own_content() -> None:
    data = {"name": "notes.txt", "mimeType": "text/plain", "content": "Buy milk"}

    html = FileItem().render(data, RenderContext(language="fr"), with_wrapper=False)

    assert "Buy milk" in html
    assert escape_html(V3Messages.get_binary_content("fr")) not in html
