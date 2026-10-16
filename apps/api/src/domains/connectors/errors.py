"""Typed refusals of the connectors domain.

A refusal another layer must READ, not only relay, carries its facts as
attributes: a status and a detail serve an HTTP client, while a confirmation
card needs to know WHICH connector to name (ADR-303 amendment 2026-10-14).
"""

from __future__ import annotations

from uuid import UUID

from src.core.exceptions import AuthorizationError
from src.core.field_names import FIELD_USER_ID
from src.domains.connectors.models import ConnectorType


class ConnectorRevokedError(AuthorizationError):
    """The credentials of a REVOKED connector were asked for.

    The person revoked it, an administrator disabled its type, or the account
    is being deleted. The status, the detail and the log context are exactly
    those ``raise_permission_denied(action="use", resource_type="connector")``
    produced, so every HTTP reader keeps its 403; ``connector_type`` lets a
    confirmation card say which connector to reconnect.

    Attributes:
        connector_type: The revoked connector's type.
    """

    def __init__(self, connector_type: ConnectorType, user_id: UUID) -> None:
        """Build the refusal.

        Args:
            connector_type: The revoked connector's type.
            user_id: The account that asked, for the audit log.
        """
        super().__init__(
            detail="Not authorized to use connector",
            **{FIELD_USER_ID: str(user_id), "action": "use", "resource_type": "connector"},
        )
        self.connector_type = connector_type
