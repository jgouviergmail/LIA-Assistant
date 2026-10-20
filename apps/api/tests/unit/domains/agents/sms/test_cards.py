"""SMS cards have a declared presentation and no attacker-controlled markup."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from uuid import uuid4

import pytest

from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.data_registry.trust import (
    TRUST_BY_REGISTRY_TYPE,
    ContentTrust,
    assert_trust_registry_completeness,
)
from src.domains.agents.display.component_registry import PRESENTATIONS
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.sms_card import SmsCard
from src.domains.agents.tools.output import REGISTRY_TYPE_TO_KEY, assert_registry_key_completeness


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs).get("href"))


@pytest.mark.parametrize(
    "language,url_language",
    [
        ("fr", "fr"),
        ("en", "en"),
        ("de", "de"),
        ("es", "es"),
        ("it", "it"),
        ("zh-CN", "zh"),
        ("zh", "zh"),
        ("zh_CN", "zh"),
        ("zh-TW", "zh"),
        ("fr-FR", "fr"),
        ("en_US", "en"),
        ("de-DE", "de"),
    ],
)
def test_external_text_is_literal_and_only_protected_archive_is_linked(language, url_language):
    message_id = str(uuid4())
    html = SmsCard().render(
        {
            "id": message_id,
            "display_name": "<img src=x onerror=bad()>",
            "sender": "tel:evil",
            "body": "<script>bad()</script> https://evil.test/ $x$",
            "received_at": datetime.now(UTC).isoformat(),
            "date_kind": "captured",
            "origin": "iphone",
            "next_body_offset": 42,
        },
        RenderContext(language=language, timezone="Europe/Paris"),
    )
    parsed = Markup()
    parsed.feed(html)
    assert "script" not in parsed.tags and "img" not in parsed.tags
    assert "&lt;script&gt;" in html
    assert parsed.links == [f"/{url_language}/dashboard/sms?message={message_id}"]
    assert "captured" not in parsed.tags


def test_sms_registry_is_exhaustive_and_external():
    kind = RegistryItemType.SMS
    assert TRUST_BY_REGISTRY_TYPE[kind] is ContentTrust.EXTERNAL
    assert REGISTRY_TYPE_TO_KEY[kind] == "sms_messages"
    assert PRESENTATIONS[kind].component is SmsCard
    assert_trust_registry_completeness()
    assert_registry_key_completeness()


def test_browser_references_are_actual_backend_cards():
    import json
    from pathlib import Path

    rows = json.loads(
        Path(__file__).with_name("card_reference_corpus.json").read_text(encoding="utf-8")
    )
    for row in rows:
        assert (
            SmsCard().render(row["data"], RenderContext(language="fr", timezone="Europe/Paris"))
            == row["html"]
        )
