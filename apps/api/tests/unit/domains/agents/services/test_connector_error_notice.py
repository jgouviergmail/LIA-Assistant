"""Unit tests for the connector error notice module (Lot 3 P3).

The module classifies TYPED connector exceptions (never string matching) into
actionable notices and emits them on the LangGraph custom stream so the chat
can render a "Reconnect" banner. Two real-world signals are covered:

- ``ConnectorTokenExpiredError`` — raised by ``_refresh_oauth_token`` when the
  refresh is rejected (``invalid_grant`` = revoked/expired token). This is the
  dominant path in practice.
- ``ConnectorAPIError`` with upstream 401/403 — direct API auth failures.

Anything else (500s, ValueError, timeouts) must classify to ``None``: a wrong
banner ("reconnect" on a transient server error) is worse than none.
"""

from typing import Any

from src.core.exceptions import ConnectorAPIError, ConnectorTokenExpiredError
from src.domains.agents.services.connector_error_notice import (
    classify_connector_exception,
    emit_connector_notice,
    emit_connector_notice_for_exception,
)
from src.domains.agents.tools.exceptions import ConnectorNotEnabledError


class _RecordingWriter:
    """Minimal stand-in for the LangGraph stream writer callable."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class TestClassifyConnectorException:
    def test_token_expired_maps_to_reconnect(self) -> None:
        exc = ConnectorTokenExpiredError("token revoked", connector_type="google_gmail")
        notice = classify_connector_exception(exc)
        assert notice is not None
        assert notice.action == "reconnect"
        assert notice.connector_type == "google_gmail"

    def test_api_error_401_maps_to_reconnect(self) -> None:
        exc = ConnectorAPIError(
            connector_type="google_calendar", status_code=401, detail="unauthorized"
        )
        notice = classify_connector_exception(exc)
        assert notice is not None
        assert notice.action == "reconnect"
        assert notice.connector_type == "google_calendar"

    def test_api_error_403_maps_to_reconnect(self) -> None:
        exc = ConnectorAPIError(
            connector_type="microsoft_outlook", status_code=403, detail="forbidden"
        )
        notice = classify_connector_exception(exc)
        assert notice is not None
        assert notice.action == "reconnect"

    def test_api_error_429_maps_to_rate_limit(self) -> None:
        exc = ConnectorAPIError(
            connector_type="google_gmail", status_code=429, detail="rate limited"
        )
        notice = classify_connector_exception(exc)
        assert notice is not None
        assert notice.action == "rate_limit"

    def test_api_error_500_is_not_actionable(self) -> None:
        exc = ConnectorAPIError(
            connector_type="google_gmail", status_code=502, detail="bad gateway"
        )
        assert classify_connector_exception(exc) is None

    def test_api_error_404_is_not_actionable(self) -> None:
        exc = ConnectorAPIError(connector_type="google_gmail", status_code=404, detail="not found")
        assert classify_connector_exception(exc) is None

    def test_generic_exception_is_not_actionable(self) -> None:
        assert classify_connector_exception(ValueError("boom")) is None
        assert classify_connector_exception(TimeoutError()) is None

    def test_not_enabled_enriched_with_error_connector_maps_to_reconnect(self) -> None:
        """ADR-134 V2: on runs AFTER the breakage the connector is status=ERROR
        and is no longer resolved — the raise site enriches the exception with
        the broken connector so the same banner comes back."""
        exc = ConnectorNotEnabledError(
            "No Email service is enabled.",
            connector_name="Email",
            functional_category="email",
            error_connector_type="google_gmail",
        )

        notice = classify_connector_exception(exc)

        assert notice is not None
        assert notice.action == "reconnect"
        assert notice.connector_type == "google_gmail"

    def test_not_enabled_without_broken_connector_is_not_actionable(self) -> None:
        """A genuinely unconfigured category must NOT show "Reconnect" — there
        is nothing to reconnect."""
        exc = ConnectorNotEnabledError("No Email service is enabled.", connector_name="Email")

        assert classify_connector_exception(exc) is None


class TestEmitConnectorNotice:
    def test_emits_structured_tool_error_event(self, monkeypatch: Any) -> None:
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )
        exc = ConnectorTokenExpiredError("token revoked", connector_type="google_gmail")

        emitted = emit_connector_notice_for_exception(exc, tool_name="search_emails")

        assert emitted is True
        assert len(writer.events) == 1
        event = writer.events[0]
        assert event["type"] == "execution_step"
        assert event["step_type"] == "tool_error"
        meta = event["metadata"]
        assert meta["connector_type"] == "google_gmail"
        assert meta["action"] == "reconnect"
        assert meta["tool_name"] == "search_emails"

    def test_non_actionable_exception_emits_nothing(self, monkeypatch: Any) -> None:
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )

        emitted = emit_connector_notice_for_exception(ValueError("x"), tool_name="t")

        assert emitted is False
        assert writer.events == []

    def test_writer_unavailable_is_a_safe_noop(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: None,
        )
        exc = ConnectorAPIError(connector_type="google_gmail", status_code=401, detail="x")

        # Must not raise — banner emission is strictly best-effort.
        emitted = emit_connector_notice_for_exception(exc, tool_name="search_emails")

        assert emitted is False

    def test_direct_emission_for_non_exception_paths(self, monkeypatch: Any) -> None:
        """ConnectorTool.execute returns a formatted error instead of raising
        when a category has no active provider — that path emits directly."""
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )

        emitted = emit_connector_notice("google_gmail", "reconnect", tool_name="get_emails_tool")

        assert emitted is True
        event = writer.events[0]
        assert event["step_type"] == "tool_error"
        assert event["metadata"] == {
            "connector_type": "google_gmail",
            "action": "reconnect",
            "tool_name": "get_emails_tool",
        }


class TestHandleToolExceptionClassification:
    """The central tool exception handler (runtime_helpers) is the main
    emission point: ConnectorToolBase catches every exception at
    ``base.py::except Exception`` — typed connector errors never reach the
    executors for standard tools, so the handler must classify + emit."""

    def test_token_expired_maps_to_unauthorized_and_emits(self, monkeypatch: Any) -> None:
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )
        from src.domains.agents.tools.runtime_helpers import handle_tool_exception

        exc = ConnectorTokenExpiredError("revoked", connector_type="google_gmail")
        output = handle_tool_exception(exc, "search_emails_tool")

        assert output.success is False
        assert output.error_code == "UNAUTHORIZED"
        assert len(writer.events) == 1
        assert writer.events[0]["metadata"]["action"] == "reconnect"

    def test_rate_limit_maps_to_rate_limit_code(self, monkeypatch: Any) -> None:
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )
        from src.domains.agents.tools.runtime_helpers import handle_tool_exception

        exc = ConnectorAPIError(connector_type="google_gmail", status_code=429, detail="x")
        output = handle_tool_exception(exc, "search_emails_tool")

        assert output.error_code == "RATE_LIMIT_EXCEEDED"
        assert writer.events[0]["metadata"]["action"] == "rate_limit"

    def test_generic_exception_stays_internal_error(self, monkeypatch: Any) -> None:
        writer = _RecordingWriter()
        monkeypatch.setattr(
            "src.domains.agents.services.connector_error_notice._get_writer",
            lambda: writer,
        )
        from src.domains.agents.tools.runtime_helpers import handle_tool_exception

        output = handle_tool_exception(ValueError("boom"), "some_tool")

        assert output.error_code == "INTERNAL_ERROR"
        assert writer.events == []


class TestConnectorTokenExpiredErrorContract:
    def test_inherits_validation_error_contract(self) -> None:
        """Subclassing keeps every existing `except ValidationError` and the
        HTTP 400 contract intact — the refresh path change is invisible to
        current callers."""
        from src.core.exceptions import ValidationError

        exc = ConnectorTokenExpiredError("msg", connector_type="google_gmail")
        assert isinstance(exc, ValidationError)
        assert exc.status_code == 400
        assert exc.connector_type == "google_gmail"

    def test_connector_api_error_exposes_typed_attributes(self) -> None:
        exc = ConnectorAPIError(connector_type="google_tasks", status_code=403, detail="d")
        assert exc.connector_type == "google_tasks"
        assert exc.upstream_status_code == 403
