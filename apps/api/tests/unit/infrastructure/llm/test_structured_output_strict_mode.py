"""Strict mode reads the column only when someone actually filled it."""

from __future__ import annotations

from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.structured_output import resolve_strict_mode


def test_declared_row_keeps_the_provider_heuristic() -> None:
    """83 rows carry an unfilled ``false``; believing it would regress them all."""
    caps = ModelProfile(supports_strict_mode=False, capability_provenance="declared")
    assert resolve_strict_mode(True, "openai", caps) is True


def test_a_filled_false_narrows() -> None:
    caps = ModelProfile(supports_strict_mode=False, capability_provenance="verified")
    assert resolve_strict_mode(True, "openai", caps) is False


def test_a_filled_true_is_honoured() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="verified")
    assert resolve_strict_mode(True, "openai", caps) is True


def test_imported_is_NOT_evidence_about_strict_mode() -> None:
    """Provenance is row-level; the evidence behind it is field-level.

    ``imported`` means the registries corroborated the fields they publish
    (``sync_diff.CORRECTABLE_FIELDS``). ``supports_strict_mode`` is not one of
    them — no registry publishes it. Measured 2026-08-24: 41 active OpenAI rows
    are ``imported`` while still carrying the unfilled ``false``, ``gpt-4.1``
    and ``gpt-5.2`` among them. Believing that would regress all 41.
    """
    caps = ModelProfile(supports_strict_mode=False, capability_provenance="imported")
    assert resolve_strict_mode(True, "openai", caps) is True


def test_strict_mode_is_outside_what_the_registries_correct() -> None:
    """A structural pin: if this field ever enters the import, revisit the rule."""
    from src.infrastructure.llm.catalogue.sync_diff import CORRECTABLE_FIELDS

    assert "supports_strict_mode" not in {column for column, _ in CORRECTABLE_FIELDS}


def test_a_non_openai_provider_never_uses_strict_mode() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="verified")
    assert resolve_strict_mode(True, "anthropic", caps) is False


def test_an_incompatible_schema_never_uses_strict_mode() -> None:
    caps = ModelProfile(supports_strict_mode=True, capability_provenance="verified")
    assert resolve_strict_mode(False, "openai", caps) is False


def test_no_profile_keeps_the_provider_heuristic() -> None:
    """A model outside the catalogue behaves exactly as it did before ADR-244."""
    assert resolve_strict_mode(True, "openai", None) is True
