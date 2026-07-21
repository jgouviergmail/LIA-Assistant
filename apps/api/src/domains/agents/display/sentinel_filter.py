"""Widget sentinels are host-owned: strip any the LLM authored itself.

Interactive widgets (`SKILL_APP`, `MCP_APP`) reach the frontend as a sentinel
``<div class="lia-skill-app" data-registry-id="...">`` that ``MarkdownContent``
replaces with a sandboxed React widget. Only :mod:`response_node` may emit one,
deterministically, from the current-turn registry.

The model learned to emit them anyway. The contamination chain, proven in
production on 2026-07-21:

1. ``_render_response_html`` appends the sentinel to the answer;
2. the enriched content is written back to ``state["messages"]`` and
   checkpointed;
3. ``_window_messages_for_react`` serves that history RAW to the ReAct loop —
   unlike the response path, it applies no HTML neutralization;
4. the model imitates the pattern (its copy even paraphrases the icon and the
   loading label), and the deterministic injection then appends a second one.

Two user-visible defects followed. **Duplicates**: message ``28eaa427`` carried
``skill_app_545e26`` twice, and two iframes really mounted. **Phantoms**: two
later answers carried a sentinel the backend never injected, pointing at a
registry id from an earlier turn — rendering by accident while the client-side
registry still held it, dead on reload.

Fixing only the duplicate would leave the phantoms. The invariant enforced here
is stronger and simpler to reason about: *the LLM never authors widget markup*.

Implementation note — this uses :mod:`html.parser`, deliberately not a regex.
The sentinel nests ``<div>`` elements (placeholder, badge, icon, loading
label); a non-greedy regex stops at the first ``</div>`` and leaves orphan
closing tags behind. Positions are resolved against the original string and
only the matched ranges are excised, so everything else survives byte for byte.
"""

from __future__ import annotations

from html.parser import HTMLParser

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Class tokens that mark a host-owned widget sentinel. Matched as whole class
# tokens, never as substrings: the sentinel's own children carry
# `lia-skill-app__placeholder` / `lia-mcp-app__loading`, which must not be
# treated as sentinels in their own right.
_SENTINEL_CLASSES = frozenset({"lia-skill-app", "lia-mcp-app"})


class _SentinelLocator(HTMLParser):
    """Collect the (start, end) character ranges of every sentinel block.

    Nested ``<div>`` elements are tracked by depth so the range ends on the
    sentinel's OWN closing tag, not the first one encountered.
    """

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self._source = source
        # Absolute index of the first character of each line (1-based lines).
        self._line_starts = [0]
        for line in source.splitlines(keepends=True):
            self._line_starts.append(self._line_starts[-1] + len(line))
        self.ranges: list[tuple[int, int]] = []
        self.unclosed = 0
        self._open_at: int | None = None
        self._depth = 0

    def _abs_pos(self) -> int:
        lineno, offset = self.getpos()
        return self._line_starts[lineno - 1] + offset

    @staticmethod
    def _is_sentinel(attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name == "class" and value:
                if _SENTINEL_CLASSES & set(value.split()):
                    return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        if self._open_at is None:
            if self._is_sentinel(attrs):
                self._open_at = self._abs_pos()
                self._depth = 1
        else:
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing `<div ... />` opens nothing: excise the tag alone.
        if tag == "div" and self._open_at is None and self._is_sentinel(attrs):
            start = self._abs_pos()
            raw = self.get_starttag_text() or ""
            self.ranges.append((start, start + len(raw)))

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._open_at is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        start_of_end = self._abs_pos()
        # HTMLParser gives the position but not the raw text of an end tag;
        # `</div >` is legal, so read up to the closing bracket.
        bracket = self._source.find(">", start_of_end)
        end = len(self._source) if bracket == -1 else bracket + 1
        self.ranges.append((self._open_at, end))
        self._open_at = None

    def close(self) -> None:
        super().close()
        if self._open_at is not None:
            # Truncated or malformed sentinel. Excise the opening tag ONLY:
            # deleting to end of input would swallow legitimate prose, and an
            # unclosed sentinel would otherwise absorb the rest of the answer
            # into a widget the frontend replaces wholesale.
            self.unclosed += 1
            self._source_slice_open_tag()

    def _source_slice_open_tag(self) -> None:
        assert self._open_at is not None
        bracket = self._source.find(">", self._open_at)
        if bracket != -1:
            self.ranges.append((self._open_at, bracket + 1))
        self._open_at = None


def strip_widget_sentinels(content: str, *, replacement: str = "") -> tuple[str, int]:
    """Remove every widget sentinel block from ``content``.

    Args:
        content: Assistant text, possibly carrying LLM-authored sentinels.
        replacement: Text substituted for each removed block. Empty (the
            default) for the output path, where the deterministic injection
            adds the canonical sentinel right after; a short opaque marker for
            the history path, where the model still needs to know a widget was
            displayed without being shown how to write one.

    Returns:
        ``(cleaned_content, removed_count)``. ``content`` is returned unchanged
        when it carries no sentinel — the overwhelmingly common case, and the
        reason for the cheap substring pre-check.
    """
    if not content or not any(cls in content for cls in _SENTINEL_CLASSES):
        return content, 0

    locator = _SentinelLocator(content)
    try:
        locator.feed(content)
        locator.close()
    except Exception as exc:  # noqa: BLE001 - malformed markup must never break a reply
        logger.warning(
            "widget_sentinel_strip_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return content, 0

    if not locator.ranges:
        return content, 0

    ranges = sorted(locator.ranges)
    parts: list[str] = []
    cursor = 0
    for start, end in ranges:
        if start < cursor:  # defensive: overlapping ranges cannot be replayed
            continue
        parts.append(content[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(content[cursor:])

    if locator.unclosed:
        logger.warning("widget_sentinel_unclosed", count=locator.unclosed)

    return "".join(parts), len(ranges)


def count_widget_sentinels(content: str) -> int:
    """Count sentinel blocks in ``content`` (test/observability helper)."""
    return strip_widget_sentinels(content)[1]
