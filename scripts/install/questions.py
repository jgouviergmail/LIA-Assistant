"""Declarative installer questionnaire (B10/B13).

Ordering is meaningful: the wizard language is asked first (it drives every
later prompt), exposure gates its conditional follow-ups, and secrets come
last so an operator can abort before typing anything sensitive.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from scripts.install.answers import (
    is_valid_domain,
    is_valid_email,
    is_valid_host,
    is_valid_password_shape,
)
from scripts.install.maps import valid_map_id, valid_maps_value
from scripts.install.turnstile import valid_turnstile_value
from scripts.install.model import (
    APP_LANGUAGES,
    OPTIONAL_PROVIDER_IDS,
    PASSWORD_RULES,
    REQUIRED_PROVIDER_IDS,
    WIZARD_LANGUAGES,
    Exposure,
    PublicAnswers,
    Question,
    QuestionKind,
)


def _needs_lan(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") is Exposure.LAN


def _needs_domains(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") in (Exposure.PROXY, Exposure.CADDY)


def _needs_caddy(answers: Mapping[str, Any]) -> bool:
    return answers.get("exposure") is Exposure.CADDY


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def build_reconfiguration_questions(current: PublicAnswers) -> tuple[Question, ...]:
    """The questions a reconfiguration asks, each defaulting to the answer in force.

    Every non-secret choice but the administrator's identity: an operator who
    presses Enter keeps what runs. A follow-up a new exposure needs (domains
    after LAN, a host after a proxy) has no answer in force and is asked.

    Args:
        current: The installation's recorded answers.

    Returns:
        The questions, in the questionnaire's order.
    """
    in_force: dict[str, str | None] = {
        "wizard_language": current.language,
        "exposure": current.exposure.value,
        "server_host": current.server_host,
        "web_domain": current.web_domain,
        "api_domain": current.api_domain,
        "caddy_email": current.caddy_email,
        "default_language": current.default_language,
        "observability": _yes_no(current.observability),
        "self_diagnostics": _yes_no(current.self_diagnostics),
        "skill_sandbox": _yes_no(current.skill_sandbox),
        "live_mode": _yes_no(current.live_mode),
        "personal_radio": _yes_no(current.personal_radio),
        "speaking_avatar": _yes_no(current.speaking_avatar),
    }
    return tuple(
        dataclasses.replace(question, default=in_force[question.key] or question.default)
        for question in build_questions()
        if question.key in in_force
    )


def build_env_changes_confirmation() -> Question:
    """Whether a reconfiguration may change the ``.env`` values it just listed.

    Defaults to ``no``: pressing Enter through a run that changed nothing must
    never replace a value edited by hand.

    Returns:
        The yes/no question.
    """
    return Question(
        key="apply_env_changes",
        kind=QuestionKind.BOOL,
        message_id="question.apply_env_changes",
        default="no",
    )


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
    # Asked, never required: memory recall, document, journal and interest
    # search run on the Gemini key, so an install that skips it is told in
    # the final report what it left degraded.
    optional_provider_questions = tuple(
        Question(
            key=f"provider_key_{provider}",
            kind=QuestionKind.SECRET,
            message_id=f"question.optional_provider_key.{provider}",
            secret=True,
            optional=True,
            validator=lambda value: bool(value.strip()),
        )
        for provider in OPTIONAL_PROVIDER_IDS
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
            key="self_diagnostics",
            kind=QuestionKind.BOOL,
            message_id="question.self_diagnostics",
            default="no",
        ),
        Question(
            key="skill_sandbox",
            kind=QuestionKind.BOOL,
            message_id="question.skill_sandbox",
            default="no",
        ),
        Question(
            key="live_mode",
            kind=QuestionKind.BOOL,
            message_id="question.live_mode",
            default="no",
        ),
        Question(
            key="personal_radio",
            kind=QuestionKind.BOOL,
            message_id="question.personal_radio",
            default="no",
        ),
        Question(
            key="speaking_avatar",
            kind=QuestionKind.BOOL,
            message_id="question.speaking_avatar",
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
        *optional_provider_questions,
        Question(
            key="maps_browser_key",
            kind=QuestionKind.SECRET,
            message_id="question.maps_browser_key",
            secret=True,
            env_only=True,
            optional=True,
            validator=valid_maps_value,
        ),
        Question(
            key="maps_map_id",
            kind=QuestionKind.SECRET,
            message_id="question.maps_map_id",
            secret=True,
            env_only=True,
            optional=True,
            validator=valid_map_id,
        ),
        # The anti-robot check on the password doors (ADR-364): an instance reached on
        # a public domain is the one scripts find; a LAN install is not asked.
        Question(
            key="turnstile_site_key",
            kind=QuestionKind.SECRET,
            message_id="question.turnstile_site_key",
            secret=True,
            env_only=True,
            optional=True,
            validator=valid_turnstile_value,
            applies=_needs_domains,
        ),
        Question(
            key="turnstile_secret_key",
            kind=QuestionKind.SECRET,
            message_id="question.turnstile_secret_key",
            secret=True,
            env_only=True,
            optional=True,
            validator=valid_turnstile_value,
            applies=_needs_domains,
        ),
    )
