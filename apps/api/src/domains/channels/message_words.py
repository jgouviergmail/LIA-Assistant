"""What a channel message says to the assistant: a shared point, a reply (Telegram lot 8).

A message is more than its words. A shared POSITION is where the person is: the
turn's consented geolocation, stated in words too, so the model and the
discussion's history read it. A shared PLACE names somewhere, never where the
person is. A REPLY points at an earlier message, whose words travel above it as
a quote, cut at :data:`CHANNEL_QUOTE_MAX_CHARS`.

These words are what the app shows as the person's message: a name or a quote
somebody else may have written renders as itself (ADR-316), never as markup.
"""

from __future__ import annotations

from src.core.constants import CHANNEL_QUOTE_MAX_CHARS
from src.core.i18n_drafts import label_separator
from src.domains.channels.abstractions import ChannelLocation
from src.domains.shared.markdown_literal import literal_quote, markdown_literal
from src.infrastructure.channels.telegram.formatter import get_bot_message


def located_words(location: ChannelLocation, language: str) -> str:
    """The words a shared point stands for, in the person's language.

    Coordinates keep five decimals (about a metre, what a phone's fix can mean)
    and a dot whatever the language, as maps write them.

    Args:
        location: The shared point.
        language: The person's language.

    Returns:
        « 📍 <label>: <coordinates> » for a position (its accuracy when measured),
        « 📍 <label>: <name> — <address> (<coordinates>) » for a place.
    """
    coordinates = f"{location.latitude:.5f}, {location.longitude:.5f}"
    separator = label_separator(language)
    title = location.title
    if title is not None:
        named = markdown_literal(title)
        if location.address:
            named = f"{named} — {markdown_literal(location.address)}"
        return f"📍 {get_bot_message('shared_place', language)}{separator}{named} ({coordinates})"
    measured = "" if location.accuracy_m is None else f" (± {round(location.accuracy_m)} m)"
    return f"📍 {get_bot_message('shared_position', language)}{separator}{coordinates}{measured}"


def with_quote(words: str, quoted: str | None) -> str:
    """The words of a reply under the message they answer.

    Args:
        words: What the person wrote (or said).
        quoted: The words of the message replied to, None when it is no reply.

    Returns:
        A block quote of the answered message, cut at :data:`CHANNEL_QUOTE_MAX_CHARS`
        and rendering as itself, a blank line, then the words; the words alone
        when nothing is quoted.
    """
    if quoted is None or not quoted.strip():
        return words
    return f"{literal_quote(quote_cut(quoted.strip(), CHANNEL_QUOTE_MAX_CHARS))}\n\n{words}"


def quote_cut(words: str, bound: int) -> str:
    """Words a channel quotes: whole, or cut at ``bound`` characters with « … ».

    Args:
        words: The words to quote.
        bound: The most characters kept.

    Returns:
        The words, or their first ``bound`` characters, trailing space dropped,
        followed by « … ».
    """
    if len(words) <= bound:
        return words
    return f"{words[:bound].rstrip()}…"
