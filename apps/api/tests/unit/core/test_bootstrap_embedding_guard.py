"""Boot guard for the embedding configuration (ADR-242, ADR-085 doctrine).

Three settings choose an embedding model and its output dimensionality
(memory, journals, RAG spaces), and each writes into a pgvector column whose
width is fixed in the SQLAlchemy model — `Vector(1536)`. Nothing tied the two
together: raising `MEMORY_EMBEDDING_DIMENSIONS` to 3072 produced 3072-wide
vectors against a `vector(1536)` column, so **every** memory write failed at
runtime, in production, long after boot.

The second half is the model itself. The adapter sends
`task_type=RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT`, and every retrieval
threshold is calibrated on the asymmetric encodings those produce. Verified
against the live API on 2026-08-22: `gemini-embedding-2` accepts the parameter
and returns bit-identical vectors for every task type. Configuring it would
silently flatten the asymmetry with no error anywhere.
"""

from __future__ import annotations

import pytest

from src.core.bootstrap import validate_embedding_configuration
from src.domains.llm_config.constants import EMBEDDING_MODEL_CAPABILITIES


@pytest.mark.unit
class TestEmbeddingCapabilityRegistry:
    """The registry is the single source of truth on embedding models."""

    def test_every_shipped_default_model_is_declared(self) -> None:
        from src.core.constants import (
            INTEREST_EMBEDDING_MODEL_DEFAULT,
            JOURNAL_EMBEDDING_MODEL_DEFAULT,
            MEMORY_EMBEDDING_MODEL_DEFAULT,
            RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
        )

        defaults = {
            MEMORY_EMBEDDING_MODEL_DEFAULT,
            INTEREST_EMBEDDING_MODEL_DEFAULT,
            JOURNAL_EMBEDDING_MODEL_DEFAULT,
            RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
        }
        undeclared = {
            m for m in defaults if m.removeprefix("models/") not in EMBEDDING_MODEL_CAPABILITIES
        }

        assert undeclared == set()

    def test_the_model_in_use_supports_task_types(self) -> None:
        """If this ever fails, the calibrated thresholds no longer apply."""
        assert EMBEDDING_MODEL_CAPABILITIES["gemini-embedding-001"].supports_task_type is True

    def test_gemini_embedding_2_is_declared_as_ignoring_task_types(self) -> None:
        """Verified against the live API: identical vectors for every task type."""
        assert EMBEDDING_MODEL_CAPABILITIES["gemini-embedding-2"].supports_task_type is False

    def test_declared_input_limits_match_the_published_ones(self) -> None:
        assert EMBEDDING_MODEL_CAPABILITIES["gemini-embedding-001"].max_input_tokens == 2048
        assert EMBEDDING_MODEL_CAPABILITIES["gemini-embedding-2"].max_input_tokens == 8192

    def test_every_entry_offers_at_least_one_dimensionality(self) -> None:
        empty = [m for m, c in EMBEDDING_MODEL_CAPABILITIES.items() if not c.dimensions]

        assert empty == []


@pytest.mark.unit
class TestValidateEmbeddingConfiguration:
    """Boot refuses an incoherent embedding configuration."""

    def test_the_shipped_configuration_boots(self) -> None:
        validate_embedding_configuration()

    def test_a_dimension_that_does_not_fit_the_column_refuses_to_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "memory_embedding_dimensions", 3072, raising=False)

        with pytest.raises(RuntimeError, match="memory_embedding_dimensions"):
            validate_embedding_configuration()

    @pytest.mark.parametrize(
        "setting",
        ["journal_embedding_dimensions", "rag_spaces_embedding_dimensions"],
    )
    def test_every_pgvector_backed_setting_is_checked(
        self, setting: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, setting, 768, raising=False)

        with pytest.raises(RuntimeError, match=setting):
            validate_embedding_configuration()

    def test_an_unknown_model_refuses_to_boot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An undeclared model means nobody checked its task_type or its limits."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "memory_embedding_model", "models/mystery-embed", False)

        with pytest.raises(RuntimeError, match="mystery-embed"):
            validate_embedding_configuration()

    def test_a_dimension_the_model_does_not_offer_refuses_to_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "interest_embedding_dimensions", 999, raising=False)

        with pytest.raises(RuntimeError, match="interest_embedding_dimensions"):
            validate_embedding_configuration()

    def test_a_width_the_column_accepts_but_the_model_cannot_produce_is_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two checks are independent: matching the column proves nothing
        about the model being able to emit that width."""
        from src.core.config import settings
        from src.domains.llm_config import constants as llm_constants

        narrow = llm_constants.EmbeddingModelCapability(
            supports_task_type=True, max_input_tokens=2048, dimensions=(768,)
        )
        monkeypatch.setitem(llm_constants.EMBEDDING_MODEL_CAPABILITIES, "narrow-embed", narrow)
        monkeypatch.setattr(settings, "memory_embedding_model", "models/narrow-embed", False)

        with pytest.raises(RuntimeError, match="not offered by"):
            validate_embedding_configuration()

    def test_a_model_ignoring_task_types_warns_but_still_boots(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """It is a deliberate quality trade-off, not a broken configuration.

        Boot must not be blocked — but it must be impossible to make the switch
        without the log saying the asymmetry is gone.
        """
        from src.core.config import settings

        monkeypatch.setattr(settings, "memory_embedding_model", "models/gemini-embedding-2", False)
        monkeypatch.setattr(settings, "memory_embedding_dimensions", 1536, raising=False)

        with caplog.at_level("WARNING"):
            validate_embedding_configuration()

        assert "task_type" in caplog.text
        assert "gemini-embedding-2" in caplog.text

    def test_the_prefixed_and_bare_model_ids_are_both_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "memory_embedding_model", "gemini-embedding-001", False)

        validate_embedding_configuration()


@pytest.mark.unit
class TestGuardIsWired:
    """A validator the lifespan never calls protects nothing."""

    def test_the_lifespan_failfast_step_runs_the_embedding_validator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.startup import registries

        called: list[bool] = []
        monkeypatch.setattr(
            registries, "validate_embedding_configuration", lambda: called.append(True)
        )

        registries.run_failfast_validations()

        assert called == [True]

    def test_an_invalid_embedding_configuration_aborts_the_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.infrastructure.startup import registries

        def _boom() -> None:
            raise RuntimeError("Invalid embedding configuration: memory_embedding_dimensions=3072")

        monkeypatch.setattr(registries, "validate_embedding_configuration", _boom)

        with pytest.raises(RuntimeError, match="memory_embedding_dimensions"):
            registries.run_failfast_validations()
