"""Document thumbnails already supplied by Drive must survive presentation."""

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.file_item import FileItem

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "mime", ["application/pdf", "application/vnd.google-apps.document", "image/png"]
)
def test_a_supplied_document_thumbnail_is_a_linked_bounded_preview(mime: str) -> None:
    data = {
        "name": "Report",
        "mimeType": mime,
        "webViewLink": "https://drive.google.com/file/d/report/view",
        "thumbnailLink": "/api/v1/connectors/google-drive/thumbnail/report",
    }
    soup = BeautifulSoup(FileItem().render(data, RenderContext(language="fr")), "html.parser")
    image = soup.select_one(".lia-file__preview img")
    assert image is not None
    assert image["src"] == data["thumbnailLink"]
    assert image["loading"] == "lazy"
    assert image.parent.name == "a"
    assert image.parent["href"] == data["webViewLink"]


@pytest.mark.parametrize("thumbnail", ["javascript:alert(1)", {"url": "https://evil.test"}, ""])
def test_no_unsafe_or_invented_thumbnail(thumbnail: object) -> None:
    soup = BeautifulSoup(
        FileItem().render(
            {"name": "Report", "mimeType": "application/pdf", "thumbnailLink": thumbnail},
            RenderContext(language="fr"),
        ),
        "html.parser",
    )
    assert not soup.select(".lia-file__preview")
