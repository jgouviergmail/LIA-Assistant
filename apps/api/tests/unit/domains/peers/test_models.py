"""Peers ORM model tests (peer-connections program, Lot 1, Task 3)."""

from uuid import UUID

import pytest

from src.domains.peers.models import (
    PeerAccessLog,
    PeerBlock,
    PeerConnection,
    PeerConnectionStatus,
    PeerDomainShare,
    PeerMessage,
    PeerMessageStatus,
    PeerShareDomain,
    PeerShareLevel,
    canonical_pair,
)

U1 = UUID("00000000-0000-0000-0000-000000000001")
U2 = UUID("00000000-0000-0000-0000-000000000002")


@pytest.mark.unit
class TestCanonicalPair:
    """The canonical ordering makes duplicate pairs unrepresentable."""

    def test_orders_uuids_regardless_of_argument_order(self):
        assert canonical_pair(U2, U1) == (U1, U2)
        assert canonical_pair(U1, U2) == (U1, U2)


@pytest.mark.unit
class TestStatusEnums:
    """String(20) columns + lowercase str-enum values (open_loops pattern)."""

    def test_connection_statuses(self):
        assert PeerConnectionStatus.PENDING.value == "pending"
        assert PeerConnectionStatus.ACCEPTED.value == "accepted"
        assert PeerConnectionStatus.DECLINED.value == "declined"
        assert PeerConnectionStatus.REMOVED.value == "removed"

    def test_share_domains_and_levels(self):
        assert PeerShareDomain.CALENDAR.value == "calendar"
        assert PeerShareDomain.TASK.value == "task"
        assert PeerShareLevel.AVAILABILITY.value == "availability"
        assert PeerShareLevel.DETAILS.value == "details"
        assert PeerShareLevel.TITLES.value == "titles"

    def test_message_statuses(self):
        assert PeerMessageStatus.PENDING.value == "pending"
        assert PeerMessageStatus.DELIVERED.value == "delivered"
        assert PeerMessageStatus.FAILED.value == "failed"
        assert PeerMessageStatus.CANCELLED.value == "cancelled"


@pytest.mark.unit
class TestTableConstraints:
    """DB-level constraints carry the pair semantics (spec §4.1)."""

    def test_connection_pair_constraints_declared(self):
        names = {c.name for c in PeerConnection.__table_args__ if hasattr(c, "name")}
        assert "uq_peer_connections_pair" in names
        assert "ck_peer_connections_pair_order" in names

    def test_block_constraints_declared(self):
        names = {c.name for c in PeerBlock.__table_args__ if hasattr(c, "name")}
        assert "uq_peer_blocks_pair" in names
        assert "ck_peer_blocks_not_self" in names

    def test_share_unique_triple_declared(self):
        names = {c.name for c in PeerDomainShare.__table_args__ if hasattr(c, "name")}
        assert "uq_peer_domain_shares_owner_domain" in names

    def test_message_table_named(self):
        assert PeerMessage.__tablename__ == "peer_messages"

    def test_access_log_is_immutable_shape(self):
        """No updated_at: the access log follows the AdminAuditLog pattern."""
        column_names = {c.name for c in PeerAccessLog.__table__.columns}
        assert "created_at" in column_names
        assert "updated_at" not in column_names
