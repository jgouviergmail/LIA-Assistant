"""A Google scope is checked only where Google serves (RC1.1, 2026-10-13).

The catalogue's multi-provider tools declare the GOOGLE scopes of their Google
implementation. The plan validator and the skill bypass compared them with the
scopes the account granted, whatever its provider: every e-mail, contacts and
calendar step of an Outlook or iCloud account was judged UNAUTHORIZED (16 times
in 7 days on one production account, 2026-10-07), and a skill dropped those
steps. Which provider a step runs on is read from the tool's CLASS (its
``functional_category``) and the account's active connectors — never from a
table written by hand.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.domains.agents.emails.catalogue_manifests import send_email_catalogue_manifest
from src.domains.agents.emails.get_emails_manifest import get_emails_catalogue_manifest
from src.domains.agents.emails.label_manifests import list_labels_catalogue_manifest
from src.domains.agents.emails.settings_catalogue_manifests import (
    set_vacation_responder_catalogue_manifest,
)
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.connector_requirements import (
    PROVIDER_BOUND_WITHOUT_A_CLASS,
    connector_categories,
    unconnected_tool_names,
    ungranted_scopes,
    without_unconnected_tools,
)
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit

GMAIL = ConnectorType.GOOGLE_GMAIL.value
OUTLOOK = ConnectorType.MICROSOFT_OUTLOOK.value
APPLE = ConnectorType.APPLE_EMAIL.value
DRIVE = ConnectorType.GOOGLE_DRIVE.value


@pytest.fixture(scope="module", autouse=True)
def _tool_classes_loaded() -> None:
    """The walk reads the classes the tool modules define."""
    from src.domains.agents.tools import tool_registry

    tool_registry.ensure_tools_loaded()


def _required(manifest: ToolManifest) -> frozenset[str]:
    return frozenset(manifest.permissions.required_scopes)


class TestACategoryTool:
    @pytest.mark.parametrize("provider", [OUTLOOK, APPLE])
    def test_on_another_provider_owes_no_google_scope(self, provider: str) -> None:
        assert ungranted_scopes(get_emails_catalogue_manifest, [], {provider}) == frozenset()

    def test_on_google_the_scope_it_lacks_is_named(self) -> None:
        granted = [scope for scope in GOOGLE_GMAIL_SCOPES if not scope.endswith("gmail.send")]

        missing = ungranted_scopes(send_email_catalogue_manifest, granted, {GMAIL})

        assert missing
        assert missing == _required(send_email_catalogue_manifest) - set(granted)

    @pytest.mark.parametrize("other", [ConnectorType.APPLE_EMAIL, ConnectorType.MICROSOFT_OUTLOOK])
    @pytest.mark.parametrize("google", [ConnectorType.GOOGLE_GMAIL, ConnectorType.GMAIL])
    async def test_a_dual_active_conflict_cannot_waive_the_selected_google_providers_scopes(
        self, other: ConnectorType, google: ConnectorType
    ) -> None:
        from src.domains.connectors.models import ConnectorStatus
        from src.domains.connectors.provider_resolver import resolve_active_connector

        now = datetime.now(UTC)
        connectors = [
            SimpleNamespace(connector_type=kind, status=ConnectorStatus.ACTIVE, updated_at=updated)
            for kind, updated in (
                (other, now - timedelta(seconds=1)),
                (google, now),
            )
        ]
        service = SimpleNamespace(
            get_user_connectors=AsyncMock(return_value=SimpleNamespace(connectors=connectors))
        )
        assert await resolve_active_connector(uuid4(), "email", service) == google
        assert ungranted_scopes(
            get_emails_catalogue_manifest, [], {google.value, other.value}
        ) == _required(get_emails_catalogue_manifest)

    def test_two_non_google_providers_still_owe_no_google_scope(self) -> None:
        assert ungranted_scopes(get_emails_catalogue_manifest, [], {APPLE, OUTLOOK}) == frozenset()

    def test_with_no_provider_at_all_the_verdict_stands(self) -> None:
        """« Connect a provider » is the honest answer (the 2026-07-30 case)."""
        assert ungranted_scopes(get_emails_catalogue_manifest, [], set()) == _required(
            get_emails_catalogue_manifest
        )

    def test_without_knowing_the_account_s_connectors_nothing_is_claimed(self) -> None:
        """Outside a request the execution, which resolves the provider, decides."""
        assert ungranted_scopes(get_emails_catalogue_manifest, [], None) == frozenset()


class TestAToolOfGoogleAlone:
    def test_a_gmail_tool_keeps_its_check_on_an_outlook_account(self) -> None:
        """Labels are Gmail's: an Outlook account has not connected what they need."""
        assert ungranted_scopes(list_labels_catalogue_manifest, [], {OUTLOOK})

    def test_a_tool_no_connector_class_names_keeps_its_check(self) -> None:
        assert ungranted_scopes(set_vacation_responder_catalogue_manifest, [], {OUTLOOK})


@pytest.fixture
def _catalogue() -> Iterator[list[ToolManifest]]:
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    registry = AgentRegistry()
    initialize_catalogue(registry)
    yield registry.list_tool_manifests()


class TestCompleteness:
    """A class whose ``tool_name`` misses its manifest would put the check back
    on silently — the defect RC1.1 was: every scoped manifest is named by a
    connector class, or declared Google's alone with its reason."""

    def test_every_scoped_manifest_names_its_connector_class(
        self, _catalogue: list[ToolManifest]
    ) -> None:
        scoped = {m.name for m in _catalogue if m.permissions.required_scopes}

        uncovered = scoped - connector_categories().keys() - PROVIDER_BOUND_WITHOUT_A_CLASS.keys()

        assert not uncovered, f"scoped manifests no connector class names: {sorted(uncovered)}"

    def test_no_declared_exception_is_stale(self, _catalogue: list[ToolManifest]) -> None:
        scoped = {m.name for m in _catalogue if m.permissions.required_scopes}

        stale = PROVIDER_BOUND_WITHOUT_A_CLASS.keys() - (scoped - connector_categories().keys())

        assert not stale, f"declared exceptions that no longer apply: {sorted(stale)}"

    def test_the_categories_are_the_providers_own(self) -> None:
        from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES

        assert (
            set(connector_categories().values()) - {None} <= CONNECTOR_FUNCTIONAL_CATEGORIES.keys()
        )


_GMAIL_BOUND = {
    "get_gmail_settings_tool",
    "list_labels_tool",
    "create_email_filter_tool",
    "set_vacation_responder_tool",
}
_DRIVE_BOUND = {"get_files_tool", "read_document_tool"}
_CATEGORY = {"get_emails_tool", "send_email_tool", "get_events_tool", "get_contacts_tool"}
_INSTANCE = {"get_places_tool", "get_air_quality_tool"}


class TestATurnIsOfferedWhatItsConnectorsServe:
    """RC2.1 (production 2026-10-07, 19:32): an Outlook account was offered
    Gmail's settings, the planner chose them for a mail question, and the turn
    failed while the Outlook mailbox had just answered."""

    def test_an_outlook_account_is_offered_no_gmail_nor_drive_tool(self) -> None:
        assert _GMAIL_BOUND | _DRIVE_BOUND <= unconnected_tool_names(frozenset({OUTLOOK}))

    def test_an_icloud_account_neither(self) -> None:
        assert _GMAIL_BOUND <= unconnected_tool_names(frozenset({APPLE}))

    def test_a_category_tool_stays_offered_its_answer_is_the_honest_one(self) -> None:
        """« Connect a provider » is what it says — the right answer of 18:13."""
        assert not _CATEGORY & unconnected_tool_names(frozenset())

    def test_an_instance_tool_is_never_hidden(self) -> None:
        """Keyless and platform-key connectors belong to the instance (ADR-307)."""
        assert not _INSTANCE & unconnected_tool_names(frozenset())

    def test_a_gmail_account_is_offered_gmail_s_own_tools_not_drive_s(self) -> None:
        hidden = unconnected_tool_names(frozenset({GMAIL}))

        assert not _GMAIL_BOUND & hidden
        assert _DRIVE_BOUND <= hidden

    def test_drive_comes_with_its_own_connector(self) -> None:
        assert not _DRIVE_BOUND & unconnected_tool_names(frozenset({GMAIL, DRIVE}))

    def test_a_legacy_gmail_row_serves_no_gmail_tool(self) -> None:
        """Their credentials are read by EXACT type: such a tool could not run."""
        assert _GMAIL_BOUND <= unconnected_tool_names(frozenset({ConnectorType.GMAIL.value}))

    def test_without_knowing_the_account_s_connectors_nothing_is_hidden(self) -> None:
        """Outside a request the execution, which reads the credentials, decides."""
        assert unconnected_tool_names(None) == frozenset()

    def test_the_catalogue_loses_exactly_the_tools_nothing_serves(
        self, _catalogue: list[ToolManifest]
    ) -> None:
        offered = without_unconnected_tools(_catalogue, frozenset({OUTLOOK}))

        names = {manifest.name for manifest in offered}
        assert names == {manifest.name for manifest in _catalogue} - unconnected_tool_names(
            frozenset({OUTLOOK})
        )
        assert _CATEGORY <= names
        assert not _GMAIL_BOUND & names

    def test_an_unknown_account_keeps_the_whole_catalogue(
        self, _catalogue: list[ToolManifest]
    ) -> None:
        assert without_unconnected_tools(_catalogue, None) == _catalogue
