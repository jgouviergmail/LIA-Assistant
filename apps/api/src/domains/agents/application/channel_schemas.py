"""Public channel selectors and the private identity frozen for confirmation."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool

from src.domains.channels.preference_commands import ChannelBindingSnapshot


class ChannelField(str, Enum):
    BINDING = "channel_binding"


class ChannelBindingsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChannelBindingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding_id: UUID
    enabled: StrictBool


class ChannelBindingUnlinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding_id: UUID


class ChannelBindingUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel_binding: ChannelBindingSnapshot


class ChannelBindingUnlinkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel_binding: ChannelBindingSnapshot
