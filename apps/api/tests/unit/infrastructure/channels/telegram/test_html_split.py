"""A long Telegram HTML message is split into parts Telegram can parse (point 8).

The plain splitter cut an HTML message anywhere: inside ``<b>…</b>``, in the
middle of a ``<pre>`` block, through an ``&amp;`` entity. Telegram then
refused the part (« can't parse entities ») and the sender's fallback sent it
again as raw text — the person read the tags. It also counted Python
characters where Telegram counts UTF-16 units, so a part dense in emoji could
pass the limit.

Every part is held to a strict validator: within the limit in UTF-16 units,
every tag closed in the part that opened it, no tag or entity cut, and the
text itself — tags aside — whole once the parts are put back together.
"""

from __future__ import annotations

import re
import time
from statistics import median

import pytest

from src.infrastructure.channels.telegram.formatter import markdown_to_telegram_html
from src.infrastructure.channels.telegram.html_split import split_html_message

pytestmark = pytest.mark.unit

_TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)[^<>]*>")
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")


def _utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _assert_parsable(part: str, limit: int) -> None:
    """What Telegram's HTML parser needs from ONE part."""
    assert _utf16(part) <= limit, f"part over the limit: {_utf16(part)} > {limit}"
    stack: list[str] = []
    for match in _TAG.finditer(part):
        closing, name = match.group(1), match.group(2).lower()
        if closing:
            assert stack and stack[-1] == name, f"</{name}> closes nothing open in {part!r}"
            stack.pop()
        else:
            stack.append(name)
    assert not stack, f"tags left open: {stack} in {part!r}"
    bare = _TAG.sub("", part)
    assert "<" not in bare and ">" not in bare, f"a tag was cut: {part!r}"
    assert _ENTITY.sub("", bare).count("&") == 0, f"an entity was cut: {part!r}"


def _words(html: str) -> str:
    """The text a reader sees, whitespace aside (a cut may move a blank)."""
    return "".join(_TAG.sub("", html).split())


def _split(html: str, limit: int) -> list[str]:
    parts = split_html_message(html, max_length=limit)
    for part in parts:
        _assert_parsable(part, limit)
    assert "".join(_words(part) for part in parts) == _words(html), "text was lost or added"
    return parts


class TestAShortMessageIsLeftAlone:
    def test_it_is_one_part_as_written(self) -> None:
        assert split_html_message("<b>Hello</b> world", max_length=100) == ["<b>Hello</b> world"]

    @pytest.mark.parametrize("count", [2, 300])
    def test_an_empty_formatted_message_has_no_part_to_send(self, count: int) -> None:
        html = markdown_to_telegram_html("```\n" + " " * count + "\n```")

        assert split_html_message(html, max_length=100) == []


class TestEveryPartParses:
    @pytest.mark.parametrize("nested", [False, True])
    def test_an_oversized_link_keeps_its_label_in_bounded_parts(self, nested: bool) -> None:
        """A real formatted Markdown link may have an address over Telegram's limit."""
        label = "anchor text " * 30
        markdown = f"[{label}](https://example.org/{'path' * 2_000})"
        html = markdown_to_telegram_html(markdown)
        if nested:
            html = f"<b>{html}</b>"

        parts = _split(html, limit=100)

        assert len(parts) < 10, "a long href must not produce one oversized message per letter"
        assert all("href=" not in part for part in parts)
        if nested:
            assert all(part.startswith("<b>") and part.endswith("</b>") for part in parts)

    def test_a_bold_span_across_the_cut_is_closed_then_reopened(self) -> None:
        html = "<b>" + "word " * 60 + "</b>"

        parts = _split(html, limit=100)

        assert len(parts) > 1
        assert all(part.startswith("<b>") and part.endswith("</b>") for part in parts)

    def test_a_code_block_longer_than_the_limit_stays_a_code_block(self) -> None:
        code = "\n".join(f"line_{index} = compute({index})" for index in range(40))
        parts = _split(f"Result:\n<pre>{code}</pre>", limit=150)

        assert len(parts) > 2
        assert all("<pre>" in part and "</pre>" in part for part in parts[1:])

    def test_a_code_cut_preserves_line_breaks_and_trailing_spaces(self) -> None:
        code = "\n".join(f"    value_{index} = {index}  " for index in range(20))
        html = markdown_to_telegram_html(f"```python\n{code}\n```")

        parts = _split(html, limit=100)

        assert "".join(_TAG.sub("", part) for part in parts) == _TAG.sub("", html)

    def test_blank_padding_cannot_grow_a_part_past_the_limit(self) -> None:
        html = markdown_to_telegram_html("```\n" + " " * 300 + "visible\n```")

        parts = _split(html, limit=100)

        assert all(_TAG.sub("", part).strip() for part in parts)

    def test_a_link_cut_in_two_keeps_its_address_in_both_parts(self) -> None:
        html = '<a href="https://example.org/a?b=1&amp;c=2">' + "anchor text " * 20 + "</a>"

        parts = _split(html, limit=120)

        assert len(parts) > 1
        assert all(
            part.startswith('<a href="https://example.org/a?b=1&amp;c=2">') for part in parts
        )

    def test_nested_tags_are_reopened_in_their_order(self) -> None:
        html = "<b><i>" + "nested " * 40 + "</i></b>"

        parts = _split(html, limit=90)

        assert all(part.startswith("<b><i>") and part.endswith("</i></b>") for part in parts)

    def test_an_entity_at_the_cut_is_never_split(self) -> None:
        html = "x" * 95 + "&amp;" + "y" * 50

        parts = _split(html, limit=98)

        assert parts[0].endswith("x") and parts[1].startswith("&amp;")

    def test_a_word_longer_than_the_limit_is_cut_hard(self) -> None:
        _split("<i>" + "a" * 500 + "</i>", limit=100)

    def test_no_part_is_only_formatting(self) -> None:
        """A part holding tags and blanks alone is an EMPTY message to Telegram,
        which refuses it: blanks at the head of a span never make a part."""
        html = "<b>" + "\n" * 30 + "x" * 150 + "</b>"

        parts = _split(html, limit=100)

        assert all(_TAG.sub("", part).strip() for part in parts)

    def test_a_paragraph_break_is_preferred_to_a_hard_cut(self) -> None:
        html = "<b>First paragraph.</b>\n\n" + "Second paragraph " * 3

        parts = _split(html, limit=60)

        assert parts[0] == "<b>First paragraph.</b>"


class TestTheLimitIsCountedTheWayTelegramCounts:
    def test_an_emoji_counts_two(self) -> None:
        """U+1F600 is ONE Python character and TWO UTF-16 units."""
        parts = _split("\U0001f600" * 80, limit=100)

        assert [_utf16(part) for part in parts] == [100, 60]


class TestTextWithoutTags:
    def test_plain_text_in_html_mode_is_split_at_its_boundaries(self) -> None:
        parts = _split("First paragraph.\n\nSecond paragraph.", limit=25)

        assert parts == ["First paragraph.", "Second paragraph."]

    def test_many_parts_do_not_rescan_the_remaining_message(self) -> None:
        """The minimum configured limit must still split a large body linearly."""
        messages = {size: "x" * size for size in (128_000, 512_000)}
        growth = []
        for pair in range(3):
            seconds = {}
            for size in ((128_000, 512_000) if pair % 2 == 0 else (512_000, 128_000)):
                started = time.thread_time()
                parts = split_html_message(messages[size], max_length=100)
                seconds[size] = time.thread_time() - started
                assert "".join(parts) == messages[size]
                assert max(map(_utf16, parts)) <= 100
            assert seconds[512_000] < 1.5, seconds
            growth.append(seconds[512_000] / max(seconds[128_000], 0.005))
        assert median(growth) <= 8.0, growth
