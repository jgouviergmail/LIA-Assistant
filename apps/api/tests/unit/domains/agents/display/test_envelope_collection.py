"""Compact envelope presentation preserves every selected message and binding."""

import pytest

from src.core.constants import HTML_EMAIL_VISIBLE_MESSAGES
from src.domains.agents.display.config import DisplayConfig
from src.domains.agents.display.html_renderer import HtmlRenderer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize("requested", [1, 10])
def test_envelope_fold_keeps_every_message_and_exact_remainder(multi: bool, requested: int) -> None:
    count = HTML_EMAIL_VISIBLE_MESSAGES + 7
    items = [
        {
            "subject": f"Envelope {index:02d}",
            "from": "Sender <sender@example.test>",
            "snippet": f"Received excerpt {index:02d}",
            "body": f"Complete body {index:02d}",
            "_lia_card_ref": f"message-{index}",
        }
        for index in range(count)
    ]
    config = DisplayConfig(language="en", max_items_per_domain=requested)
    renderer = HtmlRenderer()
    data = {"emails": items}
    html = (
        renderer.render_multi({"emails": data}, config)
        if multi
        else renderer.render("emails", data, config)
    )
    initial, remainder = html.split('<details class="lia-card-collection"', maxsplit=1)
    visible = min(requested, HTML_EMAIL_VISIBLE_MESSAGES)
    for index in range(count):
        assert f"Envelope {index:02d}" in (initial if index < visible else remainder)
        assert f"Complete body {index:02d}" in html
        assert f'data-card-ref="message-{index}"' in html
    assert f"({count - visible})" in remainder


def test_other_families_keep_their_existing_initial_limit() -> None:
    count = HTML_EMAIL_VISIBLE_MESSAGES + 2
    items = [{"summary": f"Calendar {index}"} for index in range(count)]
    html = HtmlRenderer().render(
        "calendars", {"calendars": items}, DisplayConfig(language="en", max_items_per_domain=count)
    )
    assert 'class="lia-card-collection"' not in html
    for index in range(count):
        assert f"Calendar {index}" in html
