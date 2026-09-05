"""One extraction over everything LIA records (ADR-263, lot 9).

The extraction composes five contracts and renders nothing new, so the tests
here are about the properties composition can still get wrong:

- the five sources must stay **five**, never one total — they answer different
  questions and adding them up is meaningless;
- a reader must be able to answer « is this the whole period? » from the header
  alone, which means the ceiling is stated **per source**;
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
    article12_filters,
    article12_header,
    extract_of,
    known_sources,
    render_article12,
)
from src.domains.agents.effects.technical_export import TECHNICAL_SPECS, pseudonymise

pytestmark = [pytest.mark.unit]

_WHEN = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


def _row(spec_slug: str, **values: object) -> SimpleNamespace:
    spec = TECHNICAL_SPECS[spec_slug]
    base = dict.fromkeys(spec.exported)
    base.update({"user_id": uuid.uuid4(), **values})
    return SimpleNamespace(**base)


def _extract(slug: str, count: int, *, cap: int = 100):
    spec = TECHNICAL_SPECS[slug]
    return extract_of(spec, [_row(slug) for _ in range(count)], cap=cap)


class TestTheFiveSourcesStayFIVE:
    def test_every_line_says_which_record_it_belongs_to(self) -> None:
        content = render_article12(
            [_extract("decisions", 1), _extract("actions", 1)],
            cap=100,
            filters={},
            generated_at=_WHEN,
        )

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

    def test_a_source_column_named_kind_SURVIVES_beside_it(self) -> None:
        content = render_article12(
            [_extract("integrity", 1)], cap=100, filters={}, generated_at=_WHEN
        )
        line = json.loads(content.strip().splitlines()[1])

        assert line[RECORD_KEY] == "lia.integrity"
        assert "kind" in line, "the register's own classification was lost"

    def test_the_header_counts_each_source_SEPARATELY(self) -> None:
        """One total would invite exactly the arithmetic the registers refuse."""
        header = article12_header(
            [_extract("decisions", 3), _extract("actions", 2)],
            cap=100,
            filters={},
            generated_at=_WHEN,
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
    def test_a_source_that_hit_the_ceiling_says_so(self) -> None:
        header = article12_header(
            [_extract("decisions", 5, cap=5), _extract("actions", 1, cap=5)],
            cap=5,
            filters={},
            generated_at=_WHEN,
        )

        assert header["sources"]["decisions"]["truncated"] is True
        assert header["sources"]["actions"]["truncated"] is False

    def test_a_file_complete_in_FOUR_of_five_is_not_complete(self) -> None:
        header = article12_header(
            [_extract("decisions", 5, cap=5), _extract("actions", 1, cap=5)],
            cap=5,
            filters={},
            generated_at=_WHEN,
        )

        assert header["complete"] is False

    def test_a_whole_period_says_so_too(self) -> None:
        header = article12_header(
            [_extract("decisions", 2), _extract("actions", 1)],
            cap=100,
            filters={},
            generated_at=_WHEN,
        )

        assert header["complete"] is True

    def test_the_ceiling_itself_is_published(self) -> None:
        header = article12_header([_extract("actions", 1)], cap=42, filters={}, generated_at=_WHEN)

        assert header["cap_per_source"] == 42

    def test_each_source_publishes_what_it_WITHHELD(self) -> None:
        """« excluded_columns » is what turns an allowlist into a statement."""
        header = article12_header([_extract("actions", 1)], cap=100, filters={}, generated_at=_WHEN)

        assert "label" in header["sources"]["actions"]["excluded_columns"]
        assert "user_id" in header["sources"]["actions"]["excluded_columns"]


class TestNothingIdentifyingLeaves:
    def test_no_raw_account_id_appears_in_any_line(self) -> None:
        account = uuid.uuid4()
        spec = TECHNICAL_SPECS["decisions"]
        extract = extract_of(spec, [_row("decisions", user_id=account)], cap=100)

        content = render_article12([extract], cap=100, filters={}, generated_at=_WHEN)

        assert str(account) not in content
        assert pseudonymise(account) in content

    def test_the_HEADER_pseudonymises_the_accounts_it_was_asked_about(self) -> None:
        """The lot-4 defect, in the one place a composition could reintroduce
        it: a file promising « pseudonymised by construction » printed the raw
        ids of the accounts requested, in its own header."""
        account = uuid.uuid4()
        filters = article12_filters(since=None, until=None, user_ids=[account])

        header = article12_header([_extract("actions", 1)], cap=100, filters=filters)

        assert str(account) not in json.dumps(header)

    def test_the_period_travels_as_asked(self) -> None:
        filters = article12_filters(since=_WHEN, until=None, user_ids=None)

        assert filters["since"] == _WHEN.isoformat()
        assert filters["until"] is None


class TestTheFileIsMachineREADABLE:
    def test_every_line_is_valid_json(self) -> None:
        content = render_article12(
            [_extract("decisions", 2), _extract("integrity", 1)],
            cap=100,
            filters={},
            generated_at=_WHEN,
        )

        for line in content.strip().splitlines():
            json.loads(line)

    def test_an_empty_period_still_produces_a_readable_file(self) -> None:
        """An extraction over a quiet week is a valid answer, not an error."""
        content = render_article12(
            [_extract(slug, 0) for slug in TECHNICAL_SPECS],
            cap=100,
            filters={},
            generated_at=_WHEN,
        )

        lines = content.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["complete"] is True

    def test_the_file_ends_with_a_newline(self) -> None:
        content = render_article12(
            [_extract("actions", 1)], cap=100, filters={}, generated_at=_WHEN
        )

        assert content.endswith("\n")


class TestTheCeilingIsItsOWN:
    def test_the_extraction_is_capped_lower_than_a_single_record(self) -> None:
        """Measured, not guessed: five sources at 5 000 rows render a 10,8 MB
        file with a 33,9 MB peak and 939 ms of pure serialisation, before the
        ORM instances behind them. At 1 000 the same file is 2,1 MB, peaks at
        6,6 MB and renders in 201 ms — a better bargain on the hardware this
        project deploys to, and the header says what was truncated."""
        from src.core.config import settings

        assert (
            settings.article12_export_max_rows_per_source
            < settings.effect_technical_export_max_rows
        )

    def test_the_route_uses_that_ceiling_and_not_the_other(self) -> None:
        import inspect

        from src.domains.agents.effects.admin_router import export_article12

        source = inspect.getsource(export_article12)

        assert "article12_export_max_rows_per_source" in source
        assert "effect_technical_export_max_rows" not in source
