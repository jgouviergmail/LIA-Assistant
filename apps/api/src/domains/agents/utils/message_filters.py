"""
Message filtering utilities for LangGraph agents.

Provides reusable functions for filtering and processing message lists
in different contexts (response generation, agent input, tool context, etc.).

All functions preserve immutability - input lists are never modified.
"""

import re
from collections.abc import Callable
from html.parser import HTMLParser
from itertools import groupby
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)

from src.core.constants import (
    COMPACTION_SUMMARY_MARKER,
    CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER,
    CONTEXT_RESULTS_DISPLAYED_PLACEHOLDER,
)
from src.core.turn_verdicts import note_verdict
from src.domains.agents.display.plain_text import strip_html_if_markup
from src.domains.shared.markdown_literal import read_as_markdown
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.message_view import model_view_content
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_langgraph import langgraph_history_repairs_total

logger = get_logger(__name__)

# Markdown style markers to strip when neutralizing prior assistant answers for the
# response LLM's history (see ``_neutralize_assistant_formatting``). Each pattern is
# anchored or scoped so it removes only *formatting* tokens, never the surrounding
# textual content (e.g. ``2*3`` or an in-word underscore is left untouched).
_MD_FENCED_CODE_RE = re.compile(r"^[ \t]*```[^\n]*$", re.MULTILINE)
_MD_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_MD_BLOCKQUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?", re.MULTILINE)
_MD_THEMATIC_BREAK_RE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.MULTILINE)
_MD_LIST_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.MULTILINE)
_MD_TABLE_DELIM_RE = re.compile(r"^[ \t]{0,3}\|?[ \t:|-]+\|?[ \t]*$", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_MD_ITALIC_RE = re.compile(r"(?<![\w*_])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*_])")
_MD_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)\s]+\)")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")


def _strip_markdown_syntax(text: str) -> str:
    """Remove common Markdown *formatting* tokens, preserving textual content.

    Used to neutralize the style of prior assistant answers in the response LLM's
    conversational history (via ``_neutralize_assistant_formatting``) so they cannot act
    as a Markdown style precedent that fights the HTML output directive. This is
    intentionally conservative: it strips only unambiguous formatting markers (headings,
    emphasis, list bullets, thematic breaks, table delimiter rows, inline code,
    blockquotes, and link syntax) and leaves all other characters — including
    ordered-list numbers and in-word ``*``/``_`` — intact.

    Args:
        text: Raw message text (already coerced to ``str``).

    Returns:
        The text with Markdown formatting markers removed and runs of blank lines
        collapsed. Content words, names, dates and numbers are preserved verbatim.
    """
    text = _MD_FENCED_CODE_RE.sub("", text)
    text = _MD_THEMATIC_BREAK_RE.sub("", text)
    text = _MD_TABLE_DELIM_RE.sub("", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BLOCKQUOTE_RE.sub("", text)
    text = _MD_LIST_BULLET_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_BOLD_RE.sub(r"\2", text)
    text = _MD_ITALIC_RE.sub(r"\2", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    # Drop residual table cell pipes, then collapse blank-line runs created above.
    text = text.replace("|", " ")
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def _neutralize_assistant_formatting(content: str) -> str:
    """Render a prior assistant answer as style-free text tagged for the response LLM.

    Produces a representation that preserves *what* was answered (for conversational
    continuity) while removing every *style* signal — both HTML and Markdown — so the
    response LLM cannot infer an output format from the history and only obeys the
    active formatting directive. The result is prefixed with
    ``CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER`` so the model treats it as a stripped
    excerpt rather than a style precedent.

    Rich HTML synthesis survives as text, while data cards and widget payloads
    remain excluded. The call is idempotent: content already carrying the marker
    is returned unchanged.

    Args:
        content: The assistant message content (already coerced to ``str``).

    Returns:
        Marker-prefixed, style-neutralized text. If no textual content remains
        (e.g. an HTML-only data card), the bare marker is returned.
    """
    if content.startswith(CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER):
        # Idempotency guard: never double-strip or double-prefix.
        return content

    # For HTML answers, keep only what the non-neutralized branch keeps, so we
    # do not pour entire card markup back into the context window. Markdown is
    # read as the chat reads it — a value drawn as
    # « jean_dupont&#64;example.com » is an address — and stripped of its style.
    if 'class="lia-' in content or "class='lia-" in content:
        text = _prose_of_html_answer(content, neutralize=True)
    else:
        text = read_as_markdown(content, _strip_markdown_syntax)
    if not text:
        return CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER
    return f"{CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER} {text}"


#: The card classes of a draft's confirmation and of its execution result
#: (``drafts/card_html.py``). Their words ARE the turn — what was asked, what
#: was sent and to whom — so the model reads them flattened, never dropped.
_DRAFT_CARD_MARKERS = ('class="lia-card lia-draft', "class='lia-card lia-draft")


class _RichHistoryHtml(HTMLParser):
    """Keep synthesis markup from lia-response roots, excluding data subtrees.

    Nested cards cannot be removed with a tag regex. The stack distinguishes
    the prose root from its data cards/widgets, including truncated subtrees.
    Attributes are never copied, references remain encoded until the existing
    plain-text reader runs, and no HTML is executed or fetched.
    """

    _EXCLUDED_CLASSES = frozenset(
        {"lia-card", "lia-skill-app", "lia-mcp-app", "material-symbols-outlined"}
    )
    _EXCLUDED_TAGS = frozenset({"script", "style", "head", "template", "iframe", "object"})
    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._stack: list[tuple[str, bool, bool]] = []
        self._open_tags: dict[str, int] = {}

    def _visible(self) -> bool:
        return bool(self._stack and self._stack[-1][1] and not self._stack[-1][2])

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        active = "lia-response" in classes or bool(self._stack and self._stack[-1][1])
        excluded = bool(
            classes & self._EXCLUDED_CLASSES
            or tag in self._EXCLUDED_TAGS
            or (self._stack and self._stack[-1][2])
        )
        if active and not excluded:
            self.parts.append(f"<{tag}>")
        elif self._visible():
            self.parts.append(" ")
        if tag not in self._VOID_TAGS:
            self._stack.append((tag, active, excluded))
            self._open_tags[tag] = self._open_tags.get(tag, 0) + 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        # An unmatched closing tag cannot release a hidden subtree. Counts
        # avoid rescanning the stack for every malformed closing tag.
        if not self._open_tags.get(tag):
            return
        visible = self._visible()
        while self._stack:
            # A malformed ancestor close must not escape the excluded root:
            # <p><div class="lia-card">... </p> private ... </div>.
            opened, _, excluded = self._stack[-1]
            if excluded and opened != tag and (len(self._stack) == 1 or not self._stack[-2][2]):
                return
            opened, _, _ = self._stack.pop()
            self._open_tags[opened] -= 1
            if opened == tag:
                break
        if visible:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._visible():
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")


def _prose_of_html_answer(content: str, *, neutralize: bool = False) -> str:
    """What the model reads of an assistant answer that carries HTML.

    Rich synthesis inside ``lia-response`` is flattened to text. A DATA card
    (weather, an e-mail listed) is reduced to the prose before it,
    the historical rule: the data is in the registry, and markup poured back
    into the context is markup the model re-emits. A DRAFT card (ADR-289) is
    flattened to its text instead — reducing it would erase from the
    conversation's memory what was sent and to whom (a result card opens on
    its markup, so its prose is empty).

    Args:
        content: The assistant message content, HTML included.
        neutralize: Whether the Markdown around the cards loses its style
            too (the html display mode's history).

    Returns:
        Text only, its character references read as the chat reads them.
    """
    markdown = _strip_markdown_syntax if neutralize else None
    if any(marker in content for marker in _DRAFT_CARD_MARKERS):
        return _draft_answer_text(content, markdown)
    leading = read_as_markdown(_extract_text_before_html(content), markdown)
    if "lia-response" not in content:
        return leading
    synthesis = _RichHistoryHtml()
    synthesis.feed(content)
    synthesis.close()
    # The wrapper also identifies a truncated root as markup for the shared
    # flattener. Do not strip Markdown from HTML text: code and literal card
    # values may contain pipes, asterisks or a spelled-out Markdown link.
    rich = read_as_markdown("<div>" + "".join(synthesis.parts) + "</div>", strip_html_if_markup)
    return " ".join(part for part in (leading, " ".join(rich.split())) if part)


def _is_draft_card_line(line: str) -> bool:
    return any(marker in line for marker in _DRAFT_CARD_MARKERS)


def _draft_answer_text(content: str, markdown: Callable[[str], str] | None) -> str:
    """An answer carrying a draft card, on one line: the card's words as data.

    A card is one line of HTML (``drafts/card_html``) whose values are what
    was sent or run: its text is flattened alone, its references read once,
    and no Markdown rule touches it — stripped as Markdown, a subject « A | B »
    lost its bar and « [x](https://y.example) » its address (review 14). The
    lines around it are LIA's Markdown (the question, the rule before it).

    Args:
        content: The assistant message content.
        markdown: How the Markdown around the cards is flattened (None keeps it).

    Returns:
        The answer's text on one line.
    """
    parts = [
        read_as_markdown("\n".join(lines), strip_html_if_markup if is_card else markdown)
        for is_card, lines in groupby(content.split("\n"), key=_is_draft_card_line)
    ]
    return " ".join(" ".join(parts).split())


def _extract_text_before_html(content: str) -> str:
    """
    Extract text content before any HTML tags.

    When AI responses contain both commentary text and HTML cards (lia-card),
    this extracts just the text portion to preserve context without the HTML.

    Args:
        content: Full AI message content possibly containing HTML.

    Returns:
        Text before first HTML tag, stripped. Empty string if no text found.

    Example:
        >>> _extract_text_before_html("Here is the weather!\\n\\n<div class='lia-card'>...")
        "Here is the weather!"
        >>> _extract_text_before_html("<div class='lia-card'>...")
        ""
    """
    # Find first HTML tag position
    html_match = re.search(r"<[a-zA-Z]", content)
    if html_match:
        text_before = content[: html_match.start()].strip()
        return text_before
    return content.strip()


def filter_conversational_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter messages to keep only conversational messages (HumanMessage and AIMessage without tool_calls).

    Removes:
    - ToolMessage (tool execution results - internal to agent)
    - AIMessage with tool_calls (agent internal reasoning)

    Keeps:
    - HumanMessage (user messages)
    - AIMessage without tool_calls (conversational responses from agents)

    This ensures response LLM only sees conversational history, not internal tool execution details.
    Agent results should be provided separately via agent_results parameter in prompts.

    Args:
        messages: Full message history from state.

    Returns:
        Filtered list containing only conversational messages.

    Example:
        >>> from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        >>> messages = [
        ...     HumanMessage(content="jean's e-mail"),
        ...     AIMessage(content="", tool_calls=[{"id": "call_123", "name": "search"}]),  # Filtered out
        ...     ToolMessage(content='{"results": [...]}', tool_call_id="call_123"),  # Filtered out
        ...     AIMessage(content="Here is jean's e-mail"),  # Kept
        ... ]
        >>> filtered = filter_conversational_messages(messages)
        >>> len(filtered)  # 2 (HumanMessage + final AIMessage)
        2

    Note:
        Used primarily in response_node to prepare clean message history for response LLM.
    """
    conversational = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Keep all user messages
            conversational.append(msg)
        elif isinstance(msg, AIMessage):
            # Only keep AI messages without tool calls (conversational responses)
            if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                conversational.append(msg)
        elif isinstance(msg, SystemMessage):
            # Skip internal system markers (e.g., __PLAN_REJECTED__)
            if msg.content.startswith("__"):
                continue
        # Skip ToolMessage - these are internal tool results

    logger.debug(
        "filter_conversational_messages",
        original_count=len(messages),
        filtered_count=len(conversational),
        removed=len(messages) - len(conversational),
    )

    return conversational


def filter_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter messages to keep only ToolMessages.

    Useful for extracting tool execution results from message history
    for context analysis or debugging.

    Args:
        messages: Full message history.

    Returns:
        List containing only ToolMessages.

    Example:
        >>> tool_messages = filter_tool_messages(state["messages"])
        >>> # Analyze tool execution results
        >>> for tool_msg in tool_messages:
        ...     print(f"Tool: {tool_msg.name}, Result: {tool_msg.content[:50]}")
    """
    tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]

    logger.debug(
        "filter_tool_messages",
        total_messages=len(messages),
        tool_messages_count=len(tool_messages),
    )

    return tool_messages


def filter_by_message_types(
    messages: list[BaseMessage], types: list[type[BaseMessage]]
) -> list[BaseMessage]:
    """
    Generic filter for messages by type.

    Args:
        messages: Full message history.
        types: List of message types to keep (e.g., [HumanMessage, AIMessage]).

    Returns:
        Filtered list containing only messages of specified types.

    Example:
        >>> from langchain_core.messages import HumanMessage, SystemMessage
        >>> # Keep only user messages and system messages
        >>> filtered = filter_by_message_types(messages, [HumanMessage, SystemMessage])
    """
    filtered = [msg for msg in messages if type(msg) in types]

    logger.debug(
        "filter_by_message_types",
        original_count=len(messages),
        filtered_count=len(filtered),
        types=[t.__name__ for t in types],
    )

    return filtered


def extract_system_messages(messages: list[BaseMessage]) -> list[SystemMessage]:
    """
    Extract all SystemMessages from message list.

    Useful for preserving system prompts during message truncation or filtering.

    Args:
        messages: Full message history.

    Returns:
        List of SystemMessages (empty list if none found).

    Example:
        >>> system_msgs = extract_system_messages(state["messages"])
        >>> # Always include system messages in agent input
        >>> agent_input = system_msgs + recent_messages
    """
    system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]

    logger.debug(
        "extract_system_messages",
        total_messages=len(messages),
        system_messages_count=len(system_messages),
    )

    return system_messages


def remove_orphan_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Remove ToolMessages that don't have a corresponding AIMessage with tool_calls.

    This function ensures OpenAI API compatibility by maintaining the constraint:
    "messages with role 'tool' must be a response to a preceding message with 'tool_calls'"

    Orphan ToolMessages can occur after message truncation when an AIMessage with tool_calls
    is removed but its corresponding ToolMessage is kept.

    Args:
        messages: Message list potentially containing orphan ToolMessages.

    Returns:
        Cleaned message list with orphan ToolMessages removed.

    Example:
        >>> messages = [
        ...     HumanMessage(content="search contacts"),
        ...     ToolMessage(content="result", tool_call_id="call_123"),  # Orphan (no parent AIMessage)!
        ... ]
        >>> cleaned = remove_orphan_tool_messages(messages)
        >>> len(cleaned)  # 1 (ToolMessage removed)
        1

    Note:
        This function is called automatically in add_messages_with_truncate reducer
        to prevent OpenAI API errors after message truncation.
    """
    if not messages:
        return []

    # Step 1: Collect all tool_call_ids from AIMessages
    available_tool_call_ids = set()

    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if isinstance(tool_call, dict) and "id" in tool_call:
                    available_tool_call_ids.add(tool_call["id"])

    # Step 2: Filter messages - keep everything except orphan ToolMessages
    validated = []
    orphan_count = 0

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)

            if tool_call_id not in available_tool_call_ids:
                # Orphan ToolMessage - remove it
                orphan_count += 1
                logger.warning(
                    "orphan_tool_message_removed",
                    tool_call_id=tool_call_id,
                    # Counts only: a tool result carries mail, calendar and contact text.
                    content_chars=len(str(msg.content)) if msg.content else 0,
                )
                continue  # Skip this message

        # Keep all other messages (HumanMessage, AIMessage, SystemMessage, valid ToolMessage)
        validated.append(msg)

    # Log summary if orphans were found
    if orphan_count > 0:
        logger.info(
            "orphan_tool_messages_removed",
            original_count=len(messages),
            validated_count=len(validated),
            orphans_removed=orphan_count,
        )

    return validated


def _repaired_carrier(msg: AIMessage, answered_ids: set[str]) -> AIMessage | None:
    """The pairing verdict for ONE AIMessage: keep it, mend it, or drop it.

    Args:
        msg: A candidate carrier from the history.
        answered_ids: ``tool_call_id`` values that a ``ToolMessage`` answers.

    Returns:
        The message unchanged, a mended copy without its orphan call blocks,
        or ``None`` when nothing valid remains and the carrier must go.
    """
    if msg.tool_calls:
        call_ids = {tc["id"] for tc in msg.tool_calls if isinstance(tc, dict) and "id" in tc}
        missing = call_ids - answered_ids
        if missing:
            langgraph_history_repairs_total.labels(shape="tool_calls", action="removal").inc()
            note_verdict("history_repaired", "tool_calls:removal")
            logger.warning(
                "unanswered_tool_calls_carrier_removed",
                missing_tool_call_ids=sorted(missing),
            )
            return None

    # Direction 2 again, one layer down: under responses/v1 and Anthropic the
    # call ALSO exists as a CONTENT BLOCK, serialized independently of
    # ``tool_calls``. A message whose tool_calls are clean can still carry an
    # orphan — that is how a repaired-once history kept poisoning providers.
    content, dangling_blocks = _purge_dangling_call_blocks(msg.content, answered_ids)
    if not dangling_blocks:
        return msg

    if not coerce_content_to_text(content).strip() and not msg.tool_calls:
        # Nothing readable and nothing left to answer: history, not a message.
        langgraph_history_repairs_total.labels(shape="call_block", action="removal").inc()
        note_verdict("history_repaired", "call_block:removal")
        logger.warning("unanswered_call_blocks_carrier_removed", dangling_blocks=dangling_blocks)
        return None

    langgraph_history_repairs_total.labels(shape="call_block", action="replacement").inc()
    note_verdict("history_repaired", "call_block:replacement")
    logger.warning("unanswered_call_blocks_purged", dangling_blocks=dangling_blocks)
    # Answered ``tool_calls`` are carried over explicitly; ``additional_kwargs``
    # is NOT, for the same measured reason as the turn-start repair — the
    # provider's raw calls live there too and the Responses API re-serializes
    # them, which would put back exactly what this branch just removed.
    return AIMessage(content=content, id=msg.id, tool_calls=msg.tool_calls)


def enforce_tool_message_pairing(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Enforce the provider tool-pairing contract in BOTH directions.

    OpenAI and Anthropic reject a history when:

    1. a ToolMessage has no preceding AIMessage carrying its ``tool_call_id``
       (orphan tool result), or
    2. an AIMessage declares an unanswered call — either in ``tool_calls`` or
       as a CALL BLOCK inside list-shaped ``content``.

    :func:`remove_orphan_tool_messages` only covers direction 1; this helper
    first drops AIMessages with unanswered tool_calls (direction 2 — their
    already-answered ToolMessages become orphans by construction), then
    removes every orphan ToolMessage. Dropping only orphan ToolMessages can
    never un-answer a remaining carrier, so one pass of each is stable.

    Direction 2 has a second shape, and missing it kept a production
    conversation broken for good (2026-09-02): under
    ``output_version="responses/v1"`` and on Anthropic, the call ALSO lives as
    a typed block inside ``content`` and is serialized independently of
    ``tool_calls``. A message whose ``tool_calls`` are clean can therefore
    still carry an orphan. Such blocks are purged from the message rather than
    dropping it — the text around them is legitimate history — and the message
    goes only when nothing readable and no answerable call remains.

    Args:
        messages: Message list potentially violating the pairing contract
            (typically after any truncation/filtering step).

    Returns:
        A provider-valid message list (order preserved).
    """
    if not messages:
        return []

    answered_ids = {
        msg.tool_call_id
        for msg in messages
        if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None)
    }

    without_unanswered_carriers: list[BaseMessage] = []
    dropped_carriers = 0
    for msg in messages:
        if not isinstance(msg, AIMessage):
            without_unanswered_carriers.append(msg)
            continue
        repaired = _repaired_carrier(msg, answered_ids)
        if repaired is None:
            dropped_carriers += 1
            continue
        without_unanswered_carriers.append(repaired)

    validated = remove_orphan_tool_messages(without_unanswered_carriers)

    if dropped_carriers > 0:
        logger.info(
            "tool_pairing_enforced",
            original_count=len(messages),
            validated_count=len(validated),
            carriers_removed=dropped_carriers,
        )

    return validated


def _assistant_for_llm_context(msg: AIMessage, neutralize_formatting: bool) -> AIMessage | None:
    """One final assistant answer, with its existing legacy or semantic policy."""
    if msg.tool_calls:
        return None
    view = model_view_content(msg)
    if view is not None:
        return msg.model_copy(update={"content": view})
    content = coerce_content_to_text(msg.content)
    if neutralize_formatting:
        return AIMessage(content=_neutralize_assistant_formatting(content))
    if 'class="lia-' in content or "class='lia-" in content:
        prose = _prose_of_html_answer(content)
        return AIMessage(content=prose or CONTEXT_RESULTS_DISPLAYED_PLACEHOLDER)
    read = read_as_markdown(content)
    return msg if read == content else AIMessage(content=read)


def filter_for_llm_context(
    messages: list[BaseMessage],
    *,
    neutralize_formatting: bool = False,
) -> list[BaseMessage]:
    """
    Filter messages to keep user input, JSON tool results, and simple chat AI responses.

    This filter is designed for building conversation history that the LLM sees.
    It excludes AI responses containing HTML formatting (lia-card, etc.) to prevent
    the LLM from reformulating HTML as Markdown.

    Keeps:
    - HumanMessage (user input)
    - ToolMessage (JSON results from tools)
    - AIMessage WITHOUT HTML content (simple chat responses)
    - SystemMessage carrying a compaction summary (prefixed with
      ``COMPACTION_SUMMARY_MARKER``) — the only legitimate SystemMessage here, as it
      holds the compacted conversation history and is not re-injected elsewhere.

    Removes:
    - AIMessage with tool_calls (internal agent reasoning)
    - AIMessage containing HTML (class="lia-) - formatted display responses
    - Every OTHER SystemMessage — internal node scaffolding (the ReAct agent system
      prompt with its PLAN/OBSERVE workflow + tool-calling role, memory/skills context
      blocks, ``__`` internal markers) that must never reach the response synthesizer.

    Args:
        messages: Full message history from state.
        neutralize_formatting: When ``True`` (used only by the response node in the
            ``html`` / ``html_cards`` display modes), every retained assistant answer is rewritten to
            style-free text tagged with ``CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER``
            (see ``_neutralize_assistant_formatting``). This removes the Markdown/HTML
            style precedent that otherwise accumulates in history and overrides the
            HTML output directive over multi-turn conversations. Defaults to ``False``,
            i.e. Markdown answers kept verbatim. In either path rich HTML synthesis
            survives as text, while data cards and widget payloads stay excluded.

    Returns:
        Filtered list for LLM context.

    Example:
        >>> messages = [
        ...     HumanMessage(content="hi"),
        ...     AIMessage(content="Hello!"),  # Kept (simple chat)
        ...     HumanMessage(content="search contacts jean"),
        ...     ToolMessage(content='{"items": [...]}'),  # Kept (JSON)
        ...     AIMessage(content="<div class='lia-card'>...</div>"),  # Excluded (HTML)
        ... ]
        >>> filtered = filter_for_llm_context(messages)

    Note:
        Used by format_conversation_history to build clean context for response LLM.
    """
    filtered = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Keep all user messages
            filtered.append(msg)
        elif isinstance(msg, ToolMessage):
            # Keep tool results (JSON data)
            filtered.append(msg)
        elif isinstance(msg, AIMessage):
            if (answer := _assistant_for_llm_context(msg, neutralize_formatting)) is not None:
                filtered.append(answer)
        elif isinstance(msg, SystemMessage):
            # Keep ONLY the compaction summary. It carries the compacted conversation
            # history and is the response LLM's sole source for it (the `compaction_summary`
            # state field is not re-injected into the response prompt). Every OTHER
            # SystemMessage in state["messages"] is internal node scaffolding — notably the
            # ReAct agent system prompt (with its PLAN/OBSERVE workflow + tool-calling role)
            # injected by react_setup_node, plus redundant memory/skills context blocks. If
            # those reach the response synthesizer, the model mimics the agent's reasoning
            # structure (PLAN/OBSERVATION leak) or adopts its role ("I'll search…, call
            # tool…") instead of delivering the answer. So we drop them here.
            # ``content`` may be a list (provider block format); only a str summary qualifies.
            raw_content = getattr(msg, "content", "")
            content = raw_content if isinstance(raw_content, str) else ""
            if content.startswith(COMPACTION_SUMMARY_MARKER):
                filtered.append(msg)
            # else: drop ReAct scaffolding, memory/skills context, and "__" internal markers

    logger.debug(
        "filter_for_llm_context",
        original_count=len(messages),
        filtered_count=len(filtered),
    )

    return filtered


def drop_current_turn_responses(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Drop every message that follows the last ``HumanMessage`` in the list.

    The response synthesizer builds its conversation *history* from
    ``state["messages"]``. In the ReAct passthrough path the agent's final answer is
    appended to ``state["messages"]`` during the current turn, so without this pruning
    the history would end with a fully-formed assistant answer to the very question
    being answered. The synthesis LLM then sees the turn as already complete and emits
    a dismissive or minimal reply ("you already got the answer") instead of formatting
    the data — dropping the initiative enrichment and HTML directive. The answer stays
    available to it through the AUTHORITATIVE ``agent_results`` block, so nothing is lost.

    Removing everything after the last user message yields history = strictly prior turns
    plus the current user query, matching the planner path (where the current turn has no
    assistant message in ``state["messages"]`` yet, making this a no-op there).

    Args:
        messages: Full message history from state, in chronological order.

    Returns:
        A new list keeping all messages up to and including the last ``HumanMessage``.
        If no ``HumanMessage`` is present, the input is returned unchanged (defensive:
        nothing identifies a "current turn" to prune).

    Example:
        >>> from langchain_core.messages import HumanMessage, AIMessage
        >>> msgs = [
        ...     HumanMessage(content="prev"),
        ...     AIMessage(content="prev answer"),
        ...     HumanMessage(content="search my appointments"),
        ...     AIMessage(content="Here are your 3 appointments..."),  # current-turn ReAct answer
        ... ]
        >>> [type(m).__name__ for m in drop_current_turn_responses(msgs)]
        ['HumanMessage', 'AIMessage', 'HumanMessage']
    """
    last_human_idx = -1
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = idx

    if last_human_idx == -1:
        return list(messages)

    return list(messages[: last_human_idx + 1])


def current_turn_responses(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Every message that follows the last ``HumanMessage`` — the current turn's own.

    What ``drop_current_turn_responses`` removes, counted from the END: the
    reducer trims the head by tokens, so a position taken when the turn
    started moves while it runs. Whatever reads « what this turn did » reads
    it here — a whole-thread read restated an earlier turn's failures as the
    current one's.

    Args:
        messages: Full message history from state, in chronological order.

    Returns:
        A new list of the messages after the last ``HumanMessage``. A history
        holding none — the reducer re-pins the turn's question when it trims
        (``_ensure_turn_anchor``), so one that never held any — is returned
        whole.
    """
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return list(messages[index + 1 :])
    return list(messages)


#: ``ToolMessage.artifact`` of the answer to a call that did NOT run — declined
#: by the person, a repeat the loop guard blocked, or a sandbox run whose
#: network access the person refused. An artifact is never sent to a model and
#: survives the checkpoint like ``status``.
TOOL_CALL_NOT_RUN = "tool_call_not_run"


def tool_call_not_run(content: str, tool_call_id: str, name: str) -> ToolMessage:
    """The answer to a call that never ran: neither a success nor a failure.

    Never ``status="error"`` (ADR-303): the call broke nothing, and the honesty
    directive would tell the person their own refusal was a breakdown.

    Args:
        content: What the model is told instead of a result.
        tool_call_id: The id of the call it answers.
        name: The tool the call named.

    Returns:
        The ToolMessage, marked so a reader of outcomes counts no verdict.
    """
    return ToolMessage(
        content=content, tool_call_id=tool_call_id, name=name, artifact=TOOL_CALL_NOT_RUN
    )


def tool_call_ran(message: ToolMessage) -> bool:
    """Whether this ToolMessage answers a call that actually ran."""
    return getattr(message, "artifact", None) != TOOL_CALL_NOT_RUN


def split_messages_by_turn(
    messages: list[BaseMessage],
) -> list[tuple[HumanMessage, list[BaseMessage]]]:
    """
    Split messages into turns (user message + all responses until next user message).

    A turn consists of:
    1. HumanMessage (user input)
    2. All subsequent messages (AI, Tool, System) until next HumanMessage

    Useful for analyzing conversation flow, per-turn metrics, or turn-based cleanup.

    Args:
        messages: Full conversation history.

    Returns:
        List of tuples (HumanMessage, responses_list) representing conversation turns.

    Example:
        >>> turns = split_messages_by_turn(state["messages"])
        >>> for user_msg, responses in turns:
        ...     print(f"User: {user_msg.content}")
        ...     print(f"  Responses: {len(responses)} messages")
        >>> # Output:
        >>> # User: jean's e-mail
        >>> #   Responses: 5 messages (AIMessage with tool_calls, ToolMessage, AIMessage)
    """
    turns = []
    current_turn: tuple[HumanMessage | None, list[BaseMessage]] = (None, [])

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Start new turn
            if current_turn[0] is not None:
                # Save previous turn
                turns.append((current_turn[0], current_turn[1]))
            current_turn = (msg, [])
        else:
            # Add response to current turn
            if current_turn[0] is not None:
                current_turn[1].append(msg)

    # Save last turn if exists
    if current_turn[0] is not None:
        turns.append((current_turn[0], current_turn[1]))

    logger.debug(
        "split_messages_by_turn",
        total_messages=len(messages),
        turns_count=len(turns),
    )

    return turns


__all__ = [
    "TOOL_CALL_NOT_RUN",
    "current_turn_responses",
    "drop_current_turn_responses",
    "extract_system_messages",
    "filter_by_message_types",
    "filter_conversational_messages",
    "filter_for_llm_context",
    "filter_tool_messages",
    "remove_orphan_tool_messages",
    "split_messages_by_turn",
    "tool_call_not_run",
    "tool_call_ran",
]


# ``AIMessage.content`` is either plain text or a list of typed blocks; the
# alias keeps the helpers below honest under MyPy strict without widening to
# ``Any`` at the call site.
MessageContent = str | list[str | dict[Any, Any]]

# Provider call blocks, as they appear INSIDE list-shaped ``AIMessage.content``.
# OpenAI's Responses API (``output_version="responses/v1"``) emits
# ``function_call`` / ``custom_tool_call``; Anthropic emits ``tool_use``. These
# blocks are serialized to the provider INDEPENDENTLY of ``message.tool_calls``
# (measured against langchain-openai 1.5.2 and langchain-anthropic), which is
# why stripping ``tool_calls`` alone cannot repair a poisoned history.
_CALL_BLOCK_TYPES = frozenset({"function_call", "custom_tool_call", "tool_use"})


def _call_block_id(block: str | dict[Any, Any]) -> str | None:
    """Return the call id a content block refers to, when it is a call block.

    Args:
        block: One entry of a list-shaped ``AIMessage.content``.

    Returns:
        The block's ``call_id`` (Responses API) or ``id`` (Anthropic), or
        ``None`` when the block is not a call block or carries no identifier.
        A call block WITHOUT an identifier deliberately returns ``None``: it
        cannot be matched against an answer, and guessing would corrupt
        history silently.
    """
    if not isinstance(block, dict) or block.get("type") not in _CALL_BLOCK_TYPES:
        return None
    # A Responses block carries BOTH: ``call_id`` names the CALL, ``id`` names
    # the item (``fc_…``). Anthropic's ``tool_use`` has only ``id``, and there
    # it IS the call. So the KEY decides, not truthiness — falling through on a
    # falsy ``call_id`` would hand back an item id that matches no answer and
    # purge a block we merely failed to identify.
    call_id = block.get("call_id") if "call_id" in block else block.get("id")
    return call_id if isinstance(call_id, str) and call_id else None


def _is_dangling_call_block(block: str | dict[Any, Any], answered_ids: set[str]) -> bool:
    """Whether a content block is a call whose result never came back.

    Args:
        block: One entry of a list-shaped ``AIMessage.content``.
        answered_ids: ``tool_call_id`` values that a ``ToolMessage`` answers.

    Returns:
        ``True`` only for an identified call block with no answer. Everything
        else — text, reasoning, an answered call, an unidentifiable one — is
        not dangling and must survive untouched.
    """
    call_id = _call_block_id(block)
    return call_id is not None and call_id not in answered_ids


def _purge_dangling_call_blocks(
    content: MessageContent, answered_ids: set[str]
) -> tuple[MessageContent, int]:
    """Drop unanswered call blocks from a list-shaped content, keeping the rest.

    Text, reasoning and every other block are preserved in order: the defect
    being repaired is an unanswered CALL, not the message around it.

    Args:
        content: An ``AIMessage.content`` — a ``str`` (returned untouched, the
            historical shape) or a list of typed blocks.
        answered_ids: ``tool_call_id`` values that a ``ToolMessage`` answers.

    Returns:
        ``(content, dropped)`` — the content to keep and how many call blocks
        were dropped. ``dropped == 0`` returns the input object unchanged, so
        callers can use the count to detect "nothing to repair".
    """
    if not isinstance(content, list):
        return content, 0
    kept = [block for block in content if not _is_dangling_call_block(block, answered_ids)]
    dropped = len(content) - len(kept)
    return (kept, dropped) if dropped else (content, 0)


def _dangling_repair_operation(
    msg: AIMessage, answered_ids: set[str]
) -> BaseMessage | RemoveMessage | None:
    """The reducer operation that mends ONE message, or ``None`` if it is fine.

    Args:
        msg: A candidate message from the checkpointed history.
        answered_ids: ``tool_call_id`` values that a ``ToolMessage`` answers.

    Returns:
        A same-id replacement, a ``RemoveMessage``, or ``None`` when the
        message is healthy or cannot be repaired safely.
    """
    answered_calls = [tc for tc in msg.tool_calls if tc.get("id") in answered_ids]
    dangling_calls = len(msg.tool_calls) - len(answered_calls)
    content, dangling_blocks = _purge_dangling_call_blocks(msg.content, answered_ids)
    if not dangling_calls and not dangling_blocks:
        return None  # healthy: every call answered, no orphan block left over
    if msg.id is None:
        # Reducer repair is id-based; without an id we cannot replace or
        # remove safely — never silently corrupt, let it surface.
        logger.warning("dangling_tool_calls_message_without_id_skipped")
        return None

    # ``str(content)`` would be the repr of a block list — always truthy, so
    # the removal branch below was unreachable for list-shaped content. The
    # shared coercion answers the real question: is there text left?
    has_content = bool(coerce_content_to_text(content).strip())
    action = "replacement" if (answered_calls or has_content) else "removal"
    if dangling_calls:
        langgraph_history_repairs_total.labels(shape="tool_calls", action=action).inc()
    if dangling_blocks:
        langgraph_history_repairs_total.labels(shape="call_block", action=action).inc()
    logger.warning(
        "stale_dangling_tool_calls_sanitized",
        message_id=msg.id,
        dangling_count=dangling_calls,
        dangling_blocks=dangling_blocks,
        repaired_as=action,
    )
    if action == "removal":
        return RemoveMessage(id=msg.id)
    # Keep the text and the answered calls; strip the dangling ones.
    # ``additional_kwargs`` and response metadata are DELIBERATELY not carried
    # over: providers' raw tool_calls live there too, and the Responses API
    # re-serializes them (measured), which would re-poison the payload this
    # repair exists to fix.
    return AIMessage(content=content, id=msg.id, tool_calls=answered_calls)


def sanitize_stale_dangling_tool_calls(
    messages: list[BaseMessage],
) -> list[BaseMessage | RemoveMessage]:
    """Repair AIMessages whose tool_calls were never answered (ADR-117 Lot 3).

    A cancelled (or hard-killed) run can leave an ``AIMessage`` with
    UNANSWERED ``tool_calls`` in the checkpoint (proven by the 2026-07
    de-risking POC-3: cancellation between the model call and the tool
    execution). A ReAct budget exit does the same, deliberately: the loop
    stops after the model asked for a tool that will never run. On the next
    turn that dangling message poisons strict providers: *"messages with
    'tool_calls' must be followed by tool messages responding to each
    'tool_call_id'"*.

    The call has TWO shapes and both must go. Under
    ``output_version="responses/v1"`` (and on Anthropic, as ``tool_use``) it is
    also a typed block inside list-shaped ``content``, serialized to the
    provider independently of ``tool_calls``. Stripping ``tool_calls`` while
    copying ``content`` verbatim left the block behind AND emptied
    ``tool_calls``, so every later pass skipped the message as healthy: the
    conversation stayed poisoned for good. Measured in production on
    2026-09-02 — one budget exit, eight provider calls dead on
    *"No tool output found for function call …"*, the same call id each time.

    This is the symmetric counterpart of :func:`remove_orphan_tool_messages`
    and returns REDUCER OPERATIONS (same-id replacements / RemoveMessage),
    to be merged through the ``messages`` channel by the caller.

    CRITICAL — call sites: ONLY at turn start (router_node), where every
    prior message belongs to a finished or cancelled turn. NEVER inside the
    messages reducer: mid-run, an AIMessage with not-yet-answered
    tool_calls is a LEGITIMATE transient state between the model call and
    the tool execution super-steps.

    Args:
        messages: Full message history at turn start (last entry is the new
            HumanMessage; it is never affected).

    Returns:
        Reducer operations — empty when the history is healthy:
        - ``RemoveMessage(id=...)`` for dangling AIMessages with no content;
        - a replacement ``AIMessage`` (same id, answered tool_calls only)
          when the message carries content or partially-answered calls.
        Messages without an id are left untouched (id-based repair only).

    Note:
        Replacements DELIBERATELY omit ``additional_kwargs`` and response
        metadata: providers' raw ``tool_calls`` often live in
        ``additional_kwargs`` too, and carrying them over would re-poison
        the serialized payload this repair exists to fix.
    """
    if not messages:
        return []

    answered_ids = {
        msg.tool_call_id
        for msg in messages
        if isinstance(msg, ToolMessage) and getattr(msg, "tool_call_id", None)
    }

    operations: list[BaseMessage | RemoveMessage] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        operation = _dangling_repair_operation(msg, answered_ids)
        if operation is not None:
            operations.append(operation)

    return operations
