"""What the grant row promises (ADR-298).

A grant is a DECISION the person took on a card: this host, with or without
the turn's data. It belongs to the account (cascade on deletion), one per
host, and it is never touched by a conversation reset — it is a table, not a
Redis family.
"""

from __future__ import annotations

import pytest

from src.domains.agents.python_sandbox.egress.models import SandboxEgressGrant
from src.infrastructure.database.registry import import_all_models

pytestmark = pytest.mark.unit


def test_the_row_belongs_to_the_account_and_goes_with_it() -> None:
    column = SandboxEgressGrant.__table__.c.user_id
    assert column.nullable is False
    (foreign_key,) = column.foreign_keys
    assert foreign_key.ondelete == "CASCADE"
    assert foreign_key.target_fullname == "users.id"


def test_one_grant_per_host_per_account() -> None:
    unique = [
        c
        for c in SandboxEgressGrant.__table__.constraints
        if getattr(c, "name", "") and "uq_" in c.name
    ]
    (constraint,) = unique
    assert {col.name for col in constraint.columns} == {"user_id", "host"}


def test_the_scope_is_a_non_null_boolean_and_the_last_use_optional() -> None:
    table = SandboxEgressGrant.__table__
    assert table.c.share_turn_data.nullable is False
    assert table.c.last_used_at.nullable is True
    assert table.c.host.type.length == 253


def test_the_model_is_registered_once() -> None:
    import_all_models()
    assert "sandbox_egress_grants" in SandboxEgressGrant.metadata.tables
