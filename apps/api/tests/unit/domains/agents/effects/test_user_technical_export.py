"""The reader gets the machine-readable form of their own register (ADR-263).

Three formats, one endpoint: markdown to read, CSV to count, JSON Lines to
analyse. The third is the SAME contract the administrator's export obeys — an
allowlist of columns, no content, identifiers pseudonymised — and reusing it
rather than inventing a user variant is the whole point:

- it makes the file safe to HAND ON. The readable export already carries the
  reader's own wording; what this one adds is a record of the same events that
  reveals nothing when attached to a bug report, a complaint or a portability
  request.
- it takes no new privacy decision. A second contract for the same rows would
  be a second place for a column to slip from « forbidden » to « exported ».

The scoping property is the one that must never regress: the route has no
account parameter at all, so there is no way to ask for someone else's register
by mistake — a filter one could forget is a filter someone eventually forgets.
"""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.effects.technical_reads import TechnicalQuery
from tests.unit.domains.agents.effects.route_vocabulary import literal_values
from tests.unit.domains.agents.effects.streaming import rendered, rows_of

pytestmark = [pytest.mark.unit]


@asynccontextmanager
async def _no_session() -> AsyncIterator[object]:
    """The session the streaming generator opens for itself."""
    yield object()


async def render_technical(
    spec: object, rows: list[object], language: str, timezone: str, *, total: int | None = None
) -> str:
    """The whole JSON Lines document the route composes, collected (ADR-273).

    It goes through the route's own composition rather than through the
    renderer directly: what these properties are about is what the READER
    receives, and the header, the contract and the rows are assembled here.

    Args:
        spec: Which register, in its readable declaration.
        rows: The rows the read would have produced.
        language: The reader's language — unused by this format, passed for
            signature parity with the two readable ones.
        timezone: Likewise.
        total: What the header declares; defaults to the number of rows.

    Returns:
        The document.
    """
    from src.domains.agents.effects import export_router as module

    asked = TechnicalQuery(register=spec.slug, user_ids=[uuid.uuid4()])  # type: ignore[attr-defined]
    with (
        patch.object(module, "stream_register", lambda _db, _a, *, batch: rows_of(rows)),
        patch.object(module, "get_db_context", _no_session),
    ):
        return await rendered(
            module._document(
                spec,  # type: ignore[arg-type]
                asked,
                export_format="technical",
                total=len(rows) if total is None else total,
                language=language,
                timezone=timezone,
                generated_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                batch=100,
            )
        )


def _effect(**values: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "schema_version": 1,
        "tool_name": "send_email_tool",
        "mutation_policy": "draft",
        "status": "succeeded",
        "source": "user",
        "execution_mode": "pipeline",
        "approval_kind": None,
        "error_code": None,
        "args_digest": "a" * 64,
        "draft_digest": None,
        "result_truncated": False,
        "claimed_at": datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
        "closed_at": None,
        "thread_id": "thread-A",
        "run_id": "run-1",
        "idempotency_key": "call-1",
        "approval_ref": None,
        "retry_of": None,
        "catalogue_fingerprint": None,
        "result_digest": None,
        # The two the contract must never let through.
        "label": '{"key": "effects.label.email_sent", "values": {"to": "Marie"}}',
        "result_payload": "encrypted-blob",
        "provider_ref": "msg-42",
        "claim_token": uuid.uuid4(),
    }
    base.update(values)
    return SimpleNamespace(**base)


class TestTheThirdFormatIsAnENTRYNotAnEdit:
    def test_the_route_offers_three_formats(self) -> None:
        from src.domains.agents.effects.export_router import export_register

        assert literal_values(export_register, "export_format") == {
            "markdown",
            "csv",
            "technical",
        }

    def test_the_two_spec_families_share_their_slugs(self) -> None:
        """The technical renderer finds its contract BY SLUG. A rename on one
        side would silently serve the wrong contract — or none."""
        from src.domains.agents.effects.export_readable import ACTIONS, TREATMENTS
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        assert {ACTIONS.slug, TREATMENTS.slug} <= set(TECHNICAL_SPECS)


class TestItCarriesNoCONTENT:
    async def test_the_wording_never_leaves(self) -> None:
        """`label` names people. The readable export shows it to its owner; a
        file meant to be handed on must not."""
        from src.domains.agents.effects.export_readable import ACTIONS

        body = await render_technical(ACTIONS, [_effect()], "fr", "Europe/Paris")

        assert "Marie" not in body
        assert "encrypted-blob" not in body

    async def test_the_account_id_is_pseudonymised_like_everywhere_else(self) -> None:
        from src.domains.agents.effects.export_readable import ACTIONS
        from src.domains.agents.effects.technical_export import pseudonymise

        account = uuid.uuid4()
        body = await render_technical(ACTIONS, [_effect(user_id=account)], "fr", "Europe/Paris")

        assert str(account) not in body
        assert pseudonymise(account) in body

    async def test_the_file_opens_with_a_header_naming_its_register(self) -> None:
        from src.domains.agents.effects.export_readable import ACTIONS

        header = json.loads(
            (await render_technical(ACTIONS, [_effect()], "fr", "Europe/Paris")).splitlines()[0]
        )

        assert header["register"] == "actions"
        assert header["pseudonymised"] is True
        assert "label" in header["excluded_columns"]

    async def test_every_line_is_valid_json(self) -> None:
        from src.domains.agents.effects.export_readable import TREATMENTS

        body = await render_technical(
            TREATMENTS,
            [
                SimpleNamespace(
                    id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    tool_name="get_emails_tool",
                    mutation_policy="read",
                    outcome="ok",
                    source="user",
                    execution_mode="pipeline",
                    duration_ms=12,
                    occurred_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                    thread_id="thread-A",
                    run_id="run-1",
                )
            ],
            "fr",
            "Europe/Paris",
        )

        for line in body.strip().splitlines():
            json.loads(line)

    async def test_an_empty_register_still_produces_a_readable_file(self) -> None:
        from src.domains.agents.effects.export_readable import ACTIONS

        lines = (await render_technical(ACTIONS, [], "fr", "Europe/Paris")).strip().splitlines()

        assert len(lines) == 1
        assert json.loads(lines[0])["row_count"] == 0


class TestTheReadersOwnRegisterAndNoOnesELSE:
    def test_the_route_has_no_account_parameter(self) -> None:
        """A filter one could forget is a filter someone eventually forgets.
        The scoping is structural: there is nothing to pass."""
        from src.domains.agents.effects.export_router import export_register

        parameters = set(inspect.signature(export_register).parameters)

        assert not parameters & {"user_id", "user_ids", "account", "account_id"}

    def test_the_read_is_scoped_to_the_caller(self) -> None:
        """The scope is built once, from the session, for all three formats."""
        from src.domains.agents.effects.export_router import export_register

        source = inspect.getsource(export_register)

        assert "user_ids=[user.id]" in source, "a register is read unscoped"


class TestTheReaderGetsTheirWHOLERegister:
    """What replaced « the route and the renderer publish the same ceiling ».

    That property guarded a real hazard — a header stating a ceiling the query
    had not applied would make a truncated file look complete. The hazard is
    gone with the ceiling (ADR-273), so the guard is rewritten rather than
    deleted: the file must now CLAIM completeness, and it must publish the
    total that was counted rather than the length of what it happened to send.
    """

    async def test_the_header_claims_completeness_and_advertises_no_ceiling(self) -> None:
        from src.domains.agents.effects.export_readable import ACTIONS

        header = json.loads(
            (await render_technical(ACTIONS, [_effect()], "fr", "Europe/Paris")).splitlines()[0]
        )

        assert header["truncated"] is False
        assert "row_cap" not in header

    async def test_the_header_publishes_the_COUNTED_total(self) -> None:
        """It is written before the first row is read, so it cannot be a tally."""
        from src.domains.agents.effects.export_readable import ACTIONS

        header = json.loads(
            (
                await render_technical(ACTIONS, [_effect()], "fr", "Europe/Paris", total=4211)
            ).splitlines()[0]
        )

        assert header["row_count"] == 4211
