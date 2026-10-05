"""Personal-avatar declarations: no platform key or personal-spend ledger."""

import pytest

from src.core.config import Settings
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.domains.usage_limits.cost_bearers import COST_FAMILIES, QUOTA_COLUMN_OF, CostBearer
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def test_simli_is_a_personal_connector_independent_of_live():
    simli = ConnectorType("simli")
    assert not simli.is_oauth
    assert not simli.uses_global_api_key
    assert not simli.is_keyless
    assert CONNECTOR_FUNCTIONAL_CATEGORIES["avatar"] == frozenset({simli})
    assert simli not in CONNECTOR_FUNCTIONAL_CATEGORIES["live"]


def test_avatar_is_opt_in_and_cannot_bill_the_instance():
    column = User.__table__.columns["speaking_avatar_enabled"]
    assert column.default.arg is False
    assert COST_FAMILIES["simli"].bearer is CostBearer.USER
    assert QUOTA_COLUMN_OF["simli"] is None


def test_deployment_ceiling_is_off_and_technical_bounds_are_finite():
    config = Settings(_env_file=None, avatar_enabled=False)
    assert config.avatar_enabled is False
    assert 0 < config.avatar_session_length_seconds <= 3600
    assert 0 < config.avatar_idle_seconds <= config.avatar_session_length_seconds
    with pytest.raises(ValueError):
        Settings(_env_file=None, avatar_session_length_seconds=0)
