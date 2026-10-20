"""Resource additions cannot inherit credentials or a permissive wire policy."""

import pytest

from src.domains.ingestion.registry import IngestionResource, policy_for, validate_registry

pytestmark = pytest.mark.unit


def test_health_and_sms_have_distinct_credentials_and_closed_scopes() -> None:
    validate_registry()
    health, sms = policy_for(IngestionResource.HEALTH), policy_for(IngestionResource.SMS)
    assert health.token_prefix == "hm_"
    assert health.write_scope == "health:write"
    assert health.legacy_fields == frozenset({"date_start", "date_end"})
    assert sms.token_prefix == "pi_"
    assert sms.write_scope == "sms:write"
    assert sms.legacy_fields is None


def test_an_undeclared_resource_has_no_fallback_authority() -> None:
    with pytest.raises(ValueError):
        IngestionResource("location")
