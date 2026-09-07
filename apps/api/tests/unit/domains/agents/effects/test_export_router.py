"""Downloading a register (ADR-263 lot 4, ADR-273).

The endpoint under the user's own "Exporter" button, and the shape the
administrator's extraction reuses. The properties, each of them a way the
export could have been quietly wrong:

- **it is always the CALLER's register** — the route has no account parameter,
  so there is no way to ask for someone else's by mistake;
- **two registers stay two documents**, per the owner's arbitration: an export
  that merged them would let a reader add two totals that count different
  things;
- **the reader's language and clock**, taken from their account rather than
  from a query string — evidence a caller can restyle is weaker evidence;
- **it is complete, and it says so** — no ceiling applies, the row count in the
  headers is the exact total, and the period is CLOSED at the instant the file
  is generated so the count and the body describe the same set;
- **it is compressed when the client can decompress it**, which is transport
  and never changes the document.

One thing about the harness, because it cost a green-looking run to find: a
``StreamingResponse``'s body is produced **after** the handler returns. A test
that patches the read seams inside a ``with`` block and then reads the body
outside it consumes the REAL seams — here, a live database — and passes or
fails for reasons that have nothing to do with the property. So ``_export``
collects the whole document while the patches are still in scope and hands it
back beside the headers. The same fact is why the production generator opens a
session of its own rather than borrowing the request's.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.export_router import FORMATS, REGISTERS, export_register
from src.domains.agents.effects.technical_reads import TechnicalQuery
from tests.unit.domains.agents.effects.streaming import body_of, rows_of

pytestmark = [pytest.mark.unit]

OWNER = uuid.uuid4()


def _treatment(**overrides: Any) -> Any:
    row = {
        "tool_name": "get_emails_tool",
        "mutation_policy": "read",
        "outcome": "ok",
        "source": "user",
        "execution_mode": "pipeline",
        "thread_id": "conv-7",
        "duration_ms": 142,
        "occurred_at": datetime(2026, 9, 3, 23, 40, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class _Reads:
    """The two halves of a register read, stubbed together.

    They are stubbed together because that is how the route uses them: the
    exact count and the streamed rows come out of one dispatch, and a harness
    that let them disagree would be testing a shape the code cannot produce.
    """

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


@asynccontextmanager
async def _no_session() -> AsyncIterator[Any]:
    """The session the streaming generator opens for itself."""
    yield object()


def _user(language: str = "fr", timezone: str = "Europe/Paris") -> Any:
    return SimpleNamespace(id=OWNER, language=language, timezone=timezone)


@dataclass(frozen=True)
class _Download:
    """What a reader actually received.

    Attributes:
        headers: The response headers.
        media_type: The declared type.
        status_code: The status.
        body: The whole document, decompressed if it was compressed —
            collected while the seams were still patched.
    """

    headers: Any
    media_type: str | None
    status_code: int
    body: str


async def _export(**kwargs: Any) -> _Download:
    """Call the route and read everything it produced, seams still in place."""
    reads: _Reads = kwargs.pop("reads")
    with (
        patch("src.domains.agents.effects.export_router.count_register", reads.count),
        patch("src.domains.agents.effects.export_router.stream_register", reads.stream),
        patch("src.domains.agents.effects.export_router.get_db_context", _no_session),
    ):
        response = await export_register(db=object(), **kwargs)  # type: ignore[arg-type]
        return _Download(
            headers=response.headers,
            media_type=response.media_type,
            status_code=response.status_code,
            body=await body_of(response),
        )


def _call(**overrides: Any) -> dict[str, Any]:
    """The route's parameters, with the boring ones filled in."""
    call = {
        "register": "consultations",
        "export_format": "markdown",
        "since": None,
        "until": None,
        "accept_encoding": None,
        "user": _user(),
    }
    call.update(overrides)
    return call


class TestTheTwoRegistersStayTwoDocuments:
    def test_each_register_has_its_own_name(self) -> None:
        assert set(REGISTERS) == {"actions", "consultations"}

    async def test_a_consultation_export_names_its_own_file(self) -> None:
        response = await _export(**_call(), reads=_Reads([_treatment()]))

        assert "consultations" in response.headers["content-disposition"]
        assert "actions" not in response.headers["content-disposition"]


class TestItIsAlwaysTheCallersRegister:
    async def test_the_query_is_scoped_to_the_caller(self) -> None:
        reads = _Reads([_treatment()])

        await _export(**_call(export_format="csv"), reads=reads)

        assert reads.asked is not None
        assert reads.asked.user_ids == [OWNER]

    async def test_the_route_takes_no_account_parameter(self) -> None:
        """The strongest guarantee is the one the signature makes impossible."""
        import inspect

        parameters = set(inspect.signature(export_register).parameters)

        assert "user_id" not in parameters
        assert "user_ids" not in parameters


class TestThePeriodTravels:
    async def test_both_bounds_reach_the_read(self) -> None:
        since = datetime(2026, 9, 1, tzinfo=UTC)
        until = datetime(2026, 9, 4, tzinfo=UTC)
        reads = _Reads([_treatment()])

        await _export(**_call(since=since, until=until), reads=reads)

        assert reads.asked is not None
        assert reads.asked.since == since
        assert reads.asked.until == until

    async def test_an_open_period_is_CLOSED_at_the_moment_of_generation(self) -> None:
        """Otherwise the count and the body could describe different sets.

        The headers go out before the first row is read, so the exact total is
        counted first. Left open, the upper bound would let a row written
        between the two land in the body and not in the count — a file
        disagreeing with its own header (ADR-273).
        """
        before = datetime.now(UTC)
        reads = _Reads([_treatment()])

        await _export(**_call(until=None), reads=reads)

        assert reads.asked is not None
        assert reads.asked.until is not None
        assert before <= reads.asked.until <= datetime.now(UTC)


class TestTheReadersLanguageAndClock:
    async def test_the_document_is_written_in_the_accounts_language(self) -> None:
        response = await _export(**_call(user=_user(language="de")), reads=_Reads([_treatment()]))

        assert "E-Mails" in response.body

    async def test_the_days_are_cut_on_the_accounts_clock(self) -> None:
        response = await _export(
            **_call(user=_user(timezone="Pacific/Auckland")), reads=_Reads([_treatment()])
        )

        assert "2026-09-04" in response.body

    async def test_a_missing_preference_falls_back_to_the_instance_default(self) -> None:
        response = await _export(
            **_call(user=SimpleNamespace(id=OWNER, language="fr", timezone=None)),
            reads=_Reads([_treatment()]),
        )

        assert response.status_code == 200


class TestNothingIsTruncated:
    async def test_the_export_declares_itself_complete(self) -> None:
        response = await _export(**_call(export_format="csv"), reads=_Reads([_treatment()]))

        assert response.headers["x-register-truncated"] == "false"
        assert response.headers["x-register-rows"] == "1"

    async def test_the_published_total_is_the_COUNTED_one(self) -> None:
        """It is an aggregate over the whole set, never the length of a page.

        Handing the count and the body apart is the only way to pin which one
        the header reports; in production they agree because they come from one
        statement (ADR-185, ADR-273).
        """
        reads = _Reads([_treatment()], total=8123)

        response = await _export(**_call(export_format="csv"), reads=reads)

        assert response.headers["x-register-rows"] == "8123"

    async def test_the_read_is_batched_rather_than_capped(self) -> None:
        from src.core.config import settings

        reads = _Reads([_treatment()])

        await _export(**_call(export_format="csv"), reads=reads)

        assert reads.batch == settings.effect_export_batch_rows


class TestTheDownloadIsCompressedWhenItCanBe:
    async def test_a_client_that_offers_gzip_gets_gzip(self) -> None:
        response = await _export(
            **_call(export_format="csv", accept_encoding="gzip, deflate"),
            reads=_Reads([_treatment()]),
        )

        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "Accept-Encoding"

    async def test_a_client_that_does_not_gets_plain_text(self) -> None:
        response = await _export(**_call(export_format="csv"), reads=_Reads([_treatment()]))

        assert "content-encoding" not in response.headers

    async def test_compression_does_not_change_the_document(self) -> None:
        """Transport, never content — the file the reader saves is the same."""
        plain = await _export(**_call(export_format="csv"), reads=_Reads([_treatment()]))
        compressed = await _export(
            **_call(export_format="csv", accept_encoding="gzip"), reads=_Reads([_treatment()])
        )

        assert compressed.body == plain.body

    async def test_the_file_name_stays_the_documents_own(self) -> None:
        """A ``.gz`` name would be a different contract; this is transport."""
        response = await _export(
            **_call(export_format="technical", accept_encoding="gzip"),
            reads=_Reads([_treatment()]),
        )

        assert ".jsonl" in response.headers["content-disposition"]
        assert ".gz" not in response.headers["content-disposition"]


class TestEveryFormatIsServed:
    def test_the_format_table_covers_what_the_route_accepts(self) -> None:
        """Read from the ROUTE, not from a list here: a value the route accepts
        and the table ignores raises a KeyError at the reader rather than at the
        build, and a hand-written expectation has to be remembered."""
        from tests.unit.domains.agents.effects.route_vocabulary import literal_values

        assert literal_values(export_register, "export_format") == set(FORMATS)

    def test_the_three_formats_are_the_ones_a_reader_expects(self) -> None:
        """Read it, count it, or analyse it — the third holds no content and can
        therefore be handed on (ADR-263)."""
        assert set(FORMATS) == {"markdown", "csv", "technical"}

    @pytest.mark.parametrize(
        ("export_format", "media_type"),
        [
            ("markdown", "text/markdown"),
            ("csv", "text/csv"),
            ("technical", "application/x-ndjson"),
        ],
    )
    async def test_the_media_type_matches_the_format(
        self, export_format: str, media_type: str
    ) -> None:
        response = await _export(**_call(export_format=export_format), reads=_Reads([_treatment()]))

        assert response.media_type.startswith(media_type)
