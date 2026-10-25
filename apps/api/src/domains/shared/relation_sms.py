"""Typed SMS read port; composition owns the adapter, Relations owns its view."""

from collections.abc import Callable
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.shared.aggregates import NameActivity
from src.infrastructure.database.keyset import Keyset
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class PersonalSms(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: UUID
    sender: str
    display_name: str
    body: str
    received_at: datetime
    date_kind: str
    origin: str = "iphone"
    identity_source: Literal["contact", "relation", "raw"] = "raw"
    identity_state: str = "unresolved"
    relation_key: str | None = None


class RelationSmsProof(BaseModel):
    model_config = ConfigDict(frozen=True)
    owner_id: UUID
    revision: int
    stamp: str
    as_of: datetime
    assistant: bool


class RelationSmsPage(BaseModel):
    model_config = ConfigDict(frozen=True)
    available: bool = False
    activities: list[NameActivity] = Field(default_factory=list)
    messages: list[PersonalSms] = Field(default_factory=list)
    total: int = 0
    proof: RelationSmsProof | None = None


class RelationSmsReader(Protocol):
    async def read(
        self,
        owner: UUID,
        *,
        person: str | None = None,
        limit: int = 10,
        assistant: bool = False,
        before: Keyset | None = None,
    ) -> RelationSmsPage: ...
    async def check(
        self, db: AsyncSession, owner: UUID, proof: RelationSmsProof | RelationSmsPage
    ) -> None: ...


_factory: Callable[[], RelationSmsReader] | None = None

#: Refusals that CLOSE the archive by decision — the person's consent to the
#: assistant reading it, the operator's switch — rather than failing it.
_DECIDED_REFUSALS: Final = frozenset({"SMS_CONSENT_REQUIRED", "CAPABILITY_DISABLED"})


def register_relation_sms_reader(factory: Callable[[], RelationSmsReader]) -> None:
    global _factory
    _factory = factory


async def read_relation_sms(
    owner: UUID,
    *,
    person: str | None = None,
    limit: int = 10,
    assistant: bool = False,
    before: Keyset | None = None,
) -> RelationSmsPage:
    if _factory is None:
        return RelationSmsPage()
    try:
        return await _factory().read(
            owner, person=person, limit=limit, assistant=assistant, before=before
        )
    except AuthorizationError as error:
        detail = error.detail
        code = str(detail.get("error_code")) if isinstance(detail, dict) else None
        if code in _DECIDED_REFUSALS:
            # Closed by decision: an empty page, nothing failing to warn about.
            logger.debug("relation_sms_closed", error_code=code)
        else:
            logger.warning(
                "relation_sms_unavailable", error_type=type(error).__name__, error_code=code
            )
        return RelationSmsPage()
    except Exception as error:
        logger.warning("relation_sms_unavailable", error_type=type(error).__name__)
        return RelationSmsPage()


async def check_relation_sms(db: AsyncSession, owner: UUID, proof: RelationSmsProof | None) -> None:
    if proof is None:
        return
    if _factory is None:
        raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
    await _factory().check(db, owner, proof)
