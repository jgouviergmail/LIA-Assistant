"""Who writes an e-mail sent in the person's name (ADR-383 amendment 2026-11-16).

The person's own words are kept exactly; any other text the agent proposed is what the
e-mail must SAY, handed to LIA's writer. The cases below are the measured table of
2026-11-15 (26 cases, four languages) plus the borders the rule must hold.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import EMAIL_REWRITE_MAX_SHARE
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.emails import authorship
from src.domains.agents.emails.authorship import (
    SettledWords,
    is_dictated,
    person_words_of,
    settle_words,
)

pytestmark = pytest.mark.unit

_INTENT_LATE = "Écris un mail à paul@example.com pour lui dire que je serai en retard demain."
_DICTATED_LATE = (
    "Envoie à paul@example.com : « Salut Paul, je serai en retard ce soir. À plus, Jean »"
)


@pytest.mark.parametrize(
    ("message", "body", "dictated"),
    [
        # What the person asked for, written by the agent: never theirs.
        (_INTENT_LATE, "Bonjour Paul,\n\nJe serai en retard demain.\n\nJean", False),
        ("Réponds oui à Paul par mail pour samedi", "Oui", False),
        ("Réponds oui à Paul par mail pour samedi", "Oui, c'est d'accord pour samedi.", False),
        ("Dis à paul@example.com que je ne viens pas", "je ne viens pas", False),
        ("Écris à paul@example.com : dis-lui que je serai en retard", "Je serai en retard.", False),
        (
            "Envoie à paul@example.com la liste de mes rendez-vous de demain",
            "Voici mes rendez-vous : 9 h dentiste, 14 h réunion budget",
            False,
        ),
        (
            "envoie à paul@example.com : je seré en retard ce soir dsl",
            "Je serai en retard ce soir, désolé.",
            False,
        ),
        ("Envoie à john@example.com en anglais : « je serai en retard »", "I will be late.", False),
        ("给 li@example.com 发邮件说我明天会迟到", "我明天会迟到", False),
        (
            "Write an email to anna@example.com to tell her I'll send the report on Friday.",
            "I'll send the report on Friday.",
            False,
        ),
        # The dictated words, decorated by the agent: no longer the person's alone.
        (
            "Envoie à paul@example.com : « je serai en retard ce soir »",
            "Bonjour Paul,\n\nJe serai en retard ce soir.\n\nJean",
            False,
        ),
        # Words the person MARKED: quoted, or introduced by a colon or a line break.
        (_DICTATED_LATE, "Salut Paul, je serai en retard ce soir. À plus, Jean", True),
        (_DICTATED_LATE, "Salut Paul,\n\nJe serai en retard ce soir.\n\nÀ plus,\nJean", True),
        (
            "Mail à marc@example.com, dis-lui exactement : la réunion est déplacée à 15 h.",
            "La réunion est déplacée à 15 h.",
            True,
        ),
        ("Envoie à paul@example.com « OK »", "OK", True),
        (
            "Envoie ce mail à claire@example.com : Coucou ! Merci pour samedi. Bises, Jean",
            "Coucou ! Merci pour samedi. Bises, Jean",
            True,
        ),
        (
            "Envoie à paul@example.com la liste : lait, œufs, farine, beurre",
            "Lait, œufs, farine, beurre",
            True,
        ),
        (
            "Envoie à paul@example.com : Rendez-vous à 15:30 demain devant la gare",
            "Rendez-vous à 15:30 demain devant la gare",
            True,
        ),
        (
            "Envoie ça à claire@example.com\nMerci pour samedi, c'était top ! Jean",
            "Merci pour samedi, c'était top ! Jean",
            True,
        ),
        ("给 li@example.com 发邮件：「我明天会迟到」", "我明天会迟到", True),
        ("给 li@example.com 发邮件：我明天会迟到", "我明天会迟到", True),
        (
            "Schick an anna@example.com: „Ich komme morgen später.“",
            "Ich komme morgen später.",
            True,
        ),
        ('Send to anna@example.com "See you on Friday"', "See you on Friday", True),
        (
            "Envoie à paul@example.com : « J’arrive à l’heure, c’est promis »",
            "J'arrive à l'heure, c'est promis",
            True,
        ),
        (_DICTATED_LATE, "<p>Salut Paul, je serai en retard ce soir. À plus, Jean</p>", True),
        # The message IS the e-mail (an answer to « what should it say? »).
        ("Salut Paul, je serai en retard. Jean", "Salut Paul,\nje serai en retard.\nJean", True),
        # Nothing to compare: no words of its own.
        ("Réponds 👍 à Paul", "👍", False),
        (_DICTATED_LATE, "", False),
        ("", "Salut Paul", False),
    ],
)
def test_only_the_words_the_person_marked_are_theirs(
    message: str, body: str, dictated: bool
) -> None:
    assert is_dictated(body, message) is dictated


@pytest.mark.parametrize(
    "unit",
    ["«a", "“a", ": a ", "\n", '"a', "„a", "a:", "「", "『", "‹a", "15:30 "],
    ids=[
        "open_quote",
        "curly_quote",
        "colons",
        "line_breaks",
        "straight_quotes",
        "low_quote",
        "word_colon",
        "cjk_bracket",
        "cjk_white_bracket",
        "single_guillemet",
        "times",
    ],
)
def test_reading_the_marks_stays_linear_on_hostile_input(unit: str) -> None:
    """The person's message can be long: the rule reads it once, never once per mark.

    Measured as the process's CPU time: the property is the work done, and parallel
    workers slowing the wall clock must not read as a regression (0.01 s measured
    linear, 3.8 s when a span could run past the next opening mark, 2026-11-16).
    """
    message = unit * (40_000 // len(unit))

    started = time.process_time()
    is_dictated("a " * 2_000, message)

    assert time.process_time() - started < 0.5


def _capacity_tokens() -> int:
    """What the writer may write back whole, read where production reads it."""
    return int(
        get_llm_config_for_agent(settings, "email_agent").max_tokens * EMAIL_REWRITE_MAX_SHARE
    )


def test_no_text_proposed_leaves_the_instruction_as_given() -> None:
    settled = settle_words(tool="t", body=None, instruction="say yes", person_words=("reply yes",))

    assert settled == SettledWords(body=None, instruction="say yes")


def test_a_call_outside_a_run_keeps_the_text_it_was_given() -> None:
    """No run context: the caller is code (a script, a test), not an agent."""
    settled = settle_words(tool="t", body="Hello Paul", instruction=None, person_words=None)

    assert settled == SettledWords(body="Hello Paul", instruction=None)


def test_dictated_words_are_kept_exactly() -> None:
    body = "Salut Paul, je serai en retard ce soir. À plus, Jean"

    settled = settle_words(
        tool="t", body=body, instruction="a subject", person_words=(_DICTATED_LATE,)
    )

    assert settled == SettledWords(body=body, instruction="a subject")


def test_a_text_the_agent_wrote_becomes_what_the_writer_must_say() -> None:
    body = "Bonjour Paul,\n\nJe serai en retard demain : 9 h 45 au lieu de 9 h.\n\nJean"

    settled = settle_words(tool="t", body=body, instruction=None, person_words=(_INTENT_LATE,))

    assert settled.body is None
    assert settled.instruction is not None
    assert settled.instruction.endswith(body)
    assert authorship.proposed_header() in settled.instruction


def test_the_agents_own_instruction_leads_what_it_drafted() -> None:
    body = "Paul, je serai en retard."

    settled = settle_words(
        tool="t", body=body, instruction="Tell Paul, warmly", person_words=(_INTENT_LATE,)
    )

    assert settled.instruction is not None
    assert settled.instruction.startswith("Tell Paul, warmly\n\n")
    assert settled.instruction.endswith(body)


def test_markup_the_agent_wrote_reaches_the_writer_as_its_words() -> None:
    settled = settle_words(
        tool="t",
        body="<p>Je serai <b>en retard</b>.</p>",
        instruction=None,
        person_words=(_INTENT_LATE,),
    )

    assert settled.instruction is not None
    assert "<b>" not in settled.instruction
    assert "en retard" in settled.instruction


def test_a_text_too_long_to_be_written_back_is_kept_rather_than_cut() -> None:
    body = "mot " * (_capacity_tokens() * 2)

    settled = settle_words(tool="t", body=body, instruction=None, person_words=(_INTENT_LATE,))

    assert settled == SettledWords(body=body, instruction=None)


def test_a_text_within_what_the_writer_can_write_back_is_rewritten() -> None:
    body = "mot " * (_capacity_tokens() // 4)

    settled = settle_words(tool="t", body=body, instruction=None, person_words=(_INTENT_LATE,))

    assert settled.body is None


def test_the_persons_words_are_read_from_the_tools_own_runtime() -> None:
    context = LiaRuntimeContext(
        user_id=uuid4(),
        thread_id="thread",
        conversation_id="conversation",
        user_message="« Bonjour »",
    )

    assert person_words_of(SimpleNamespace(context=context)) == ("« Bonjour »",)
    assert person_words_of(SimpleNamespace(context=None)) is None
    assert person_words_of(None) is None


def test_a_resumed_turn_reads_the_request_it_began_with_too() -> None:
    """« Which Paul? » answered: the run's message is the answer, the request still counts."""
    context = LiaRuntimeContext(
        user_id=uuid4(),
        thread_id="thread",
        conversation_id="conversation",
        user_message="Paul Martin",
        turn_request=_DICTATED_LATE,
    )

    said = person_words_of(SimpleNamespace(context=context))

    assert said == ("Paul Martin", _DICTATED_LATE)
    body = "Salut Paul, je serai en retard ce soir. À plus, Jean"
    settled = settle_words(tool="t", body=body, instruction=None, person_words=said)
    assert settled == SettledWords(body=body, instruction=None)


def test_a_new_turn_reads_its_own_message_once() -> None:
    context = LiaRuntimeContext(
        user_id=uuid4(),
        thread_id="thread",
        conversation_id="conversation",
        user_message=_INTENT_LATE,
        turn_request=_INTENT_LATE,
    )

    assert person_words_of(SimpleNamespace(context=context)) == (_INTENT_LATE,)
