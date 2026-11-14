"""Shared source reference resolution and local-date normalization for legacy tool arguments.

Three words of a legacy call are NAMES the service resolves — who holds the
ticket, which ticket it is a step of, and which category it is filed under —
and two are local dates. Everything else travels untouched.

The category is resolved among the ACTOR's own categories, never the ticket
owner's: a holder who names one is refused the same way whether or not the
owner has a category called that, so the refusal says nothing about somebody
else's board. « No category » has no keyword — a keyword would collide with a
category called that — and is said with ``clear_category``.
"""

from uuid import UUID

from src.core.time_utils import normalize_user_datetime
from src.domains.workboard.service import WorkboardService


async def normalize_workboard_legacy(
    service: WorkboardService,
    owner_id: UUID,
    zone: str,
    values: dict[str, object],
    *,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    """Turn the legacy words of a ticket tool into the source schema's fields.

    Args:
        service: The workboard service — it owns every resolution.
        owner_id: The ticket's owner: whose connections and tickets are read.
        zone: The user's timezone, for the local dates.
        values: The legacy fields the model gave.
        actor_id: Who is asking, when it is not the owner — whose categories
            a ``category`` name is read among.

    Returns:
        The fields as ``TicketCreate`` / ``TicketUpdate`` name them.

    Raises:
        ValueError: A reference that is not a string.
        ValidationError: A name the service does not find (stable code).
    """
    values = dict(values)
    assignee = values.pop("assignee", None)
    parent = values.pop("parent_ticket", None)
    category = values.pop("category", None)
    references = (assignee, parent, category)
    if any(value is not None and not isinstance(value, str) for value in references):
        raise ValueError("Legacy assignee, parent and category references require strings")
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
    if isinstance(category, str):
        values["category_id"] = await service.categories.own_named(actor_id or owner_id, category)
    for field in ("start_at", "due_at"):
        value = values.get(field)
        if isinstance(value, str):
            values[field] = normalize_user_datetime(value, zone)
    return values
