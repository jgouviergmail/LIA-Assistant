"""The page a mode works from, found in the conversation (ADR-370)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.core.config import settings as app_settings
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.interactive_page import page_sources as mod
from src.domains.interactive_pages.document import page_frame
from src.domains.interactive_pages.schemas import PageMode, PageSource

pytestmark = pytest.mark.unit

_CONVERSATION = "00000000-0000-0000-0000-00000000c001"
PAGE = "<html><head><title>Morpion</title></head><body><p>🎃</p></body></html>"


def _answer(code: str) -> str:
    escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div class="lia-response">\n<p>Voici.</p>\n'
        f'<pre><code class="language-html">{escaped}\n</code></pre>\n</div>'
    )


def _widget_metadata(source: str, title: str = "Morpion") -> dict[str, Any]:
    frame = page_frame(source)
    return {
        "widgets": {
            "page_app_1": {
                "id": "page_app_1",
                "type": RegistryItemType.PAGE_APP.value,
                "payload": {
                    "title": title,
                    "html_content": frame.document,
                    "source_offset": frame.source_offset,
                },
            }
        }
    }


def _message(
    content: str = "", metadata: dict[str, Any] | None = None, role: str = "assistant"
) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content, message_metadata=metadata)


class TestHtmlCodeOf:
    def test_reads_the_code_of_an_html_answer_back_as_written(self) -> None:
        assert mod.html_code_of(_answer(PAGE)) == PAGE

    def test_reads_a_markdown_fence(self) -> None:
        assert mod.html_code_of(f"Voici :\n\n```html\n{PAGE}\n```\n") == PAGE

    def test_keeps_the_page_when_snippets_sit_beside_it(self) -> None:
        content = _answer("<p>a</p>") + _answer(PAGE) + _answer("<b>c</b>")
        assert mod.html_code_of(content) == PAGE

    @pytest.mark.parametrize(
        "content",
        [
            "Rien ici.",
            '<pre><code class="language-python">print(1)</code></pre>',
            "```python\nprint(1)\n```",
            '<pre><code class="language-html">sans fin',
            "```html\nsans fin",
        ],
    )
    def test_finds_nothing_else(self, content: str) -> None:
        assert mod.html_code_of(content) is None


class TestTitleOf:
    def test_reads_the_title_of_a_page(self) -> None:
        assert mod.title_of(PAGE) == "Morpion"

    def test_decodes_its_entities(self) -> None:
        assert mod.title_of("<title>Jeu &amp; quiz</title>") == "Jeu & quiz"

    def test_is_empty_without_one(self) -> None:
        assert mod.title_of("<p>x</p>") == ""


class TestPageOfMetadata:
    def test_reads_the_page_of_a_widget_without_its_policy(self) -> None:
        assert mod.page_of_metadata(_widget_metadata(PAGE)) == PageSource(PAGE, "Morpion")

    @pytest.mark.parametrize("offset", ["abc", None, [1], {"a": 1}])
    def test_an_unreadable_offset_keeps_the_whole_page(self, offset: Any) -> None:
        """A second prefix is harmless, a lost page is not (``source_of``)."""
        metadata = _widget_metadata(PAGE)
        payload = metadata["widgets"]["page_app_1"]["payload"]
        metadata["widgets"]["page_app_1"]["payload"] = {**payload, "source_offset": offset}

        found = mod.page_of_metadata(metadata)

        assert found is not None and found.html == payload["html_content"]

    @pytest.mark.parametrize(
        "metadata",
        [
            None,
            {},
            {"widgets": "x"},
            {"widgets": {"a": "x"}},
            {"widgets": {"a": {"type": "SKILL_APP", "payload": {"html_content": "<p>x</p>"}}}},
            {"widgets": {"a": {"type": "PAGE_APP", "payload": "x"}}},
            {"widgets": {"a": {"type": "PAGE_APP", "payload": {"html_content": 3}}}},
        ],
    )
    def test_ignores_everything_else(self, metadata: Any) -> None:
        assert mod.page_of_metadata(metadata) is None


class _FakeRepo:
    rows: list[SimpleNamespace] = []
    calls: list[dict[str, Any]] = []

    def __init__(self, db: object) -> None:
        self._db = db

    async def get_messages_for_conversation(
        self, conversation_id: uuid.UUID, limit: int = 50, order_desc: bool = True
    ) -> list[SimpleNamespace]:
        type(self).calls.append(
            {"conversation_id": conversation_id, "limit": limit, "order_desc": order_desc}
        )
        return type(self).rows


@asynccontextmanager
async def _fake_db_context() -> AsyncIterator[object]:
    yield object()


async def _find(*rows: SimpleNamespace, conversation: str = _CONVERSATION) -> PageSource | None:
    _FakeRepo.rows = list(rows)
    _FakeRepo.calls = []
    with (
        patch.object(mod, "ConversationRepository", _FakeRepo),
        patch.object(mod, "get_db_context", _fake_db_context),
    ):
        return await mod.find_page_source(conversation)


class TestFindPageSource:
    async def test_prefers_the_newest_message(self) -> None:
        found = await _find(
            _message(metadata=_widget_metadata("<p>new</p>", "New")),
            _message(metadata=_widget_metadata("<p>old</p>", "Old")),
        )
        assert found == PageSource("<p>new</p>", "New")

    async def test_finds_a_code_answer_newer_than_a_page(self) -> None:
        found = await _find(
            _message(_answer(PAGE)), _message(metadata=_widget_metadata("<p>old</p>"))
        )
        assert found == PageSource(PAGE, "Morpion")

    async def test_prefers_a_page_over_the_code_of_the_same_message(self) -> None:
        found = await _find(_message(_answer("<p>code</p>"), _widget_metadata("<p>page</p>")))
        assert found is not None
        assert found.html == "<p>page</p>"

    async def test_never_reads_a_page_out_of_the_person_s_words(self) -> None:
        assert await _find(_message(f"```html\n{PAGE}\n```", role="user")) is None

    async def test_reads_a_bounded_number_of_recent_messages(self) -> None:
        await _find(_message("rien"))
        assert _FakeRepo.calls == [
            {
                "conversation_id": uuid.UUID(_CONVERSATION),
                "limit": app_settings.interactive_page_source_lookback_messages,
                "order_desc": True,
            }
        ]

    async def test_finds_nothing_in_an_empty_conversation(self) -> None:
        assert await _find() is None

    async def test_finds_nothing_without_a_conversation(self) -> None:
        """A routine runs on a thread that names no conversation."""
        assert await _find(conversation="not-a-uuid") is None
        assert _FakeRepo.calls == []


class TestResolvePageBase:
    async def _resolve(
        self, mode: PageMode, source_data: str, found: PageSource | None
    ) -> PageSource | None:
        async def lookup(_conversation: str) -> PageSource | None:
            return found

        with patch.object(mod, "find_page_source", lookup):
            return await mod.resolve_page_base(mode, source_data, _CONVERSATION)

    async def test_a_new_page_reads_nothing(self) -> None:
        found = PageSource("<p>x</p>", "")
        assert await self._resolve(PageMode.CREATE, "<p>y</p>", found) is None

    @pytest.mark.parametrize("mode", [PageMode.SHOW, PageMode.CODE])
    async def test_code_handed_over_is_shown_rather_than_an_older_page(
        self, mode: PageMode
    ) -> None:
        base = await self._resolve(mode, PAGE, PageSource("<p>old</p>", "Old"))
        assert base == PageSource(PAGE, "Morpion")

    @pytest.mark.parametrize("mode", [PageMode.SHOW, PageMode.CODE])
    async def test_without_code_handed_over_the_conversation_answers(self, mode: PageMode) -> None:
        found = PageSource("<p>old</p>", "Old")
        assert await self._resolve(mode, "  ", found) == found

    async def test_a_revision_starts_from_the_conversation(self) -> None:
        found = PageSource("<p>old</p>", "Old")
        assert await self._resolve(PageMode.REVISE, "des faits", found) == found

    async def test_a_revision_of_a_pasted_page_starts_from_it(self) -> None:
        assert await self._resolve(PageMode.REVISE, PAGE, None) == PageSource(PAGE, "Morpion")

    async def test_nothing_anywhere_is_nothing(self) -> None:
        assert await self._resolve(PageMode.REVISE, "", None) is None
