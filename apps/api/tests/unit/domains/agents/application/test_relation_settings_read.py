"""Read contracts bound model context and preserve unavailable dependencies."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.relation_settings_read import (
    RelationSettingsProjection,
    _debrief_available,
)
from src.domains.relations.overview_scope import RelationOverviewScope

pytestmark = pytest.mark.unit


def test_source_empty_scope_stays_empty_and_projection_contains_only_public_controls():
    observed = RelationSettingsProjection(
        overview_scope=RelationOverviewScope(sections=[], directions=[], roles=[]),
        debrief_enabled=False,
        debrief_platform_enabled=False,
        observed_at=datetime.now(UTC),
    )
    assert observed.overview_scope.sections == []
    assert {"user_id", "debrief", "contact", "email", "token"}.isdisjoint(
        RelationSettingsProjection.model_fields
    )
    with pytest.raises(ValidationError):
        RelationSettingsProjection.model_validate({**observed.model_dump(), "user_id": "other"})


async def test_dependency_failure_is_not_misrepresented_as_disabled(monkeypatch):
    failure = AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    monkeypatch.setattr(
        "src.domains.agents.application.relation_settings_read.require_capability_fresh",
        AsyncMock(side_effect=failure),
    )
    with pytest.raises(AuthorizationError) as caught:
        await _debrief_available(AsyncMock())
    assert caught.value is failure
