"""Capability provenance: which authority filled a row's capability fields."""

from __future__ import annotations

from src.domains.llm.models import LLMCapabilityProvenanceEnum, LLMModel


def test_provenance_enum_values() -> None:
    assert {m.value for m in LLMCapabilityProvenanceEnum} == {
        "declared",
        "imported",
        "verified",
    }


def test_model_declares_the_columns() -> None:
    columns = LLMModel.__table__.columns
    assert "capability_provenance" in columns
    assert "deprecation_date" in columns
    assert columns["deprecation_date"].nullable is True
    assert columns["capability_provenance"].nullable is False


def test_provenance_defaults_to_declared() -> None:
    """A row nobody curated must announce itself as uncurated."""
    column = LLMModel.__table__.columns["capability_provenance"]
    assert column.default is not None
    assert column.default.arg is LLMCapabilityProvenanceEnum.declared
    assert column.server_default is not None


def test_deprecation_date_has_no_default() -> None:
    """Absence of a date means "the registry published none", never "today"."""
    column = LLMModel.__table__.columns["deprecation_date"]
    assert column.default is None
    assert column.server_default is None


def test_the_runtime_constants_match_the_orm_enum() -> None:
    """The hot path uses strings; the two vocabularies must never drift.

    ``ModelProfile``, ``get_effective_context_window`` and the catalogue sync
    compare against the ``core.constants`` strings rather than importing the
    ORM enum, so the runtime does not pull the domain layer into ``core`` and
    ``infrastructure``. This pins every member.
    """
    from src.core import constants

    runtime = {
        constants.CAPABILITY_PROVENANCE_DECLARED,
        constants.CAPABILITY_PROVENANCE_IMPORTED,
        constants.CAPABILITY_PROVENANCE_VERIFIED,
    }
    assert runtime == {member.value for member in LLMCapabilityProvenanceEnum}


def test_verified_is_reachable_from_a_human_edit() -> None:
    """An enum member no code path can produce is dead vocabulary.

    ``imported`` comes from the catalogue sync, ``declared`` is the column
    default; ``verified`` is produced by :class:`LLMModelService.update` when a
    human changes a registry-owned capability, which is what stops the sync
    from ever overwriting that row again.
    """
    import inspect

    from src.domains.llm import service as service_module

    source = inspect.getsource(service_module.LLMModelService.update)
    assert "LLMCapabilityProvenanceEnum.verified" in source
    assert service_module._REGISTRY_OWNED_FIELDS, "the trigger set must not be empty"
    assert "max_input_tokens" in service_module._REGISTRY_OWNED_FIELDS


def test_the_documented_scope_names_the_real_field_set() -> None:
    """The enum docstring promises ``imported`` covers CORRECTABLE_FIELDS.

    If a field ever joins or leaves that tuple, the promise changes and every
    provenance-arbitrated reader must be revisited — starting with
    ``resolve_strict_mode``, which requires ``verified`` precisely because
    ``supports_strict_mode`` is outside it.
    """
    from src.infrastructure.llm.catalogue.sync_diff import CORRECTABLE_FIELDS

    assert {column for column, _ in CORRECTABLE_FIELDS} == {
        "max_input_tokens",
        "max_output_tokens",
        "supports_tools",
        "supports_structured_output",
        "supports_vision",
    }
    docstring = LLMCapabilityProvenanceEnum.__doc__ or ""
    assert "CORRECTABLE_FIELDS" in docstring
