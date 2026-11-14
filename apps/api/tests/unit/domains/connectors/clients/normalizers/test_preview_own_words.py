"""A message's PREVIEW says its writer's words, then the history it quotes (ADR-379).

A provider's preview is the body's first characters on one line: a short reply runs
straight into what it answers — measured on a real Graph mailbox (2026-11-11), seventeen
characters of a reply, then forty underscores and the quoted header block. « What I
answered » must be the person's words alone, so the trimmer's own markers (ADR-287) are
searched INSIDE the line. The corpus is the trimmer's: one vocabulary, two readers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.text_clip import one_line
from src.domains.connectors.clients.normalizers.reply_trimming import preview_own_words

pytestmark = [pytest.mark.unit]

CORPUS = json.loads(
    (Path(__file__).parent / "reply_trimming_corpus.json").read_text(encoding="utf-8")
)
#: The families whose tail is someone else's words.
QUOTING = (
    "reply_on_wrote",
    "reply_on_wrote_wrapped",
    "original_message_block",
    "header_block",
    "trailing_gt_quotes",
)
#: The families whose tail is still the writer's own text: a signature is theirs.
OWN_TAIL = ("signature_dashes", "sent_from_device", "no_quote_at_all")


def _cases(families: tuple[str, ...]) -> list[tuple[str, str, str, str]]:
    return [
        (family, language, body, CORPUS["families"][family]["kept"])
        for family in families
        for language, body in CORPUS["families"][family]["bodies"].items()
    ]


def test_every_family_of_the_corpus_is_read_one_way_or_the_other() -> None:
    """A family added to the trimmer's corpus must be placed here too."""
    assert set(QUOTING) | set(OWN_TAIL) == set(CORPUS["families"])


@pytest.mark.parametrize(
    ("family", "language", "body", "kept"),
    _cases(QUOTING),
    ids=[f"{family}-{language}" for family, language, _b, _k in _cases(QUOTING)],
)
def test_the_writers_words_are_kept_and_the_quoted_history_leaves(
    family: str, language: str, body: str, kept: str
) -> None:
    assert preview_own_words(one_line(body)) == one_line(kept)


@pytest.mark.parametrize(
    ("family", "language", "body", "kept"),
    _cases(OWN_TAIL),
    ids=[f"{family}-{language}" for family, language, _b, _k in _cases(OWN_TAIL)],
)
def test_a_signature_is_the_writers_own_text_and_stays(
    family: str, language: str, body: str, kept: str
) -> None:
    assert preview_own_words(one_line(body)) == one_line(body)


def test_a_bare_thanks_is_all_the_writer_said() -> None:
    """The body trimmer keeps the quote under so short a reply; an excerpt of « what I
    answered » is the two words."""
    assert preview_own_words(one_line(CORPUS["guards"]["bare_thanks_reply"])) == "Merci !"


@pytest.mark.parametrize("kind", ["by_banner", "by_subject"])
@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh"])
def test_the_words_above_a_forwarded_message_are_the_writers(kind: str, language: str) -> None:
    body = CORPUS["forwards"][kind][language]["body"]
    own_words = body.split("\n\n", 1)[0]

    assert preview_own_words(one_line(body)) == own_words


def test_the_rule_outlook_draws_under_a_reply_opens_the_history() -> None:
    """Graph's preview of a reply, as measured: the words, a rule of underscores, the
    header block — here cut by the preview's bound before any subject line."""
    preview = (
        f"See you Friday. {'_' * 40} From: Alice Vernier <alice@example.com> Sent: Tuesday, Sept"
    )

    assert preview_own_words(preview) == "See you Friday."


@pytest.mark.parametrize(
    "preview",
    [
        "> Peux-tu venir lundi ? Oui, à 10h. > Et apporter le contrat ? Non, mercredi.",
        "On Tue, Sep 15, 2026 at 10:24 AM Alice Vernier <alice@example.com> wrote: > Can you? Yes.",
    ],
    ids=["interleaved-answers", "answer-under-the-quote"],
)
def test_a_preview_opening_on_the_history_hands_over_nothing(preview: str) -> None:
    """Words that may be someone else's are never handed over as the writer's."""
    assert preview_own_words(preview) == ""


@pytest.mark.parametrize(
    "preview",
    [
        "On the plan he wrote: fine by me. See you there.",
        "Le directeur a écrit : la réunion est maintenue.",
        "If the quote is > 100 EUR we stop there.",
        "The plan -- as discussed -- holds for Friday.",
        "De toute façon, objet du jour : le budget.",
        "Fill in your name here: ____ and send it back.",
    ],
    ids=["wrote-in-prose", "a-ecrit-in-prose", "one-greater-than", "dashes", "de-objet", "blank"],
)
def test_ordinary_prose_is_left_whole(preview: str) -> None:
    assert preview_own_words(preview) == preview
