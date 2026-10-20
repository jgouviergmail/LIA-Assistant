"""Content-free source proof carried beside a tool message through checkpoints."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.domains.agents.sms.projection import SmsToolPage


class SmsSnapshotProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    owner: UUID
    revision: int = Field(ge=0)
    ids: list[UUID] = Field(max_length=50)


def page_proof(page: SmsToolPage) -> str:
    return SmsSnapshotProof(
        owner=page.owner_id, revision=page.revision, ids=[item.id for item in page.sms_messages]
    ).model_dump_json()


def sms_message_metadata(raw: object) -> dict[str, str]:
    metadata = getattr(raw, "metadata", None)
    value = metadata.get("sms_snapshot") if isinstance(metadata, Mapping) else None
    if not isinstance(value, str):
        return {}
    try:
        proof = SmsSnapshotProof.model_validate_json(value)
    except ValidationError:
        return {}
    return {"sms_snapshot": proof.model_dump_json()}
