"""Behavioural contract for grouped OAuth reconnection planning."""

from uuid import uuid4

import pytest

from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.oauth_bulk import (
    connectable_provider_types,
    plan_connection,
    plan_reconnection,
    scopes_cover_connector,
    scopes_for_connector,
)


def _connector(
    kind: ConnectorType, *, status: ConnectorStatus = ConnectorStatus.ERROR
) -> Connector:
    return Connector(
        id=uuid4(),
        user_id=uuid4(),
        connector_type=kind,
        status=status,
        scopes=[],
        credentials_encrypted="legacy",
    )


def test_google_reconnection_requests_one_union_for_only_selected_expired_services() -> None:
    gmail = _connector(ConnectorType.GOOGLE_GMAIL)
    calendar = _connector(ConnectorType.GOOGLE_CALENDAR)
    drive = _connector(ConnectorType.GOOGLE_DRIVE, status=ConnectorStatus.ACTIVE)

    plan = plan_reconnection(
        "google",
        [gmail, calendar, drive],
        [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CALENDAR],
    )

    assert plan.connector_types == (ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CALENDAR)
    assert plan.scopes == (
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    )


def test_microsoft_reconnection_deduplicates_common_scopes() -> None:
    outlook = _connector(ConnectorType.MICROSOFT_OUTLOOK)
    tasks = _connector(ConnectorType.MICROSOFT_TASKS)

    plan = plan_reconnection(
        "microsoft",
        [outlook, tasks],
        [ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.MICROSOFT_TASKS],
    )

    assert plan.scopes == (
        "openid",
        "profile",
        "email",
        "User.Read",
        "offline_access",
        "Mail.Read",
        "Mail.ReadWrite",
        "Mail.Send",
        "Tasks.Read",
        "Tasks.ReadWrite",
    )


@pytest.mark.parametrize(
    "selected",
    [
        [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_GMAIL],
        [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK],
        [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_DRIVE],
        [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CONTACTS],
    ],
)
def test_reconnection_refuses_duplicate_foreign_active_or_never_configured_services(
    selected: list[ConnectorType],
) -> None:
    with pytest.raises(ValueError):
        plan_reconnection("google", [_connector(ConnectorType.GOOGLE_GMAIL)], selected)


def test_reconnection_refuses_known_different_accounts() -> None:
    gmail = _connector(ConnectorType.GOOGLE_GMAIL)
    calendar = _connector(ConnectorType.GOOGLE_CALENDAR)
    gmail.oauth_grant_id = uuid4()
    calendar.oauth_grant_id = uuid4()

    with pytest.raises(ValueError, match="account"):
        plan_reconnection(
            "google", [gmail, calendar], [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CALENDAR]
        )


def test_reconnection_does_not_replace_an_active_alternative_provider() -> None:
    gmail = _connector(ConnectorType.GOOGLE_GMAIL)
    outlook = _connector(ConnectorType.MICROSOFT_OUTLOOK, status=ConnectorStatus.ACTIVE)

    with pytest.raises(ValueError, match="active"):
        plan_reconnection("google", [gmail, outlook], [ConnectorType.GOOGLE_GMAIL])


def test_broader_google_scope_covers_narrower_scopes_but_not_unrelated_service() -> None:
    assert scopes_cover_connector(
        ConnectorType.GOOGLE_CALENDAR, {"https://www.googleapis.com/auth/calendar"}
    )
    assert not scopes_cover_connector(
        ConnectorType.GOOGLE_GMAIL, {"https://www.googleapis.com/auth/calendar"}
    )


def test_microsoft_mail_write_does_not_implicitly_grant_send() -> None:
    assert not scopes_cover_connector(
        ConnectorType.MICROSOFT_OUTLOOK, {"Mail.ReadWrite", "User.Read"}
    )


def test_microsoft_access_token_scope_need_not_repeat_offline_access() -> None:
    assert scopes_cover_connector(
        ConnectorType.MICROSOFT_TASKS,
        {"https://graph.microsoft.com/User.Read", "Tasks.ReadWrite"},
    )


def test_connect_all_selects_only_absent_unblocked_enabled_google_services() -> None:
    existing = [
        _connector(ConnectorType.GOOGLE_CALENDAR, status=ConnectorStatus.ACTIVE),
        _connector(ConnectorType.MICROSOFT_OUTLOOK, status=ConnectorStatus.ACTIVE),
        _connector(ConnectorType.GOOGLE_DRIVE),
    ]

    selected = connectable_provider_types("google", existing, disabled={ConnectorType.GOOGLE_TASKS})

    assert selected == (ConnectorType.GOOGLE_CONTACTS,)
    plan = plan_connection("google", existing, list(selected))
    assert plan.connector_types == selected
    assert "https://www.googleapis.com/auth/contacts" in plan.scopes


def test_connect_all_legacy_gmail_row_prevents_duplicate_mailbox() -> None:
    selected = connectable_provider_types(
        "google", [_connector(ConnectorType.GMAIL, status=ConnectorStatus.ACTIVE)]
    )
    assert ConnectorType.GOOGLE_GMAIL not in selected


def test_legacy_gmail_uses_google_mail_scopes_when_preserving_an_existing_grant() -> None:
    assert scopes_for_connector(ConnectorType.GMAIL) == scopes_for_connector(
        ConnectorType.GOOGLE_GMAIL
    )
    assert scopes_cover_connector(
        ConnectorType.GMAIL, set(scopes_for_connector(ConnectorType.GOOGLE_GMAIL))
    )


def test_connect_all_active_legacy_gmail_blocks_microsoft_outlook() -> None:
    selected = connectable_provider_types(
        "microsoft", [_connector(ConnectorType.GMAIL, status=ConnectorStatus.ACTIVE)]
    )
    assert ConnectorType.MICROSOFT_OUTLOOK not in selected


@pytest.mark.parametrize("status", [ConnectorStatus.ACTIVE, ConnectorStatus.ERROR])
def test_connect_all_refuses_to_overwrite_an_existing_service(status: ConnectorStatus) -> None:
    with pytest.raises(ValueError):
        plan_connection(
            "google",
            [_connector(ConnectorType.GOOGLE_CALENDAR, status=status)],
            [ConnectorType.GOOGLE_CALENDAR],
        )


def test_connect_all_microsoft_uses_one_scope_union() -> None:
    selected = connectable_provider_types("microsoft", [])
    plan = plan_connection("microsoft", [], list(selected))
    assert len(selected) == 4
    assert plan.scopes.count("offline_access") == 1
    assert "Mail.Send" in plan.scopes
    assert "Tasks.ReadWrite" in plan.scopes
