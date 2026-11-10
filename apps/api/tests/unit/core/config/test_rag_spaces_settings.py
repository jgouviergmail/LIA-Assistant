"""The RAG spaces bounds admit what the operator runs in production."""

from __future__ import annotations

import pytest

from src.core.config.rag_spaces import RAGSpacesSettings

pytestmark = pytest.mark.unit


def test_a_space_may_hold_ten_thousand_documents() -> None:
    """Owner decision, 2026-11-09: production runs 10 000 documents per space. The
    former ceiling of 200 refused that value at boot and kept the API restarting."""
    settings = RAGSpacesSettings(rag_spaces_max_docs_per_space=10_000)

    assert settings.rag_spaces_max_docs_per_space == 10_000


def test_a_mail_sync_can_fill_the_configured_space_capacity() -> None:
    """An operator can align a full label census with the space's capacity."""
    settings = RAGSpacesSettings(rag_spaces_max_docs_per_space=10_000)
    configured = RAGSpacesSettings(
        rag_spaces_max_docs_per_space=settings.rag_spaces_max_docs_per_space,
        rag_mail_max_threads_per_sync=settings.rag_spaces_max_docs_per_space,
    )

    assert configured.rag_mail_max_threads_per_sync == settings.rag_spaces_max_docs_per_space
