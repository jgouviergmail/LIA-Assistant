"""Guard the DocumentGenerationSettings composition into the Settings MRO (ADR-226)."""

import pytest

from src.core.config.document_generation import DocumentGenerationSettings
from src.core.constants import (
    DOCUMENT_GENERATION_ENABLED_DEFAULT,
    DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
)


@pytest.mark.unit
class TestDocumentGenerationSettings:
    """The document-generation config module is composed and carries sane defaults."""

    def test_defaults_come_from_constants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Neutralize any ambient overrides so defaults are actually exercised.
        for var in (
            "DOCUMENT_GENERATION_ENABLED",
            "DOCUMENT_GENERATION_RATE_LIMIT_CALLS",
            "DOCUMENT_GENERATION_RATE_LIMIT_WINDOW",
            "DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS",
            "MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS",
            "DOCUMENT_GENERATION_MAX_SOURCE_CHARS",
        ):
            monkeypatch.delenv(var, raising=False)

        s = DocumentGenerationSettings()
        assert s.document_generation_enabled is DOCUMENT_GENERATION_ENABLED_DEFAULT
        assert (
            s.document_generation_rate_limit_calls == DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT
        )
        assert (
            s.document_generation_rate_limit_window
            == DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT
        )
        assert (
            s.document_generation_tool_timeout_seconds
            == DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT
        )
        assert (
            s.max_document_generation_tool_timeout_seconds
            == MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT
        )
        assert (
            s.document_generation_max_source_chars == DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT
        )

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCUMENT_GENERATION_ENABLED", "false")
        monkeypatch.setenv("DOCUMENT_GENERATION_RATE_LIMIT_CALLS", "3")
        s = DocumentGenerationSettings()
        assert s.document_generation_enabled is False
        assert s.document_generation_rate_limit_calls == 3

    def test_composed_into_settings(self) -> None:
        from src.core.config import Settings

        assert "document_generation_enabled" in Settings.model_fields
        assert "max_document_generation_tool_timeout_seconds" in Settings.model_fields
