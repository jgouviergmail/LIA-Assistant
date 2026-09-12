"""A new account starts with every user connector that needs no key.

Wikipedia, the browser, Google Places, Google Weather and Google Environment
are activated by ONE click in the settings and ask nothing of the person: a
fresh account that has to find and press five buttons before the assistant
can look up a place or the weather is a worse first day than one where those
already work (owner decision, 2026-09-11 — firm, no instance setting).

What must hold:
- the list is the backend's declaration (``ConnectorType.get_keyless_types``),
  never a copy typed here;
- a type the administrator disabled globally is NOT provisioned;
- a platform-key type is NOT provisioned when ``GOOGLE_API_KEY`` is empty —
  an active connector that can only fail is worse than an absent one;
- the browser is NOT provisioned when the instance switched it off;
- the rows are ACTIVE and carry the shape manual activation writes, plus a
  ``provisioned_by`` stamp so the register says where they came from;
- a failure never breaks a sign-up.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.models import ConnectorStatus, ConnectorType

pytestmark = pytest.mark.unit

MODULE = "src.domains.users.keyless_connectors_provisioning"


def _settings(*, google_api_key: str = "platform-key", browser_enabled: bool = True) -> MagicMock:
    fake = MagicMock()
    fake.google_api_key = google_api_key
    fake.browser_enabled = browser_enabled
    return fake


def _repository(disabled: frozenset[ConnectorType] = frozenset()) -> MagicMock:
    """A ConnectorRepository whose global configs disable the given types."""

    async def _get_global_config_by_type(connector_type: ConnectorType) -> MagicMock | None:
        if connector_type in disabled:
            config = MagicMock()
            config.is_enabled = False
            return config
        return None  # No row: enabled by default, like ConnectorService._check_connector_enabled

    repo = MagicMock()
    repo.get_global_config_by_type = AsyncMock(side_effect=_get_global_config_by_type)
    return repo


def _added_types(db: MagicMock) -> set[ConnectorType]:
    return {call.args[0].connector_type for call in db.add.call_args_list}


async def _run(
    db: MagicMock,
    *,
    settings: MagicMock | None = None,
    disabled: frozenset[ConnectorType] = frozenset(),
) -> list[ConnectorType]:
    from src.domains.users.keyless_connectors_provisioning import provision_keyless_connectors

    with (
        patch(f"{MODULE}.settings", settings or _settings()),
        patch(f"{MODULE}.ConnectorRepository", return_value=_repository(disabled)),
    ):
        return await provision_keyless_connectors(db, uuid4())


def test_the_keyless_list_is_the_backend_declaration() -> None:
    """Five types, each activated by one click and asking nothing of the person."""
    assert ConnectorType.get_keyless_types() == frozenset(
        {
            ConnectorType.WIKIPEDIA,
            ConnectorType.BROWSER,
            ConnectorType.GOOGLE_PLACES,
            ConnectorType.GOOGLE_WEATHER,
            ConnectorType.GOOGLE_ENVIRONMENT,
        }
    )
    assert ConnectorType.WIKIPEDIA.is_keyless
    assert not ConnectorType.BRAVE_SEARCH.is_keyless
    # Routes is platform-key too but has no connector row: its tools read the
    # platform key directly, so nothing here may create one.
    assert not ConnectorType.GOOGLE_ROUTES.is_keyless


async def test_a_new_account_gets_every_keyless_connector() -> None:
    db = MagicMock()
    db.add = MagicMock()

    provisioned = await _run(db)

    assert set(provisioned) == ConnectorType.get_keyless_types()
    assert _added_types(db) == ConnectorType.get_keyless_types()
    for call in db.add.call_args_list:
        connector = call.args[0]
        # ACTIVE, or the tool answers "category not activated".
        assert connector.status is ConnectorStatus.ACTIVE
        assert connector.scopes == []
        assert connector.credentials_encrypted == "{}"
        assert connector.connector_metadata["provisioned_by"] == "signup_keyless"
        assert "activated_at" in connector.connector_metadata
        assert connector.connector_metadata["functionally_verified"] is False


async def test_the_platform_key_types_say_so_and_the_others_say_none() -> None:
    db = MagicMock()
    db.add = MagicMock()

    await _run(db)

    auth_types = {
        call.args[0].connector_type: call.args[0].connector_metadata["auth_type"]
        for call in db.add.call_args_list
    }
    assert auth_types[ConnectorType.GOOGLE_PLACES] == "global_api_key"
    assert auth_types[ConnectorType.GOOGLE_WEATHER] == "global_api_key"
    assert auth_types[ConnectorType.GOOGLE_ENVIRONMENT] == "global_api_key"
    assert auth_types[ConnectorType.WIKIPEDIA] == "none"
    assert auth_types[ConnectorType.BROWSER] == "none"


async def test_a_type_the_administrator_disabled_is_skipped() -> None:
    db = MagicMock()
    db.add = MagicMock()

    provisioned = await _run(
        db, disabled=frozenset({ConnectorType.WIKIPEDIA, ConnectorType.GOOGLE_PLACES})
    )

    assert ConnectorType.WIKIPEDIA not in provisioned
    assert ConnectorType.GOOGLE_PLACES not in provisioned
    assert _added_types(db) == {
        ConnectorType.BROWSER,
        ConnectorType.GOOGLE_WEATHER,
        ConnectorType.GOOGLE_ENVIRONMENT,
    }


async def test_platform_key_types_are_skipped_without_a_platform_key() -> None:
    db = MagicMock()
    db.add = MagicMock()

    provisioned = await _run(db, settings=_settings(google_api_key=""))

    # An active Places connector on an instance with no key can only fail.
    assert _added_types(db) == {ConnectorType.WIKIPEDIA, ConnectorType.BROWSER}
    assert set(provisioned) == {ConnectorType.WIKIPEDIA, ConnectorType.BROWSER}


async def test_the_browser_is_skipped_when_the_instance_switched_it_off() -> None:
    db = MagicMock()
    db.add = MagicMock()

    provisioned = await _run(db, settings=_settings(browser_enabled=False))

    assert ConnectorType.BROWSER not in provisioned
    assert ConnectorType.BROWSER not in _added_types(db)
    assert len(provisioned) == 4


async def test_a_failure_never_breaks_the_sign_up() -> None:
    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("boom"))

    provisioned = await _run(db)

    # Nothing provisioned, nothing raised: the account still gets created.
    assert provisioned == []


async def test_nothing_is_committed_here() -> None:
    """The caller owns the transaction (same contract as the demo search key)."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    await _run(db)

    db.commit.assert_not_awaited()
