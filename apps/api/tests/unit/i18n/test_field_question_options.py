"""A clarification question offers its choices in the reader's punctuation (ADR-323).

It was cut at its « ? » and closed on « ? (options) » after a space in every
language: « this task ? (High, …) » in English, the French no-break space made
ordinary, « ？ ? » in Chinese — the question the semantic validator asks when
a plan misses a field.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import HitlMessages

pytestmark = pytest.mark.unit

_NBSP = chr(0xA0)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("fr", f"Quelle est la priorité de cette tâche{_NBSP}? (Haute, Moyenne, Basse)"),
        ("en", "What is the priority of this task? (High, Medium, Low)"),
        ("es", "¿Cuál es la prioridad de esta tarea? (Alta, Media, Baja)"),
        ("de", "Welche Priorität hat diese Aufgabe? (Hoch, Mittel, Niedrig)"),
        ("it", "Qual è la priorità di questa attività? (Alta, Media, Bassa)"),
        ("zh-CN", "这个任务的优先级是什么？（高、中、低）"),
    ],
)
def test_the_choices_follow_the_question_in_its_own_punctuation(
    language: str, expected: str
) -> None:
    assert HitlMessages.format_field_question_with_options("task", "priority", language) == expected


def test_a_field_without_choices_is_asked_as_it_is() -> None:
    question = HitlMessages.get_field_question("email", "recipient", "fr")

    assert HitlMessages.format_field_question_with_options("email", "recipient", "fr") == question
