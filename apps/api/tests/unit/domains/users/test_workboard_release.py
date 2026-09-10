"""Releasing what a departing account merely HELD on a workboard (ADR-276).

Account deletion SCRUBS the ``users`` row rather than deleting it, so no
foreign-key action fires on that path: the ``ON DELETE SET NULL`` that protects
the four hard-delete paths is inert here, and this explicit statement is the
only thing that hands the ticket back to its owner.

It lives in the users domain, with the rest of the purge, for the reason the
whole purge is metadata-driven: ``users`` imports no domain, and reaching into
one closes a runtime import cycle the F009 ratchet counts.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects import postgresql

from src.domains.users.account_deletion_service import build_workboard_release

pytestmark = pytest.mark.unit


def _sql(user_id: uuid.UUID) -> str:
    return str(
        build_workboard_release(user_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestReleaseStatement:
    def test_it_updates_the_ticket_table(self) -> None:
        assert "UPDATE workboard_tickets" in _sql(uuid.uuid4())

    def test_it_hands_the_ticket_back_by_clearing_the_assignee(self) -> None:
        """NULL is « the owner holds it » — one convention, not two."""
        assignments = _sql(uuid.uuid4()).split("WHERE", 1)[0].replace(" ", "")
        assert "assignee_user_id=NULL" in assignments
        assert "assignee_kind='human'" in assignments

    def test_it_silences_the_notifications_the_departing_side_had_asked_for(self) -> None:
        assert "follow_assignee=false" in _sql(uuid.uuid4()).replace(" ", "").lower()

    def test_it_never_touches_the_tickets_the_account_owns(self) -> None:
        """The owner's own rows are DELETED by the purge; releasing them too
        would be a wasted write and would mask a purge that failed to run."""
        user_id = uuid.uuid4()
        where = _sql(user_id).split("WHERE", 1)[1]
        assert f"assignee_user_id = '{user_id}'" in where
        assert f"owner_user_id != '{user_id}'" in where

    def test_it_names_the_departing_account_and_no_other(self) -> None:
        user_id = uuid.uuid4()
        other = uuid.uuid4()
        sql = _sql(user_id)
        assert str(user_id) in sql
        assert str(other) not in sql


class TestNoDomainImport:
    def test_the_users_domain_imports_no_workboard_module(self) -> None:
        """F009: ``users`` imports no domain, local imports included — the
        ratchet counts those too, so hiding the edge in a function would only
        make it harder to see.
        """
        from pathlib import Path

        source = Path("src/domains/users/account_deletion_service.py").read_text(encoding="utf-8")
        assert "domains.workboard" not in source
        assert "domains.peers" not in source
