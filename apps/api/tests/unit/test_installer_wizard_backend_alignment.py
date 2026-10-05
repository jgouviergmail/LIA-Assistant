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
from pathlib import Path

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


def test_new_capability_defaults_boot_the_real_settings() -> None:
    """The minimal install profile must express what the composed API loads.

    Radio and avatars are deliberate installer opt-ins. Their finite limits
    and the other capability defaults must remain bootable together.
    """
    from scripts.install.envgen import generate_secrets

    from src.core.config import Settings
    from src.core.config.avatars import AvatarSettings

    profile = {}
    template = Path(repo_root_or_skip(), ".env.min.prod.example")
    for line in template.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if "=" in entry:
            key, value = entry.split("=", 1)
            profile[key] = value.strip()

    assert profile["RADIO_ENABLED"] == "false"
    for name, field in AvatarSettings.model_fields.items():
        expected = field.default
        actual = profile[name.upper()]
        if isinstance(expected, bool):
            assert actual == str(expected).lower()
        else:
            assert float(actual) == expected
    assert profile["ELEVENLABS_TTS_MAX_CONCURRENCY"] == "5"
    assert (
        int(profile["ELEVENLABS_TTS_MAX_CONCURRENCY"])
        == Settings.model_fields["elevenlabs_tts_max_concurrency"].default
    )
    secrets = generate_secrets()
    required = {
        "database_url": "postgresql+asyncpg://lia:test@localhost:5432/lia",
        "redis_url": "redis://localhost:6379/0",
        "secret_key": secrets["SECRET_KEY"],
        "fernet_key": secrets["FERNET_KEY"],
    }
    defaults = {
        **{name: profile[name.upper()] for name in AvatarSettings.model_fields},
        "radio_enabled": profile["RADIO_ENABLED"],
        "elevenlabs_tts_max_concurrency": profile["ELEVENLABS_TTS_MAX_CONCURRENCY"],
        "email_share_enabled": Settings.model_fields["email_share_enabled"].default,
        "generated_assets_keep_max_files": Settings.model_fields[
            "generated_assets_keep_max_files"
        ].default,
        "generated_assets_keep_max_mb": Settings.model_fields[
            "generated_assets_keep_max_mb"
        ].default,
    }
    settings = Settings(_env_file=None, **required, **defaults)
    assert settings.radio_enabled is False
    assert settings.avatar_enabled is False
    assert 0 < settings.avatar_idle_seconds <= settings.avatar_session_length_seconds
    assert settings.elevenlabs_tts_max_concurrency == 5
    assert settings.email_share_enabled is True
    assert settings.generated_assets_keep_max_files == 100
    assert settings.generated_assets_keep_max_mb == 500
    assert Settings(
        _env_file=None, **required, **{**defaults, "radio_enabled": "true"}
    ).radio_enabled


@pytest.mark.parametrize("language", ("fr", "en", "es", "de", "it", "zh-CN"))
@pytest.mark.parametrize("avatar_enabled", (False, True))
def test_emitted_installer_defaults_load_the_composed_settings(
    language: str, avatar_enabled: bool
) -> None:
    """Generated public choices and bounds must reach the real API settings."""
    _wizard_modules()
    from scripts.install.envgen import derive_environment, generate_secrets
    from scripts.install.model import Exposure, InstallMode, PublicAnswers

    from src.core.config import Settings
    from src.core.config.avatars import AvatarSettings

    public = PublicAnswers(
        language="en",
        mode=InstallMode.LOCAL,
        exposure=Exposure.LAN,
        admin_email="admin@ops.tld",
        admin_name="Admin",
        default_language=language,
        observability=False,
        skill_sandbox=False,
        server_host="192.168.1.50",
        web_domain=None,
        api_domain=None,
        caddy_email=None,
        manifest_path=None,
        speaking_avatar=avatar_enabled,
    )
    environment = derive_environment(public, generate_secrets())
    values = {
        key.lower(): value
        for key, value in environment.items()
        if key.lower() in Settings.model_fields
    }
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://lia:test@localhost:5432/lia",
        redis_url="redis://localhost:6379/0",
        **values,
    )
    assert settings.default_language == language
    assert settings.radio_enabled is False
    assert settings.live_enabled is False
    assert settings.diagnostics_enabled is False
    assert settings.avatar_enabled is avatar_enabled
    for name, field in AvatarSettings.model_fields.items():
        if name != "avatar_enabled":
            assert getattr(settings, name) == field.default, name
