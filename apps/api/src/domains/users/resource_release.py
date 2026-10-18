"""Release references owned by other accounts before erasing one account."""

from uuid import UUID

from sqlalchemy import Select, Update, case, update

from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base


def workboard_release(user_id: UUID) -> Update:
    import_all_models()
    tickets = Base.metadata.tables["workboard_tickets"]
    return (
        update(tickets)
        .where(tickets.c.assignee_user_id == user_id, tickets.c.owner_user_id != user_id)
        .values(assignee_kind="human", assignee_user_id=None, follow_assignee=False)
    )


def build_capability_origin_scrub(user_id: UUID | Select[tuple[UUID]]) -> Update:
    """Copies survive sender erasure; unpublished bytes and stale claims do not."""
    import_all_models()
    transfers = Base.metadata.tables["peer_capability_transfers"]
    predicate = (
        transfers.c.sender_id == user_id
        if isinstance(user_id, UUID)
        else transfers.c.sender_id.in_(user_id)
    )
    return (
        update(transfers)
        .where(predicate)
        .values(
            sender_id=None,
            snapshot=None,
            lease_owner=None,
            lease_expires_at=None,
            fence=transfers.c.fence + 1,
            status=case(
                (transfers.c.status.in_(("preparing", "installing")), "cancelled"),
                else_=transfers.c.status,
            ),
        )
    )
