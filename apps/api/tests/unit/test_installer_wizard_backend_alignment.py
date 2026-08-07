"""Wizard ↔ backend anti-drift (ADR-215, B10-bis).

``scripts/install/`` is stdlib-only, so it carries COPIES of three backend
contracts. This test pins each copy to its live backend source — moving the
backend value without the wizard (or vice versa) turns CI red:

- the required provider tuple mirrors ``required_current_core_provider_ids()``
  (derived from code defaults + the parsed reference seed);
- the wizard password pre-check mirrors the core password policy constants;
- the wizard's provider base URLs (and env override names) mirror the
  adapter's ``_BASE_URL_DEFAULTS`` so hermetic qualification points both
  sides at the same fake endpoint.
"""

from __future__ import annotations

import sys

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def _wizard_modules():
    root = repo_root_or_skip()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.install import answers, model, verify

    return model, verify, answers


def test_required_provider_tuple_matches_the_derived_baseline() -> None:
    model, _verify, _answers = _wizard_modules()
    from src.domains.llm_config.install_contract import (
        required_current_core_provider_ids,
    )

    assert model.REQUIRED_PROVIDER_IDS == required_current_core_provider_ids()


def test_password_rules_mirror_the_core_policy_constants() -> None:
    model, _verify, _answers = _wizard_modules()
    from src.core import constants

    rules = model.PASSWORD_RULES
    assert rules.min_length == constants.PASSWORD_MIN_LENGTH
    assert rules.max_length == constants.PASSWORD_MAX_LENGTH
    assert rules.min_uppercase == constants.PASSWORD_MIN_UPPERCASE
    assert rules.min_digits == constants.PASSWORD_MIN_DIGITS
    assert rules.min_special == constants.PASSWORD_MIN_SPECIAL
    assert rules.special_chars == constants.PASSWORD_SPECIAL_CHARS


def test_wizard_pre_check_accepts_what_the_backend_accepts() -> None:
    _model, _verify, answers = _wizard_modules()
    from src.core.security.password_validation import validate_password

    for candidate in (
        "Xx12!!abcdA9$Z",
        "weak",
        "Alllowercase11!!x",
        "xx12!!abcdzz",
        "AB12cdefgh",
        "AB12!?cdef",
    ):
        assert answers.is_valid_password_shape(candidate) == (
            validate_password(candidate).is_valid
        ), candidate


def test_provider_base_urls_mirror_the_adapter_defaults() -> None:
    _model, verify, _answers = _wizard_modules()
    from src.infrastructure.llm.providers.adapter import _BASE_URL_DEFAULTS

    for provider in verify._BASE_URLS:
        assert verify._BASE_URLS[provider] == _BASE_URL_DEFAULTS[provider]
