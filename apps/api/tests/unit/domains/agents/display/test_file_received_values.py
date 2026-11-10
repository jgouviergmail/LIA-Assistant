"""A malformed optional Drive field cannot invent a fact or hide valid siblings."""

import pytest
from bs4 import BeautifulSoup

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.file_item import FileItem

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", ["false", "true", 1, [], {"raw": "PRIVATE_TREE"}])
def test_file_badges_require_a_real_boolean(value: object) -> None:
    soup = BeautifulSoup(
        FileItem().render(
            {"name": "Report", "shared": value, "starred": value},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert V3Messages.get_shared("en") not in soup.get_text()
    assert V3Messages.get_favorite("en") not in soup.get_text()
    assert "PRIVATE_TREE" not in soup.get_text()


@pytest.mark.parametrize(
    "size",
    [True, -1, "-1", "1.5", float("inf"), float("nan"), {"raw": "PRIVATE_TREE"}, 10**5000],
    ids=["boolean", "negative", "negative-string", "fraction", "infinite", "nan", "tree", "huge"],
)
def test_invalid_file_size_never_prevents_reading_other_received_facts(size: object) -> None:
    soup = BeautifulSoup(
        FileItem().render(
            {
                "title": {"raw": "PRIVATE_TITLE"},
                "name": "Actual report",
                "mimeType": ["application/pdf"],
                "size": size,
                "description": "RECEIVED_DESCRIPTION",
                "webViewLink": "https://source.example.test/report",
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "Actual report" in soup.get_text() and "RECEIVED_DESCRIPTION" in soup.get_text()
    assert soup.find("a", href="https://source.example.test/report") is not None
    assert "PRIVATE_" not in soup.get_text()
    assert "straighten" not in soup.get_text()


@pytest.mark.parametrize("size", [0, "0"])
def test_zero_file_size_is_a_received_measurement(size: object) -> None:
    markup = FileItem().render({"name": "Empty", "size": size}, RenderContext(language="en"))
    assert f"0 {V3Messages.get_size_unit('en', 'b')}" in markup
