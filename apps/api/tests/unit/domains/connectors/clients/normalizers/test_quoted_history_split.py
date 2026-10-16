"""A draft's own words and its quoted history are told apart, losslessly.

Editing a mailbox draft rewrites what the person wrote and must never touch
the history a reply quotes or a forward carries. The split reuses the markers
the ADR-287 trimmer was measured on, with two differences that belong to a
DRAFT: the signature is the person's own text (it stays above the cut), and
there is no minimum length (an empty reply still has its history).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.connectors.clients.normalizers.reply_trimming import split_quoted_history

pytestmark = [pytest.mark.unit]

CORPUS = json.loads(
    (Path(__file__).parent / "reply_trimming_corpus.json").read_text(encoding="utf-8")
)
HISTORY_FAMILIES = (
    "reply_on_wrote",
    "reply_on_wrote_wrapped",
    "original_message_block",
    "header_block",
    "trailing_gt_quotes",
)
NO_HISTORY_FAMILIES = ("signature_dashes", "sent_from_device", "no_quote_at_all")


def _bodies(families: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    return [
        (family, language, body, CORPUS["families"][family]["kept"])
        for family in families
        for language, body in CORPUS["families"][family]["bodies"].items()
    ]


@pytest.mark.parametrize(
    ("family", "language", "body", "kept"),
    _bodies(HISTORY_FAMILIES),
    ids=[f"{f}-{lang}" for f, lang, _b, _k in _bodies(HISTORY_FAMILIES)],
)
def test_the_history_is_cut_where_the_trimmer_cuts(
    family: str, language: str, body: str, kept: str
) -> None:
    own, history = split_quoted_history(body)

    assert own + history == body
    assert own.rstrip() == kept
    assert history.strip()


@pytest.mark.parametrize(
    ("family", "language", "body", "kept"),
    _bodies(NO_HISTORY_FAMILIES),
    ids=[f"{f}-{lang}" for f, lang, _b, _k in _bodies(NO_HISTORY_FAMILIES)],
)
def test_a_body_without_history_is_all_own_words(
    family: str, language: str, body: str, kept: str
) -> None:
    assert split_quoted_history(body) == (body, "")


def test_an_empty_reply_keeps_its_history() -> None:
    body = "On Mon, 12 Oct 2026 at 10:00, Paul <paul@example.com> wrote:\n> Can you confirm?"

    assert split_quoted_history(body) == ("", body)


def test_a_short_answer_is_still_split() -> None:
    """The trimmer keeps a bare « Merci ! » whole; a draft edit must still find the quote."""
    body = "Merci !\n\nLe lun. 12 oct. 2026 à 10:00, Paul <paul@example.com> a écrit :\n> Bonjour"

    own, history = split_quoted_history(body)

    assert own == "Merci !\n\n"
    assert history.startswith("Le lun. 12 oct.")


def test_a_forward_banner_opens_the_history() -> None:
    body = (
        "For your information.\n\n"
        "---------- Forwarded message ----------\n"
        "From: Paul <paul@example.com>\n"
        "Subject: Budget\n\n"
        "Here is the budget."
    )

    own, history = split_quoted_history(body)

    assert own == "For your information.\n\n"
    assert history.startswith("---------- Forwarded message")


def test_a_sentence_naming_a_forwarded_message_is_not_a_banner() -> None:
    body = "I read the forwarded message yesterday, thanks for sending it."

    assert split_quoted_history(body) == (body, "")


def test_an_empty_body_splits_into_nothing() -> None:
    assert split_quoted_history("") == ("", "")
