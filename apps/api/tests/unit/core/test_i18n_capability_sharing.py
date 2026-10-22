"""The recipient's line for a shared skill, MCP server or plugin.

It must say WHO shared WHICH KIND of capability and its TITLE, in every
backend-canonical language, for every kind a transfer can carry — and still
name someone when the sender's account is gone.
"""

from typing import get_args

import pytest

from src.core.capability_origin import CapabilityOriginKind
from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_capability_sharing import _BODIES, capability_shared_body

pytestmark = pytest.mark.unit

KINDS: tuple[str, ...] = get_args(CapabilityOriginKind)

#: How each language names each kind, as the settings sections title them.
KIND_WORDS: dict[str, dict[str, str]] = {
    "skill": {
        "fr": "compétence",
        "en": "skill",
        "es": "competencia",
        "de": "Kompetenz",
        "it": "competenza",
        "zh-CN": "技能",
    },
    "mcp": {
        "fr": "serveur MCP",
        "en": "MCP server",
        "es": "servidor MCP",
        "de": "MCP-Server",
        "it": "server MCP",
        "zh-CN": "MCP 服务器",
    },
    "plugin": {
        "fr": "plugin",
        "en": "plugin",
        "es": "plugin",
        "de": "Plugin",
        "it": "plugin",
        "zh-CN": "插件",
    },
}


def test_every_transfer_kind_has_a_line_in_every_language() -> None:
    assert set(_BODIES) == set(KINDS)
    for kind in KINDS:
        assert set(_BODIES[kind]) == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_line_names_the_sender_the_kind_and_the_title(kind: str, language: str) -> None:
    body = capability_shared_body(kind, "Weekly digest", "Marie Dupont", language)

    assert body.startswith("Marie Dupont")
    assert "Weekly digest" in body
    assert KIND_WORDS[kind][language] in body
    assert "{" not in body and "}" not in body


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_a_departed_sender_is_still_someone(language: str) -> None:
    body = capability_shared_body("skill", "Weekly digest", None, language)

    assert not body.startswith(" ")
    assert "None" not in body
    assert body != capability_shared_body("skill", "Weekly digest", "Marie Dupont", language)


def test_a_raw_locale_reads_as_its_canonical_language() -> None:
    assert capability_shared_body("mcp", "Tickets", "Marie", "zh") == capability_shared_body(
        "mcp", "Tickets", "Marie", "zh-CN"
    )


def test_braces_in_a_title_or_a_name_are_kept_as_written() -> None:
    body = capability_shared_body("plugin", "{name}", "{sender}", "en")

    assert body.startswith("{sender} shared the plugin “{name}”")
