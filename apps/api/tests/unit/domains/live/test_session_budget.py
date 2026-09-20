"""An optional per-session spend ceiling on a live connector (ADR-300 wave 3).

The ceiling is the CONNECTOR's (provider granularity, owner decision
2026-09-19), in euros on the person's own key: stored beside the models,
published at the start, enforced by the browser's indicative meter — the
platform records nothing of it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.constants import LIVE_SESSION_BUDGET_EUR_MAX
from src.domains.live.model_settings import (
    BUDGET_KEY,
    read_session_budget,
    write_session_budget,
)
from src.domains.live.schemas import LiveConnectorSettings
from tests.unit.domains.live.test_service import (
    CMODULE,
    MODULE,
    USER,
    _chosen,
    _connector,
    _fake_provider,
    _service,
)

pytestmark = pytest.mark.unit


# -- the metadata --------------------------------------------------------------


def test_the_ceiling_is_read_only_when_readable_and_within_the_bound() -> None:
    assert read_session_budget(None) is None
    assert read_session_budget({}) is None
    assert read_session_budget({BUDGET_KEY: 2.5}) == 2.5
    assert read_session_budget({BUDGET_KEY: 3}) == 3.0
    assert read_session_budget({BUDGET_KEY: "2.5"}) is None
    assert read_session_budget({BUDGET_KEY: True}) is None
    assert read_session_budget({BUDGET_KEY: 0}) is None
    assert read_session_budget({BUDGET_KEY: -1}) is None
    assert read_session_budget({BUDGET_KEY: LIVE_SESSION_BUDGET_EUR_MAX + 1}) is None


def test_the_ceiling_is_written_as_a_new_dict_and_dropped_when_none() -> None:
    before = {"model": "m", "models": {}}
    with_budget = write_session_budget(before, 2.0)
    assert with_budget is not before
    assert with_budget[BUDGET_KEY] == 2.0 and before.get(BUDGET_KEY) is None
    without = write_session_budget(with_budget, None)
    assert BUDGET_KEY not in without
    assert without["model"] == "m"


# -- the schema ----------------------------------------------------------------


def test_the_schema_publishes_the_bound_it_enforces() -> None:
    assert _chosen(session_budget_eur=LIVE_SESSION_BUDGET_EUR_MAX).session_budget_eur == (
        LIVE_SESSION_BUDGET_EUR_MAX
    )
    with pytest.raises(ValidationError):
        _chosen(session_budget_eur=LIVE_SESSION_BUDGET_EUR_MAX + 0.01)
    with pytest.raises(ValidationError):
        _chosen(session_budget_eur=0)
    assert _chosen().session_budget_eur is None


# -- the service ---------------------------------------------------------------


async def test_the_ceiling_is_stored_beside_the_models_and_read_back() -> None:
    connector = _connector()
    service, _, _ = _service(connector)
    provider = _fake_provider()
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.connectors.update_connector_settings(
            USER, "gemini", _chosen(session_budget_eur=2.5), language="fr"
        )
    assert response.settings.session_budget_eur == 2.5
    assert connector.connector_metadata[BUDGET_KEY] == 2.5
    # It is the connector's: no model carries it.
    assert BUDGET_KEY not in connector.connector_metadata["models"]["gemini-3.8-live"]
    # And a save without it drops it.
    with patch(f"{CMODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.connectors.update_connector_settings(
            USER, "gemini", _chosen(), language="fr"
        )
    assert response.settings.session_budget_eur is None
    assert BUDGET_KEY not in connector.connector_metadata


async def test_start_publishes_the_connectors_ceiling() -> None:
    connector = _connector()
    connector.connector_metadata = {**connector.connector_metadata, BUDGET_KEY: 1.5}
    service, _, _ = _service(connector)
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_budget_eur == 1.5


async def test_start_publishes_no_ceiling_when_none_is_set() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex"
        )
    assert response.session_budget_eur is None


def test_the_settings_schema_round_trips_the_ceiling() -> None:
    settings = LiveConnectorSettings(
        model="m",
        voice="Kore",
        thinking_level=None,
        idle_timeout_seconds=60,
        session_max_minutes=10,
        session_budget_eur=2,
    )
    assert LiveConnectorSettings.model_validate(settings.model_dump()).session_budget_eur == 2.0
