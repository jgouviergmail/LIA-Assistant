"""The read-only catalogue verdict: one computation, three readers.

The CLI, the admin endpoint and these tests all go through ``status_from_rows``.
Before it existed, the CLI carried its own copy of the retirement rendering,
and the screen carried none at all — so the only way to know what the vendored
registries said about a deployment was to run a script on the host.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.infrastructure.llm.catalogue.status import (
    RETIREMENT_STATES,
    status_from_rows,
)
from src.infrastructure.llm.catalogue.sync_diff import CatalogueRow

pytestmark = pytest.mark.unit

#: A date far enough back that nothing in the snapshot has retired yet, and one
#: far enough forward that the announced ones have. Injected rather than "now":
#: the rule reads a published date, so a test that drifts with the clock would
#: start reporting differently in October without a line of code changing.
BEFORE_THE_WAVE = date(2026, 1, 1)
AFTER_THE_WAVE = date(2027, 1, 1)


def _row(model_name: str, provider: str = "openai", **overrides: object) -> CatalogueRow:
    base: dict[str, object] = {
        "model_name": model_name,
        "provider": provider,
        "kind": "chat",
        "max_input_tokens": 8192,
        "max_output_tokens": 4096,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_vision": False,
        "provenance": "declared",
        "deprecation_date": None,
        "is_active": True,
    }
    base.update(overrides)
    return CatalogueRow(**base)  # type: ignore[arg-type]


def test_it_counts_the_rows_it_examined() -> None:
    status = status_from_rows([_row("gpt-5.2"), _row("gpt-4.1")], today=BEFORE_THE_WAVE)
    assert status.compared == 2


def test_it_breaks_the_provenance_down() -> None:
    """The one number that says how much of the catalogue was ever measured."""
    rows = [
        _row("gpt-5.2", provenance="imported"),
        _row("gpt-4.1", provenance="imported"),
        _row("gpt-4o", provenance="declared"),
        _row("o3", provenance="verified"),
    ]
    status = status_from_rows(rows, today=BEFORE_THE_WAVE)
    assert status.provenance == {"imported": 2, "declared": 1, "verified": 1}


def test_a_declared_row_that_disagrees_with_the_registry_counts_as_auto() -> None:
    """No human curated it, so correcting it arbitrates nothing."""
    stale = _row("gpt-5.2", max_input_tokens=8192, provenance="declared")
    status = status_from_rows([stale], today=BEFORE_THE_WAVE)
    assert status.auto >= 1
    assert status.review == 0


def test_a_curated_row_that_disagrees_counts_as_review() -> None:
    """A human filled it: the registry may propose, never overwrite."""
    curated = _row("gpt-5.2", max_input_tokens=8192, provenance="verified")
    status = status_from_rows([curated], today=BEFORE_THE_WAVE)
    assert status.review >= 1
    assert status.auto == 0


def test_a_model_the_registries_do_not_know_is_simply_absent() -> None:
    """Absence of evidence is never a correction to propose."""
    status = status_from_rows([_row("some-private-build")], today=BEFORE_THE_WAVE)
    assert status.auto == 0
    assert status.review == 0
    assert status.retiring == ()


def test_it_reports_the_announced_retirements_with_their_evidence() -> None:
    status = status_from_rows([_row("gpt-4.1-nano")], today=BEFORE_THE_WAVE)
    assert len(status.retiring) == 1
    entry = status.retiring[0]
    assert entry.model_name == "gpt-4.1-nano"
    assert entry.state in RETIREMENT_STATES
    assert entry.seen_by, "a retirement with no source is not evidence"


def test_the_state_follows_the_reference_date() -> None:
    """Announced today, retired once the date has passed — same row, same rule."""
    announced = status_from_rows([_row("gpt-4.1-nano")], today=BEFORE_THE_WAVE).retiring[0]
    later = status_from_rows([_row("gpt-4.1-nano")], today=AFTER_THE_WAVE).retiring[0]
    assert announced.state == "announced"
    assert later.state == "retired"


def test_retirements_are_sorted_so_the_screen_is_stable() -> None:
    rows = [_row("o3-mini"), _row("gpt-4.1-nano"), _row("o1")]
    names = [entry.model_name for entry in status_from_rows(rows, today=BEFORE_THE_WAVE).retiring]
    assert names == sorted(names)


def test_it_carries_the_snapshot_date() -> None:
    """Which registry snapshot produced this verdict is part of the verdict."""
    status = status_from_rows([_row("gpt-5.2")], today=BEFORE_THE_WAVE)
    assert status.snapshot_generated_at is not None


def test_an_empty_catalogue_reports_zeroes_rather_than_failing() -> None:
    status = status_from_rows([], today=BEFORE_THE_WAVE)
    assert (status.compared, status.auto, status.review) == (0, 0, 0)
    assert status.retiring == ()
    assert status.provenance == {}
