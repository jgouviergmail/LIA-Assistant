"""Native health observations inherit public UI contracts and refuse authority/effects inputs."""

from datetime import datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from src.core.constants import HEALTH_METRICS_KINDS
from src.domains.agents.application.health_read_schemas import (
    HealthSampleKind,
    HealthSamplesRead,
    HealthTokensProjection,
    HealthTokensRead,
)
from src.domains.health_metrics.schemas import (
    HealthMetricTokenListResponse,
    HealthMetricTokenRow,
    HealthSampleRow,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "foreign"},
        {"token_hash": "secret"},
        {"delete": True},
        {"limit": True},
        {"limit": 101},
        {"as_of": datetime(2026, 1, 1)},
        {"kind": "unknown"},
        {"from_ts": "2026-01-02T00:00:00Z", "to_ts": "2026-01-01T00:00:00Z"},
    ],
)
def test_sample_request_refuses_invalid_bounds_authority_and_effects(payload):
    with pytest.raises(ValidationError):
        HealthSamplesRead.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [{"token": "secret"}, {"user_id": "foreign"}, {"limit": True}, {"as_of": datetime(2026, 1, 1)}],
)
def test_token_request_is_only_bounded_public_observation(payload):
    with pytest.raises(ValidationError):
        HealthTokensRead.model_validate(payload)


def test_source_kinds_and_nonsecret_dto_contracts_enrich_together():
    assert (
        set(get_args(HealthSampleKind))
        == set(get_args(HealthSampleRow.model_fields["kind"].annotation))
        == set(HEALTH_METRICS_KINDS)
    )
    assert set(HealthMetricTokenListResponse.model_fields) <= set(
        HealthTokensProjection.model_fields
    )
    assert not {"token", "token_hash", "raw_token", "user_id"}.intersection(
        HealthMetricTokenRow.model_fields
    )
