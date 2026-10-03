"""Escape card text for both HTML and the chat math pipeline."""

import html

_CHAT_TEXT_MARKS = str.maketrans({"$": "&#36;", "\\": "&#92;", "`": "&#96;"})


def escape_html(text: str | None) -> str:
    """Escape a text for an HTML card of the chat.

    ``html.escape`` makes it text for an HTML parser; the chat then reads math
    in that DECODED text, so a dollar, a backslash and a backtick are
    referenced too — measured through the chat's pipeline (review 14): a card
    value « rm -rf $BACKUP_DIR/$OLD » drew a formula, and so did one holding a
    backslash before a bracket. The chat takes a referenced dollar as a
    literal one (``lib/markdown-dollars.ts``).

    Args:
        text: A text a card shows (None or empty gives an empty string).

    Returns:
        The text, safe inside an element or a quoted attribute.
    """
    if not text:
        return ""
    return html.escape(str(text)).translate(_CHAT_TEXT_MARKS)
