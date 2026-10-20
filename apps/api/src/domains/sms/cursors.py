"""Encrypted cursors bind a closed window to owner, filters and data revision."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from src.core.exceptions import ResourceConflictError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.sms.constants import SMS_SEARCH_INDEX_VERSION
from src.domains.sms.read_schemas import SmsQuery


class SmsCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = 1
    owner: UUID
    filters: str
    revision: int
    as_of: AwareDatetime
    stamp: AwareDatetime | None = None
    id: UUID | None = None

    def encode(self) -> str:
        return encrypt_data(self.model_dump_json())


def cursor_for(
    owner: UUID, query: SmsQuery, revision: int, *, surface: str = "messages"
) -> SmsCursor:
    fingerprint = hashlib.sha256(
        (
            surface
            + str(SMS_SEARCH_INDEX_VERSION if query.query is not None else 0)
            + query.model_dump_json(exclude={"cursor"})
        ).encode()
    ).hexdigest()
    if query.cursor is None:
        return SmsCursor(
            owner=owner, filters=fingerprint, revision=revision, as_of=datetime.now(UTC)
        )
    try:
        cursor = SmsCursor.model_validate_json(decrypt_data(query.cursor))
    except ValueError, ValidationError:
        raise ResourceConflictError("sms_cursor", detail={"error_code": "STALE_CURSOR"}) from None
    if (
        cursor.version != 1
        or cursor.owner != owner
        or cursor.filters != fingerprint
        or cursor.revision != revision
        or cursor.as_of > datetime.now(UTC)
        or cursor.stamp is None
        or cursor.id is None
    ):
        raise ResourceConflictError("sms_cursor", detail={"error_code": "STALE_CURSOR"})
    return cursor
