"""Peers configuration module (peer-connections program, Lot 1).

User-to-user connections feature flag and policy thresholds. Every value is
env-overridable (``PEERS_*``) so quotas and cadences can be tuned in
production without a code change.

Defaults are imported from ``src.core.constants`` (NOT from the domain — the
config layer never imports domains, see ``briefing.py``'s rationale).

Phase: peer-connections program, Lot 1
Created: 2026-07-29
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    PEERS_ACCESS_LOG_RETENTION_DAYS_DEFAULT,
    PEERS_DELIVERY_MAX_ATTEMPTS_DEFAULT,
    PEERS_DELIVERY_SWEEP_SECONDS_DEFAULT,
    PEERS_DISCOVERY_RATE_LIMIT_CALLS_DEFAULT,
    PEERS_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    PEERS_MESSAGE_MAX_CHARS_DEFAULT,
    PEERS_MESSAGE_MAX_PER_DAY_DEFAULT,
    PEERS_MESSAGE_MAX_PER_DAY_PER_PAIR_DEFAULT,
    PEERS_MESSAGE_RETENTION_DAYS_DEFAULT,
    PEERS_REQUEST_COOLDOWN_DAYS_DEFAULT,
    PEERS_REQUEST_EXPIRY_DAYS_DEFAULT,
)


class PeersSettings(BaseSettings):
    """Env-overridable settings for user-to-user peer connections."""

    peers_enabled: bool = Field(
        default=False,
        description="Enable the peer-connections feature (discovery, messages, sharing).",
    )
    peers_discovery_rate_limit_calls: int = Field(
        default=PEERS_DISCOVERY_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=100,
        description="Discovery searches allowed per user per window (anti-enumeration).",
    )
    peers_discovery_rate_limit_window_seconds: int = Field(
        default=PEERS_DISCOVERY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Window of the discovery-search rate limit, in seconds.",
    )
    peers_message_max_per_day: int = Field(
        default=PEERS_MESSAGE_MAX_PER_DAY_DEFAULT,
        ge=1,
        le=500,
        description="Relayed messages a sender may enqueue per UTC day (all peers).",
    )
    peers_message_max_per_day_per_pair: int = Field(
        default=PEERS_MESSAGE_MAX_PER_DAY_PER_PAIR_DEFAULT,
        ge=1,
        le=100,
        description="Relayed messages a sender may enqueue per UTC day toward one peer.",
    )
    peers_message_max_chars: int = Field(
        default=PEERS_MESSAGE_MAX_CHARS_DEFAULT,
        ge=100,
        le=10000,
        description="Max characters of a relayed-message directive.",
    )
    peers_message_retention_days: int = Field(
        default=PEERS_MESSAGE_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description=(
            "Retention TTL (days) for relayed-message texts. The ledger row "
            "survives forever (audit, counts, timeline); the sender's directive "
            "and the delivered text are purged past it — the same contract as "
            "telephony_call_retention_days."
        ),
    )
    peers_request_cooldown_days: int = Field(
        default=PEERS_REQUEST_COOLDOWN_DAYS_DEFAULT,
        ge=0,
        le=365,
        description="Days before a declined pair may receive a new request.",
    )
    peers_request_expiry_days: int = Field(
        default=PEERS_REQUEST_EXPIRY_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Pending requests older than this are expired silently.",
    )
    peers_delivery_sweep_seconds: int = Field(
        default=PEERS_DELIVERY_SWEEP_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Interval of the pending-message delivery sweep (Lot 4).",
    )
    peers_delivery_max_attempts: int = Field(
        default=PEERS_DELIVERY_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Real delivery failures before a message is marked failed (Lot 4).",
    )
    peers_access_log_retention_days: int = Field(
        default=PEERS_ACCESS_LOG_RETENTION_DAYS_DEFAULT,
        ge=7,
        le=730,
        description="Sweep prunes peer_access_log rows older than this (Lot 5).",
    )
