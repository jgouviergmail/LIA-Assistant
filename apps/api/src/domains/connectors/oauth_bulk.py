"""Provider-specific scope rules for a single OAuth reconnection journey."""

from dataclasses import dataclass
from uuid import UUID

from src.core.constants import (
    GOOGLE_CALENDAR_SCOPES,
    GOOGLE_CONTACTS_SCOPES,
    GOOGLE_DRIVE_SCOPES,
    GOOGLE_GMAIL_SCOPES,
    GOOGLE_TASKS_SCOPES,
    MICROSOFT_CALENDAR_SCOPES,
    MICROSOFT_CONTACTS_SCOPES,
    MICROSOFT_OUTLOOK_SCOPES,
    MICROSOFT_TASKS_SCOPES,
)
from src.domains.connectors.models import (
    Connector,
    ConnectorStatus,
    ConnectorType,
    get_conflicting_connector_types,
)

_SCOPES: dict[ConnectorType, list[str]] = {
    ConnectorType.GOOGLE_GMAIL: GOOGLE_GMAIL_SCOPES,
    ConnectorType.GOOGLE_CALENDAR: GOOGLE_CALENDAR_SCOPES,
    ConnectorType.GOOGLE_DRIVE: GOOGLE_DRIVE_SCOPES,
    ConnectorType.GOOGLE_CONTACTS: GOOGLE_CONTACTS_SCOPES,
    ConnectorType.GOOGLE_TASKS: GOOGLE_TASKS_SCOPES,
    ConnectorType.MICROSOFT_OUTLOOK: MICROSOFT_OUTLOOK_SCOPES,
    ConnectorType.MICROSOFT_CALENDAR: MICROSOFT_CALENDAR_SCOPES,
    ConnectorType.MICROSOFT_CONTACTS: MICROSOFT_CONTACTS_SCOPES,
    ConnectorType.MICROSOFT_TASKS: MICROSOFT_TASKS_SCOPES,
}

_IDENTITY_SCOPES = {
    "google": ("openid", "email"),
    "microsoft": ("openid", "profile", "email"),
}

_PROVIDER_TYPES: dict[str, tuple[ConnectorType, ...]] = {
    "google": tuple(kind for kind in _SCOPES if kind.is_google),
    "microsoft": tuple(kind for kind in _SCOPES if kind.is_microsoft),
}

_IMPLIED: dict[str, frozenset[str]] = {
    "https://www.googleapis.com/auth/gmail.readonly": frozenset(
        {"https://www.googleapis.com/auth/gmail.modify"}
    ),
    "https://www.googleapis.com/auth/calendar.readonly": frozenset(
        {"https://www.googleapis.com/auth/calendar"}
    ),
    "https://www.googleapis.com/auth/calendar.events": frozenset(
        {"https://www.googleapis.com/auth/calendar"}
    ),
    "https://www.googleapis.com/auth/drive.readonly": frozenset(
        {"https://www.googleapis.com/auth/drive"}
    ),
    "https://www.googleapis.com/auth/drive.file": frozenset(
        {"https://www.googleapis.com/auth/drive"}
    ),
    "https://www.googleapis.com/auth/drive.metadata.readonly": frozenset(
        {"https://www.googleapis.com/auth/drive"}
    ),
    "https://www.googleapis.com/auth/contacts.readonly": frozenset(
        {"https://www.googleapis.com/auth/contacts"}
    ),
    "https://www.googleapis.com/auth/tasks.readonly": frozenset(
        {"https://www.googleapis.com/auth/tasks"}
    ),
    "mail.read": frozenset({"mail.readwrite"}),
    "calendars.read": frozenset({"calendars.readwrite"}),
    "contacts.read": frozenset({"contacts.readwrite"}),
    "tasks.read": frozenset({"tasks.readwrite"}),
}


@dataclass(frozen=True)
class ReconnectionPlan:
    """Validated set of previously configured services to recover together."""

    connector_types: tuple[ConnectorType, ...]
    scopes: tuple[str, ...]
    expected_grant_id: UUID | None


def _belongs_to_provider(provider: str, connector_type: ConnectorType) -> bool:
    return connector_type.is_google if provider == "google" else connector_type.is_microsoft


def _selected_connectors(
    provider: str, connectors: list[Connector], selected: list[ConnectorType]
) -> list[Connector]:
    by_type = {connector.connector_type: connector for connector in connectors}
    chosen: list[Connector] = []
    for connector_type in selected:
        connector = by_type.get(connector_type)
        if (
            not _belongs_to_provider(provider, connector_type)
            or connector_type not in _SCOPES
            or connector is None
            or connector.status != ConnectorStatus.ERROR
        ):
            raise ValueError("Only expired, configured provider connectors can be reconnected")
        chosen.append(connector)
    return chosen


def plan_reconnection(
    provider: str,
    connectors: list[Connector],
    selected: list[ConnectorType],
) -> ReconnectionPlan:
    """Reject ambiguous or invented selections before sending the browser away."""
    if provider not in _IDENTITY_SCOPES or not selected or len(selected) != len(set(selected)):
        raise ValueError("Invalid provider or duplicate/empty selection")

    chosen = _selected_connectors(provider, connectors, selected)

    grant_ids = {connector.oauth_grant_id for connector in chosen if connector.oauth_grant_id}
    if len(grant_ids) > 1:
        raise ValueError("Selected connectors belong to different accounts")

    active_types = {
        connector.connector_type
        for connector in connectors
        if connector.status == ConnectorStatus.ACTIVE
    }
    if any(active_types & set(get_conflicting_connector_types(ct)) for ct in selected):
        raise ValueError("An alternative provider is already active")

    scopes = tuple(
        dict.fromkeys((*_IDENTITY_SCOPES[provider], *(s for ct in selected for s in _SCOPES[ct])))
    )
    return ReconnectionPlan(tuple(selected), scopes, next(iter(grant_ids), None))


def connectable_provider_types(
    provider: str,
    connectors: list[Connector],
    *,
    disabled: frozenset[ConnectorType] | set[ConnectorType] = frozenset(),
) -> tuple[ConnectorType, ...]:
    """Services with no row and no active competing provider, in canonical order."""
    if provider not in _PROVIDER_TYPES:
        raise ValueError("Unsupported OAuth provider")
    existing = {row.connector_type for row in connectors}
    if ConnectorType.GMAIL in existing:
        existing.add(ConnectorType.GOOGLE_GMAIL)
    active = {row.connector_type for row in connectors if row.status == ConnectorStatus.ACTIVE}
    return tuple(
        kind
        for kind in _PROVIDER_TYPES[provider]
        if kind not in existing
        and kind not in disabled
        and not active.intersection(get_conflicting_connector_types(kind))
        and not (kind == ConnectorType.MICROSOFT_OUTLOOK and ConnectorType.GMAIL in active)
    )


def plan_connection(
    provider: str,
    connectors: list[Connector],
    selected: list[ConnectorType],
    *,
    expected_grant_id: UUID | None = None,
) -> ReconnectionPlan:
    """Validate a new-service selection; never overwrite an existing row."""
    if provider not in _PROVIDER_TYPES or not selected or len(selected) != len(set(selected)):
        raise ValueError("Invalid provider or duplicate/empty selection")
    available = set(connectable_provider_types(provider, connectors))
    if any(kind not in available for kind in selected):
        raise ValueError("Only unconfigured, unblocked provider services can be connected")
    scopes = tuple(
        dict.fromkeys(
            (*_IDENTITY_SCOPES[provider], *(s for kind in selected for s in _SCOPES[kind]))
        )
    )
    return ReconnectionPlan(tuple(selected), scopes, expected_grant_id)


def scopes_cover_connector(connector_type: ConnectorType, granted: set[str]) -> bool:
    """Check entitlements, allowing documented broader scopes to satisfy narrower ones."""
    canonical_type = (
        ConnectorType.GOOGLE_GMAIL if connector_type == ConnectorType.GMAIL else connector_type
    )
    required = _SCOPES.get(canonical_type)
    if required is None:
        return False
    normalized = {scope.lower().removeprefix("https://graph.microsoft.com/") for scope in granted}
    access_scopes = (scope for scope in required if scope != "offline_access")
    return all(
        scope.lower() in normalized or bool(_IMPLIED.get(scope.lower(), frozenset()) & normalized)
        for scope in access_scopes
    )


def scopes_for_connector(connector_type: ConnectorType) -> tuple[str, ...]:
    """Canonical scope declaration for a logical connector."""
    canonical_type = (
        ConnectorType.GOOGLE_GMAIL if connector_type == ConnectorType.GMAIL else connector_type
    )
    return tuple(_SCOPES[canonical_type])
