"""Unit tests for ``domains/auth/native_handoff.py``.

The handoff exists because OAuth cannot run inside a WebView: both engines
refuse it (``disallowed_useragent``), so a native shell sends the user to the
system browser — where the resulting session cookie lands in the *browser*, not
in the app.

The deep link that brings the user back uses a **custom scheme**, because App
Links cannot follow a server URL the user types at first launch. A custom scheme
can be claimed by any installed app, so interception is a real threat and the
code alone must be worthless: it is bound to a verifier only the legitimate
WebView holds (RFC 8252 / RFC 7636). These tests pin that property first,
because everything else rests on it.
"""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.auth.native_handoff import (
    NativeHandoff,
    build_native_redirect,
    consume_handoff,
    is_valid_challenge,
    issue_handoff,
)

pytestmark = pytest.mark.unit

_STORE = "src.core.single_use_token.get_redis_session"


def _challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


_VERIFIER = "a" * 43
_CHALLENGE = _challenge_for(_VERIFIER)


class TestChallengeValidation:
    """What the login endpoint accepts before anything is stored."""

    def test_accepts_a_well_formed_challenge(self) -> None:
        assert is_valid_challenge(_CHALLENGE) is True

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "a" * 42,  # below the RFC 7636 floor
            "a" * 129,  # above the ceiling
            "not+base64url/",  # '+' and '/' belong to standard base64, not url-safe
            "abc def",
            "a" * 43 + "=",  # padding is stripped by construction
        ],
    )
    def test_rejects_anything_else(self, value: str) -> None:
        assert is_valid_challenge(value) is False

    def test_rejects_a_non_string(self) -> None:
        assert is_valid_challenge(None) is False  # type: ignore[arg-type]


class TestIssue:
    """Minting the code the deep link carries."""

    async def test_stores_the_challenge_and_never_the_verifier(self) -> None:
        redis = AsyncMock()
        with patch(_STORE, return_value=redis):
            code = await issue_handoff(user_id="u-1", challenge=_CHALLENGE, mfa_pending=False)

        assert code
        stored = json.loads(redis.set.await_args.args[1])
        assert stored == {"user_id": "u-1", "challenge": _CHALLENGE, "mfa_pending": False}
        # The verifier is the app's secret. If the server ever held it, an
        # attacker reading Redis could redeem any intercepted code.
        assert _VERIFIER not in redis.set.await_args.args[1]

    async def test_uses_the_configured_ttl(self) -> None:
        redis = AsyncMock()
        with patch(_STORE, return_value=redis):
            with patch("src.domains.auth.native_handoff.settings") as fake:
                fake.native_handoff_ttl_seconds = 45
                await issue_handoff(user_id="u-1", challenge=_CHALLENGE, mfa_pending=False)

        assert redis.set.await_args.kwargs["ex"] == 45

    async def test_refuses_a_malformed_challenge(self) -> None:
        redis = AsyncMock()
        with patch(_STORE, return_value=redis):
            with pytest.raises(ValueError):
                await issue_handoff(user_id="u-1", challenge="short", mfa_pending=False)

        redis.set.assert_not_awaited()

    async def test_carries_the_mfa_flag(self) -> None:
        redis = AsyncMock()
        with patch(_STORE, return_value=redis):
            await issue_handoff(user_id="u-1", challenge=_CHALLENGE, mfa_pending=True)

        assert json.loads(redis.set.await_args.args[1])["mfa_pending"] is True


class TestConsume:
    """Redeeming the code — the security boundary."""

    @staticmethod
    def _redis_holding(payload: dict[str, object]) -> AsyncMock:
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps(payload)
        return redis

    async def test_returns_the_payload_for_the_matching_verifier(self) -> None:
        redis = self._redis_holding(
            {"user_id": "u-9", "challenge": _CHALLENGE, "mfa_pending": False}
        )
        with patch(_STORE, return_value=redis):
            result = await consume_handoff("code", _VERIFIER)

        assert result == NativeHandoff(user_id="u-9", challenge=_CHALLENGE, mfa_pending=False)

    async def test_rejects_a_wrong_verifier(self) -> None:
        """The whole point: an intercepted code cannot be spent."""
        redis = self._redis_holding(
            {"user_id": "u-9", "challenge": _CHALLENGE, "mfa_pending": False}
        )
        with patch(_STORE, return_value=redis):
            assert await consume_handoff("code", "b" * 43) is None

    async def test_a_wrong_verifier_still_destroys_the_code(self) -> None:
        """Failing the check must not leave the code available for a retry."""
        redis = self._redis_holding(
            {"user_id": "u-9", "challenge": _CHALLENGE, "mfa_pending": False}
        )
        with patch(_STORE, return_value=redis):
            await consume_handoff("code", "b" * 43)

        redis.getdel.assert_awaited_once()

    @pytest.mark.parametrize("verifier", ["", "short", "a" * 129])
    async def test_rejects_a_malformed_verifier_without_touching_redis(self, verifier: str) -> None:
        redis = AsyncMock()
        with patch(_STORE, return_value=redis):
            assert await consume_handoff("code", verifier) is None

        redis.getdel.assert_not_awaited()

    async def test_returns_none_for_an_unknown_or_replayed_code(self) -> None:
        redis = AsyncMock()
        redis.getdel.return_value = None
        with patch(_STORE, return_value=redis):
            assert await consume_handoff("code", _VERIFIER) is None

    async def test_returns_none_when_the_stored_challenge_is_missing(self) -> None:
        redis = self._redis_holding({"user_id": "u-9", "mfa_pending": False})
        with patch(_STORE, return_value=redis):
            assert await consume_handoff("code", _VERIFIER) is None


class TestDeepLink:
    """The URL handed back to the operating system."""

    def test_builds_a_success_link_on_the_configured_scheme(self) -> None:
        with patch("src.domains.auth.native_handoff.settings") as fake:
            fake.native_app_scheme = "lia"
            url = build_native_redirect(code="abc")

        assert url == "lia://auth-callback?code=abc"

    def test_builds_an_error_link_carrying_no_code(self) -> None:
        with patch("src.domains.auth.native_handoff.settings") as fake:
            fake.native_app_scheme = "lia"
            url = build_native_redirect(error="access_denied")

        assert url == "lia://auth-callback?error=access_denied"

    def test_percent_encodes_its_parameters(self) -> None:
        with patch("src.domains.auth.native_handoff.settings") as fake:
            fake.native_app_scheme = "lia"
            url = build_native_redirect(error="a b&c=d")

        assert url == "lia://auth-callback?error=a+b%26c%3Dd"

    def test_refuses_to_build_a_link_with_neither_code_nor_error(self) -> None:
        """A link with no outcome would silently look like a success."""
        with patch("src.domains.auth.native_handoff.settings") as fake:
            fake.native_app_scheme = "lia"
            with pytest.raises(ValueError):
                build_native_redirect()
