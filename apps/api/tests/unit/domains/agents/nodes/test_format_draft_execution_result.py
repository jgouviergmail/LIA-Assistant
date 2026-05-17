"""Unit tests for ``_format_draft_execution_result`` post-HITL renderer.

Covers the full matrix of execution outcomes for every ``DraftType``:

- Single confirm: success / cancelled / error
- Batch confirm: success / partial_error / empty
- Edge cases: unknown draft type, missing fields, nested label resolution,
  per-language header composition.

These tests focus on the markdown text that ends up in the chat (the LLM
fast-path uses the returned string verbatim when a draft confirmation closes
the turn — see response_node.py:2680 area).
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.models import DraftAction, DraftType
from src.domains.agents.nodes.response_node import _format_draft_execution_result

# =============================================================================
# Helpers — minimal payload builders
# =============================================================================


def _single_success(draft_type: DraftType, *, draft_content: dict, message: str = "") -> dict:
    """Build a single-confirm success payload."""
    return {
        "status": "success",
        "message": message or f"{draft_type.value} executed",
        "draft_type": draft_type.value,
        "action": DraftAction.CONFIRM.value,
        "data": {"_draft_content": draft_content},
    }


def _batch_success(draft_type: DraftType, *, items: list[dict], lang: str = "fr") -> dict:
    """Build a batch-confirm full-success payload."""
    batch_results = [
        {
            "status": "success",
            "message": "ok",
            "data": {"_draft_content": {**item, "user_language": lang}},
        }
        for item in items
    ]
    return {
        "status": "success",
        "message": "batch ok",
        "draft_type": draft_type.value,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {
            "batch_results": batch_results,
            "success_count": len(items),
            "total_count": len(items),
        },
    }


def _batch_partial(
    draft_type: DraftType, *, items: list[tuple[dict, str]], lang: str = "fr"
) -> dict:
    """Build a batch-confirm partial-error payload.

    ``items`` is a list of ``(draft_content, status)`` tuples where ``status``
    is either ``"success"`` or ``"error"``.
    """
    batch_results = [
        {
            "status": st,
            "message": "ok" if st == "success" else "boom",
            "data": {"_draft_content": {**content, "user_language": lang}},
        }
        for (content, st) in items
    ]
    return {
        "status": "partial_error",
        "message": "partial",
        "draft_type": draft_type.value,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {
            "batch_results": batch_results,
            "success_count": sum(1 for (_, st) in items if st == "success"),
            "total_count": len(items),
        },
    }


# =============================================================================
# Empty / unknown input
# =============================================================================


def test_format_empty_input_returns_empty_string() -> None:
    """Empty input is rendered as an empty string."""
    assert _format_draft_execution_result(None) == ""
    assert _format_draft_execution_result({}) == ""


def test_format_unknown_draft_type_does_not_crash() -> None:
    """An unknown draft type still produces a sensible (empty-emoji) output."""
    result = {
        "status": "success",
        "message": "Did the thing",
        "draft_type": "totally_unknown",
        "action": DraftAction.CONFIRM.value,
        "data": {"_draft_content": {}},
    }
    rendered = _format_draft_execution_result(result)
    assert "✅" in rendered
    assert "Did the thing" in rendered


# =============================================================================
# Single confirm — REMINDER_DELETE (the originally-broken case)
# =============================================================================


def test_single_reminder_delete_renders_content_and_trigger() -> None:
    """Single reminder deletion shows the content + trigger_at."""
    result = _single_success(
        DraftType.REMINDER_DELETE,
        draft_content={
            "content": "Faire les courses",
            "trigger_at": "2026-05-16T14:00:00+00:00",
            "user_language": "fr",
            "user_timezone": "Europe/Paris",
        },
        message="Rappel annulé : Faire les courses",
    )
    rendered = _format_draft_execution_result(result)

    assert "🔔" in rendered, "Reminder emoji must appear in header"
    assert "Rappel annulé" in rendered
    assert "Faire les courses" in rendered
    # The detail line must include the localized French date.
    assert "mai" in rendered.lower()


# =============================================================================
# Batch confirm — REMINDER_DELETE (regression: was "Action exécutée avec succès" ×N)
# =============================================================================


def test_batch_reminder_delete_french_full_success() -> None:
    """3 reminders deleted in French — full success with localized header."""
    result = _batch_success(
        DraftType.REMINDER_DELETE,
        items=[
            {
                "content": "Faire les courses",
                "trigger_at": "2026-05-16T14:00:00+00:00",
                "user_timezone": "Europe/Paris",
            },
            {
                "content": "Appeler Maman",
                "trigger_at": "2026-05-17T09:00:00+00:00",
                "user_timezone": "Europe/Paris",
            },
            {
                "content": "Rendez-vous médecin",
                "trigger_at": "2026-05-18T11:00:00+00:00",
                "user_timezone": "Europe/Paris",
            },
        ],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    # Localized header: "3 rappels supprimés"
    assert "3 rappels supprimés" in rendered
    assert "🔔" in rendered
    # Each row uses the content label, not "Action exécutée avec succès".
    assert "**Faire les courses**" in rendered
    assert "**Appeler Maman**" in rendered
    assert "**Rendez-vous médecin**" in rendered
    # Regression guard: the bland default must NOT appear anymore.
    assert "Action exécutée avec succès" not in rendered


def test_batch_reminder_delete_english_full_success() -> None:
    """3 reminders deleted in English — header & rows correct."""
    result = _batch_success(
        DraftType.REMINDER_DELETE,
        items=[
            {"content": "Buy groceries", "user_timezone": "UTC"},
            {"content": "Call Mom", "user_timezone": "UTC"},
            {"content": "Doctor appointment", "user_timezone": "UTC"},
        ],
        lang="en",
    )
    rendered = _format_draft_execution_result(result)

    assert "3 reminders deleted" in rendered
    assert "**Buy groceries**" in rendered
    assert "**Call Mom**" in rendered


@pytest.mark.parametrize(
    "language,expected_header",
    [
        ("fr", "3 rappels supprimés"),
        ("en", "3 reminders deleted"),
        ("es", "3 recordatorios eliminados"),
        ("de", "3 Erinnerungen gelöscht"),
        ("it", "3 promemoria eliminati"),
        ("zh-CN", "已删除 3 个提醒"),
    ],
)
def test_batch_reminder_delete_header_per_language(language: str, expected_header: str) -> None:
    """The batch header is grammatically correct in every supported language."""
    result = _batch_success(
        DraftType.REMINDER_DELETE,
        items=[
            {"content": "a", "user_timezone": "UTC"},
            {"content": "b", "user_timezone": "UTC"},
            {"content": "c", "user_timezone": "UTC"},
        ],
        lang=language,
    )
    rendered = _format_draft_execution_result(result)
    assert expected_header in rendered


def test_batch_reminder_delete_partial_error_uses_warning_emoji() -> None:
    """A partial-error batch shows ⚠️ and a ``X/Y`` style count."""
    result = _batch_partial(
        DraftType.REMINDER_DELETE,
        items=[
            ({"content": "ok", "user_timezone": "UTC"}, "success"),
            ({"content": "ok2", "user_timezone": "UTC"}, "success"),
            ({"content": "boom", "user_timezone": "UTC"}, "error"),
        ],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    assert "⚠️" in rendered
    # Partial result: "2/3 rappels supprimés" — agreement on total.
    assert "2/3 rappels supprimés" in rendered
    # One row should carry the failure marker.
    assert "❌" in rendered


def test_batch_reminder_delete_french_singular_one() -> None:
    """A 1-item batch in French renders as singular ("1 rappel supprimé")."""
    result = _batch_success(
        DraftType.REMINDER_DELETE,
        items=[{"content": "Solo", "user_timezone": "UTC"}],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)
    assert "1 rappel supprimé" in rendered, rendered


# =============================================================================
# Batch confirm — other DraftTypes (smoke + grammar checks)
# =============================================================================


def test_batch_email_delete_french_feminine_no_agreement() -> None:
    """Email is masculine in French — verb stays ``supprimé(s)``."""
    result = _batch_success(
        DraftType.EMAIL_DELETE,
        items=[{"subject": "Hi"}, {"subject": "Hello"}],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    assert "2 emails supprimés" in rendered
    assert "**Hi**" in rendered and "**Hello**" in rendered


def test_batch_task_create_french_feminine_agreement() -> None:
    """Task is feminine in French — verb agrees as ``créée``/``créées``."""
    result = _batch_success(
        DraftType.TASK,
        items=[{"title": "Préparer démo"}, {"title": "Réserver salle"}],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    assert "2 tâches créées" in rendered
    assert "**Préparer démo**" in rendered


def test_batch_event_delete_extracts_summary_and_datetime() -> None:
    """Event batch rows include the start_datetime as secondary context."""
    result = _batch_success(
        DraftType.EVENT_DELETE,
        items=[
            {
                "summary": "Réunion équipe",
                "start_datetime": "2026-05-20T10:00:00+02:00",
                "user_timezone": "Europe/Paris",
            },
        ],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    assert "**Réunion équipe**" in rendered
    # Secondary datetime appears after an em-dash.
    assert " — " in rendered


def test_batch_file_delete_resolves_nested_file_name() -> None:
    """File delete uses the nested ``file.name`` field as item label."""
    result = _batch_success(
        DraftType.FILE_DELETE,
        items=[{"file": {"name": "report.pdf", "mimeType": "application/pdf"}}],
        lang="fr",
    )
    rendered = _format_draft_execution_result(result)

    assert "**report.pdf**" in rendered
    assert "1 fichier supprimé" in rendered  # French: 0/1 → singular


# =============================================================================
# Cancel / error paths
# =============================================================================


def test_single_cancelled_renders_strike_emoji() -> None:
    """Cancelled drafts get the 🚫 marker."""
    result = {
        "status": "cancelled",
        "message": "Suppression annulée",
        "draft_type": DraftType.REMINDER_DELETE.value,
        "action": DraftAction.CANCEL.value,
        "data": {},
    }
    rendered = _format_draft_execution_result(result)

    assert "🚫" in rendered
    assert "Suppression annulée" in rendered


def test_single_error_renders_cross_emoji() -> None:
    """Failed single drafts get the ❌ marker."""
    result = {
        "status": "error",
        "message": "Something broke",
        "draft_type": DraftType.EMAIL.value,
        "data": {},
    }
    rendered = _format_draft_execution_result(result)

    assert "❌" in rendered
    assert "Something broke" in rendered
