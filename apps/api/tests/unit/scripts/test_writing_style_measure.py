"""The writing-style bench reads a draft the way it claims (lot 19): its tallies are the proof."""

from __future__ import annotations

import pytest

from scripts.emails.measure_writing_style import (
    ARMS,
    COMPOSE_ARMS,
    EXAMPLES_SHOWN,
    PERSONAS,
    Draft,
    answer_text,
    compose_prompt,
    composed_body,
    draft_messages,
    leaked,
    marks,
    profile_request,
    tally,
)
from src.domains.agents.emails.writing_style import compose_block, reply_block

pytestmark = pytest.mark.unit

SEB = next(p for p in PERSONAS if p.key == "seb")
MARIE = next(p for p in PERSONAS if p.key == "marie")
JAKE = next(p for p in PERSONAS if p.key == "jake")


def test_every_persona_carries_its_own_style_in_what_it_sent() -> None:
    """The corpus is coherent: each sent e-mail carries the marks its card states."""
    for persona in PERSONAS:
        for sent in persona.sent:
            carried = marks(persona.style, sent)
            assert carried["greeting"] and carried["closing"] and carried["signature"], (
                persona.key,
                sent[:40],
            )
        assert len(persona.received) == 3 and len(persona.sent) > EXAMPLES_SHOWN


def test_no_received_email_mentions_a_planted_fact() -> None:
    """A planted fact in a draft can only come from the person's past mail."""
    for persona in PERSONAS:
        for received in persona.received:
            assert leaked(persona, received.text + received.instruction) == []


def test_a_reply_in_the_persons_voice_carries_their_marks() -> None:
    reply = "Salut Claire,\n\nVendredi 10h ça me va 👍\n\n++\nSeb"
    assert marks(SEB.style, reply) == {
        "greeting": True,
        "closing": True,
        "signature": True,
        "emoji": True,
        "length": True,
        "register": True,
    }


def test_a_generic_reply_misses_them() -> None:
    reply = (
        "Bonjour Claire,\n\nVendredi à 10h me convient, merci de votre message.\n\nCordialement,"
    )
    carried = marks(SEB.style, reply)
    assert not carried["greeting"] and not carried["closing"] and not carried["signature"]
    assert not carried["emoji"] and not carried["register"]


def test_a_writer_who_never_signs_is_matched_by_an_unsigned_reply() -> None:
    style = MARIE.style.__class__(**{**MARIE.style.__dict__, "signature": None})
    assert marks(style, "Bonjour,\n\nC'est noté.\n\nBien cordialement,")["signature"]
    assert not marks(style, "Bonjour,\n\nC'est noté.\n\nBien cordialement,\nMarie Durand")[
        "signature"
    ]


def test_a_copied_fact_is_caught() -> None:
    assert leaked(JAKE, "Hi Emma,\n\nFriday works, see you at Fulton.\n\nThx,\nJ") == ["Fulton"]


def test_each_arm_adds_only_its_own_block() -> None:
    received = SEB.received[0]
    plain, profile, examples = (draft_messages(SEB, received, arm, "writes short") for arm in ARMS)

    assert plain[0].content == profile[0].content == examples[0].content  # one static prefix
    assert reply_block("writes short") in profile[1].content
    assert "writes short" not in plain[1].content
    assert (
        SEB.sent[0] in examples[1].content and SEB.sent[EXAMPLES_SHOWN] not in examples[1].content
    )
    for messages in (plain, profile, examples):
        assert received.text in messages[1].content and received.instruction in messages[1].content


def test_the_tally_counts_marks_and_leaks_per_family_and_arm() -> None:
    rows = [
        Draft("seb", "r1", "m", "plain", "x", marks={"greeting": False, "closing": True}),
        Draft("seb", "r1", "m", "profile", "y", marks={"greeting": True, "closing": True}),
        Draft(
            "seb",
            "r2",
            "m",
            "profile",
            "z",
            marks={"greeting": True, "closing": False},
            leaked=["Orion"],
        ),
    ]

    summary = tally(rows)

    assert summary["m / plain"]["marks"] == "1/2" and summary["m / plain"]["leaks"] == 0
    assert summary["m / profile"]["marks"] == "3/4" and summary["m / profile"]["leaks"] == 1
    assert summary["m / profile"]["per_mark"] == {"closing": "1/2", "greeting": "2/2"}


def test_every_persona_asks_for_new_mails_that_name_no_planted_fact() -> None:
    """A composed mail is scored like a reply: its instruction plants nothing to copy."""
    for persona in PERSONAS:
        assert len(persona.composed) == 2
        for item in persona.composed:
            assert leaked(persona, item.recipient + item.instruction) == []


def test_the_compose_arms_differ_by_the_style_block_alone() -> None:
    item = SEB.composed[0]
    plain, profile = (compose_prompt(SEB, item, arm, "writes short") for arm in COMPOSE_ARMS)
    block = compose_block("writes short")

    assert "writes short" not in plain
    assert profile.replace(block, "", 1) == plain  # nothing else moved
    for prompt in (plain, profile):
        assert item.instruction in prompt and item.recipient in prompt


def test_a_composed_answer_is_scored_on_its_body() -> None:
    answer = '{"subject": "Vendredi", "body": "Salut Claire,\\n\\nVendredi 10h ?\\n\\n++\\nSeb"}'
    assert composed_body(answer) == "Salut Claire,\n\nVendredi 10h ?\n\n++\nSeb"
    assert composed_body("```json\n" + answer + "\n```").startswith("Salut Claire")
    assert composed_body("not json") == ""


def test_an_answer_of_blocks_is_read_as_its_words() -> None:
    """A Responses-API family answers with blocks: its repr would read as no greeting at all."""
    reply = "Salut Claire,\n\nOk pour vendredi.\n\n++\nSeb"
    blocks = [{"type": "text", "text": reply}]
    assert answer_text(blocks) == reply
    assert marks(SEB.style, answer_text(blocks))["greeting"]


def test_the_profile_is_asked_as_production_asks_it() -> None:
    messages = profile_request(SEB)

    assert "Never say WHAT they wrote about" in str(messages[0].content)
    assert all(mail.split("\n")[0] in str(messages[-1].content) for mail in SEB.sent)
