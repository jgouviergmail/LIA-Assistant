"""The workbench's descriptor: what each provider accepts, declared once (ADR-369, ADR-085).

The page offers a gesture only when the active provider accepts it (ADR-184:
what a validator can refuse, its producer must be able to read). A connector
type of a workbench tool with no entry would silently offer nothing — or
everything — so the boot refuses it, and a stray entry fails too.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.domains.workbench import features
from src.domains.workbench.features import (
    PROVIDER_FEATURES,
    TOOL_PROVIDERS,
    WorkbenchFeature,
    WorkbenchTool,
    assert_descriptor_completeness,
)

pytestmark = pytest.mark.unit


def test_each_tool_is_served_by_the_connectors_of_its_category() -> None:
    assert TOOL_PROVIDERS[WorkbenchTool.MAIL] == CONNECTOR_FUNCTIONAL_CATEGORIES["email"]
    assert TOOL_PROVIDERS[WorkbenchTool.CALENDAR] == CONNECTOR_FUNCTIONAL_CATEGORIES["calendar"]
    assert TOOL_PROVIDERS[WorkbenchTool.TASKS] == CONNECTOR_FUNCTIONAL_CATEGORIES["tasks"]
    assert TOOL_PROVIDERS[WorkbenchTool.CONTACTS] == CONNECTOR_FUNCTIONAL_CATEGORIES["contacts"]
    assert TOOL_PROVIDERS[WorkbenchTool.LIGHTS] == CONNECTOR_FUNCTIONAL_CATEGORIES["smart_home"]
    assert TOOL_PROVIDERS[WorkbenchTool.FILES] == CONNECTOR_FUNCTIONAL_CATEGORIES["files"]
    assert TOOL_PROVIDERS[WorkbenchTool.FILES] == frozenset(
        {ConnectorType.GOOGLE_DRIVE, ConnectorType.MICROSOFT_ONEDRIVE}
    )


def test_the_shipped_descriptor_is_complete() -> None:
    assert_descriptor_completeness()


def test_a_provider_with_no_entry_stops_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    trimmed = {k: v for k, v in PROVIDER_FEATURES.items() if k is not ConnectorType.APPLE_CONTACTS}
    monkeypatch.setattr(features, "PROVIDER_FEATURES", trimmed)
    with pytest.raises(RuntimeError, match="apple_contacts"):
        assert_descriptor_completeness()


def test_an_entry_for_a_provider_no_tool_has_stops_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    widened = {**PROVIDER_FEATURES, ConnectorType.BRAVE_SEARCH: frozenset()}
    monkeypatch.setattr(features, "PROVIDER_FEATURES", widened)
    with pytest.raises(RuntimeError, match="brave_search"):
        assert_descriptor_completeness()


def test_gmail_alone_manages_labels() -> None:
    """Outlook files mail in folders, and iCloud has no labels either (owner's brief §6.3)."""
    gesture = WorkbenchFeature.LABELS
    offering = {t for t, offered in PROVIDER_FEATURES.items() if gesture in offered}
    assert offering == {ConnectorType.GOOGLE_GMAIL}


def test_a_mailbox_s_settings_are_gmail_s_and_outlook_s() -> None:
    """iCloud has no automatic reply nor rule a client can reach (ADR-369, lot 12)."""
    for gesture in (WorkbenchFeature.VACATION, WorkbenchFeature.FILTERS):
        offering = {t for t, offered in PROVIDER_FEATURES.items() if gesture in offered}
        assert offering == {ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK}, gesture


def test_the_attachments_chip_follows_what_each_translator_carries() -> None:
    """IMAP has no criterion for ``has:attachment``: its translator sets it
    aside in silence, so the chip would filter nothing there."""
    from src.domains.connectors.clients.normalizers.email_normalizer import parse_imap_query
    from src.domains.connectors.clients.normalizers.graph_mail_query import graph_mail_query

    imap = parse_imap_query("has:attachment").criteria
    carried = {
        ConnectorType.GOOGLE_GMAIL: True,  # Gmail reads its own syntax
        ConnectorType.MICROSOFT_OUTLOOK: "hasAttachments"
        in str(graph_mail_query("has:attachment").params),
        ConnectorType.APPLE_EMAIL: str(imap) != str(parse_imap_query("").criteria),
    }
    for provider, carries in carried.items():
        offered = WorkbenchFeature.ATTACHMENT_FILTER in PROVIDER_FEATURES[provider]
        assert offered is carries, provider


def test_parity_gestures_reach_every_provider_of_their_tool() -> None:
    """D2: a gesture one provider's client has exists for the others."""
    parity = {
        WorkbenchTool.MAIL: {WorkbenchFeature.MARK_READ, WorkbenchFeature.DRAFTS},
        WorkbenchTool.CALENDAR: {WorkbenchFeature.ALL_DAY},
        WorkbenchTool.CONTACTS: {WorkbenchFeature.MULTI_VALUED},
    }
    for tool, gestures in parity.items():
        for provider in TOOL_PROVIDERS[tool]:
            assert gestures <= PROVIDER_FEATURES[provider], (tool, provider)
