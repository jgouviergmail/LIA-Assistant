"""How the workbench refuses, and how a provider failure becomes a refusal (ADR-369).

Every refusal is a stable ``detail.code`` the web app tells in the reader's
language. A provider failure is classified by its TYPE and its status code —
never by the words of its message (ADR-303 ratchet) — and the classification
knows whether the failed call was an ACT: a send whose answer was lost may have
left, so it is « outcome unknown », never « unavailable, try again » (ADR-221).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError

from src.core.exceptions import (
    AuthenticationError,
    BaseAPIException,
    ConnectorAPIError,
    ConnectorTokenExpiredError,
    ExternalServiceError,
    RateLimitError,
)
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentNotFoundError,
    EmailAttachmentTooLargeError,
)
from src.domains.connectors.clients.mail_folders import (
    MailFolderAmbiguousError,
    MailFolderNotFoundError,
)
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
)
from src.domains.workbench import errors
from src.domains.workbench.errors import refusal_for, refuse, refuse_provider_failure
from src.domains.workbench.ids import ProviderId

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.example/send")


def _api_error(status: int) -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_gmail", status_code=status, detail="x")


def _revoked() -> BaseException:
    from uuid import uuid4

    from src.domains.connectors.errors import ConnectorRevokedError
    from src.domains.connectors.models import ConnectorType

    return ConnectorRevokedError(ConnectorType.PHILIPS_HUE, uuid4())


def _wrapped(cause: BaseException) -> ExternalServiceError:
    try:
        raise ExternalServiceError(service_name="google_gmail") from cause
    except ExternalServiceError as error:
        return error


class TestRefuse:
    def test_carries_the_code_its_status_and_the_facts(self) -> None:
        with pytest.raises(BaseAPIException) as raised:
            refuse(errors.TOO_LARGE, max_bytes=10)
        assert raised.value.status_code == 413
        assert raised.value.detail == {"code": "too_large", "max_bytes": 10}

    def test_a_rate_limit_publishes_retry_after_as_a_header(self) -> None:
        with pytest.raises(BaseAPIException) as raised:
            refuse(errors.PROVIDER_RATE_LIMITED, retry_after=30)
        assert raised.value.status_code == 429
        assert raised.value.headers == {"Retry-After": "30"}

    def test_every_code_has_a_status(self) -> None:
        for code in errors.WORKBENCH_CODES:
            with pytest.raises(BaseAPIException) as raised:
                refuse(code)
            assert 400 <= raised.value.status_code < 600, code


class TestProviderStatus:
    @pytest.mark.parametrize(
        ("status", "code"),
        [
            (404, errors.ITEM_GONE),
            (410, errors.ITEM_GONE),
            (409, errors.CONFLICT),
            (412, errors.CONFLICT),
            (401, errors.RECONNECT_REQUIRED),
            # Google answers 403 for a missing scope AND for a usage limit; only
            # the reason tells them apart, and a reason is text: « refused » is
            # true of both, « reconnect » of one.
            (403, errors.PROVIDER_REFUSED),
            (413, errors.TOO_LARGE),
            (400, errors.PROVIDER_REFUSED),
            (422, errors.PROVIDER_REFUSED),
            (429, errors.PROVIDER_RATE_LIMITED),
            (500, errors.PROVIDER_UNAVAILABLE),
        ],
    )
    def test_an_answered_status_is_classified(self, status: int, code: str) -> None:
        assert refusal_for(_api_error(status), act=False)[0] == code

    def test_an_answered_status_says_the_same_for_an_act(self) -> None:
        """A provider that ANSWERED 404 did not perform the act: no doubt to state."""
        assert refusal_for(_api_error(404), act=True)[0] == errors.ITEM_GONE


class TestTransport:
    def test_a_lost_answer_to_an_act_is_an_unknown_outcome(self) -> None:
        lost = _wrapped(httpx.ReadTimeout("lost", request=_REQUEST))
        assert refusal_for(lost, act=True)[0] == errors.OUTCOME_UNKNOWN

    def test_a_lost_answer_to_a_read_is_unavailable(self) -> None:
        lost = _wrapped(httpx.ReadTimeout("lost", request=_REQUEST))
        assert refusal_for(lost, act=False)[0] == errors.PROVIDER_UNAVAILABLE

    def test_a_request_that_never_left_is_unavailable_even_for_an_act(self) -> None:
        never_left = _wrapped(httpx.ConnectError("refused", request=_REQUEST))
        assert refusal_for(never_left, act=True)[0] == errors.PROVIDER_UNAVAILABLE

    def test_a_connect_timeout_never_left_either(self) -> None:
        never_left = _wrapped(httpx.ConnectTimeout("slow", request=_REQUEST))
        assert refusal_for(never_left, act=True)[0] == errors.PROVIDER_UNAVAILABLE

    def test_a_bare_refused_connection_on_an_act_never_left(self) -> None:
        refused = httpx.ConnectError("refused", request=_REQUEST)
        assert refusal_for(refused, act=True)[0] == errors.PROVIDER_UNAVAILABLE

    def test_a_bare_transport_timeout_on_an_act_is_unknown(self) -> None:
        assert (
            refusal_for(httpx.WriteTimeout("x", request=_REQUEST), act=True)[0]
            == errors.OUTCOME_UNKNOWN
        )

    def test_retries_exhausted_is_unavailable(self) -> None:
        exhausted = ExternalServiceError(service_name="google_gmail", error_type="max_retries")
        assert refusal_for(exhausted, act=True)[0] == errors.PROVIDER_UNAVAILABLE

    def test_an_open_breaker_passes_its_retry_after_on(self) -> None:
        breaker = ExternalServiceError(service_name="google_gmail", headers={"Retry-After": "12"})
        code, detail = refusal_for(breaker, act=False)
        assert (code, detail) == (errors.PROVIDER_UNAVAILABLE, {"retry_after": 12})


class TestARawHttpClient:
    """The Hue client raises httpx's own errors (L9): read by their type and status."""

    @pytest.mark.parametrize(
        ("status", "code"),
        [
            (404, errors.ITEM_GONE),
            (400, errors.PROVIDER_REFUSED),
            (401, errors.RECONNECT_REQUIRED),
            (503, errors.PROVIDER_UNAVAILABLE),
        ],
    )
    def test_an_answered_status_is_classified(self, status: int, code: str) -> None:
        response = httpx.Response(status, request=_REQUEST)
        answered = httpx.HTTPStatusError("x", request=_REQUEST, response=response)
        assert refusal_for(answered, act=True)[0] == code

    def test_an_answered_throttle_passes_its_wait_on(self) -> None:
        response = httpx.Response(429, headers={"Retry-After": "7"}, request=_REQUEST)
        throttled = httpx.HTTPStatusError("x", request=_REQUEST, response=response)
        assert refusal_for(throttled, act=False) == (
            errors.PROVIDER_RATE_LIMITED,
            {"retry_after": 7},
        )

    def test_an_open_breaker_never_sent_anything(self) -> None:
        from src.infrastructure.resilience import CircuitBreakerError
        from src.infrastructure.resilience.circuit_breaker import CircuitState

        open_breaker = CircuitBreakerError("philips_hue", CircuitState.OPEN, retry_after=30)
        assert refusal_for(open_breaker, act=True) == (
            errors.PROVIDER_UNAVAILABLE,
            {"retry_after": 30},
        )


class TestAuthorityAndThrottle:
    def test_a_rejected_refresh_means_reconnect(self) -> None:
        expired = ConnectorTokenExpiredError(detail="x", connector_type="google_gmail")
        assert refusal_for(expired, act=False)[0] == errors.RECONNECT_REQUIRED

    def test_an_invalidated_connector_means_reconnect(self) -> None:
        assert refusal_for(AuthenticationError(detail="x"), act=True)[0] == (
            errors.RECONNECT_REQUIRED
        )

    def test_the_local_throttle_is_a_rate_limit_with_its_wait(self) -> None:
        throttled = RateLimitError(limit=10, window_seconds=60, retry_after=60)
        assert refusal_for(throttled, act=True) == (
            errors.PROVIDER_RATE_LIMITED,
            {"retry_after": 60},
        )


class TestTypedClientErrors:
    @pytest.mark.parametrize(
        ("failure", "code"),
        [
            (MailboxDraftNotFoundError("d"), errors.ITEM_GONE),
            (MailboxDraftChangedError("d"), errors.CONFLICT),
            (MailboxFolderUnavailableError("drafts"), errors.NOT_SUPPORTED_BY_PROVIDER),
            (EmailAttachmentNotFoundError("a"), errors.ITEM_GONE),
            (EmailAttachmentAmbiguousError("a.pdf", [{}, {}]), errors.STALE_HANDLE),
            # A folder of the pane gone, or two now answering to its name.
            (MailFolderNotFoundError("Projets", [], complete=True), errors.ITEM_GONE),
            (MailFolderAmbiguousError("Projets", ["a", "b"]), errors.CONFLICT),
            (ValueError("unreadable"), errors.INVALID_REQUEST),
            # The Hue bridge's remote token refresh finds the connector revoked.
            (_revoked(), errors.NOT_CONNECTED),
        ],
    )
    def test_a_typed_failure_is_classified(self, failure: BaseException, code: str) -> None:
        assert refusal_for(failure, act=True)[0] == code

    def test_a_part_over_the_bound_quotes_the_bound(self) -> None:
        too_large = EmailAttachmentTooLargeError(size=30, max_bytes=20)
        assert refusal_for(too_large, act=False) == (errors.TOO_LARGE, {"max_bytes": 20})


class TestStructuralOnly:
    def test_words_in_a_message_classify_nothing(self) -> None:
        """« rate limit » in a message is not a 429: an unknown failure of a read
        is « unavailable », of an act « unknown » — the safe side of each."""
        worded: Any = RuntimeError("429 rate limit exceeded, not found, conflict")
        assert refusal_for(worded, act=False)[0] == errors.PROVIDER_UNAVAILABLE
        assert refusal_for(worded, act=True)[0] == errors.OUTCOME_UNKNOWN

    def test_refuse_provider_failure_raises_the_classified_refusal(self) -> None:
        with pytest.raises(BaseAPIException) as raised:
            refuse_provider_failure(_api_error(404), act=False)
        assert raised.value.detail == {"code": "item_gone"}


class TestProviderId:
    _ADAPTER = TypeAdapter(ProviderId)

    @pytest.mark.parametrize(
        "value",
        ["18c2f0a1b2c3d4e5", "AAMkAGI2THVSAAA=", "imap:INBOX/Archive:42", "people/c123"],
    )
    def test_real_provider_ids_pass(self, value: str) -> None:
        assert self._ADAPTER.validate_python(value) == value

    @pytest.mark.parametrize("value", ["", "a b", "line\nbreak", "x" * 1025, "tab\there"])
    def test_whitespace_control_and_oversize_are_refused(self, value: str) -> None:
        with pytest.raises(ValidationError):
            self._ADAPTER.validate_python(value)
