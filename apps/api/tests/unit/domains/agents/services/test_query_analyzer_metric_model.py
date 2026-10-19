"""A delayed metric must name the model that ran, not a later configuration."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.domains.agents.services.test_query_analyzer_peer_routing import (
    _make_service,
    _misrouted_result,
    _run,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "model_used,expected", [("model-before", "model-before"), (None, "unknown")]
)
async def test_semantic_terms_metric_keeps_the_call_model_after_an_admin_switch(
    model_used: str | None, expected: str
) -> None:
    analysis = replace(
        _misrouted_result(), semantic_filter_terms=["delayed shipment"], model_used=model_used
    )
    metric = MagicMock()
    with (
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            return_value=SimpleNamespace(model="model-after"),
        ),
        patch(
            "src.domains.agents.services.query_analyzer_service.planner_semantic_filter_terms_emitted",
            metric,
        ),
    ):
        await _run(_make_service(), [], analysis_result=analysis)
    metric.labels.assert_called_once_with(model=expected, term_count_bucket="1")
