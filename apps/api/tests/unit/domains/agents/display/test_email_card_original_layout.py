"""A message in the chat opens as the Tools show it (owner, 2026-11-14).

The card keeps the message's text, the one every surface can read (a channel, an export, a reader
whose page cannot open the original), and wraps it in the marker the web chat replaces with the
original layout the Tools draw. The marker names the message by its id, as an attribute value: it
carries no markup of the sender's and changes no word of the text.
"""

from html import unescape

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.email_card import EmailCard

pytestmark = pytest.mark.unit

ORIGINAL = 'class="lia-email-original"'


def _details(data: dict[str, object]) -> str:
    out = EmailCard().render({"subject": "Board meeting", **data}, RenderContext(language="fr"))
    return out.partition("<details")[2]


def test_the_message_s_text_is_wrapped_in_the_marker_naming_it() -> None:
    details = _details({"id": "18c2f0a1b2", "body": "Thursday at 14:00, room Galilée."})

    marker = details.index(ORIGINAL)
    assert 'data-message-id="18c2f0a1b2"' in details[marker : marker + 120]
    assert "Thursday at 14:00, room Galilée." in details[marker:], "the text stays as the fallback"


def test_an_id_is_written_as_an_attribute_value_never_as_markup() -> None:
    hostile = 'x" onclick="alert(1)'
    details = _details({"id": hostile, "body": "Hello"})

    assert 'onclick="alert(1)"' not in details
    marker = details.index(ORIGINAL)
    start = details.index('data-message-id="', marker) + len('data-message-id="')
    assert unescape(details[start : details.index('"', start)]) == hostile


def test_a_message_without_an_id_keeps_its_text_unmarked() -> None:
    details = _details({"body": "Thursday at 14:00."})

    assert ORIGINAL not in details
    assert "Thursday at 14:00." in details


def test_a_message_without_text_carries_no_marker() -> None:
    details = _details({"id": "18c2f0a1b2", "body": "", "snippet": "Short preview"})

    assert ORIGINAL not in details
