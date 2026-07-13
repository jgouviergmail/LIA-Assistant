"""Unit tests for the ELEVENLABS_TELEPHONY connector type (P1.2)."""

import pytest

from src.domains.connectors.models import (
    ConnectorType,
    get_conflicting_connector_types,
    get_connector_display_name,
    get_functional_category,
)


@pytest.mark.unit
def test_telephony_connector_type_exists():
    assert ConnectorType.ELEVENLABS_TELEPHONY.value == "elevenlabs_telephony"


@pytest.mark.unit
def test_telephony_is_its_own_category_and_has_display_name():
    assert get_functional_category(ConnectorType.ELEVENLABS_TELEPHONY) == "telephony"
    assert get_connector_display_name(ConnectorType.ELEVENLABS_TELEPHONY) == "Telephony"


@pytest.mark.unit
def test_telephony_has_no_mutually_exclusive_conflicts():
    # Single-member category → activating telephony conflicts with nothing.
    assert get_conflicting_connector_types(ConnectorType.ELEVENLABS_TELEPHONY) == frozenset()
