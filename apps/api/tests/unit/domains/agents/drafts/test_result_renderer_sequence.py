"""The result of a sequence names each draft by ITS type and says what was cancelled.

ADR-288: a sequence of independent drafts executes as one batch whose entries
may differ in type and in decision. Rendering every row with the first entry's
type labelled an event as an e-mail (probe 2026-09-16: « 📧 Email » with no
label at all), and a cancelled entry had no row to appear on.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.drafts.result_renderer import render_execution_result

pytestmark = pytest.mark.unit


def _row(status: str, draft_type: str, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "draft_id": f"d-{draft_type}",
        "draft_type": draft_type,
        "message": "ok" if status == "success" else "",
        "data": {"_draft_content": {**content, "user_language": "fr"}},
    }


def _result(draft_type: str, rows: list[dict[str, Any]], *, cancelled: int = 0) -> dict[str, Any]:
    attempted = [r for r in rows if r["status"] != "cancelled"]
    return {
        "status": "success",
        "message": "batch ok",
        "draft_type": draft_type,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {
            "batch_results": rows,
            "success_count": sum(1 for r in attempted if r["status"] == "success"),
            "error_count": 0,
            "cancelled_count": cancelled,
            "total_count": len(attempted),
        },
    }


class TestEachRowWearsItsOwnType:
    def test_an_event_in_an_email_batch_is_named_by_its_summary(self) -> None:
        rendered = render_execution_result(
            _result(
                "batch",
                [
                    _row("success", "email", {"subject": "All good", "to": "x@example.com"}),
                    _row(
                        "success",
                        "event",
                        {"summary": "Call Hua", "start_datetime": "2026-09-17T10:00:00+02:00"},
                    ),
                ],
            )
        )
        assert "**All good**" in rendered
        assert "**Call Hua**" in rendered

    def test_a_mixed_batch_is_headed_as_actions(self) -> None:
        rendered = render_execution_result(
            _result(
                "batch",
                [
                    _row("success", "email", {"subject": "All good"}),
                    _row("success", "event", {"summary": "Call Hua"}),
                ],
            )
        )
        first_line = rendered.splitlines()[0]
        assert "2 actions" in first_line
        assert "email" not in first_line.lower()


class TestACancelledEntryHasARow:
    def test_the_cancelled_draft_is_marked_and_the_other_counted(self) -> None:
        rendered = render_execution_result(
            _result(
                "email",
                [
                    _row("cancelled", "email", {"subject": "Not this one"}),
                    _row("success", "email", {"subject": "This one"}),
                ],
                cancelled=1,
            )
        )
        lines = rendered.splitlines()
        assert lines[0].startswith("📧 ✅")
        assert "1 email" in lines[0]
        assert any(line.startswith("- 🚫 **Not this one**") for line in lines)
        assert any(line.startswith("- ✅ **This one**") for line in lines)
