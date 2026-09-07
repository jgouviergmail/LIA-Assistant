"""Taking a register out of the application, readable (ADR-263, lot 4).

Four extractions were asked for, and this module is the engine under all of
them: a user's own register, and an administrator's over one, several or every
account for a period. Two formats, because they answer different questions —
Markdown is read, CSV is counted — and ONE renderer, because two would drift
and a register whose two exports disagree is evidence of nothing.

What the wording must satisfy, and each of these is a property below:

- **the reader's clock, not the server's**: an action stamped 23:40 UTC
  happened on the next day in Auckland and the previous one in Los Angeles, so
  the day headers are cut in the reader's own display timezone;
- **the reader's language**, resolved at export time from the stored key;
- **the authority is on the line**, because "who allowed this" is the whole
  question a register answers;
- **nothing invented**: a provider reference is printed when the world gave
  one back and left out otherwise (ADR-263's own rule).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.effects.export_readable import (
    ACTIONS,
    TREATMENTS,
    stream_csv,
    stream_markdown,
)
from tests.unit.domains.agents.effects.streaming import rendered, rows_of

pytestmark = [pytest.mark.unit]


async def render_markdown(spec: Any, rows: list[Any], language: str, timezone_name: str) -> str:
    """The whole Markdown document, collected from the stream that renders it.

    The renderers stream since ADR-273; these properties are about the
    DOCUMENT, so they read it whole. Collecting in one helper rather than at
    fifty assertions keeps the chunk boundaries an implementation detail.

    Args:
        spec: Which register.
        rows: Its rows, oldest first.
        language: The reader's language.
        timezone_name: The reader's display timezone.

    Returns:
        The document.
    """
    return await rendered(stream_markdown(spec, rows_of(rows), language, timezone_name))


async def render_csv(spec: Any, rows: list[Any], language: str, timezone_name: str) -> str:
    """The whole CSV document, collected from the stream that renders it.

    Args:
        spec: Which register.
        rows: Its rows, oldest first.
        language: The reader's language.
        timezone_name: The reader's display timezone.

    Returns:
        The document.
    """
    return await rendered(stream_csv(spec, rows_of(rows), language, timezone_name))


def _action(**overrides: Any) -> Any:
    row = {
        "id": "11111111-1111-4111-8111-111111111111",
        "label": json.dumps(
            {"i18n_key": "effects.labels.draft.email", "values": {"recipient": "Marie"}}
        ),
        "tool_name": "draft:email",
        "mutation_policy": "draft",
        "status": "succeeded",
        "source": "user",
        "execution_mode": "pipeline",
        "approval_kind": "draft_confirm",
        "provider_ref": "msg-42",
        "error_code": None,
        "thread_id": "conv-7",
        "claimed_at": datetime(2026, 9, 3, 23, 40, tzinfo=UTC),
        "closed_at": datetime(2026, 9, 3, 23, 40, 2, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _treatment(**overrides: Any) -> Any:
    row = {
        "id": "22222222-2222-4222-8222-222222222222",
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


class TestTheDayIsTheReadersDay:
    async def test_a_late_utc_action_falls_on_the_next_day_in_auckland(self) -> None:
        markdown = await render_markdown(ACTIONS, [_action()], "fr", "Pacific/Auckland")

        assert "2026-09-04" in markdown, "the day was cut on the server's clock"

    async def test_the_same_action_falls_on_the_previous_day_in_los_angeles(self) -> None:
        markdown = await render_markdown(ACTIONS, [_action()], "fr", "America/Los_Angeles")

        assert "2026-09-03" in markdown

    async def test_an_unknown_timezone_does_not_break_the_export(self) -> None:
        """A stale preference must degrade, never lose the register."""
        markdown = await render_markdown(ACTIONS, [_action()], "fr", "Mars/Olympus_Mons")

        assert "Marie" in markdown

    async def test_one_header_per_day_not_per_row(self) -> None:
        rows = [
            _action(claimed_at=datetime(2026, 9, 3, 8, 0, tzinfo=UTC)),
            _action(claimed_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC)),
            _action(claimed_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC)),
        ]
        markdown = await render_markdown(ACTIONS, rows, "fr", "UTC")

        assert markdown.count("## 2026-09-03") == 1
        assert markdown.count("## 2026-09-04") == 1


class TestTheWordingIsTheReadersLanguage:
    @pytest.mark.parametrize(
        ("language", "expected"),
        [("fr", "Marie"), ("de", "Marie"), ("en", "Marie")],
    )
    async def test_the_action_label_is_rendered(self, language: str, expected: str) -> None:
        assert expected in await render_markdown(ACTIONS, [_action()], language, "UTC")

    async def test_a_treatment_reads_as_its_domain(self) -> None:
        markdown = await render_markdown(TREATMENTS, [_treatment()], "fr", "UTC")

        assert "E-mails" in markdown
        assert "get_emails_tool" in markdown


class TestTheAuthorityIsOnTheLine:
    async def test_an_action_says_how_it_was_authorised(self) -> None:
        assert "draft_confirm" in await render_markdown(ACTIONS, [_action()], "fr", "UTC")

    async def test_an_action_says_who_asked_for_the_turn(self) -> None:
        markdown = await render_markdown(ACTIONS, [_action(source="scheduled")], "fr", "UTC")

        assert "scheduled" in markdown

    async def test_a_provider_reference_is_printed_when_there_is_one(self) -> None:
        assert "msg-42" in await render_markdown(ACTIONS, [_action()], "fr", "UTC")

    async def test_nothing_is_invented_when_there_is_none(self) -> None:
        markdown = await render_markdown(ACTIONS, [_action(provider_ref=None)], "fr", "UTC")

        assert "None" not in markdown
        assert "msg-42" not in markdown


class TestTheCsvIsCountable:
    async def test_the_action_header_names_every_column(self) -> None:
        rows = list(csv.reader(io.StringIO(await render_csv(ACTIONS, [_action()], "fr", "UTC"))))

        assert rows[0] == list(ACTIONS.csv_columns)
        assert len(rows) == 2

    async def test_the_treatment_header_names_every_column(self) -> None:
        rows = list(
            csv.reader(io.StringIO(await render_csv(TREATMENTS, [_treatment()], "fr", "UTC")))
        )

        assert rows[0] == list(TREATMENTS.csv_columns)
        assert len(rows[1]) == len(TREATMENTS.csv_columns)

    async def test_the_timestamp_is_the_readers_too(self) -> None:
        body = await render_csv(ACTIONS, [_action()], "fr", "Pacific/Auckland")

        assert "2026-09-04" in body

    async def test_a_cell_that_starts_like_a_formula_is_neutralised(self) -> None:
        """A CSV opened in a spreadsheet must not execute what it carries."""
        body = await render_csv(
            TREATMENTS, [_treatment(tool_name="=cmd|'/c calc'!A1")], "fr", "UTC"
        )

        assert "\n=cmd" not in body
        assert ",=cmd" not in body
        assert "'=cmd" in body or "\"'=cmd" in body

    async def test_an_empty_register_still_carries_its_header(self) -> None:
        rows = list(csv.reader(io.StringIO(await render_csv(ACTIONS, [], "fr", "UTC"))))

        assert rows[0] == list(ACTIONS.csv_columns)


class TestTheTwoRegistersShareOneEngine:
    async def test_both_specs_render_through_the_same_functions(self) -> None:
        """Two renderers would drift; a register that disagrees proves nothing."""
        assert await render_markdown(ACTIONS, [], "fr", "UTC")
        assert await render_markdown(TREATMENTS, [], "fr", "UTC")

    async def test_each_spec_names_its_own_file(self) -> None:
        assert ACTIONS.slug != TREATMENTS.slug
        assert ACTIONS.slug and TREATMENTS.slug
