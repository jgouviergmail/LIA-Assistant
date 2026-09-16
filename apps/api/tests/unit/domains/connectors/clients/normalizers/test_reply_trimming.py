"""The quoted history and the signature leave a reply before the model reads it (ADR-287).

A thread of eight replies used to reach the model eight times over: every
reply quotes the whole history, and nothing removed it. The corpus holds
eight families of markers in the six languages LIA speaks (48 bodies) plus
two guards — a reply too short to stand alone, and answers interleaved with
the quote — where the trimmer must NOT cut. The measurement script
(`task emails:corpus:measure`) replays the same corpus and, when a
third-party trimmer is installed, scores it beside this one: the choice
between the two is measured, never assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.connectors.clients.normalizers.reply_trimming import trim_quoted_reply

pytestmark = [pytest.mark.unit]

CORPUS = json.loads(
    (Path(__file__).parent / "reply_trimming_corpus.json").read_text(encoding="utf-8")
)
CASES = [
    (family, language, body, spec["kept"])
    for family, spec in CORPUS["families"].items()
    for language, body in spec["bodies"].items()
]


@pytest.mark.parametrize(
    ("family", "language", "body", "kept"),
    CASES,
    ids=[f"{family}-{language}" for family, language, _b, _k in CASES],
)
def test_the_persons_words_are_kept_and_the_rest_leaves(
    family: str, language: str, body: str, kept: str
) -> None:
    assert trim_quoted_reply(body) == kept


def test_every_family_covers_the_six_languages() -> None:
    for family, spec in CORPUS["families"].items():
        assert set(spec["bodies"]) == {"fr", "en", "de", "es", "it", "zh"}, family


@pytest.mark.parametrize("name", sorted(k for k in CORPUS["guards"] if not k.startswith("_")))
def test_a_body_the_trimmer_must_not_cut_is_returned_unchanged(name: str) -> None:
    body = CORPUS["guards"][name]
    assert trim_quoted_reply(body) == body


FORWARDS = [
    (kind, language, case["subject"], case["body"])
    for kind in ("by_subject", "by_banner")
    for language, case in CORPUS["forwards"][kind].items()
]


@pytest.mark.parametrize(
    ("kind", "language", "subject", "body"),
    FORWARDS,
    ids=[f"{kind}-{language}" for kind, language, _s, _b in FORWARDS],
)
def test_a_forward_is_never_trimmed(kind: str, language: str, subject: str, body: str) -> None:
    """The forwarded text under the header block IS the message."""
    assert trim_quoted_reply(body, subject=subject) == body


def test_the_same_header_block_in_a_reply_is_cut() -> None:
    """The forward rule is decided by the subject or the banner, never by the block."""
    body = CORPUS["forwards"]["by_subject"]["en"]["body"]
    assert trim_quoted_reply(body, subject="Re: Quote for room B") != body


def test_empty_and_whitespace_bodies_are_returned_as_is() -> None:
    assert trim_quoted_reply("") == ""
    assert trim_quoted_reply("   \n  ") == "   \n  "
