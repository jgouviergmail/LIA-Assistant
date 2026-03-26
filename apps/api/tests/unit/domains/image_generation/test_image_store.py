"""Unit tests for image_store module.

Tests the module-level pending image store: store, peek, get_and_clear.
"""

from __future__ import annotations

import pytest

from src.domains.image_generation.image_store import (
    _pending_images,
    _sanitize_alt_text,
    get_and_clear_pending_images,
    peek_pending_images,
    store_pending_image,
)


@pytest.mark.unit
class TestSanitizeAltText:
    """Tests for _sanitize_alt_text helper."""

    def test_removes_brackets(self) -> None:
        assert _sanitize_alt_text("a [test] image") == "a test image"

    def test_removes_parens(self) -> None:
        assert _sanitize_alt_text("hello (world)") == "hello world"

    def test_removes_newlines(self) -> None:
        assert _sanitize_alt_text("line1\nline2") == "line1 line2"

    def test_truncates_to_100_chars(self) -> None:
        long_text = "x" * 200
        assert len(_sanitize_alt_text(long_text)) == 100

    def test_empty_string(self) -> None:
        assert _sanitize_alt_text("") == ""


@pytest.mark.unit
class TestPendingImageStore:
    """Tests for store, peek, and get_and_clear operations."""

    def setup_method(self) -> None:
        """Clear the store before each test."""
        _pending_images.clear()

    def teardown_method(self) -> None:
        """Clear the store after each test."""
        _pending_images.clear()

    def test_store_and_retrieve(self) -> None:
        """Stored image can be retrieved and cleared."""
        store_pending_image("conv-1", "/api/v1/attachments/abc", "a cat")
        images = get_and_clear_pending_images("conv-1")

        assert len(images) == 1
        assert images[0].url == "/api/v1/attachments/abc"
        assert images[0].alt_text == "a cat"

    def test_get_and_clear_removes(self) -> None:
        """get_and_clear removes images from the store."""
        store_pending_image("conv-1", "/url", "alt")
        get_and_clear_pending_images("conv-1")

        # Second call returns empty
        assert get_and_clear_pending_images("conv-1") == []

    def test_peek_does_not_remove(self) -> None:
        """peek reads without removing."""
        store_pending_image("conv-1", "/url", "alt")

        peeked = peek_pending_images("conv-1")
        assert len(peeked) == 1

        # Still available
        images = get_and_clear_pending_images("conv-1")
        assert len(images) == 1

    def test_multiple_images(self) -> None:
        """Multiple images for same conversation are accumulated."""
        store_pending_image("conv-1", "/url1", "alt1")
        store_pending_image("conv-1", "/url2", "alt2")

        images = get_and_clear_pending_images("conv-1")
        assert len(images) == 2

    def test_isolation_between_conversations(self) -> None:
        """Different conversations are isolated."""
        store_pending_image("conv-1", "/url1", "alt1")
        store_pending_image("conv-2", "/url2", "alt2")

        images_1 = get_and_clear_pending_images("conv-1")
        images_2 = get_and_clear_pending_images("conv-2")

        assert len(images_1) == 1
        assert len(images_2) == 1
        assert images_1[0].url == "/url1"
        assert images_2[0].url == "/url2"

    def test_unknown_conversation_returns_empty(self) -> None:
        """Unknown conversation_id returns empty list."""
        assert get_and_clear_pending_images("nonexistent") == []
        assert peek_pending_images("nonexistent") == []

    def test_alt_text_sanitized(self) -> None:
        """Alt text is sanitized on store."""
        store_pending_image("conv-1", "/url", "a [dangerous](link)")

        images = get_and_clear_pending_images("conv-1")
        assert "[" not in images[0].alt_text
        assert "(" not in images[0].alt_text
