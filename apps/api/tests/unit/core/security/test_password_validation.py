"""Unit tests for the password policy — and its cross-stack parity guard.

``validate_password_strict`` is wired as a Pydantic field validator
(``domains/shared/schemas.py``), so it gates EVERY password at registration and
at change. It had no test at all.

The policy is implemented TWICE — once here, once in the browser
(``apps/web/src/lib/password-validation.ts``, whose header states the constants
"must match backend constants.py"). Two independent implementations of one rule
is the classic drift surface: when they disagree the user is either blocked by a
UI that is stricter than the API, or accepted by a UI and rejected by the API.
The parity guard at the bottom pins the shared constants.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_DIGITS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_SPECIAL,
    PASSWORD_MIN_UPPERCASE,
    PASSWORD_SPECIAL_CHARS,
)
from src.core.security.password_validation import (
    get_password_requirements_message,
    validate_password,
    validate_password_strict,
)

pytestmark = pytest.mark.unit


def _valid_password() -> str:
    """Build a password that satisfies every rule, derived from the settings."""
    return (
        "A" * PASSWORD_MIN_UPPERCASE
        + "1" * PASSWORD_MIN_DIGITS
        + PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL
        + "a" * PASSWORD_MIN_LENGTH  # pad well past the minimum
    )


# ============================================================================
# Accepted passwords
# ============================================================================


class TestAcceptedPasswords:
    def test_a_policy_compliant_password_is_valid(self) -> None:
        result = validate_password(_valid_password())
        assert result.is_valid
        assert result.errors == []

    def test_exactly_at_the_minimum_length_is_valid(self) -> None:
        """Bounds are inclusive — a password OF the minimum length passes."""
        password = "AB12!@" + "a" * (PASSWORD_MIN_LENGTH - 6)
        assert len(password) == PASSWORD_MIN_LENGTH
        assert validate_password(password).is_valid

    def test_exactly_at_the_maximum_length_is_valid(self) -> None:
        password = "AB12!@" + "a" * (PASSWORD_MAX_LENGTH - 6)
        assert len(password) == PASSWORD_MAX_LENGTH
        assert validate_password(password).is_valid

    def test_strict_returns_the_password_unchanged(self) -> None:
        """As a Pydantic validator it must return the value, not just approve."""
        password = _valid_password()
        assert validate_password_strict(password) == password


# ============================================================================
# Rejected passwords — one rule at a time
# ============================================================================


class TestRejectedPasswords:
    def test_too_short(self) -> None:
        result = validate_password("AB12!@" + "a" * (PASSWORD_MIN_LENGTH - 7))
        assert not result.is_valid
        assert any(str(PASSWORD_MIN_LENGTH) in e for e in result.errors)

    def test_too_long(self) -> None:
        result = validate_password("AB12!@" + "a" * PASSWORD_MAX_LENGTH)
        assert not result.is_valid
        assert any(str(PASSWORD_MAX_LENGTH) in e for e in result.errors)

    def test_not_enough_uppercase(self) -> None:
        password = "A" * (PASSWORD_MIN_UPPERCASE - 1) + "1" * PASSWORD_MIN_DIGITS
        password += PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL + "a" * PASSWORD_MIN_LENGTH
        assert not validate_password(password).is_valid

    def test_not_enough_digits(self) -> None:
        password = "A" * PASSWORD_MIN_UPPERCASE + "1" * (PASSWORD_MIN_DIGITS - 1)
        password += PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL + "a" * PASSWORD_MIN_LENGTH
        assert not validate_password(password).is_valid

    def test_not_enough_special_chars(self) -> None:
        password = "A" * PASSWORD_MIN_UPPERCASE + "1" * PASSWORD_MIN_DIGITS
        password += PASSWORD_SPECIAL_CHARS[0] * (PASSWORD_MIN_SPECIAL - 1)
        password += "a" * PASSWORD_MIN_LENGTH
        assert not validate_password(password).is_valid

    def test_empty_password_fails_every_rule(self) -> None:
        result = validate_password("")
        assert not result.is_valid
        assert len(result.errors) >= 4

    def test_all_violations_are_reported_together(self) -> None:
        """The user gets the full list in one round-trip, not one error at a time."""
        result = validate_password("abc")
        assert len(result.errors) >= 4
        assert result.error_message  # combined, non-empty

    def test_strict_raises_on_an_invalid_password(self) -> None:
        with pytest.raises(ValueError):
            validate_password_strict("abc")

    def test_strict_error_carries_every_reason(self) -> None:
        with pytest.raises(ValueError) as exc:
            validate_password_strict("abc")
        assert str(exc.value)


# ============================================================================
# Character classes actually accepted
# ============================================================================


class TestCharacterClasses:
    @pytest.mark.parametrize("special", list(PASSWORD_SPECIAL_CHARS))
    def test_every_declared_special_char_counts(self, special: str) -> None:
        """The declared set is the contract — each character in it must satisfy
        the "special" requirement, or the UI and the API disagree on one key."""
        password = "AB12" + special * PASSWORD_MIN_SPECIAL + "a" * PASSWORD_MIN_LENGTH
        assert validate_password(password).is_valid

    def test_a_space_is_not_a_special_char(self) -> None:
        password = "AB12" + "  " + "a" * PASSWORD_MIN_LENGTH
        assert not validate_password(password).is_valid

    def test_unicode_uppercase_counts_server_side(self) -> None:
        """CHARACTERIZATION of a cross-stack divergence, not an endorsement.

        The backend counts uppercase with ``str.isupper()``, which is UNICODE
        aware, while the browser counts with ``/[A-Z]/g``, which is ASCII only.
        So an accented capital satisfies the API but not the UI: with a 6-language
        product, "ÉÀ…" is a natural choice and the user is blocked by a form that
        is stricter than the endpoint behind it.

        Pinned here with the exact reproducer so the divergence is visible and
        whichever side is aligned later is a measured decision. Note the drift is
        one-way — the UI is the stricter of the two — so nothing the UI accepts
        can be refused by the API.
        """
        password = "ÉÀ12!@" + "a" * PASSWORD_MIN_LENGTH
        assert validate_password(password).is_valid  # server: accepted
        assert len(re.findall(r"[A-Z]", password)) < PASSWORD_MIN_UPPERCASE  # browser: refused

    def test_unicode_digits_count_server_side(self) -> None:
        """Same divergence on digits: ``str.isdigit()`` vs ``/[0-9]/g``."""
        password = "AB٣٤!@" + "a" * PASSWORD_MIN_LENGTH
        assert validate_password(password).is_valid
        assert len(re.findall(r"[0-9]", password)) < PASSWORD_MIN_DIGITS


# ============================================================================
# Requirements message
# ============================================================================


class TestRequirementsMessage:
    def test_message_quotes_every_threshold(self) -> None:
        message = get_password_requirements_message()
        for threshold in (
            PASSWORD_MIN_LENGTH,
            PASSWORD_MIN_UPPERCASE,
            PASSWORD_MIN_DIGITS,
            PASSWORD_MIN_SPECIAL,
        ):
            assert str(threshold) in message


# ============================================================================
# Cross-stack parity guard
# ============================================================================

_TS_POLICY = (
    Path(__file__).resolve().parents[4] / ".." / "web" / "src" / "lib" / "password-validation.ts"
)


def _ts_constant(source: str, name: str) -> int | None:
    match = re.search(rf"export const {name}\s*=\s*(\d+)\s*;", source)
    return int(match.group(1)) if match else None


class TestFrontendParity:
    """The browser re-implements this policy; its header says the constants
    "must match backend constants.py". Drift silently desynchronises the form
    from the endpoint, so it is pinned here rather than trusted to a comment."""

    @pytest.fixture
    def ts_source(self) -> str:
        path = _TS_POLICY.resolve()
        if not path.is_file():
            pytest.skip(f"frontend policy not found at {path}")
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        ("ts_name", "backend_value"),
        [
            ("PASSWORD_MIN_LENGTH", PASSWORD_MIN_LENGTH),
            ("PASSWORD_MAX_LENGTH", PASSWORD_MAX_LENGTH),
            ("PASSWORD_MIN_UPPERCASE", PASSWORD_MIN_UPPERCASE),
            ("PASSWORD_MIN_SPECIAL", PASSWORD_MIN_SPECIAL),
            ("PASSWORD_MIN_DIGITS", PASSWORD_MIN_DIGITS),
        ],
    )
    def test_numeric_thresholds_match(
        self, ts_source: str, ts_name: str, backend_value: int
    ) -> None:
        ts_value = _ts_constant(ts_source, ts_name)
        assert ts_value is not None, f"{ts_name} not found in the frontend policy"
        assert ts_value == backend_value, (
            f"{ts_name} drifted: frontend={ts_value}, backend={backend_value}. "
            "The form and the endpoint would disagree on what is acceptable."
        )

    def test_special_character_set_matches(self, ts_source: str) -> None:
        match = re.search(r"export const PASSWORD_SPECIAL_CHARS\s*=\s*'(.*)';", ts_source)
        assert match, "PASSWORD_SPECIAL_CHARS not found in the frontend policy"
        # The TS literal is single-quoted: \' and \\ are the only escapes used.
        ts_chars = match.group(1).replace("\\'", "'").replace("\\\\", "\\")
        assert set(ts_chars) == set(PASSWORD_SPECIAL_CHARS), (
            "Special-character sets drifted between the browser and the API: "
            f"frontend-only={sorted(set(ts_chars) - set(PASSWORD_SPECIAL_CHARS))}, "
            f"backend-only={sorted(set(PASSWORD_SPECIAL_CHARS) - set(ts_chars))}"
        )
