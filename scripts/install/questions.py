"""Declarative installer questionnaire (B10/B13).

Ordering is meaningful: the wizard language is asked first (it drives every
later prompt), exposure gates its conditional follow-ups, and secrets come
last so an operator can abort before typing anything sensitive.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scripts.install.answers import (
    is_valid_domain,
    is_valid_email,
    is_valid_host,
    is_valid_password_shape,
)
from scripts.install.model import (
    APP_LANGUAGES,
    PASSWORD_RULES,
    REQUIRED_PROVIDER_IDS,
    WIZARD_LANGUAGES,
    Exposure,
    Question,
    QuestionKind,
)


def _needs_lan(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") is Exposure.LAN


def _needs_domains(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") in (Exposure.PROXY, Exposure.CADDY)


def _needs_caddy(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") is Exposure.CADDY


def build_questions() -> tuple[Question, ...]:
    """The complete ordered questionnaire (public first, secrets last)."""
    password_args = (
        ("min_length", str(PASSWORD_RULES.min_length)),
        ("min_uppercase", str(PASSWORD_RULES.min_uppercase)),
        ("min_digits", str(PASSWORD_RULES.min_digits)),
        ("min_special", str(PASSWORD_RULES.min_special)),
    )
    provider_questions = tuple(
        Question(
            key=f"provider_key_{provider}",
            kind=QuestionKind.SECRET,
            message_id="question.provider_key",
            secret=True,
            validator=lambda value: bool(value.strip()),
            message_args=(("provider", provider),),
        )
        for provider in REQUIRED_PROVIDER_IDS
    )
    return (
        Question(
            key="wizard_language",
            kind=QuestionKind.CHOICE,
            message_id="question.wizard_language",
            choices=WIZARD_LANGUAGES,
            default="en",
        ),
        Question(
            key="exposure",
            kind=QuestionKind.CHOICE,
            message_id="question.exposure",
            choices=tuple(e.value for e in Exposure),
            default=Exposure.LAN.value,
        ),
        Question(
            key="server_host",
            kind=QuestionKind.TEXT,
            message_id="question.server_host",
            validator=is_valid_host,
            applies=_needs_lan,
        ),
        Question(
            key="web_domain",
            kind=QuestionKind.TEXT,
            message_id="question.web_domain",
            validator=is_valid_domain,
            applies=_needs_domains,
        ),
        Question(
            key="api_domain",
            kind=QuestionKind.TEXT,
            message_id="question.api_domain",
            validator=is_valid_domain,
            applies=_needs_domains,
        ),
        Question(
            key="caddy_email",
            kind=QuestionKind.TEXT,
            message_id="question.caddy_email",
            validator=is_valid_email,
            applies=_needs_caddy,
        ),
        Question(
            key="admin_email",
            kind=QuestionKind.TEXT,
            message_id="question.admin_email",
            validator=is_valid_email,
        ),
        Question(
            key="admin_name",
            kind=QuestionKind.TEXT,
            message_id="question.admin_name",
            default="Admin",
            validator=lambda value: bool(value.strip()),
        ),
        Question(
            key="default_language",
            kind=QuestionKind.CHOICE,
            message_id="question.default_language",
            choices=APP_LANGUAGES,
            default="en",
        ),
        Question(
            key="observability",
            kind=QuestionKind.BOOL,
            message_id="question.observability",
            default="no",
        ),
        Question(
            key="skill_sandbox",
            kind=QuestionKind.BOOL,
            message_id="question.skill_sandbox",
            default="no",
        ),
        Question(
            key="admin_password",
            kind=QuestionKind.SECRET,
            message_id="question.admin_password",
            secret=True,
            validator=is_valid_password_shape,
            message_args=password_args,
        ),
        *provider_questions,
    )
