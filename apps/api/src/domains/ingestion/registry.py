"""Closed ingestion resource policies, shared by legacy and new entry points."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from src.core.constants import HEALTH_METRICS_TOKEN_PREFIX


class IngestionResource(StrEnum):
    HEALTH = "health"
    SMS = "sms"


@dataclass(frozen=True, slots=True)
class IngestionPolicy:
    write_scope: str
    token_prefix: str
    legacy_fields: frozenset[str] | None = None
    managed_tokens: bool = False
    keyed_state_tables: tuple[str, ...] = ()


_POLICIES = MappingProxyType(
    {
        IngestionResource.HEALTH: IngestionPolicy(
            "health:write", HEALTH_METRICS_TOKEN_PREFIX, frozenset({"date_start", "date_end"})
        ),
        IngestionResource.SMS: IngestionPolicy(
            "sms:write", "pi_", managed_tokens=True, keyed_state_tables=("sms_sender_blocks",)
        ),
    }
)


def policy_for(resource: IngestionResource) -> IngestionPolicy:
    return _POLICIES[resource]


def validate_registry() -> None:
    """Fail at boot if a resource lacks an explicit, distinct authority policy."""
    if set(_POLICIES) != set(IngestionResource):
        raise ValueError("incomplete_ingestion_registry")
    scopes = {policy.write_scope for policy in _POLICIES.values()}
    prefixes = {policy.token_prefix for policy in _POLICIES.values()}
    if len(scopes) != len(_POLICIES) or len(prefixes) != len(_POLICIES):
        raise ValueError("ambiguous_ingestion_authority")
