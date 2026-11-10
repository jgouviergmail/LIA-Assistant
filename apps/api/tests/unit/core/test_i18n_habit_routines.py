"""The routine a recurring-need proposal creates, in the person's language (ADR-375)."""

from __future__ import annotations

import pytest

from src.core.i18n_habit_routines import HABIT_ROUTINE_COPY, routine_copy
from src.domains.habits.need_domains import automatable_domains

pytestmark = pytest.mark.unit

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


def test_every_language_carries_every_automatable_domain() -> None:
    assert set(HABIT_ROUTINE_COPY) == set(LANGUAGES)
    for language in LANGUAGES:
        assert set(HABIT_ROUTINE_COPY[language]) == automatable_domains(), language


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_text_is_written(language: str) -> None:
    for domain, (title, day, week) in HABIT_ROUTINE_COPY[language].items():
        assert title.strip() and day.strip() and week.strip(), (language, domain)
        assert day != week, (language, domain)


def test_the_horizon_picks_the_prompt() -> None:
    title, prompt = routine_copy("event", "day", "fr")
    assert title == HABIT_ROUTINE_COPY["fr"]["event"][0]
    assert prompt == HABIT_ROUTINE_COPY["fr"]["event"][1]
    assert routine_copy("event", "week", "fr")[1] == HABIT_ROUTINE_COPY["fr"]["event"][2]


def test_a_frontend_chinese_code_is_normalised() -> None:
    assert routine_copy("email", "day", "zh") == routine_copy("email", "day", "zh-CN")


def test_a_domain_that_cannot_be_automated_has_no_routine() -> None:
    with pytest.raises(KeyError):
        routine_copy("web_search", "day", "fr")
