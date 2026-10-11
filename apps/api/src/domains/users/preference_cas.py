"""Compare an approved preference snapshot while the caller holds the row lock."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, JsonValue

from src.core.exceptions import ResourceConflictError
from src.domains.users.models import User


@dataclass
class PreferenceWriteReceipt:
    """Local receipt set only after the shared service commits its own write."""

    committed: bool = False
    no_op: bool = False
    values: dict[str, JsonValue] | None = None


def verified_preference_noop(
    patch: BaseModel, expected: Mapping[str, JsonValue], receipt: PreferenceWriteReceipt | None
) -> bool:
    """Called only after the approved snapshot has been verified under its lock."""
    if patch.model_dump(mode="json", exclude_unset=True) != dict(expected):
        return False
    if receipt is not None:
        receipt.committed = True
        receipt.no_op = True
    return True


def check_expected_preferences(
    user: User, patch: BaseModel, expected: Mapping[str, JsonValue]
) -> None:
    if set(expected) != patch.model_fields_set:
        raise ValueError("Expected state must cover exactly the patched preference fields")
    for name, expected_value in expected.items():
        actual = getattr(user, name)
        actual = str(actual) if isinstance(actual, UUID) else actual
        if json.dumps(actual, sort_keys=True) != json.dumps(expected_value, sort_keys=True):
            raise ResourceConflictError("preferences", detail={"error_code": "STALE_STATE"})
