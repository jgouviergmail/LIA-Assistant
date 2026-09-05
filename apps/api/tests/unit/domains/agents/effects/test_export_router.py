"""Downloading a register (ADR-263, lot 4).

The endpoint under the user's own "Exporter" button, and the shape the
administrator's extraction reuses. Four properties, each of them a way the
export could have been quietly wrong:

- **it is always the CALLER's register** — the route has no account parameter,
  so there is no way to ask for someone else's by mistake;
- **two registers stay two documents**, per the owner's arbitration: an export
  that merged them would let a reader add two totals that count different
  things;
- **the reader's language and clock**, taken from their account rather than
  from a query string — evidence a caller can restyle is weaker evidence;
- **the cap is published**, so a register cut at the ceiling says so instead of
  looking complete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.export_router import FORMATS, REGISTERS, export_register

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


class _Repository:
    """Both repositories at once — they answer the same export question."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.seen: dict[str, Any] = {}

    def __call__(self, _db: Any) -> Any:
        return self

    async def list_for_export(self, **kwargs: Any) -> list[Any]:
        self.seen = kwargs
        return self._rows


def _user(language: str = "fr", timezone: str = "Europe/Paris") -> Any:
    return SimpleNamespace(id=OWNER, language=language, timezone=timezone)


def _with(repository: _Repository) -> Any:
    return (
        patch("src.domains.agents.effects.treatment_repository.TreatmentRepository", repository),
        patch("src.domains.agents.effects.repository.EffectLedgerRepository", repository),
    )


async def _export(**kwargs: Any) -> Any:
    repository = kwargs.pop("repository")
    patches = _with(repository)
    with patches[0], patches[1]:
        return await export_register(db=object(), **kwargs)  # type: ignore[arg-type]


class TestTheTwoRegistersStayTwoDocuments:
    def test_each_register_has_its_own_name(self) -> None:
        assert set(REGISTERS) == {"actions", "consultations"}

    async def test_a_consultation_export_names_its_own_file(self) -> None:
        response = await _export(
            register="consultations",
            export_format="markdown",
            since=None,
            until=None,
            user=_user(),
            repository=_Repository([_treatment()]),
        )

        assert "consultations" in response.headers["content-disposition"]
        assert "actions" not in response.headers["content-disposition"]


class TestItIsAlwaysTheCallersRegister:
    async def test_the_query_is_scoped_to_the_caller(self) -> None:
        repository = _Repository([_treatment()])

        await _export(
            register="consultations",
            export_format="csv",
            since=None,
            until=None,
            user=_user(),
            repository=repository,
        )

        assert repository.seen["user_id"] == OWNER

    async def test_the_route_takes_no_account_parameter(self) -> None:
        """The strongest guarantee is the one the signature makes impossible."""
        import inspect

        parameters = set(inspect.signature(export_register).parameters)

        assert "user_id" not in parameters
        assert "user_ids" not in parameters


class TestThePeriodTravels:
    async def test_both_bounds_reach_the_repository(self) -> None:
        since = datetime(2026, 9, 1, tzinfo=UTC)
        until = datetime(2026, 9, 4, tzinfo=UTC)
        repository = _Repository([_treatment()])

        await _export(
            register="consultations",
            export_format="markdown",
            since=since,
            until=until,
            user=_user(),
            repository=repository,
        )

        assert repository.seen["since"] == since
        assert repository.seen["until"] == until


class TestTheReadersLanguageAndClock:
    async def test_the_document_is_written_in_the_accounts_language(self) -> None:
        response = await _export(
            register="consultations",
            export_format="markdown",
            since=None,
            until=None,
            user=_user(language="de"),
            repository=_Repository([_treatment()]),
        )

        assert "E-Mails" in response.body.decode()

    async def test_the_days_are_cut_on_the_accounts_clock(self) -> None:
        response = await _export(
            register="consultations",
            export_format="markdown",
            since=None,
            until=None,
            user=_user(timezone="Pacific/Auckland"),
            repository=_Repository([_treatment()]),
        )

        assert "2026-09-04" in response.body.decode()

    async def test_a_missing_preference_falls_back_to_the_instance_default(self) -> None:
        response = await _export(
            register="consultations",
            export_format="markdown",
            since=None,
            until=None,
            user=SimpleNamespace(id=OWNER, language="fr", timezone=None),
            repository=_Repository([_treatment()]),
        )

        assert response.status_code == 200


class TestTheCapIsPublished:
    async def test_a_complete_export_says_it_is_complete(self) -> None:
        response = await _export(
            register="consultations",
            export_format="csv",
            since=None,
            until=None,
            user=_user(),
            repository=_Repository([_treatment()]),
        )

        assert response.headers["x-register-truncated"] == "false"
        assert response.headers["x-register-rows"] == "1"

    async def test_a_truncated_export_says_so(self) -> None:
        from src.core.config import settings

        rows = [_treatment() for _ in range(settings.effect_technical_export_max_rows)]

        response = await _export(
            register="consultations",
            export_format="csv",
            since=None,
            until=None,
            user=_user(),
            repository=_Repository(rows),
        )

        assert response.headers["x-register-truncated"] == "true"


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
        response = await _export(
            register="consultations",
            export_format=export_format,
            since=None,
            until=None,
            user=_user(),
            repository=_Repository([_treatment()]),
        )

        assert response.media_type.startswith(media_type)
