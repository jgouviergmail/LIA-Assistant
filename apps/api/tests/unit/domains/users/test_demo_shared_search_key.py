"""Web search on a demonstrator: one shared key, provisioned per visitor.

Brave Search is a per-USER connector — its key lives on each account, and a
visitor of a throwaway instance has no key of their own and no reason to get
one. Without help, the search agent would be visible and permanently broken,
which is worse than an absent feature.

So the instance holds ONE key and lends it to every visitor account at
creation. The purge takes the connectors down with the accounts (FK cascade),
so nothing outlives the night.

Why Brave rather than Perplexity: Brave's API has a free tier, Perplexity's is
billed per call and would spend the daily budget on searches instead of on
the conversation (owner arbitration 2026-08-06).

What must hold:
- nothing happens outside demo mode, and nothing happens without a key;
- the connector is created ACTIVE, or the tool would report "not activated";
- provisioning a visitor never fails because of it — a broken search is worth
  less than a broken sign-up.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _settings(*, demo: bool, key: str) -> MagicMock:
    fake = MagicMock()
    fake.demo_mode_enabled = demo
    fake.demo_shared_search_api_key = key
    return fake


async def test_a_visitor_gets_the_shared_search_connector() -> None:
    from src.domains.users.demo_search_provisioning import provision_shared_search

    db = MagicMock()
    db.add = MagicMock()
    user_id = uuid4()
    with (
        patch(
            "src.domains.users.demo_search_provisioning.settings",
            _settings(demo=True, key="brave-key"),
        ),
        patch(
            "src.domains.users.demo_search_provisioning.encrypt_data",
            lambda value: f"enc:{value}",
        ),
    ):
        created = await provision_shared_search(db, user_id)

    from src.domains.connectors.models import ConnectorStatus

    assert created is True
    connector = db.add.call_args.args[0]
    assert connector.user_id == user_id
    # Created ACTIVE: an inactive connector makes the tool answer "not
    # activated", which is exactly the broken-looking state we avoid.
    assert connector.status is ConnectorStatus.ACTIVE
    # The key is encrypted like every other credential — never stored raw,
    # and inside the same JSON envelope the connector service uses.
    assert connector.credentials_encrypted.startswith("enc:")
    assert "brave-key" in connector.credentials_encrypted


async def test_nothing_happens_outside_demo_mode() -> None:
    from src.domains.users.demo_search_provisioning import provision_shared_search

    db = MagicMock()
    db.add = MagicMock()
    with patch(
        "src.domains.users.demo_search_provisioning.settings",
        _settings(demo=False, key="brave-key"),
    ):
        created = await provision_shared_search(db, uuid4())

    # A private instance must never have connectors appear on its accounts.
    assert created is False
    db.add.assert_not_called()


async def test_nothing_happens_without_a_shared_key() -> None:
    from src.domains.users.demo_search_provisioning import provision_shared_search

    db = MagicMock()
    db.add = MagicMock()
    with patch(
        "src.domains.users.demo_search_provisioning.settings",
        _settings(demo=True, key=""),
    ):
        created = await provision_shared_search(db, uuid4())

    assert created is False
    db.add.assert_not_called()


async def test_a_failure_never_breaks_the_sign_up() -> None:
    from src.domains.users.demo_search_provisioning import provision_shared_search

    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("boom"))
    with (
        patch(
            "src.domains.users.demo_search_provisioning.settings",
            _settings(demo=True, key="brave-key"),
        ),
        patch("src.domains.users.demo_search_provisioning.encrypt_data", lambda value: value),
    ):
        created = await provision_shared_search(db, uuid4())

    # A visitor who cannot search is disappointed; a visitor who cannot sign
    # up sees nothing at all.
    assert created is False


async def test_the_connector_targets_brave_search() -> None:
    from src.domains.connectors.models import ConnectorType
    from src.domains.users.demo_search_provisioning import provision_shared_search

    db = MagicMock()
    db.add = MagicMock()
    with (
        patch(
            "src.domains.users.demo_search_provisioning.settings",
            _settings(demo=True, key="brave-key"),
        ),
        patch("src.domains.users.demo_search_provisioning.encrypt_data", lambda value: value),
    ):
        await provision_shared_search(db, uuid4())

    assert db.add.call_args.args[0].connector_type is ConnectorType.BRAVE_SEARCH


async def test_the_account_provisioning_calls_it() -> None:
    """The wiring: a visitor account gets it without anyone remembering to."""
    from src.domains.users.account_provisioning_service import AccountProvisioningService

    db = MagicMock()
    db.commit = AsyncMock()
    service = AccountProvisioningService(db)
    skills = MagicMock()
    skills.return_value.ensure_user_skills = AsyncMock()
    with (
        patch(
            "src.domains.users.demo_search_provisioning.provision_shared_search",
            new_callable=AsyncMock,
        ) as provision,
        patch("src.domains.skills.preference_service.SkillPreferenceService", skills),
        patch("src.core.config.settings.usage_limits_enabled", False, create=True),
    ):
        await service.provision_new_user(uuid4(), commit_per_step=False)

    provision.assert_awaited_once()
