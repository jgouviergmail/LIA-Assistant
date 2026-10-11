"""Shared source reference resolution and local-date normalization for legacy tool arguments."""

from uuid import UUID

from src.core.time_utils import normalize_user_datetime
from src.domains.workboard.service import WorkboardService


async def normalize_workboard_legacy(
    service: WorkboardService, owner_id: UUID, zone: str, values: dict[str, object]
) -> dict[str, object]:
    values = dict(values)
    assignee = values.pop("assignee", None)
    parent = values.pop("parent_ticket", None)
    if any(value is not None and not isinstance(value, str) for value in (assignee, parent)):
        raise ValueError("Legacy assignee and parent references require strings")
    if isinstance(assignee, str):
        keyword = assignee.strip().lower()
        if keyword in {"me", "lia"}:
            values["assignee"] = keyword
        else:
            values["assignee_user_id"] = await service.resolve_connected_user_id(
                owner_id, assignee.strip()
            )
    if isinstance(parent, str):
        values["parent_id"] = (await service.resolve_reference(owner_id, parent)).id
    for field in ("start_at", "due_at"):
        value = values.get(field)
        if isinstance(value, str):
            values[field] = normalize_user_datetime(value, zone)
    return values
