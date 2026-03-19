"""
Unit tests for browser data models.

Phase: evolution F7 — Browser Control (Playwright)
"""

from datetime import UTC, datetime

from src.infrastructure.browser.models import (
    BrowserAction,
    BrowserSessionInfo,
    PageSnapshot,
)


class TestPageSnapshot:
    """Tests for PageSnapshot model."""

    def test_create_snapshot(self):
        """PageSnapshot can be created with required fields."""
        snapshot = PageSnapshot(
            url="https://example.com",
            title="Example",
            content="Hello World",
            interactive_count=5,
            total_count=100,
        )
        assert snapshot.url == "https://example.com"
        assert snapshot.title == "Example"
        assert snapshot.content == "Hello World"
        assert snapshot.interactive_count == 5

    def test_snapshot_defaults(self):
        """PageSnapshot has sensible defaults."""
        snapshot = PageSnapshot(
            url="https://example.com",
            title="Example",
            content="",
        )
        assert snapshot.interactive_count == 0
        assert snapshot.total_count == 0


class TestBrowserAction:
    """Tests for BrowserAction model."""

    def test_navigate_action(self):
        """Navigate action has no ref/value."""
        action = BrowserAction(action_type="navigate")
        assert action.action_type == "navigate"
        assert action.ref is None

    def test_click_action(self):
        """Click action has a ref."""
        action = BrowserAction(action_type="click", ref="E3")
        assert action.ref == "E3"

    def test_fill_action(self):
        """Fill action has ref and value."""
        action = BrowserAction(action_type="fill", ref="E2", value="Hello")
        assert action.ref == "E2"
        assert action.value == "Hello"


class TestBrowserSessionInfo:
    """Tests for BrowserSessionInfo model."""

    def test_create_session_info(self):
        """BrowserSessionInfo can be created and serialized."""
        info = BrowserSessionInfo(
            session_id="abc123",
            user_id="user456",
            created_at=datetime.now(UTC),
            current_url="https://example.com",
            page_title="Example",
            worker_pid=1234,
            navigation_count=3,
        )
        assert info.session_id == "abc123"
        assert info.worker_pid == 1234

    def test_session_info_serialization(self):
        """BrowserSessionInfo serializes to JSON correctly."""
        info = BrowserSessionInfo(
            session_id="abc",
            user_id="user",
            created_at=datetime.now(UTC),
            worker_pid=1,
        )
        json_str = info.model_dump_json()
        assert "abc" in json_str
        assert "worker_pid" in json_str
