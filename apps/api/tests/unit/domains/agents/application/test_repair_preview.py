"""A valid correction can show an invalid legacy value without hiding its effect."""

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.drafts.card_spec import Row
from tests.unit.domains.agents.application.test_native_draft import content

pytestmark = pytest.mark.unit


def test_explicit_font_repair_presents_the_actual_out_of_range_saved_value() -> None:
    proposal = {**content(), "before": {"font_size": 26}}
    lines = render_application_preview(
        proposal, get_draft_preview_labels("en"), lambda value: value or ""
    )
    assert isinstance(lines[0], Row)
    assert lines[0].value == "Before: 26 → After: 17"
