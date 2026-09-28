"""Stream a prepared HITL text token by token, keeping what the reader must see.

The dialogs whose text is written in code — the FOR_EACH and destructive
confirmations, a draft batch, a clarification, a disambiguation — stream it
word by word so the chat draws it the way it draws a model's answer. They split
it with ``str.split()``, which breaks on EVERY whitespace, the no-break space a
French colon takes included, and re-emitted each piece followed by an ordinary
space: the typography the text carried never reached the reader, nor the stored
question (ADR-323 review). Two of them did not even keep the line breaks.
An item preview drawn on one line had the same flaw: every HITL and draft
preview — the dialogs, the drafts' rows, the card's title, a result's
label and excerpt — goes through ``core.text_clip.one_line``, and a tool
call's arguments, a program's values, through ``core.text_clip.clip_data``.
"""

from __future__ import annotations

from collections.abc import Iterator


def text_tokens(text: str) -> Iterator[str]:
    """Yield ``text`` as stream tokens: every word followed by a space, a newline
    after every line.

    Only an ordinary space separates two words; any other character — a
    no-break space included — stays inside the word it belongs to. A blank
    text yields nothing: a lone newline would be archived as an empty bubble.

    Args:
        text: The prepared text.

    Yields:
        The tokens, in order.
    """
    if not text.strip():
        return
    for line in text.split("\n"):
        for word in line.split(" "):
            if word:
                yield word + " "
        yield "\n"
