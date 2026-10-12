"""analyze_full hands the turn typed references: an address stays an address."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.analysis.resolved_references import (
    ReferenceValueKind,
    person_name_values,
)
from src.domains.agents.services.analysis.memory_resolver import MemoryResolution
from src.domains.agents.services.memory_reference_resolution_service import ResolvedReferences
from tests.unit.domains.agents.services.test_query_analyzer_person_evidence import (
    QUERY,
    _analysis_result,
    _make_service,
)

pytestmark = pytest.mark.unit


async def test_analyze_full_returns_typed_references() -> None:
    memory = MemoryResolution(
        facts=["The user's brother lives at 12 rue des Lilas, Lyon."],
        resolved=ResolvedReferences(
            original_query=QUERY,
            enriched_query=QUERY,
            mappings={"chez mon frère": "12 rue des Lilas, Lyon"},
            value_kinds={"chez mon frère": "postal_address"},
        ),
        references=["mon frère"],
    )
    service = _make_service(memory)
    analysis = _analysis_result(
        [{"original": "demain", "resolved": "2026-10-12", "type": "temporal"}]
    )
    with (
        patch.object(service, "analyze", AsyncMock(return_value=analysis)),
        patch.object(
            service, "_expand_domains_for_semantic_types", AsyncMock(return_value=["route"])
        ),
    ):
        intelligence = await service.analyze_full(
            query=QUERY,
            messages=[HumanMessage(content=QUERY)],
            state={"user_language": "fr"},
            config={"configurable": {}},
            original_query=QUERY,
        )
    kinds = {entry.reference: entry.kind for entry in intelligence.resolved_references}
    assert kinds == {
        "chez mon frère": ReferenceValueKind.POSTAL_ADDRESS,
        "demain": ReferenceValueKind.DATETIME,
    }
    assert person_name_values(intelligence.resolved_references) == ()
    assert intelligence.english_enriched_query == analysis.english_query
