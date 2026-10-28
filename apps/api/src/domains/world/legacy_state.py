"""Erasure-only reader for older scenes; never serializes newly introduced defaults."""

from typing import Literal

from pydantic import Field, field_validator

from src.domains.world.schemas import WorldStateShape
from src.domains.world.store import AuthorityStore, decode_authority_state
from src.domains.world.wire_models import VersionedModel, require_integer_version


class LegacyWorldState(WorldStateShape, VersionedModel):
    """Original persistence generation, independent of the current socket generation."""


def decode_legacy_state(raw: str | bytes | None) -> LegacyWorldState:
    """Read a bounded strict v1 document without converting its generation or epoch."""
    return decode_authority_state(raw, LegacyWorldState)


def encode_legacy_state(state: WorldStateShape) -> str:
    """Keep original nested field sets so an older worker can still read its own scene.

    Only selective erasure uses this encoder. New admission must use the current
    store: mutating an unset default mapping is deliberately not a legacy write.
    """
    return state.model_dump_json(exclude_unset=True)


class LegacyWorldStore(AuthorityStore[LegacyWorldState]):
    """Use the same bounded CAS while preserving the old worker's accepted shape."""

    decode = staticmethod(decode_legacy_state)
    encode = staticmethod(encode_legacy_state)


class LegacyWorldStateV2(WorldStateShape):
    """Frozen pre-game persistence generation; it never declares or writes game tables."""

    version: Literal[2] = Field(
        default=2,
        description="Previous persistence generation, accepted only for selective erasure.",
    )

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        """Preserve exact legacy generation validation without coercion."""
        return require_integer_version(value)


def decode_legacy_state_v2(raw: str | bytes | None) -> LegacyWorldStateV2:
    """Read the previous bounded generation without converting its epoch or fields."""
    return decode_authority_state(raw, LegacyWorldStateV2)


class LegacyWorldStoreV2(AuthorityStore[LegacyWorldStateV2]):
    """Erasure-only CAS for still-active pre-game scenes."""

    decode = staticmethod(decode_legacy_state_v2)
    encode = staticmethod(encode_legacy_state)
