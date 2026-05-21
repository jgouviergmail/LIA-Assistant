"""Plain-text normalization for LangChain message content.

LLM responses are LangChain messages whose ``.content`` is a plain ``str`` for
most providers (OpenAI, Anthropic text, Gemini <= 2.5, DeepSeek, Ollama, ...).
**Gemini 3.x**, however, returns ``content`` as a **list of content blocks**
(e.g. ``[{"type": "text", "text": "...", "index": 0}]``). Any code that treats
such content as a string breaks: regex / ``.strip()`` / ``.lower()`` raise
``AttributeError`` or ``TypeError``, a list assigned to a ``str``-typed Pydantic
field raises ``ValidationError`` (e.g. ``ChatStreamChunk``), ``json.loads`` on a
list raises ``TypeError``, and f-strings silently embed the dict repr.

This module exposes a single canonical primitive, :func:`coerce_content_to_text`,
used at the boundaries where a ``str`` is contractually required. It is
deliberately non-destructive: callers normalize the *value they consume*, never
the source-of-truth message stored in graph state. This mirrors LangChain Core
1.2+ ``BaseMessage.text`` semantics (concatenate ``text`` blocks, no separator)
while remaining usable on raw ``content`` values where no message object is at
hand.
"""

from __future__ import annotations

from typing import Any

__all__ = ["coerce_content_to_text"]


def coerce_content_to_text(content: Any) -> str:
    """Normalize a LangChain message ``content`` value to plain text.

    Handles every shape ``AIMessage.content`` / ``AIMessageChunk.content`` can
    take across providers so downstream string operations are always safe:

    - ``str`` -> returned unchanged (the common case; zero behavior change for
      non-Gemini-3.x models).
    - ``list`` of content blocks (Gemini 3.x) -> the ``text`` of every ``text``
      block is concatenated. Reasoning / thought-signature / tool-use and other
      non-text blocks are ignored, so only the user-facing answer text remains.
    - ``None`` -> empty string.
    - Anything else -> ``str(content)`` as a last-resort fallback.

    Args:
        content: A message's ``.content`` (``str``, ``list`` of blocks, ``None``,
            or any other value). Typed ``Any`` deliberately: this is a defensive
            coercion boundary for the loosely-typed LangChain ``.content`` and
            ``getattr(msg, "content", ...)`` values callers pass — narrowing it
            would fight the function's purpose and drop robustness against
            unexpected shapes (the ``str()`` fallback below handles them).

    Returns:
        Plain text suitable for regex, ``.strip()``, ``str``-typed Pydantic
        fields, SSE serialization and JSON parsing.

    Example:
        >>> coerce_content_to_text("hello")
        'hello'
        >>> coerce_content_to_text([{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}])
        'hello'
        >>> coerce_content_to_text([{"type": "thinking", "thinking": "..."}])
        ''
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)
