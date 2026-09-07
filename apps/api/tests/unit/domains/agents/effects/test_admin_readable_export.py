"""An administrator extracting a readable register (ADR-263 lot 4, ADR-273).

The third and fourth extractions the owner asked for: a human-readable register
for one account, several, or all of them over a period — and the technical one
under the same scoping. Both reuse the engine the user's own export uses, so
the three documents cannot disagree about what a register says.

Three properties are this surface's own:

- **masked by default, unmasked on the record.** An administrator may
  legitimately need to read what an action said; nobody should be able to do so
  without leaving a trace. That applies to the ACTION register, whose label
  names people — the consultation register has nothing to mask, and pretending
  otherwise would be security theatre that costs an operator information.
- **"all accounts" is a request, not an omission.** Passing no account must
  mean the whole instance because an administrator asked for the whole
  instance, and the row count says how much that was.
- **the record is whole.** No ceiling applies (ADR-273), and the trace of an
  unmasking is written BEFORE the first byte leaves: the administrator asked to
  see the wordings, which is true whether or not the download completes.

A note on the harness: a ``StreamingResponse``'s body is produced after the
handler returns, so ``_run`` collects it while the read seams are still
patched. Reading it afterwards would consume the real ones.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.admin_router import export_readable_admin
from src.domains.agents.effects.technical_reads import TechnicalQuery
from tests.unit.domains.agents.effects.streaming import body_of, rows_of

pytestmark = [pytest.mark.unit]

ADMIN = uuid.uuid4()
ALICE = uuid.uuid4()
BOB = uuid.uuid4()


def _action(user_id: uuid.UUID = ALICE, **overrides: Any) -> Any:
    row = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "label": None,
        "tool_name": "send_email_tool",
        "mutation_policy": "confirm",
        "status": "succeeded",
        "source": "user",
        "execution_mode": "pipeline",
        "approval_kind": "tool_confirm",
        "provider_ref": "msg-1",
        "error_code": None,
        "thread_id": "conv-1",
        "claimed_at": datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 9, 3, 10, 0, 1, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _treatment(user_id: uuid.UUID = ALICE, **overrides: Any) -> Any:
    row = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "tool_name": "get_emails_tool",
        "mutation_policy": "read",
        "outcome": "ok",
        "source": "user",
        "execution_mode": "pipeline",
        "thread_id": "conv-1",
        "duration_ms": 120,
        "occurred_at": datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class _Reads:
    """The count and the stream of one register, stubbed together."""

    def __init__(self, rows: list[Any], *, total: int | None = None) -> None:
        self._rows = rows
        self._total = len(rows) if total is None else total
        self.asked: TechnicalQuery | None = None
        self.batch: int | None = None

    async def count(self, _db: Any, asked: TechnicalQuery) -> int:
        self.asked = asked
        return self._total

    def stream(self, _db: Any, asked: TechnicalQuery, *, batch: int) -> AsyncIterator[Any]:
        self.asked = asked
        self.batch = batch
        return rows_of(self._rows)


class _Ledger:
    """Only what the readable document asks of the ledger repository."""

    @staticmethod
    def decrypted_label(_row: Any) -> dict[str, Any]:
        return {"i18n_key": "effects.labels.send_email_tool", "values": {"recipient": "Marie"}}


@asynccontextmanager
async def _no_session() -> AsyncIterator[Any]:
    """The session the streaming generator opens for itself."""
    yield SimpleNamespace()


def _admin(is_superuser: bool = True) -> Any:
    return SimpleNamespace(
        id=ADMIN, is_superuser=is_superuser, language="fr", timezone="Europe/Paris"
    )


def _request() -> Any:
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers={"user-agent": "x"})


@dataclass(frozen=True)
class _Download:
    """What the administrator actually received."""

    headers: Any
    media_type: str | None
    body: str
    audited: list[Any]


def _seams() -> tuple[Any, ...]:
    """Patch the reads, the streaming session and the ledger's one helper."""
    return (
        patch("src.domains.agents.effects.admin_router.get_db_context", _no_session),
        patch("src.domains.agents.effects.repository.EffectLedgerRepository", _Ledger),
    )


async def _run(**kwargs: Any) -> _Download:
    """Call the readable route and read everything it produced."""
    reads: _Reads = kwargs.pop("reads")
    db = kwargs.pop("db", None) or AsyncMock()
    audited: list[Any] = []
    db.add = audited.append
    session, ledger = _seams()
    with (
        patch("src.domains.agents.effects.admin_router.count_register", reads.count),
        patch("src.domains.agents.effects.admin_router.stream_register", reads.stream),
        session,
        ledger,
    ):
        response = await export_readable_admin(
            request=_request(), db=db, accept_encoding=None, **kwargs
        )
        return _Download(
            headers=response.headers,
            media_type=response.media_type,
            body=await body_of(response),
            audited=audited,
        )


def _call(**overrides: Any) -> dict[str, Any]:
    """The readable route's parameters, with the boring ones filled in."""
    call = {
        "register": "actions",
        "export_format": "markdown",
        "user_ids": None,
        "since": None,
        "until": None,
        "unmask": False,
        "current_user": _admin(),
    }
    call.update(overrides)
    return call


class TestOnlyAnAdministrator:
    async def test_an_ordinary_user_is_refused(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - the raiser's own type
            await _run(**_call(current_user=_admin(is_superuser=False)), reads=_Reads([_action()]))


class TestTheScopeIsWhatWasAsked:
    async def test_one_account_narrows_the_query(self) -> None:
        reads = _Reads([_action()])

        await _run(**_call(user_ids=[ALICE]), reads=reads)

        assert reads.asked is not None
        assert reads.asked.user_ids == [ALICE]

    async def test_several_accounts_narrow_it_to_several(self) -> None:
        reads = _Reads([_action(), _action(BOB)])

        await _run(**_call(export_format="csv", user_ids=[ALICE, BOB]), reads=reads)

        assert reads.asked is not None
        assert reads.asked.user_ids == [ALICE, BOB]

    async def test_no_account_means_every_account(self) -> None:
        """An omission that means "everything" must be a request, not a bug."""
        reads = _Reads([_action(), _action(BOB)])

        response = await _run(**_call(export_format="csv"), reads=reads)

        assert reads.asked is not None
        assert reads.asked.user_ids is None
        assert response.headers["x-register-rows"] == "2"

    async def test_the_period_travels(self) -> None:
        since = datetime(2026, 9, 1, tzinfo=UTC)
        until = datetime(2026, 9, 4, tzinfo=UTC)
        reads = _Reads([_action()])

        await _run(**_call(since=since, until=until), reads=reads)

        assert reads.asked is not None
        assert reads.asked.since == since
        assert reads.asked.until == until


class TestTheWordingIsMaskedUnlessAsked:
    async def test_an_action_wording_is_withheld_by_default(self) -> None:
        response = await _run(**_call(), reads=_Reads([_action()]))

        assert "Marie" not in response.body
        assert "send_email_tool" in response.body, "masking must not hide WHICH capability acted"

    async def test_unmasking_reveals_and_is_recorded(self) -> None:
        response = await _run(**_call(unmask=True), reads=_Reads([_action()]))

        assert "Marie" in response.body
        assert len(response.audited) == 1, "an unmasked export left no trace"

    async def test_the_trace_is_written_BEFORE_the_document_is_sent(self) -> None:
        """An administrator asked to read the wordings; that is what is audited.

        Recording it only once the download completed would leave no trace of a
        request the reader abandoned halfway — and the abandoned half was read
        all the same.
        """
        reads = _Reads([_action()])
        db = AsyncMock()
        audited: list[Any] = []
        db.add = audited.append
        session, ledger = _seams()
        with (
            patch("src.domains.agents.effects.admin_router.count_register", reads.count),
            patch("src.domains.agents.effects.admin_router.stream_register", reads.stream),
            session,
            ledger,
        ):
            await export_readable_admin(
                request=_request(), db=db, accept_encoding=None, **_call(unmask=True)
            )

            assert len(audited) == 1, "nothing was recorded before the first byte"

    async def test_nothing_is_audited_when_nothing_was_revealed(self) -> None:
        response = await _run(**_call(), reads=_Reads([_action()]))

        assert response.audited == []

    async def test_a_consultation_export_has_nothing_to_mask(self) -> None:
        """No label, no arguments: masking here would cost information for nothing."""
        response = await _run(**_call(register="consultations"), reads=_Reads([_treatment()]))

        assert "E-mails" in response.body
        assert "•••" not in response.body


class TestTheDocumentSaysWhatItIs:
    async def test_the_file_is_named_after_the_register(self) -> None:
        response = await _run(
            **_call(register="consultations", export_format="csv"), reads=_Reads([_treatment()])
        )

        assert "consultations" in response.headers["content-disposition"]

    async def test_the_export_declares_itself_complete(self) -> None:
        """It replaced « a truncated export says so »: there is no ceiling left.

        The header is kept rather than dropped for the same reason it existed:
        a reader must not have to infer completeness from the absence of a
        warning (ADR-273).
        """
        response = await _run(
            **_call(register="consultations", export_format="csv"),
            reads=_Reads([_treatment()], total=12_000),
        )

        assert response.headers["x-register-truncated"] == "false"
        assert response.headers["x-register-rows"] == "12000"

    async def test_the_masking_state_travels_with_the_document(self) -> None:
        masked = await _run(**_call(), reads=_Reads([_action()]))
        revealed = await _run(**_call(unmask=True), reads=_Reads([_action()]))

        assert masked.headers["x-register-masked"] == "true"
        assert revealed.headers["x-register-masked"] == "false"


class TestTheTechnicalExportServesBothRegisters:
    """The consultation register had NO technical export: an administrator
    could analyse what the assistant did and nothing of what it looks at."""

    @staticmethod
    async def _run(**kwargs: Any) -> _Download:
        reads: _Reads = kwargs.pop("reads")
        db = AsyncMock()
        session, ledger = _seams()
        with (
            patch("src.domains.agents.effects.admin_router.count_register", reads.count),
            patch("src.domains.agents.effects.admin_router.stream_register", reads.stream),
            session,
            ledger,
        ):
            from src.domains.agents.effects.admin_router import export_technical

            response = await export_technical(db=db, accept_encoding=None, **kwargs)
            return _Download(
                headers=response.headers,
                media_type=response.media_type,
                body=await body_of(response),
                audited=[],
            )

    @staticmethod
    def _technical_call(**overrides: Any) -> dict[str, Any]:
        call = {
            "register": "consultations",
            "since": None,
            "until": None,
            "user_ids": None,
            "tool_name": None,
            "mutation_policy": None,
            "status": None,
            "source": None,
            "execution_mode": None,
            "current_user": _admin(),
        }
        call.update(overrides)
        return call

    async def test_consultations_are_exportable_and_pseudonymised(self) -> None:
        reads = _Reads([_treatment()])

        response = await self._run(**self._technical_call(user_ids=[ALICE]), reads=reads)

        assert "get_emails_tool" in response.body
        assert str(ALICE) not in response.body, "an account id reached a pseudonymised export"
        assert "conv-1" not in response.body, "a conversation id reconstructs someone's day"
        assert reads.asked is not None
        assert reads.asked.user_ids == [ALICE]

    async def test_the_file_is_named_after_the_register(self) -> None:
        response = await self._run(**self._technical_call(), reads=_Reads([_treatment()]))

        assert "consultations" in response.headers["content-disposition"]

    async def test_a_filter_the_register_cannot_honour_is_REPORTED_not_ignored(self) -> None:
        """Silently dropping a filter makes an unfiltered file look filtered."""
        import json

        response = await self._run(
            **self._technical_call(execution_mode="react"), reads=_Reads([_treatment()])
        )

        header = json.loads(response.body.splitlines()[0])
        assert "execution_mode" in header["filters"]["ignored_filters"]

    async def test_the_action_export_is_unchanged(self) -> None:
        response = await self._run(
            **self._technical_call(register="actions"), reads=_Reads([_action()])
        )

        assert "actions" in response.headers["content-disposition"]
        assert "send_email_tool" in response.body
