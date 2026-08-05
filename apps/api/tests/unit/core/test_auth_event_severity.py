"""An expired session is a lifecycle event; a rejected credential is a signal.

``AuthenticationError`` logged every 401 at WARNING. Measured in production over
7 days (2026-07-29 → 2026-08-05): 465 ``authentication_failed`` entries, of which
**438 on ``GET /api/v1/auth/me``** — the endpoint the frontend calls to discover
whether a session is still valid. Answering "no" there is the nominal outcome for
any visitor whose cookie expired, or who never had one.

Ninety-four percent of a warning stream describing normal behaviour is how a
reader learns to ignore warnings, and it is exactly what hid the genuine 401s
(``token_already_used``) in the same bucket.

Severity now follows the ORIGIN, not the status code:

* session absent or expired  -> INFO  (lifecycle, expected, self-healing)
* credential rejected, token replayed, bearer refused -> WARNING (security)

The HTTP contract is untouched: the client still receives 401 in every case.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.exceptions import (
    AuthenticationError,
    raise_bearer_auth_failed,
    raise_session_invalid,
    raise_user_not_authenticated,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def logged(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    """Records (level, event, fields) for every exception raised in the test."""
    from src.core import _exceptions_base

    records: list[tuple[str, str, dict[str, Any]]] = []

    class _StubLogger:
        def __getattr__(self, level: str):  # noqa: ANN202 - dynamic by design
            def _log(event: str, **fields: Any) -> None:
                records.append((level, event, fields))

            return _log

    monkeypatch.setattr(_exceptions_base, "logger", _StubLogger())
    return records


def _levels(records: list[tuple[str, str, dict[str, Any]]]) -> list[str]:
    return [level for level, _event, _fields in records]


class TestSessionLifecycleIsNotAWarning:
    """The 94% that described a normal outcome."""

    def test_an_expired_session_is_information(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        with pytest.raises(AuthenticationError) as raised:
            raise_session_invalid()

        assert raised.value.status_code == 401, "the HTTP contract must not change"
        assert _levels(logged) == ["info"], (
            "an expired or unknown session is the nominal answer of /auth/me, not an "
            "incident: 438 of the 465 weekly warnings came from exactly this."
        )

    def test_a_missing_cookie_is_information(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        with pytest.raises(AuthenticationError) as raised:
            raise_user_not_authenticated()

        assert raised.value.status_code == 401
        assert _levels(logged) == ["info"], "an anonymous visitor is not a security event"

    def test_the_event_name_is_preserved(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        """Only the level moves — dashboards and queries keep working."""
        with pytest.raises(AuthenticationError):
            raise_session_invalid()

        assert logged[0][1] == "authentication_failed"


class TestRejectedCredentialsStayWarnings:
    """The signal the noise was burying."""

    def test_a_replayed_token_stays_a_warning(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        from src.core.exceptions import raise_token_already_used

        with pytest.raises(AuthenticationError):
            raise_token_already_used(token_type="refresh")

        assert _levels(logged) == [
            "warning"
        ], "a token replay is an attack pattern, not a lifecycle event"

    def test_a_refused_bearer_stays_a_warning(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        with pytest.raises(AuthenticationError):
            raise_bearer_auth_failed("bad token")

        assert _levels(logged) == ["warning"]

    def test_the_default_severity_is_still_warning(
        self, logged: list[tuple[str, str, dict[str, Any]]]
    ) -> None:
        """Any 401 raised without an explicit decision keeps the loud default."""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError(detail="Invalid credentials")

        assert _levels(logged) == ["warning"]
