"""Selected results stay reachable; one malformed item cannot erase its siblings."""

from html.parser import HTMLParser

import pytest

from src.domains.agents.display.card_collection import render_collection_item
from src.domains.agents.display.components.base import BaseComponent, RenderContext
from src.domains.agents.display.config import DisplayConfig
from src.domains.agents.display.html_renderer import HtmlRenderer

pytestmark = pytest.mark.unit


class _Content(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.folds = 0

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "details":
            self.folds += 1


@pytest.mark.parametrize("multi", [False, True])
def test_every_selected_calendar_is_reachable_beyond_the_initial_visible_limit(multi: bool) -> None:
    items = [{"summary": f"Selected calendar {index:02d}"} for index in range(14)]
    renderer = HtmlRenderer()
    config = DisplayConfig(language="en", max_items_per_domain=3)
    data = {"calendars": items}
    html = (
        renderer.render_multi({"calendars": data}, config)
        if multi
        else renderer.render("calendars", data, config)
    )
    content = _Content()
    content.feed(html)
    for item in items:
        assert item["summary"] in " ".join(content.text)
    assert content.folds == 1
    assert "(11)" in " ".join(content.text)


@pytest.mark.parametrize("multi", [False, True])
def test_a_malformed_calendar_does_not_remove_valid_neighbors(multi: bool) -> None:
    data = {"calendars": [{"summary": "Before"}, None, {"summary": "After"}]}
    renderer = HtmlRenderer()
    config = DisplayConfig(language="en")
    html = (
        renderer.render_multi({"calendars": data}, config)
        if multi
        else renderer.render("calendars", data, config)
    )
    content = _Content()
    content.feed(html)
    assert "Before" in content.text
    assert "After" in content.text
    assert "Some details could not be displayed" in " ".join(content.text)


def test_failed_card_keeps_its_known_identity_without_injecting_markup() -> None:
    class BrokenCard(BaseComponent):
        def render(
            self,
            data: dict[str, object],
            ctx: RenderContext,
            *,
            is_first_item: bool = True,
            is_last_item: bool = True,
        ) -> str:
            raise ValueError("Unusable upstream field")

    title = "<script>Known message</script>"
    html = render_collection_item(BrokenCard(), {"subject": title}, RenderContext(language="en"))
    content = _Content()
    content.feed(html)
    assert title in " ".join(content.text)
    assert "Some details could not be displayed" in " ".join(content.text)
    assert "<script>" not in html
