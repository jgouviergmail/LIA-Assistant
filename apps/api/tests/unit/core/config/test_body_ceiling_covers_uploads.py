"""The global body ceiling must cover every configured upload (SEC-031).

``BodySizeLimitMiddleware`` rejects an oversized body before any handler runs.
Both upload ceilings (`ATTACHMENTS_MAX_DOC_SIZE_MB`, `RAG_SPACES_MAX_FILE_SIZE_MB`)
are operator-configurable up to 100 MB while `MAX_REQUEST_BODY_BYTES` defaults to
21 MB — raising one without the other would turn a valid upload into a 413 that
no endpoint log explains, and only for users large enough to hit it.

The composed ``Settings`` therefore refuses to build on that contradiction.
"""

from __future__ import annotations

import pytest

from src.core.config import Settings, get_settings
from src.core.constants import MULTIPART_ENVELOPE_OVERHEAD_BYTES


class TestBodyCeilingCoversUploads:
    """Boot-time consistency between the global cap and the upload limits."""

    def test_shipped_defaults_are_consistent(self) -> None:
        """The values we ship must satisfy their own invariant."""
        settings = get_settings()

        largest_mb = max(
            settings.attachments_max_doc_size_mb,
            settings.attachments_max_image_size_mb,
            settings.rag_spaces_max_file_size_mb,
        )
        assert settings.max_request_body_bytes >= (
            largest_mb * 1024 * 1024 + MULTIPART_ENVELOPE_OVERHEAD_BYTES
        )

    @pytest.mark.parametrize(
        "field",
        [
            "rag_spaces_max_file_size_mb",
            "attachments_max_doc_size_mb",
            "attachments_max_image_size_mb",
        ],
    )
    def test_raising_any_upload_ceiling_alone_is_refused(self, field: str) -> None:
        """Each upload ceiling is covered — not just the one that motivated it."""
        base = get_settings().model_dump()
        base[field] = 50  # allowed by the field itself (le=100), not by the cap

        with pytest.raises(ValueError, match="max_request_body_bytes"):
            Settings(**base)

    def test_raising_both_together_is_accepted(self) -> None:
        """The guard blocks the contradiction, not the legitimate change."""
        base = get_settings().model_dump()
        base["rag_spaces_max_file_size_mb"] = 50
        base["max_request_body_bytes"] = 51 * 1024 * 1024

        settings = Settings(**base)

        assert settings.rag_spaces_max_file_size_mb == 50

    def test_exact_boundary_is_accepted(self) -> None:
        """A cap sized exactly at upload + envelope is valid, not off-by-one."""
        base = get_settings().model_dump()
        base["rag_spaces_max_file_size_mb"] = 30
        base["max_request_body_bytes"] = 30 * 1024 * 1024 + MULTIPART_ENVELOPE_OVERHEAD_BYTES

        assert Settings(**base).max_request_body_bytes > 0

    def test_one_byte_below_the_boundary_is_refused(self) -> None:
        """Falsifies the test above: the comparison really is enforced."""
        base = get_settings().model_dump()
        base["rag_spaces_max_file_size_mb"] = 30
        base["max_request_body_bytes"] = 30 * 1024 * 1024 + MULTIPART_ENVELOPE_OVERHEAD_BYTES - 1

        with pytest.raises(ValueError, match="max_request_body_bytes"):
            Settings(**base)
