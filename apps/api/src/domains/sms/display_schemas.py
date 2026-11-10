"""Native-only display queries; assistant lexical requests keep their original contract."""

import hashlib
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from src.core.constants import SMS_DISPLAY_INDEX_VERSION
from src.core.exceptions import ResourceConflictError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.sms.read_schemas import SmsQuery


class SmsDisplayQuery(SmsQuery):
    """Literal displayed-body or resolved-name search, before pagination."""

    sort: Literal["recent", "oldest", "name"] = Field(
        "recent", description="Display order; ties end on message identity."
    )


class SmsDisplayCursor(BaseModel):
    """Encrypted continuation bound to owner, data, query and the resolved identity map."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[2] = Field(2, description="Native display cursor format.")
    owner: UUID = Field(description="Account owning the archive.")
    filters: str = Field(description="Digest of the complete native query.")
    revision: int = Field(ge=0, description="Account extraction/erasure revision.")
    as_of: AwareDatetime = Field(description="Server-stamped upper creation instant.")
    offset: int = Field(0, ge=0, description="Number of matching rows already shown.")
    identities: str | None = Field(
        None, description="Keyed digest of the identity map when it affects membership or order."
    )

    def encode(self) -> str:
        """Keep query and identity metadata opaque on the wire."""
        return encrypt_data(self.model_dump_json())


def display_cursor_for(owner: UUID, query: SmsDisplayQuery, revision: int) -> SmsDisplayCursor:
    """Validate every continuation before any archive or identity read."""
    filters = hashlib.sha256(
        (str(SMS_DISPLAY_INDEX_VERSION) + query.model_dump_json(exclude={"cursor"})).encode()
    ).hexdigest()
    now = datetime.now(UTC)
    if query.cursor is None:
        return SmsDisplayCursor(owner=owner, filters=filters, revision=revision, as_of=now)
    try:
        cursor = SmsDisplayCursor.model_validate_json(decrypt_data(query.cursor))
    except ValueError, ValidationError:
        raise ResourceConflictError("sms_cursor", detail={"error_code": "STALE_CURSOR"}) from None
    if (
        cursor.owner != owner
        or cursor.filters != filters
        or cursor.revision != revision
        or cursor.as_of > now
    ):
        raise ResourceConflictError("sms_cursor", detail={"error_code": "STALE_CURSOR"})
    return cursor
