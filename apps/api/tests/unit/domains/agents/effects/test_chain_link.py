"""The link: how one entry binds to its predecessor (ADR-263, lot 5).

Pure, and tested apart from the database on purpose. Everything the chain
promises reduces to two functions — how an entry is hashed, and how a walk
decides a chain holds — and both must be verifiable without a PostgreSQL, so
the property is pinned rather than merely observed on a happy path.

The verdict is deliberately RICH rather than a boolean: an audit device that
answers "broken" without saying where and why sends an operator to guess, and
guessing is how a real break gets dismissed as a false alarm.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.domains.agents.effects.chain_link import (
    ChainBreak,
    ChainLink,
    link_hash,
    walk,
)

pytestmark = [pytest.mark.unit]

_SUBJECT = uuid.UUID("11111111-2222-4333-8444-555555555555")
_WHEN = datetime(2026, 9, 4, 17, 2, 26, 123456, tzinfo=UTC)


def _link(
    seq: int, prev: str | None, *, digest: str = "d" * 64, kind: str = "effect.claimed"
) -> ChainLink:
    return ChainLink(
        seq=seq,
        kind=kind,
        subject_id=_SUBJECT,
        payload_digest=digest,
        prev_hash=prev,
        entry_hash=link_hash(
            seq=seq, kind=kind, subject_id=_SUBJECT, payload_digest=digest, prev_hash=prev
        ),
        digest_version=1,
        occurred_at=_WHEN,
    )


def _chain(length: int) -> list[ChainLink]:
    links: list[ChainLink] = []
    previous: str | None = None
    for seq in range(1, length + 1):
        link = _link(seq, previous, digest=f"{seq:064d}")
        links.append(link)
        previous = link.entry_hash
    return links


class TestTheHashBindsEverythingItShould:
    @pytest.mark.parametrize(
        "changed",
        ["seq", "kind", "subject_id", "payload_digest", "prev_hash"],
    )
    def test_changing_any_bound_field_changes_the_hash(self, changed: str) -> None:
        base = {
            "seq": 1,
            "kind": "effect.claimed",
            "subject_id": _SUBJECT,
            "payload_digest": "a" * 64,
            "prev_hash": "b" * 64,
        }
        altered = dict(base)
        altered[changed] = (
            2
            if changed == "seq"
            else (
                uuid.UUID("99999999-2222-4333-8444-555555555555")
                if changed == "subject_id"
                else "x" * 64 if changed in {"payload_digest", "prev_hash"} else "effect.settled"
            )
        )

        assert link_hash(**base) != link_hash(**altered)  # type: ignore[arg-type]

    def test_the_first_link_has_no_predecessor_and_still_hashes(self) -> None:
        assert link_hash(
            seq=1, kind="chain.genesis", subject_id=None, payload_digest="0" * 64, prev_hash=None
        )

    def test_no_predecessor_is_not_the_empty_string(self) -> None:
        """Otherwise a chain could be re-rooted at an arbitrary point."""
        without = link_hash(
            seq=1, kind="k", subject_id=None, payload_digest="0" * 64, prev_hash=None
        )
        empty = link_hash(seq=1, kind="k", subject_id=None, payload_digest="0" * 64, prev_hash="")

        assert without != empty


class TestAHealthyChainWalks:
    def test_an_empty_chain_is_valid(self) -> None:
        """An account that has done nothing has nothing to prove."""
        verdict = walk([])

        assert verdict.ok
        assert verdict.entries_checked == 0

    def test_a_chain_of_one_is_valid(self) -> None:
        assert walk(_chain(1)).ok

    def test_a_long_chain_is_valid(self) -> None:
        verdict = walk(_chain(500))

        assert verdict.ok
        assert verdict.entries_checked == 500
        assert verdict.head_hash == _chain(500)[-1].entry_hash


class TestABrokenChainSaysWHERE:
    def test_a_rewritten_entry_is_found_at_its_seq(self) -> None:
        links = _chain(10)
        links[4] = ChainLink(**{**links[4].__dict__, "payload_digest": "f" * 64})

        verdict = walk(links)

        assert not verdict.ok
        assert verdict.broken_at_seq == 5
        assert verdict.reason is ChainBreak.ENTRY_HASH

    def test_a_cut_predecessor_is_found(self) -> None:
        links = _chain(10)
        links[6] = ChainLink(**{**links[6].__dict__, "prev_hash": "0" * 64})

        verdict = walk(links)

        assert not verdict.ok
        assert verdict.broken_at_seq == 7
        assert verdict.reason is ChainBreak.PREV_HASH

    def test_a_deleted_entry_leaves_a_gap_that_is_found(self) -> None:
        links = _chain(10)
        del links[5]

        verdict = walk(links)

        assert not verdict.ok
        assert verdict.broken_at_seq == 7
        assert verdict.reason is ChainBreak.SEQUENCE

    def test_a_chain_that_does_not_start_at_one_is_found(self) -> None:
        """Deleting the FIRST entry must not read as a shorter valid chain."""
        verdict = walk(_chain(5)[1:])

        assert not verdict.ok
        assert verdict.reason is ChainBreak.SEQUENCE
        assert verdict.broken_at_seq == 2

    def test_a_second_root_is_found(self) -> None:
        """An entry past the first may not claim to have no predecessor."""
        links = _chain(4)
        links[2] = ChainLink(**{**links[2].__dict__, "prev_hash": None})

        verdict = walk(links)

        assert not verdict.ok
        assert verdict.broken_at_seq == 3

    def test_the_walk_STOPS_at_the_break(self) -> None:
        """On a million-entry chain, reporting only at the end is useless."""
        links = _chain(100)
        links[9] = ChainLink(**{**links[9].__dict__, "payload_digest": "f" * 64})

        verdict = walk(links)

        assert verdict.entries_checked == 9, "the walk kept going past the break"


class TestTheVerdictIsUsable:
    def test_a_healthy_verdict_names_the_head(self) -> None:
        """The head hash is what an operator writes down to detect a later
        rewrite of the whole chain — the only defence against someone who can
        rewrite both a row and its entry."""
        verdict = walk(_chain(3))

        assert verdict.head_hash is not None
        assert len(verdict.head_hash) == 64

    def test_a_broken_verdict_has_no_head(self) -> None:
        links = _chain(3)
        links[1] = ChainLink(**{**links[1].__dict__, "payload_digest": "f" * 64})

        assert walk(links).head_hash is None
