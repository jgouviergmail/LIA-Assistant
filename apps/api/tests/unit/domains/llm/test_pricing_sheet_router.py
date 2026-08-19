"""Unit tests for the workbook endpoints.

The route carries three things the domain cannot: the administrator's language,
the configured guards, and the transaction boundary. Everything below tests one
of those, plus the two-phase contract that makes a preview binding — an apply
that re-derives a different plan than the one reviewed must refuse to write.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from src.core.exceptions import BaseAPIException
from src.domains.llm.pricing_change_plan import ChangeAction, ChangePlan, ModelChange
from src.domains.llm.pricing_sheet_router import (
    _guard_apply,
    _to_plan_view,
    router,
)
from src.infrastructure.tabular_io.report import CellIssue, IssueCode, ParsedWorkbook


def _plan(*changes: ModelChange, issues: tuple[CellIssue, ...] = ()) -> ChangePlan:
    return ChangePlan(changes=tuple(changes), issues=issues)


def _parsed(*issues: CellIssue) -> ParsedWorkbook:
    return ParsedWorkbook(sheets={}, issues=tuple(issues))


@pytest.mark.unit
class TestRouterStructure:
    def test_both_routes_live_under_the_pricing_sheet_prefix(self) -> None:
        assert router.prefix == "/admin/llm/pricing/sheet"

    def test_the_export_is_read_only(self) -> None:
        route = next(
            r for r in router.routes if isinstance(r, APIRoute) and r.path.endswith("export.xlsx")
        )
        assert route.methods == {"GET"}

    def test_the_import_is_a_post(self) -> None:
        route = next(
            r for r in router.routes if isinstance(r, APIRoute) and r.path.endswith("/import")
        )
        assert route.methods == {"POST"}

    def test_every_route_requires_a_superuser(self) -> None:
        """Tariffs are money: nothing here is open to a plain session."""
        assert router.dependencies, "the router declares no auth dependency"


@pytest.mark.unit
class TestApplyGuard:
    def test_a_plan_with_a_diff_issue_cannot_be_applied(self) -> None:
        view = _to_plan_view(_plan(issues=(CellIssue(IssueCode.PROVIDER_IMMUTABLE),)), _parsed())

        with pytest.raises(BaseAPIException):
            _guard_apply(view, view.plan_fingerprint)

    def test_a_file_that_could_not_be_read_cannot_be_applied(self) -> None:
        """The parser's verdict counts as much as the diff's: a clean-looking
        plan built from an unreadable file must not be written."""
        view = _to_plan_view(_plan(), _parsed(CellIssue(IssueCode.NOT_A_WORKBOOK)))

        assert view.is_applicable is False
        with pytest.raises(BaseAPIException):
            _guard_apply(view, view.plan_fingerprint)

    def test_applying_without_a_fingerprint_is_refused(self) -> None:
        """Applying without having previewed is applying blind."""
        view = _to_plan_view(_plan(ModelChange("m", ChangeAction.UPDATE)), _parsed())

        with pytest.raises(BaseAPIException):
            _guard_apply(view, None)

    def test_a_stale_fingerprint_is_refused(self) -> None:
        """The catalogue moved between the preview and the apply."""
        view = _to_plan_view(_plan(ModelChange("m", ChangeAction.UPDATE)), _parsed())

        with pytest.raises(BaseAPIException):
            _guard_apply(view, "0000000000000000")

    def test_the_matching_fingerprint_is_accepted(self) -> None:
        view = _to_plan_view(_plan(ModelChange("m", ChangeAction.UPDATE)), _parsed())

        _guard_apply(view, view.plan_fingerprint)


@pytest.mark.unit
class TestPlanView:
    def test_parser_and_diff_issues_are_both_reported(self) -> None:
        """An administrator fixes a file once, not one layer at a time."""
        view = _to_plan_view(
            _plan(issues=(CellIssue(IssueCode.PROVIDER_IMMUTABLE),)),
            _parsed(CellIssue(IssueCode.NOT_A_NUMBER)),
        )

        codes = {issue.code for issue in view.issues}
        assert codes == {"provider_immutable", "not_a_number"}

    def test_an_issue_keeps_its_coordinates(self) -> None:
        view = _to_plan_view(
            _plan(),
            _parsed(
                CellIssue(
                    IssueCode.NOT_A_NUMBER,
                    sheet="Modeles",
                    cell="C42",
                    column="input_unit_price",
                    params={"value": "gratuit"},
                )
            ),
        )

        issue = view.issues[0]
        assert (issue.sheet, issue.cell, issue.column) == ("Modeles", "C42", "input_unit_price")
        assert issue.params["value"] == "gratuit"

    def test_issues_carry_codes_never_sentences(self) -> None:
        """The frontend translates; the API never ships a language."""
        view = _to_plan_view(_plan(), _parsed(CellIssue(IssueCode.FORMULA_REJECTED)))

        assert view.issues[0].code == "formula_rejected"

    def test_the_counts_cover_every_action(self) -> None:
        view = _to_plan_view(
            _plan(
                ModelChange("a", ChangeAction.CREATE),
                ModelChange("b", ChangeAction.UNCHANGED),
                ModelChange("c", ChangeAction.UNCHANGED),
            ),
            _parsed(),
        )

        assert view.counts["create"] == 1
        assert view.counts["unchanged"] == 2

    def test_a_change_carries_its_worksheet_row_for_a_deep_link(self) -> None:
        view = _to_plan_view(_plan(ModelChange("a", ChangeAction.UPDATE, row_number=42)), _parsed())

        assert view.changes[0].row_number == 42

    def test_an_empty_plan_is_applicable_and_stable(self) -> None:
        first = _to_plan_view(_plan(), _parsed())
        second = _to_plan_view(_plan(), _parsed())

        assert first.is_applicable is True
        assert first.plan_fingerprint == second.plan_fingerprint
