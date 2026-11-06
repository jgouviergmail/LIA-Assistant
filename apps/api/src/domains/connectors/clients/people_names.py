"""The only shapes a People API path is built from (ADR-369).

A resource name comes from a browser or a model: interpolated raw, ``people/c1:batch…`` or a
``../`` would aim the person's token at another People API operation.
"""

from __future__ import annotations

import re
from typing import Final

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.models import ConnectorType

PERSON_NAME: Final = re.compile(r"people/[A-Za-z0-9_-]+")
GROUP_NAME: Final = re.compile(r"contactGroups/[A-Za-z0-9_-]+")
OTHER_CONTACT_NAME: Final = re.compile(r"otherContacts/[A-Za-z0-9_-]+")


def named_path(resource_name: str, shape: re.Pattern[str] = PERSON_NAME) -> str:
    """The path of a resource name of the expected shape — any other names nothing.

    Raises:
        ConnectorAPIError: 404, the name names no such resource (never quoted back).
    """
    if not shape.fullmatch(resource_name):
        raise ConnectorAPIError(
            connector_type=ConnectorType.GOOGLE_CONTACTS.value,
            status_code=404,
            detail="google_contacts API error: no such contact",
        )
    return f"/{resource_name}"


__all__ = ["GROUP_NAME", "OTHER_CONTACT_NAME", "PERSON_NAME", "named_path"]
