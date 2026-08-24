"""Lot B: the work the registries did must be visible where the catalogue is.

ADR-244 corrected 83 rows from two vendored public registries and recorded who
filled every row's capabilities — and nothing exposed that to the admin. A
column an operator cannot see is a column they cannot trust, and the first
question ``capability_provenance`` answers is exactly the one they ask in front
of the table: *is this 8192 a measurement or a placeholder nobody curated?*
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_the_model_payload_carries_the_provenance() -> None:
    from src.domains.llm.schemas import ModelPriceResponse

    assert "capability_provenance" in ModelPriceResponse.model_fields


def test_the_provenance_vocabulary_is_the_enum_the_column_stores() -> None:
    """The payload must not invent a value the column cannot hold."""
    from typing import get_args

    from src.domains.llm.models import LLMCapabilityProvenanceEnum
    from src.domains.llm.schemas import CapabilityProvenanceLiteral

    assert set(get_args(CapabilityProvenanceLiteral)) == {
        member.value for member in LLMCapabilityProvenanceEnum
    }


def test_the_status_payload_reports_what_the_sync_would_do() -> None:
    """The read-only verdict of ``task llm:catalogue:sync``, as an API shape."""
    from src.domains.llm.schemas import CatalogueStatusResponse

    fields = CatalogueStatusResponse.model_fields
    for name in ("compared", "auto", "review", "retiring", "provenance", "snapshot_generated_at"):
        assert name in fields, name


def test_the_status_counters_cannot_be_negative() -> None:
    from pydantic import ValidationError

    from src.domains.llm.schemas import CatalogueStatusResponse

    with pytest.raises(ValidationError):
        CatalogueStatusResponse(
            compared=-1,
            auto=0,
            review=0,
            retiring=[],
            provenance={},
            snapshot_generated_at=None,
        )


def test_the_retirement_vocabulary_has_one_authority() -> None:
    """The schema Literal and the status module must name the same states.

    Two hand-written copies of a closed vocabulary is the pattern this whole
    lot exists to remove: the API would happily publish a state the reporter
    never produces, or refuse one it does.
    """
    from typing import get_args

    from src.domains.llm.schemas import RetiringModelPayload
    from src.infrastructure.llm.catalogue.status import RETIREMENT_STATES

    published = get_args(RetiringModelPayload.model_fields["state"].annotation)
    assert set(published) == set(RETIREMENT_STATES)
