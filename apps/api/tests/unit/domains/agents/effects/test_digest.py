"""Digests are stable identities, never proofs of correctness (ADR-263).

A digest answers *"is this still exactly the same object?"* — never *"is this
object correct?"*. The ledger uses three of them: the call that was authorised,
the draft the user was shown, and the result that came back.

``args_digest`` reuses the loop guard's keyed digest so ONE call hashes the same
way in both places; a second implementation would drift and the two subsystems
would disagree about what "the same call" means.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.domains.agents.effects.digest import args_digest, draft_digest, payload_digest
from src.domains.agents.utils.loop_guard import compute_call_digest

pytestmark = [pytest.mark.unit]


class TestTheCallIdentity:
    def test_key_order_does_not_change_the_identity(self) -> None:
        a = args_digest("send_email_tool", {"to": "a@b.c", "subject": "s"})
        b = args_digest("send_email_tool", {"subject": "s", "to": "a@b.c"})
        assert a == b
        assert len(a) == 64

    def test_a_changed_argument_changes_the_identity(self) -> None:
        a = args_digest("send_email_tool", {"to": "a@b.c", "subject": "s"})
        assert a != args_digest("send_email_tool", {"to": "a@b.c", "subject": "S"})

    def test_a_changed_tool_changes_the_identity(self) -> None:
        a = args_digest("send_email_tool", {"to": "a@b.c"})
        assert a != args_digest("reply_email_tool", {"to": "a@b.c"})

    def test_none_arguments_are_the_empty_call(self) -> None:
        assert args_digest("x_tool", None) == args_digest("x_tool", {})

    def test_it_is_the_loop_guard_digest_not_a_second_one(self) -> None:
        """One definition of "the same call", shared with the no-progress guard."""
        from src.core.config import settings

        expected = compute_call_digest("send_email_tool", {"to": "a@b.c"}, settings.secret_key)
        assert args_digest("send_email_tool", {"to": "a@b.c"}) == expected

    def test_the_digest_is_keyed_so_it_is_not_reversible_by_a_reader(self) -> None:
        """A raw sha256 of the args would let anyone with the row rebuild them."""
        import hashlib
        import json

        raw = hashlib.sha256(
            json.dumps(["send_email_tool", {"to": "a@b.c"}], sort_keys=True).encode()
        ).hexdigest()
        assert args_digest("send_email_tool", {"to": "a@b.c"}) != raw


class TestThePayloadIdentity:
    def test_it_survives_values_json_cannot_render(self) -> None:
        value = {"id": uuid.UUID(int=1), "at": datetime(2026, 9, 3, tzinfo=UTC)}
        digest = payload_digest(value)
        assert len(digest) == 64

    def test_key_order_does_not_change_it(self) -> None:
        a = payload_digest({"id": uuid.UUID(int=1), "at": "x"})
        b = payload_digest({"at": "x", "id": uuid.UUID(int=1)})
        assert a == b

    def test_none_has_an_identity_of_its_own(self) -> None:
        assert payload_digest(None) != payload_digest({})

    def test_a_list_keeps_its_order(self) -> None:
        assert payload_digest([1, 2]) != payload_digest([2, 1])


class TestTheDraftIdentity:
    def test_an_edited_draft_is_a_different_draft(self) -> None:
        """ADR-092: what is confirmed must be what was last shown."""
        before = draft_digest({"to": "a@b.c", "body": "v1"})
        after = draft_digest({"to": "a@b.c", "body": "v2"})
        assert before != after

    def test_the_same_draft_is_the_same_identity(self) -> None:
        assert draft_digest({"to": "a@b.c", "body": "v1"}) == draft_digest(
            {"body": "v1", "to": "a@b.c"}
        )
