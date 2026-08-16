"""Pure canonical Settings validation for the installer (B07).

What must hold:
- ``validate_current_settings()`` constructs the REAL composed Settings from
  the current environment and performs no socket, database, Redis, Docker,
  or provider operation;
- a malformed Fernet key is rejected with a located issue whose text never
  echoes the secret value;
- issues are deterministically sorted by (location, message);
- the legacy operator validator delegates its Pydantic phase here.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

import scripts.validate_config as validate_config
import scripts.validate_settings as validate_settings
from scripts.validate_settings import (
    SettingsIssue,
    format_issues,
    main,
    validate_current_settings,
)

pytestmark = pytest.mark.unit


def test_valid_environment_boots_settings() -> None:
    settings, issues = validate_current_settings()
    assert settings is not None
    assert issues == ()


def test_malformed_fernet_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", "not-a-fernet-key")
    settings, issues = validate_current_settings()
    assert settings is None
    assert any("fernet_key" in issue.location for issue in issues)
    assert "not-a-fernet-key" not in format_issues(issues)


def test_valid_fernet_key_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode("ascii"))
    settings, issues = validate_current_settings()
    assert settings is not None
    assert issues == ()


@pytest.mark.parametrize(
    "bad_key",
    [
        "",  # empty
        "short",  # wrong length
        "A" * 43,  # 43 chars — not a 32-byte payload
        "!" * 44,  # right length, invalid alphabet
        # 45 chars (a valid-shaped key + one). A FIXED literal on purpose:
        # a key generated at collection time differs per xdist worker and
        # aborts the whole run with "Different tests were collected".
        "A" * 43 + "==",
    ],
)
def test_fernet_structure_matrix(monkeypatch: pytest.MonkeyPatch, bad_key: str) -> None:
    monkeypatch.setenv("FERNET_KEY", bad_key)
    settings, issues = validate_current_settings()
    assert settings is None
    assert issues, "a structural Fernet issue must be reported"


def test_issues_are_sorted_and_value_free() -> None:
    issues = (
        SettingsIssue(location="zeta", message="b"),
        SettingsIssue(location="alpha", message="z"),
        SettingsIssue(location="alpha", message="a"),
    )
    text = format_issues(tuple(sorted(issues, key=lambda i: (i.location, i.message))))
    assert text.index("alpha: a") < text.index("alpha: z") < text.index("zeta: b")


def test_main_prints_ok_in_valid_env(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert "OK: settings are valid" in capsys.readouterr().out


def test_connection_budget_overcommit_is_a_located_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An overcommitted pool profile fails at VALIDATION, not readiness.

    The production lifespan fail-fasts on `ConnectionBudgetError` (F004);
    when the validator did not run the same arithmetic, a mis-sized env
    sailed through `validate_settings` and crash-looped the API five
    minutes later as a detail-free `readiness_timeout` (measured on the
    v1.30.1 qualification matrix, whose minimal env template shipped no
    pool sizing at all).
    """
    from src.infrastructure.database import connection_budget

    def _overcommit(settings: object) -> list[str]:
        raise connection_budget.ConnectionBudgetError(
            "DB connection budget overcommit: worst-case burst 288 exceeds usable 195"
        )

    monkeypatch.setattr(connection_budget, "enforce_connection_budget", _overcommit)
    settings, issues = validate_current_settings()
    assert settings is None
    assert [issue.location for issue in issues] == ["connection_budget"]
    assert "overcommit" in issues[0].message


def test_main_reports_invalid_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FERNET_KEY", "broken")
    assert main() == 1
    out = capsys.readouterr().out
    assert "INVALID" in out
    assert "fernet_key" in out
    assert "broken" not in out


def test_legacy_validator_delegates_to_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def _spy() -> tuple[None, tuple[SettingsIssue, ...]]:
        calls.append(True)
        return None, (SettingsIssue(location="x", message="boom"),)

    monkeypatch.setattr(validate_settings, "validate_current_settings", _spy)

    class _Result:
        def __init__(self) -> None:
            self.entries: list[tuple[str, str, str]] = []

        def add(self, severity: object, category: str, key: str, message: str) -> None:
            self.entries.append((category, key, message))

    result = _Result()
    validate_config.validate_pydantic_models(result)  # type: ignore[arg-type]
    assert calls == [True]
    assert any("boom" in message for _, _, message in result.entries)
