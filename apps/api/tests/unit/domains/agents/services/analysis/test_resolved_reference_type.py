"""The analyzer declares what each resolved value is — and a typo never fails the turn.

A validation failure of ``QueryAnalysisOutput`` sends the whole turn to the
conversation fallback with no domain, so the closed vocabulary is read
forgivingly (ADR-120 amendment 2026-10-11).
"""

import pytest

from src.domains.agents.analysis.resolved_references import AnalyzerReferenceType
from src.domains.agents.services.analysis.query_analysis_schemas import QueryAnalysisOutput

pytestmark = pytest.mark.unit


def _output(reference: dict[str, object]) -> QueryAnalysisOutput:
    return QueryAnalysisOutput.model_validate(
        {
            "intent": "action",
            "english_query": "q",
            "reasoning": "r",
            "resolved_references": [reference],
        }
    )


def test_a_declared_type_is_read() -> None:
    out = _output({"original": "montbéliard", "resolved": "Montbéliard", "type": "place"})
    assert out.resolved_references[0].type is AnalyzerReferenceType.PLACE


@pytest.mark.parametrize("raw", ["location", None, 3, "", ["place"]])
def test_unknown_type_never_fails_the_analysis(raw: object) -> None:
    out = _output({"original": "x", "resolved": "y", "type": raw})
    assert out.resolved_references[0].type is AnalyzerReferenceType.CONTEXTUAL


def test_an_absent_type_is_contextual() -> None:
    out = _output({"original": "x", "resolved": "y"})
    assert out.resolved_references[0].type is AnalyzerReferenceType.CONTEXTUAL


def test_the_schema_publishes_the_vocabulary() -> None:
    schema = QueryAnalysisOutput.model_json_schema()
    assert set(schema["$defs"]["AnalyzerReferenceType"]["enum"]) == {
        t.value for t in AnalyzerReferenceType
    }
