"""
External content wrapping for prompt injection prevention.

Wraps untrusted external content (web pages, search results) in XML-like markers
that signal to the LLM that the content is data-only and should not be interpreted
as instructions.

Architecture:
    wrap_external_content(content, source_url, source_type) -> str
        Wraps content with <external_content> tags and an UNTRUSTED warning.
        Escapes any occurrences of the tag itself within the content.

    strip_external_markers(content) -> str
        Removes wrapping markers, returning the original content.
        Useful for display or storage where markers are not needed.

Security:
    - Prevents prompt injection via web-fetched content
    - Escapes tag occurrences in content to prevent marker breakout
    - Feature-flagged via external_content_wrapping_enabled setting
"""

import re

from src.core.constants import (
    EXTERNAL_CONTENT_CLOSE_TAG,
    EXTERNAL_CONTENT_OPEN_TAG,
    EXTERNAL_CONTENT_WARNING,
)


def _escape_tags(content: str) -> str:
    """Escape external_content tags within content to prevent marker breakout.

    Replaces literal occurrences of the open/close tags with escaped versions
    so that the content cannot prematurely close the wrapper.
    """
    # Escape opening tag: <external_content -> &lt;external_content
    content = content.replace("<external_content", "&lt;external_content")
    # Escape closing tag: </external_content> -> &lt;/external_content&gt;
    content = content.replace("</external_content>", "&lt;/external_content&gt;")
    return content


def wrap_external_content(
    content: str,
    source_url: str,
    source_type: str = "web_page",
) -> str:
    """Wrap untrusted external content with safety markers.

    Adds XML-like tags and an UNTRUSTED warning that instructs the LLM
    to treat the enclosed content as data only.

    Args:
        content: The raw external content to wrap.
        source_url: URL or identifier of the content source.
        source_type: Type of content (e.g., "web_page", "search_synthesis", "search_snippet").

    Returns:
        Wrapped content string with safety markers.
    """
    if not content:
        return content

    escaped_content = _escape_tags(content)

    # Sanitize source_url: escape quotes to prevent XML attribute injection
    safe_source_url = source_url.replace('"', "&quot;")

    return (
        f'{EXTERNAL_CONTENT_OPEN_TAG} source="{safe_source_url}" type="{source_type}">'
        f"\n{EXTERNAL_CONTENT_WARNING}\n"
        f"{escaped_content}\n"
        f"{EXTERNAL_CONTENT_CLOSE_TAG}"
    )


# Regex pattern to strip external content markers (greedy across multiple wrapped blocks)
_STRIP_PATTERN = re.compile(
    r"<external_content[^>]*>\s*"
    + re.escape(EXTERNAL_CONTENT_WARNING)
    + r"\s*(.*?)\s*</external_content>",
    re.DOTALL,
)


def _unescape_tags(content: str) -> str:
    """Reverse the escaping done by _escape_tags."""
    content = content.replace("&lt;external_content", "<external_content")
    content = content.replace("&lt;/external_content&gt;", "</external_content>")
    return content


def strip_external_markers(content: str) -> str:
    """Remove external content wrapping markers, returning original content.

    Useful for display, storage, or contexts where safety markers are not needed.
    Handles multiple wrapped blocks within a single string.

    Args:
        content: Content potentially containing external_content markers.

    Returns:
        Content with markers removed and tag escaping reversed.
    """
    if not content:
        return content

    def _replace_match(match: re.Match) -> str:
        inner = match.group(1)
        return _unescape_tags(inner)

    return _STRIP_PATTERN.sub(_replace_match, content)
