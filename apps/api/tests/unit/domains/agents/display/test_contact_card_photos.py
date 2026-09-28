"""Contact photos keep their frame through the frontend Markdown renderer.

The shared corpus is consumed by Vitest and Playwright. Pinning it to the real
renderer prevents a hand-written browser fixture from hiding broken API HTML.
"""

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import TypedDict

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.contact_card import ContactCard

pytestmark = pytest.mark.unit


class _ContactCase(TypedDict):
    id: str
    data: dict[str, object]
    html: str


CORPUS: list[_ContactCase] = json.loads(
    Path(__file__).with_name("contact_card_corpus.json").read_text(encoding="utf-8")
)


class _Images(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            self.images.append(dict(attrs))


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case["id"])
def test_contact_photo_corpus_matches_renderer(case: _ContactCase) -> None:
    rendered = ContactCard().render(case["data"], RenderContext(language="fr"), with_wrapper=False)
    assert rendered == case["html"]
    images = _Images()
    images.feed(rendered)
    if case["id"] == "initials":
        assert not images.images
        assert ">LD</span>" in rendered
    else:
        assert len(images.images) == 1
        # MarkdownImage preserves structured images only when they opt into
        # the lia-* component contract. It does not forward inline dimensions.
        assert images.images[0]["class"] == "lia-illus__image"
        assert images.images[0]["alt"] == ""
        assert "style" not in images.images[0]
