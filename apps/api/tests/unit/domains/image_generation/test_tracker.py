"""Unit tests for image generation tracker helper.

Tests the track_image_generation_call() function that records costs
into the current TrackingContext via the current_tracker ContextVar.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domains.image_generation.tracker import track_image_generation_call


@pytest.mark.unit
class TestTrackImageGenerationCall:
    """Tests for track_image_generation_call()."""

    def test_records_when_tracker_active(self) -> None:
        """Records cost when a TrackingContext is active."""
        mock_tracker = MagicMock()
        with patch("src.domains.image_generation.tracker.current_tracker") as mock_ctx:
            mock_ctx.get.return_value = mock_tracker

            track_image_generation_call(
                model="gpt-image-1",
                quality="low",
                size="1024x1024",
                image_count=1,
                prompt="a cat",
            )

        mock_tracker.record_image_generation_call.assert_called_once_with(
            model="gpt-image-1",
            quality="low",
            size="1024x1024",
            image_count=1,
            prompt_preview="a cat",
            duration_ms=0.0,
        )

    def test_noop_when_no_tracker(self) -> None:
        """Silently no-ops when no TrackingContext is active."""
        with patch("src.domains.image_generation.tracker.current_tracker") as mock_ctx:
            mock_ctx.get.return_value = None

            # Should not raise
            track_image_generation_call(
                model="gpt-image-1",
                quality="low",
                size="1024x1024",
                image_count=1,
                prompt="a cat",
            )
