"""Finite SMS management intents and private source snapshots."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.domains.ingestion.schemas import IngestionTokenSelection
from src.domains.sms.management_schemas import SmsEraseSelection
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.sender_commands import SmsSenderBlockSelection


class SmsTokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    label: StrictStr = Field(default="iPhone", min_length=1, max_length=128)
    source_id: UUID | None = None


class SmsTokenRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token_id: UUID


class SmsTokenCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ingestion_token_to_create: SmsTokenCreateRequest


class SmsTokenRevokePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ingestion_token_to_revoke: IngestionTokenSelection


class SmsPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sms_preferences: SmsPreferences


class SmsSenderBlockPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sms_sender_block: SmsSenderBlockSelection


class SmsErasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sms_messages_to_delete: SmsEraseSelection


class SmsActionField(str, Enum):
    TOKEN_CREATE = "ingestion_token_to_create"
    TOKEN_REVOKE = "ingestion_token_to_revoke"
    PREFERENCES = "sms_preferences"
    SENDER_BLOCK = "sms_sender_block"
    ERASE = "sms_messages_to_delete"
