"""One extraction over everything LIA records (ADR-263 lot 9, ADR-273).

The extraction composes five contracts and renders nothing new, so the tests
here are about the properties composition can still get wrong:

- the five sources must stay **five**, never one total — they answer different
  questions and adding them up is meaningless;
- a reader must be able to answer « is this the whole period? » from the header
  alone. Until ADR-273 that meant stating a ceiling per source; now it means
  there is none, and the file says so rather than leaving it to be inferred;
- the count in the header is the EXACT total, and it is published before the
  first row is read — a streamed file cannot revise its own first line;
- nothing identifying may leave in the clear, in the rows OR in the header —
  the defect lot 4 found in a file that promised the opposite;
- a sixth record declared tomorrow must join the extraction without anyone
  remembering it.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.domains.agents.effects.article12_export import (
    RECORD_KEY,
    SourceStream,
    article12_filters,
    article12_header,
    known_sources,
    stream_article12,
)
from src.domains.agents.effects.technical_export import TECHNICAL_SPECS, pseudonymise
from tests.unit.domains.agents.effects.streaming import rendered, rows_of

pytestmark = [pytest.mark.unit]

_WHEN = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


def _row(spec_slug: str, **values: object) -> SimpleNamespace:
    spec = TECHNICAL_SPECS[spec_slug]
    base = dict.fromkeys(spec.exported)
    base.update({"user_id": uuid.uuid4(), **values})
    return SimpleNamespace(**base)


def _source(slug: str, count: int, *, total: int | None = None) -> SourceStream:
    """One source's contribution: its exact total, and its rows.

    Args:
        slug: Which record.
        count: How many rows the body carries.
        total: What the header declares — defaults to ``count``. A test that
            wants to prove the header reads the COUNT rather than tallying the
            body passes the two apart.

    Returns:
        The source.
    """
    spec = TECHNICAL_SPECS[slug]
    return SourceStream(
        spec=spec,
        total=count if total is None else total,
        rows=rows_of([_row(slug) for _ in range(count)]),
    )


async def _content(*sources: SourceStream, filters: dict[str, object] | None = None) -> str:
    """The whole extraction, collected from the stream that renders it."""
    return await rendered(
        stream_article12(list(sources), filters=filters or {}, generated_at=_WHEN)
    )


class TestTheFiveSourcesStayFIVE:
    async def test_every_line_says_which_record_it_belongs_to(self) -> None:
        content = await _content(_source("decisions", 1), _source("actions", 1))

        records = [json.loads(line)[RECORD_KEY] for line in content.strip().splitlines()]
        assert records == ["lia.article12", "lia.decisions", "lia.actions"]

    def test_the_discriminator_cannot_be_SHADOWED_by_a_source_column(self) -> None:
        """The integrity register has a business column called ``kind``, and a
        plain discriminator by that name was silently overwritten on the first
        render against real rows. The key belongs to the FILE."""
        for slug, spec in TECHNICAL_SPECS.items():
            assert RECORD_KEY not in spec.exported, (
                f"{slug} exports a column named {RECORD_KEY!r}; it would shadow the "
                "line's own discriminator and make the file unreadable"
            )

    async def test_a_source_column_named_kind_SURVIVES_beside_it(self) -> None:
        content = await _content(_source("integrity", 1))
        line = json.loads(content.strip().splitlines()[1])

        assert line[RECORD_KEY] == "lia.integrity"
        assert "kind" in line, "the register's own classification was lost"

    def test_the_header_counts_each_source_SEPARATELY(self) -> None:
        """One total would invite exactly the arithmetic the registers refuse."""
        header = article12_header(
            [_source("decisions", 3), _source("actions", 2)], filters={}, generated_at=_WHEN
        )

        assert header["sources"]["decisions"]["lines"] == 3
        assert header["sources"]["actions"]["lines"] == 2
        assert "total" not in header
        assert "row_count" not in header

    def test_the_extraction_covers_every_declared_contract(self) -> None:
        """Read from the registry, so a sixth record joins on its own."""
        assert {spec.slug for spec in known_sources()} == set(TECHNICAL_SPECS)

    def test_the_turn_comes_first_because_the_others_hang_off_it(self) -> None:
        assert known_sources()[0].slug == "decisions"


class TestTheHeaderAnswersIsThisTheWHOLEPeriod:
    def test_no_source_is_ever_reported_as_truncated(self) -> None:
        """There is no ceiling to hit any more (ADR-273)."""
        header = article12_header(
            [_source("decisions", 5), _source("actions", 1)], filters={}, generated_at=_WHEN
        )

        assert header["sources"]["decisions"]["truncated"] is False
        assert header["sources"]["actions"]["truncated"] is False

    def test_completeness_is_CLAIMED_rather_than_left_to_be_inferred(self) -> None:
        """Dropping the key would have been tidier and a worse contract.

        A reader would then tell a complete file from a partial one by the
        ABSENCE of a warning, which is what an extraction must never ask of
        them — and it is the same reasoning that made the ceiling stated per
        source in the first place.
        """
        header = article12_header([_source("decisions", 2)], filters={}, generated_at=_WHEN)

        assert header["complete"] is True

    def test_a_ceiling_that_no_longer_exists_is_not_advertised(self) -> None:
        header = article12_header([_source("actions", 1)], filters={}, generated_at=_WHEN)

        assert "cap_per_source" not in header

    def test_the_count_is_the_one_that_was_COUNTED_not_a_tally_of_the_body(self) -> None:
        """The header goes out before the first row is read.

        Tallying while rendering would be the obvious implementation and it
        cannot work: the first line is already on the wire. The count comes
        from an aggregate over the same statement the body streams, so this
        test hands the two apart and pins which one the header reports.
        """
        header = article12_header([_source("actions", 1, total=7)], filters={}, generated_at=_WHEN)

        assert header["sources"]["actions"]["lines"] == 7

    def test_each_source_publishes_what_it_WITHHELD(self) -> None:
        """« excluded_columns » is what turns an allowlist into a statement."""
        header = article12_header([_source("actions", 1)], filters={}, generated_at=_WHEN)

        assert "label" in header["sources"]["actions"]["excluded_columns"]
        assert "user_id" in header["sources"]["actions"]["excluded_columns"]


class TestNothingIdentifyingLeaves:
    async def test_no_raw_account_id_appears_in_any_line(self) -> None:
        account = uuid.uuid4()
        spec = TECHNICAL_SPECS["decisions"]
        source = SourceStream(
            spec=spec, total=1, rows=rows_of([_row("decisions", user_id=account)])
        )

        content = await _content(source)

        assert str(account) not in content
        assert pseudonymise(account) in content

    def test_the_HEADER_pseudonymises_the_accounts_it_was_asked_about(self) -> None:
        """The lot-4 defect, in the one place a composition could reintroduce
        it: a file promising « pseudonymised by construction » printed the raw
        ids of the accounts requested, in its own header."""
        account = uuid.uuid4()
        filters = article12_filters(since=None, until=None, user_ids=[account])

        header = article12_header([_source("actions", 1)], filters=filters)

        assert str(account) not in json.dumps(header)

    def test_the_period_travels_as_asked(self) -> None:
        filters = article12_filters(since=_WHEN, until=None, user_ids=None)

        assert filters["since"] == _WHEN.isoformat()
        assert filters["until"] is None


class TestTheFileIsMachineREADABLE:
    async def test_every_line_is_valid_json(self) -> None:
        content = await _content(_source("decisions", 2), _source("integrity", 1))

        for line in content.strip().splitlines():
            json.loads(line)

    async def test_an_empty_period_still_produces_a_readable_file(self) -> None:
        """An extraction over a quiet week is a valid answer, not an error."""
        content = await _content(*[_source(slug, 0) for slug in TECHNICAL_SPECS])

        lines = content.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["complete"] is True

    async def test_the_file_ends_with_a_newline(self) -> None:
        content = await _content(_source("actions", 1))

        assert content.endswith("\n")


class TestNoExtractionCarriesACeiling:
    """The guard that replaced « the ceiling is its own, and lower ».

    That property became unfalsifiable the day the ceiling was removed, and a
    test which cannot fail is worse than no test: it reads as coverage. What
    stays falsifiable is the opposite claim — that no export route reads a row
    ceiling — and it fails the moment someone reintroduces one.
    """

    @staticmethod
    def _export_routes() -> dict[str, object]:
        from src.domains.agents.effects.admin_router import (
            export_article12 as admin_article12,
        )
        from src.domains.agents.effects.admin_router import (
            export_readable_admin,
            export_technical,
        )
        from src.domains.agents.effects.export_router import (
            export_article12 as user_article12,
        )
        from src.domains.agents.effects.export_router import (
            export_register,
        )

        return {
            "admin/export": export_technical,
            "admin/export/article12": admin_article12,
            "admin/export/readable": export_readable_admin,
            "export": export_register,
            "export/article12": user_article12,
        }

    def test_the_two_row_ceilings_are_gone_from_the_settings(self) -> None:
        from src.core.config import settings

        assert not hasattr(settings, "effect_technical_export_max_rows")
        assert not hasattr(settings, "article12_export_max_rows_per_source")

    def test_what_replaced_them_bounds_MEMORY_and_says_so(self) -> None:
        from src.core.config import settings

        assert settings.effect_export_batch_rows > 0

    def test_no_export_route_reads_a_row_ceiling(self) -> None:
        import inspect

        for name, route in self._export_routes().items():
            source = inspect.getsource(route)  # type: ignore[arg-type]
            assert "max_rows" not in source, (
                f"{name} reads a row ceiling again — an extraction of a register is "
                "complete or it is not an extraction (ADR-273)"
            )

    def test_every_export_route_declares_its_completeness(self) -> None:
        import inspect

        for name, route in self._export_routes().items():
            source = inspect.getsource(route)  # type: ignore[arg-type]
            assert (
                "X-Register-Truncated" in source
            ), f"{name} sends no completeness claim; a reader would have to infer it"
