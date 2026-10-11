"""Injected channel-to-assistant boundary; the channel domain owns no agent dependency."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class ChannelStreamChunk(Protocol):
    @property
    def type(self) -> str: ...

    @property
    def content(self) -> object: ...

    @property
    def metadata(self) -> Mapping[str, object] | None: ...


@dataclass(frozen=True)
class ChannelAgentRequest:
    user_message: str
    user_id: UUID
    session_id: str
    user_timezone: str
    user_language: str
    user_memory_enabled: bool
    original_run_id: str | None
    user_display_name: str | None
    user_journals_enabled: bool
    user_psyche_enabled: bool
    hitl_decision: Mapping[str, str] | None


@dataclass(frozen=True)
class ChannelAssistantGateway:
    stream: Callable[[ChannelAgentRequest], AsyncGenerator[ChannelStreamChunk]]
    pending: Callable[[str], Awaitable[dict[str, object] | None]]
    confirmation_text: Callable[[str], str]


_gateway: ChannelAssistantGateway | None = None


def configure_channel_gateway(
    gateway: ChannelAssistantGateway | None,
) -> ChannelAssistantGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_channel_gateway() -> ChannelAssistantGateway:
    if _gateway is None:
        raise RuntimeError("Channel assistant gateway is not initialized")
    return _gateway
