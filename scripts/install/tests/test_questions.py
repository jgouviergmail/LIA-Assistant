"""Declarative questionnaire contract (B10/B13).

- provider-key questions exist for EXACTLY the wizard's required provider
  tuple (backend anti-drift binds that tuple to the derived post-seed set);
- secrets are Question(secret=True) and never environment-key questions;
- PublicAnswers structurally cannot carry a password or provider key;
- conditional questions follow the exposure branches;
- every question's message id is translated in both wizard languages.
"""

from __future__ import annotations

import dataclasses

from scripts.install.i18n import MESSAGES
from scripts.install.model import (
    APP_LANGUAGES,
    REQUIRED_PROVIDER_IDS,
    Exposure,
    PublicAnswers,
    Question,
    QuestionKind,
)
from scripts.install.questions import build_questions


def _by_key() -> dict[str, Question]:
    questions = build_questions()
    keys = [q.key for q in questions]
    assert len(keys) == len(set(keys)), "duplicate question keys"
    return {q.key: q for q in questions}


def test_provider_key_questions_match_the_required_tuple_exactly() -> None:
    questions = _by_key()
    provider_questions = {
        key.removeprefix("provider_key_")
        for key in questions
        if key.startswith("provider_key_")
    }
    assert provider_questions == set(REQUIRED_PROVIDER_IDS)
    assert REQUIRED_PROVIDER_IDS == ("deepseek", "openai")
    for provider in REQUIRED_PROVIDER_IDS:
        question = questions[f"provider_key_{provider}"]
        assert question.secret, f"{provider} key must be a secret question"
        assert question.kind is QuestionKind.SECRET


def test_admin_password_is_a_secret_question() -> None:
    question = _by_key()["admin_password"]
    assert question.secret
    assert question.kind is QuestionKind.SECRET


def test_public_answers_cannot_carry_secrets() -> None:
    field_names = {f.name for f in dataclasses.fields(PublicAnswers)}
    for forbidden in ("password", "key", "secret", "token"):
        assert not any(forbidden in name for name in field_names), field_names


def test_exposure_branches_gate_the_conditional_questions() -> None:
    questions = _by_key()
    lan = {"exposure": Exposure.LAN}
    proxy = {"exposure": Exposure.PROXY}
    caddy = {"exposure": Exposure.CADDY}

    assert questions["server_host"].applies_to(lan)
    assert not questions["server_host"].applies_to(proxy)
    for key in ("web_domain", "api_domain"):
        assert not questions[key].applies_to(lan)
        assert questions[key].applies_to(proxy)
        assert questions[key].applies_to(caddy)
    assert questions["caddy_email"].applies_to(caddy)
    assert not questions["caddy_email"].applies_to(proxy)
    assert not questions["caddy_email"].applies_to(lan)


def test_default_language_offers_the_six_app_languages() -> None:
    question = _by_key()["default_language"]
    assert question.choices == APP_LANGUAGES
    assert APP_LANGUAGES == ("fr", "en", "es", "de", "it", "zh-CN")


def test_every_question_message_id_is_translated() -> None:
    for question in build_questions():
        assert question.message_id in MESSAGES, question.key


def test_no_question_reads_an_environment_key() -> None:
    for question in build_questions():
        assert "env" not in question.key.lower()
        assert not question.key.isupper(), "no ENV-style question keys"
