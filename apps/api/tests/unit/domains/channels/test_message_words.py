"""What a channel message says to the assistant (Telegram lot 8).

A shared pin said nothing and a reply lost the message it answered: a position
reads as the person's position, a place as the place it names, and the words
of a reply sit under the message they answer, quoted as itself.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.constants import CHANNEL_QUOTE_MAX_CHARS
from src.core.i18n_drafts import label_separator
from src.domains.channels.abstractions import ChannelLocation
from src.domains.channels.message_words import located_words, quote_cut, with_quote
from src.infrastructure.channels.telegram.formatter import get_bot_message

pytestmark = pytest.mark.unit

#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


class TestAPositionReadsAsThePersons:
    def test_it_is_named_with_its_coordinates_and_accuracy(self) -> None:
        words = located_words(ChannelLocation(48.856613, 2.352222, accuracy_m=12.6), _PERSON)

        label = get_bot_message("shared_position", _PERSON)
        assert words == f"📍 {label}{label_separator(_PERSON)}48.85661, 2.35222 (± 13 m)"

    def test_a_position_with_no_accuracy_states_none(self) -> None:
        words = located_words(ChannelLocation(-33.8688, 151.2093), _PERSON)

        assert words.endswith("-33.86880, 151.20930")


class TestAPlaceReadsAsThePlace:
    def test_it_is_named_by_its_title_and_address(self) -> None:
        place = ChannelLocation(48.85837, 2.29448, title="Tour Eiffel", address="Champ de Mars")

        words = located_words(place, _PERSON)

        label = get_bot_message("shared_place", _PERSON)
        assert words == (
            f"📍 {label}{label_separator(_PERSON)}Tour Eiffel — Champ de Mars (48.85837, 2.29448)"
        )

    def test_a_place_with_no_address_is_its_title(self) -> None:
        words = located_words(ChannelLocation(1.0, 2.0, title="Home"), _PERSON)

        assert words.endswith(f"{label_separator(_PERSON)}Home (1.00000, 2.00000)")

    def test_a_name_somebody_else_wrote_draws_nothing(self) -> None:
        """A venue can come from any bot: its words render as themselves in the app."""
        place = ChannelLocation(1.0, 2.0, title="[win](https://x.example)", address="<b>here</b>")

        words = located_words(place, _PERSON)

        assert "[" not in words and "<" not in words
        assert "&#91;win&#93;" in words and "&#60;b&#62;here" in words


class TestAReplySitsUnderWhatItAnswers:
    def test_the_answered_message_is_quoted_above_the_words(self) -> None:
        assert with_quote("and this one?", "1. Paris\n2. Lyon") == (
            "> 1. Paris\n> 2. Lyon\n\nand this one?"
        )

    def test_a_long_message_is_quoted_cut(self) -> None:
        quoted = "word " * CHANNEL_QUOTE_MAX_CHARS

        first = with_quote("why?", quoted).split("\n\n")[0]

        assert first.endswith("…")
        assert len(first) <= len("> ") + CHANNEL_QUOTE_MAX_CHARS + len("…")

    @pytest.mark.parametrize("quoted", [None, "", "  \n "], ids=["none", "empty", "blank"])
    def test_nothing_to_quote_leaves_the_words(self, quoted: str | None) -> None:
        assert with_quote("why?", quoted) == "why?"

    def test_quoted_markup_draws_nothing(self) -> None:
        quoted = with_quote("ok", "see [this](https://x.example) `code`")

        assert quoted.startswith("> see &#91;this&#93;(https://x.example) &#96;code&#96;")


class TestQuoteCut:
    def test_words_within_the_bound_are_whole(self) -> None:
        assert quote_cut("short", 10) == "short"

    def test_words_past_the_bound_end_on_an_ellipsis(self) -> None:
        assert quote_cut("one two three", 8) == "one two…"
