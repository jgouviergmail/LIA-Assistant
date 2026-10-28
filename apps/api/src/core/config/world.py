"""Bounded, opt-in world settings; independent from existing voice sockets."""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    WORLD_ARCADE_BOT_SECONDS_DEFAULT,
    WORLD_ARCADE_ENABLED_DEFAULT,
    WORLD_ARCADE_INPUT_RATE_DEFAULT,
    WORLD_ARCADE_RECONNECT_SECONDS_DEFAULT,
    WORLD_ARCADE_REQUEST_SECONDS_DEFAULT,
    WORLD_ARCADE_RESULT_SECONDS_DEFAULT,
    WORLD_ARCADE_ROUND_SECONDS_DEFAULT,
    WORLD_ARCADE_TURN_SECONDS_DEFAULT,
    WORLD_ARCADE_WAIT_SECONDS_DEFAULT,
    WORLD_AUTH_TIMEOUT_DEFAULT,
    WORLD_AUTHORITY_TIMEOUT_DEFAULT,
    WORLD_CAPACITY_DEFAULT,
    WORLD_ENABLED_DEFAULT,
    WORLD_FRAME_BYTES_DEFAULT,
    WORLD_IDLE_SECONDS_DEFAULT,
    WORLD_INPUT_RATE_DEFAULT,
    WORLD_LEASE_SECONDS_DEFAULT,
    WORLD_OFFER_SECONDS_DEFAULT,
    WORLD_POLICY_TIMEOUT_DEFAULT,
    WORLD_QUEUE_SECONDS_DEFAULT,
    WORLD_QUEUE_SIZE_DEFAULT,
    WORLD_SEND_TIMEOUT_DEFAULT,
    WORLD_SOCKET_LIMIT_DEFAULT,
    WORLD_STATE_SECONDS_DEFAULT,
    WORLD_TICK_SECONDS_DEFAULT,
    WORLD_TICKET_SECONDS_DEFAULT,
)


class WorldSettings(BaseSettings):
    world_arcade_enabled: bool = Field(
        default=WORLD_ARCADE_ENABLED_DEFAULT,
        description="Subordinate arcade deployment ceiling; World and its native operator capability must also be enabled.",
    )
    world_arcade_input_rate: int = Field(
        default=WORLD_ARCADE_INPUT_RATE_DEFAULT,
        ge=1,
        le=10,
        description="Maximum game commands per second/account, in addition to the transport ceiling.",
    )
    world_arcade_wait_seconds: int = Field(
        default=WORLD_ARCADE_WAIT_SECONDS_DEFAULT,
        ge=20,
        le=180,
        description="Absolute empty-lobby lifetime, unaffected by hidden-tab or reconnect pauses.",
    )
    world_arcade_request_seconds: int = Field(
        default=WORLD_ARCADE_REQUEST_SECONDS_DEFAULT,
        ge=10,
        le=60,
        description="Deadline for the current host's explicit join consent.",
    )
    world_arcade_reconnect_seconds: int = Field(
        default=WORLD_ARCADE_RECONNECT_SECONDS_DEFAULT,
        ge=10,
        le=60,
        description="Non-renewable transport-loss/rejoin grace for an existing game member.",
    )
    world_arcade_turn_seconds: int = Field(
        default=WORLD_ARCADE_TURN_SECONDS_DEFAULT,
        ge=30,
        le=600,
        description="Seconds without a legal human move before abandonment; saved/restored on transport suspension.",
    )
    world_arcade_round_seconds: int = Field(
        default=WORLD_ARCADE_ROUND_SECONDS_DEFAULT,
        ge=300,
        le=1800,
        description="Absolute round lifetime, including suspended intervals.",
    )
    world_arcade_result_seconds: int = Field(
        default=WORLD_ARCADE_RESULT_SECONDS_DEFAULT,
        ge=10,
        le=60,
        description="Maximum terminal result/idempotency tombstone display lifetime.",
    )
    world_arcade_bot_seconds: float = Field(
        default=WORLD_ARCADE_BOT_SECONDS_DEFAULT,
        ge=0.1,
        le=3,
        description="Bounded off-thread computer preparation deadline; CPU work never runs inside CAS/SQL locks.",
    )
    world_enabled: bool = Field(
        default=WORLD_ENABLED_DEFAULT,
        description="Enable native authoritative World; operator capability policy still applies.",
    )
    world_namespace: str = Field(
        default="lia",
        pattern=r"^[a-z0-9_-]{1,40}$",
        description="Instance namespace separating authority, tickets and durable message fences.",
    )
    world_capacity: int = Field(
        default=WORLD_CAPACITY_DEFAULT,
        ge=1,
        le=10,
        description="Maximum simultaneously admitted native accounts in the shared World.",
    )
    world_queue_size: int = Field(
        default=WORLD_QUEUE_SIZE_DEFAULT,
        ge=1,
        le=128,
        description="Maximum accounts retained in the FIFO admission queue.",
    )
    world_lease_seconds: int = Field(
        default=WORLD_LEASE_SECONDS_DEFAULT,
        ge=10,
        le=120,
        description="Visible actor lease lifetime in seconds.",
    )
    world_queue_seconds: int = Field(
        default=WORLD_QUEUE_SECONDS_DEFAULT,
        ge=30,
        le=180,
        description="Visible queued-controller lease lifetime in seconds.",
    )
    world_offer_seconds: int = Field(
        default=WORLD_OFFER_SECONDS_DEFAULT,
        ge=10,
        le=60,
        description="Seconds allowed to accept an offered FIFO place.",
    )
    world_idle_seconds: int = Field(
        default=WORLD_IDLE_SECONDS_DEFAULT,
        ge=60,
        le=1800,
        description="Maximum seconds without accepted activity before releasing an admitted place.",
    )
    world_ticket_seconds: int = Field(
        default=WORLD_TICKET_SECONDS_DEFAULT,
        ge=10,
        le=60,
        description="Lifetime in seconds for a single-use cookie-bound World ticket.",
    )
    world_state_seconds: int = Field(
        default=WORLD_STATE_SECONDS_DEFAULT,
        ge=1800,
        le=7200,
        description="Redis authority TTL in seconds, also bounding socket claim duration.",
    )
    world_frame_bytes: int = Field(
        default=WORLD_FRAME_BYTES_DEFAULT,
        ge=1024,
        le=16384,
        description="Maximum UTF-8 byte size of one inbound World command frame.",
    )
    world_tick_seconds: float = Field(
        default=WORLD_TICK_SECONDS_DEFAULT,
        ge=0.05,
        le=0.25,
        description="Interval in seconds between recipient-filtered authoritative snapshots.",
    )
    world_socket_limit: int = Field(
        default=WORLD_SOCKET_LIMIT_DEFAULT,
        ge=6,
        le=64,
        description="Maximum distributed concurrent World sockets, including duplicate tabs.",
    )
    world_input_rate: int = Field(
        default=WORLD_INPUT_RATE_DEFAULT,
        ge=10,
        le=60,
        description="Maximum accepted inbound frames per socket per second.",
    )
    world_auth_timeout: int = Field(
        default=WORLD_AUTH_TIMEOUT_DEFAULT,
        ge=2,
        le=5,
        description="Maximum seconds to complete bounded first-frame authentication.",
    )
    world_send_timeout: int = Field(
        default=WORLD_SEND_TIMEOUT_DEFAULT,
        ge=1,
        le=5,
        description="Maximum seconds allowed for one outgoing snapshot write.",
    )
    world_authority_timeout: float = Field(
        default=WORLD_AUTHORITY_TIMEOUT_DEFAULT,
        ge=0.5,
        le=5,
        description="Maximum seconds for one authoritative Redis operation or CAS transition.",
    )
    world_policy_timeout: float = Field(
        default=WORLD_POLICY_TIMEOUT_DEFAULT,
        ge=1,
        le=5,
        description="Maximum seconds for a fresh native SQL/account-policy operation.",
    )
