"""The demonstrator's daily report — what it says, and when it may say it.

The public instance keeps its database in tmpfs and empties it at 02:30 UTC, so
everything it could tell an operator about the day disappears with the accounts
it describes. A report is therefore the ONLY historised trace: the operator's
mailbox is the archive, and nothing needs to be retained on the instance — which
is also what keeps the promise its own terms make.

That makes the timing a load-bearing coupling rather than a preference: a report
scheduled after the purge counts an empty database and mails a page of zeros,
with nothing to say it lied. The guard for it lives at the bottom of this file.

Owner arbitration 2026-08-07, recorded here because it departs from a standing
rule: this report is FRENCH ONLY. It goes to one operator address, not to
users. The strings are therefore held in a single table so a later
internationalisation is a substitution rather than a rewrite.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.infrastructure.scheduler.demo_daily_report import (
    LABELS,
    DemoDayReport,
    render_demo_day_report_html,
    run_demo_daily_report,
)

pytestmark = pytest.mark.unit


def _report(**over) -> DemoDayReport:
    base: dict[str, object] = {
        "utc_day": date(2026, 8, 7),
        "visitors": 12,
        "verified": 9,
        "signups": 12,
        "signup_limit": 50,
        "conversations": 17,
        "user_messages": 64,
        "assistant_messages": 61,
        "tokens_in": 412_000,
        "tokens_out": 98_000,
        "tokens_cached": 31_000,
        "runs": 64,
        "cost_eur": Decimal("0.4231"),
        "budget_eur": Decimal("1.00"),
    }
    base.update(over)
    return DemoDayReport(**base)


class TestTheSynthesisComesFirst:
    """An operator reads the first screen; the detail is for the doubts."""

    def test_the_html_opens_on_the_synthesis(self) -> None:
        html = render_demo_day_report_html(_report())

        assert html.index(LABELS["synthesis"]) < html.index(LABELS["detail"])

    def test_the_synthesis_carries_the_four_figures_that_matter(self) -> None:
        html = render_demo_day_report_html(_report())
        head = html[: html.index(LABELS["detail"])]

        for expected in ("12", "17", "0,42", "50"):
            assert expected in head, f"{expected!r} absent de la synthese"


class TestTheFiguresAreReadableByAHuman:
    def test_large_counts_are_grouped(self) -> None:
        html = render_demo_day_report_html(_report(tokens_in=412_000))

        # Narrow no-break space: 412 000, never 412000.
        assert "412 000" in html

    def test_the_cost_is_shown_in_euros_with_two_decimals(self) -> None:
        html = render_demo_day_report_html(_report(cost_eur=Decimal("0.4231")))

        assert "0,42" in html and "€" in html

    def test_a_ceiling_is_shown_next_to_what_it_bounds(self) -> None:
        """A figure without its ceiling cannot be judged."""
        html = render_demo_day_report_html(
            _report(cost_eur=Decimal("0.90"), budget_eur=Decimal("1.00"))
        )

        assert "0,90" in html and "1,00" in html

    def test_an_absent_ceiling_is_stated_rather_than_shown_as_zero(self) -> None:
        html = render_demo_day_report_html(_report(budget_eur=None, signup_limit=None))

        assert LABELS["no_limit"] in html
        assert "0,00 €" not in html.split(LABELS["detail"])[0]


class TestTheReportSaysWhenSomethingDeservesAttention:
    def test_a_ceiling_nearly_reached_is_flagged(self) -> None:
        html = render_demo_day_report_html(
            _report(cost_eur=Decimal("0.95"), budget_eur=Decimal("1.00"))
        )

        assert LABELS["alert_budget"] in html

    def test_a_quiet_day_is_stated_explicitly(self) -> None:
        """Always sent, so a page of zeros must read as 'nothing happened'
        rather than as a broken collector."""
        html = render_demo_day_report_html(
            _report(
                visitors=0,
                verified=0,
                signups=0,
                conversations=0,
                user_messages=0,
                assistant_messages=0,
                tokens_in=0,
                tokens_out=0,
                tokens_cached=0,
                runs=0,
                cost_eur=Decimal("0"),
            )
        )

        assert LABELS["quiet_day"] in html

    def test_an_ordinary_day_is_not_flagged(self) -> None:
        html = render_demo_day_report_html(_report())

        assert LABELS["alert_budget"] not in html
        assert LABELS["quiet_day"] not in html


class TestTheHtmlIsSelfContainedAndSafe:
    def test_it_carries_its_own_styling_inline(self) -> None:
        """Mail clients drop <style> blocks and every external asset."""
        html = render_demo_day_report_html(_report())

        assert "style=" in html
        assert "<link" not in html and "<script" not in html

    def test_it_names_the_instance_and_the_day(self) -> None:
        html = render_demo_day_report_html(_report())

        assert "07/08/2026" in html


class TestTheJobNeverBreaksTheInstance:
    async def test_it_does_nothing_outside_demo_mode(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "demo_mode_enabled", False, raising=False)

        with patch("src.infrastructure.scheduler.demo_daily_report._send", new=AsyncMock()) as send:
            await run_demo_daily_report()

        send.assert_not_awaited()

    async def test_it_does_nothing_without_a_recipient(self, monkeypatch) -> None:
        """A report with nowhere to go is not an error, it is a choice."""
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        monkeypatch.setattr(settings, "demo_daily_report_recipient", "", raising=False)

        with patch("src.infrastructure.scheduler.demo_daily_report._send", new=AsyncMock()) as send:
            await run_demo_daily_report()

        send.assert_not_awaited()

    async def test_a_failure_is_logged_not_raised(self, monkeypatch) -> None:
        """It runs minutes before the purge; an exception here must never take
        the scheduler — and therefore the purge — down with it."""
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        monkeypatch.setattr(settings, "demo_daily_report_recipient", "ops@client.fr", raising=False)

        with patch(
            "src.infrastructure.scheduler.demo_daily_report._collect",
            new=AsyncMock(side_effect=RuntimeError("base indisponible")),
        ):
            await run_demo_daily_report()  # must not raise


class TestTheReportRunsBeforeThePurge:
    """The coupling that silently empties the report of all meaning.

    The database dies with the tmpfs at the purge. A report scheduled at or
    after that moment counts nothing and says so with total confidence.
    """

    def test_the_configured_time_precedes_the_purge(self) -> None:
        report = settings.demo_daily_report_hour * 60 + settings.demo_daily_report_minute
        purge = settings.demo_account_purge_hour * 60 + settings.demo_account_purge_minute

        assert report < purge, (
            f"le rapport est programme a {report // 60:02d}:{report % 60:02d} et la purge "
            f"a {purge // 60:02d}:{purge % 60:02d} — il compterait une base deja vide"
        )

    def test_it_leaves_room_for_the_collection_to_finish(self) -> None:
        report = settings.demo_daily_report_hour * 60 + settings.demo_daily_report_minute
        purge = settings.demo_account_purge_hour * 60 + settings.demo_account_purge_minute

        assert purge - report >= 10, (
            "moins de dix minutes entre le rapport et la purge : une collecte "
            "lente serait interrompue par la suppression de ce qu'elle lit"
        )
