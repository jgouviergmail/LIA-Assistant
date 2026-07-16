"""Contract tests for the API-key activation semantics (audit F051).

Pins the two-tier contract that the module docstring, the service comment and
the router all now agree on:

* ``ACTIVE`` means "activated and usable".
* ``functionally_verified`` (metadata / validate response) is what distinguishes
  a provider-proven key from a format-only one.
* A **verifier** type is gated on a real authenticated probe — a wrong key is
  rejected by ``validate_api_key`` and never activates.
* A **format-only** type activates on the format check alone
  (``functionally_verified=False``).

The suite also guards against regressing the docstring back to the former,
self-contradictory wording ("must not go ACTIVE on a format-only check").
"""

from __future__ import annotations

import pytest

import src.domains.connectors.api_key_verifiers as verifiers_mod
from src.domains.connectors.api_key_verifiers import API_KEY_FUNCTIONAL_VERIFIERS
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService

# Async tests run under the repo-wide ``asyncio_mode = "auto"`` — no marker needed.

# A well-formed key: >= 8 chars, no placeholder token.
GOOD_KEY = "abcd1234efgh"


def _service() -> ConnectorService:
    """A ConnectorService whose ``validate_api_key`` needs no DB (it uses none)."""
    return object.__new__(ConnectorService)


def _ui_functionally_verified(is_valid: bool, connector_type: ConnectorType) -> bool:
    """Mirror the router's UI-label computation (router.py validate_api_key)."""
    return is_valid and connector_type in API_KEY_FUNCTIONAL_VERIFIERS


class TestRegistryContract:
    def test_verifier_types_are_registered(self) -> None:
        assert ConnectorType.OPENWEATHERMAP in API_KEY_FUNCTIONAL_VERIFIERS
        assert ConnectorType.BRAVE_SEARCH in API_KEY_FUNCTIONAL_VERIFIERS

    def test_format_only_types_have_no_verifier(self) -> None:
        for fmt_only in (
            ConnectorType.PERPLEXITY,
            ConnectorType.GOOGLE_PLACES,
            ConnectorType.PHILIPS_HUE,
        ):
            assert fmt_only not in API_KEY_FUNCTIONAL_VERIFIERS


class TestValidateFormatChecks:
    async def test_rejects_too_short_key(self) -> None:
        ok, msg = await _service().validate_api_key(ConnectorType.PERPLEXITY, "short")
        assert ok is False
        assert "8 characters" in msg

    async def test_rejects_placeholder_key(self) -> None:
        ok, msg = await _service().validate_api_key(
            ConnectorType.PERPLEXITY, "your_api_key_here_value"
        )
        assert ok is False


class TestVerifierGating:
    async def test_wrong_key_for_verifier_type_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _reject(_key: str, _secret: str | None) -> tuple[bool, str]:
            return False, "provider rejected the key"

        monkeypatch.setattr(
            verifiers_mod,
            "API_KEY_FUNCTIONAL_VERIFIERS",
            {ConnectorType.OPENWEATHERMAP: _reject},
        )
        ok, msg = await _service().validate_api_key(ConnectorType.OPENWEATHERMAP, GOOD_KEY)
        assert ok is False  # never reaches ACTIVE
        assert "rejected" in msg

    async def test_good_key_for_verifier_type_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _accept(_key: str, _secret: str | None) -> tuple[bool, str]:
            return True, "verified"

        monkeypatch.setattr(
            verifiers_mod,
            "API_KEY_FUNCTIONAL_VERIFIERS",
            {ConnectorType.OPENWEATHERMAP: _accept},
        )
        ok, msg = await _service().validate_api_key(ConnectorType.OPENWEATHERMAP, GOOD_KEY)
        assert ok is True
        assert "verified" in msg


class TestFormatOnlyActivation:
    async def test_format_only_type_passes_on_format_alone(self) -> None:
        ok, msg = await _service().validate_api_key(ConnectorType.PERPLEXITY, GOOD_KEY)
        assert ok is True
        assert "no functional verifier" in msg


class TestUiFunctionallyVerifiedLabel:
    def test_verifier_type_is_labelled_verified_when_valid(self) -> None:
        assert _ui_functionally_verified(True, ConnectorType.OPENWEATHERMAP) is True

    def test_format_only_type_is_never_labelled_verified(self) -> None:
        # Even a valid (format-passing) key must not be shown as verified.
        assert _ui_functionally_verified(True, ConnectorType.PERPLEXITY) is False

    def test_invalid_key_is_never_labelled_verified(self) -> None:
        assert _ui_functionally_verified(False, ConnectorType.OPENWEATHERMAP) is False


class TestDocstringContract:
    def test_docstring_states_the_two_tier_contract(self) -> None:
        doc = verifiers_mod.__doc__ or ""
        assert "functionally_verified" in doc
        assert "usable" in doc  # ACTIVE == usable framing

    def test_docstring_dropped_the_contradictory_claim(self) -> None:
        doc = verifiers_mod.__doc__ or ""
        # The old wording universally forbade ACTIVE after a format-only check,
        # contradicting the service which activates format-only types.
        assert "must not go ACTIVE on a format-only check" not in doc
        assert "the key actually authenticates" not in doc
