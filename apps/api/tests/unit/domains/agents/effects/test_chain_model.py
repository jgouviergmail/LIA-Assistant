"""What a chain entry may carry, and what makes it a CHAIN (ADR-263, lot 5).

A tamper-evident journal is not a table with a hash column: it is a table whose
shape makes the properties true. Three of them are enforced by the schema
itself rather than by code that could forget:

- **one chain per account**, so deleting an account removes a COMPLETE chain
  and leaves no permanent hole in anyone else's (the erasure tension, dissolved
  by the shape rather than by a policy);
- **`UNIQUE (user_id, seq)`**, which makes a forked chain impossible even when
  two notaries run at once — simulated: one pass is refused, the sequence stays
  contiguous, no subject is notarised twice;
- **no content**, ever: an entry holds digests and identifiers, so notarising
  costs ~387 bytes and duplicates nothing the register already keeps.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


class TestTheColumnsAreTheContract:
    def test_the_row_carries_what_a_verifier_needs(self) -> None:
        from src.domains.agents.effects.models import LedgerChainEntry

        assert set(LedgerChainEntry.__table__.columns.keys()) == {
            "id",
            "user_id",
            "seq",
            "kind",
            "subject_id",
            "payload_digest",
            "prev_hash",
            "entry_hash",
            "digest_version",
            "occurred_at",
        }

    @pytest.mark.parametrize(
        "forbidden",
        ["label", "result_payload", "args", "content", "prompt", "tool_args"],
    )
    def test_no_column_can_carry_CONTENT(self, forbidden: str) -> None:
        """The chain notarises; it never becomes a second copy of the data."""
        from src.domains.agents.effects.models import LedgerChainEntry

        assert forbidden not in LedgerChainEntry.__table__.columns


class TestTheShapeEnforcesTheProperties:
    def test_a_forked_chain_is_impossible(self) -> None:
        from src.domains.agents.effects.models import LedgerChainEntry

        uniques = {
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in LedgerChainEntry.__table__.constraints
            if type(constraint).__name__ == "UniqueConstraint"
        }

        assert ("seq", "user_id") in uniques

    def test_the_chain_belongs_to_the_account_and_dies_with_it(self) -> None:
        from src.domains.agents.effects.models import LedgerChainEntry

        keys = list(LedgerChainEntry.__table__.c.user_id.foreign_keys)

        assert len(keys) == 1
        assert keys[0].column.table.name == "users"
        assert keys[0].ondelete == "CASCADE"

    def test_it_is_indexed_for_the_walk_it_serves(self) -> None:
        """Verification reads one account's chain in `seq` order, paginated."""
        from src.domains.agents.effects.models import LedgerChainEntry

        indexed = {
            tuple(column.name for column in index.columns)
            for index in LedgerChainEntry.__table__.indexes
        }

        assert ("user_id", "seq") in indexed or ("seq", "user_id") in indexed

    def test_a_subject_can_be_found_without_scanning(self) -> None:
        """Verification also asks « is this row covered, and by what »."""
        from src.domains.agents.effects.models import LedgerChainEntry

        indexed = {
            tuple(column.name for column in index.columns)
            for index in LedgerChainEntry.__table__.indexes
        }

        assert ("subject_id", "kind") in indexed


class TestTheEntryDeclaresItsOwnRULE:
    def test_it_carries_the_digest_version(self) -> None:
        """Without it, changing the encoding would invalidate every past chain
        instead of starting a new rule."""
        from src.domains.agents.effects.models import LedgerChainEntry

        assert "digest_version" in LedgerChainEntry.__table__.columns
        assert not LedgerChainEntry.__table__.c.digest_version.nullable

    def test_the_first_entry_of_a_chain_may_have_no_predecessor(self) -> None:
        from src.domains.agents.effects.models import LedgerChainEntry

        assert LedgerChainEntry.__table__.c.prev_hash.nullable

    def test_every_entry_has_a_hash(self) -> None:
        from src.domains.agents.effects.models import LedgerChainEntry

        assert not LedgerChainEntry.__table__.c.entry_hash.nullable
