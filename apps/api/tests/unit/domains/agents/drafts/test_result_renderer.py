"""What a person reads once they confirmed: the execution result (ADR-276 lot 13).

Moved here from ``tests/unit/domains/agents/nodes/`` with the renderer itself:
this is a draft presentation surface, not a node concern, and the node that
used to own it is a frozen-size hotspot.

Two contracts, and the second one is why the module exists:

1. **What it says** — the outcome matrix for every ``DraftType``: single
   confirm (success / cancelled / error), batch confirm (success /
   partial_error), unknown types, nested label resolution, per-language header
   composition. Inherited verbatim from the previous test module.
2. **How it says it** — ONE vocabulary, Markdown, the same the confirmation
   card speaks. It used to open every field with ``<br/>`` AND join them with
   ``\\n``, which the chat renders as a blank line per field (measured on
   production 2026-09-09) and which any surface rendering no markup reads out
   as typed. The properties at the bottom of this module are what keeps that
   from coming back.

The chat fast path uses the returned string verbatim when a draft confirmation
closes the turn (``response_node`` — no LLM call), so this string IS the
message.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.models import DraftAction, DraftType
from src.domains.agents.drafts.result_renderer import render_execution_result

pytestmark = pytest.mark.unit


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
    assert render_execution_result(None) == ""
    assert render_execution_result({}) == ""


def test_format_unknown_status_returns_empty_string() -> None:
    """A status nobody declared says nothing rather than inventing a verdict."""
    assert render_execution_result({"status": "who_knows", "message": "x"}) == ""


def test_format_unknown_draft_type_does_not_crash() -> None:
    """An unknown draft type still produces a sensible (empty-emoji) output."""
    result = {
        "status": "success",
        "message": "Did the thing",
        "draft_type": "totally_unknown",
        "action": DraftAction.CONFIRM.value,
        "data": {"_draft_content": {}},
    }
    rendered = render_execution_result(result)
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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)
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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)
    assert "1 rappel supprimé" in rendered, rendered


def test_batch_with_no_results_still_names_the_outcome() -> None:
    """An empty batch says what happened rather than rendering a bare header."""
    result = {
        "status": "success",
        "message": "batch ok",
        "draft_type": DraftType.REMINDER_DELETE.value,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {"batch_results": [], "success_count": 0, "total_count": 0},
    }
    rendered = render_execution_result(result)
    assert rendered.strip() != ""
    assert "🔔" in rendered


# =============================================================================
# Batch confirm — other DraftTypes (smoke + grammar checks)
# =============================================================================


def test_batch_email_delete_french_masculine_agreement() -> None:
    """Email is masculine in French — verb stays ``supprimé(s)``."""
    result = _batch_success(
        DraftType.EMAIL_DELETE,
        items=[{"subject": "Hi"}, {"subject": "Hello"}],
        lang="fr",
    )
    rendered = render_execution_result(result)

    assert "2 emails supprimés" in rendered
    assert "**Hi**" in rendered and "**Hello**" in rendered


def test_batch_task_create_french_feminine_agreement() -> None:
    """Task is feminine in French — verb agrees as ``créée``/``créées``."""
    result = _batch_success(
        DraftType.TASK,
        items=[{"title": "Préparer démo"}, {"title": "Réserver salle"}],
        lang="fr",
    )
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)

    assert "**report.pdf**" in rendered
    assert "1 fichier supprimé" in rendered  # French: 0/1 → singular


def test_batch_row_without_a_resolvable_label_falls_back_to_its_message() -> None:
    """A row that names nothing still says something."""
    result = {
        "status": "success",
        "message": "batch ok",
        "draft_type": DraftType.REMINDER_DELETE.value,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {
            "batch_results": [
                {"status": "success", "message": "Fallback line", "data": {"_draft_content": {}}}
            ],
            "success_count": 1,
            "total_count": 1,
        },
    }
    rendered = render_execution_result(result)
    assert "Fallback line" in rendered


def test_batch_item_label_longer_than_the_cap_is_elided() -> None:
    """A 300-character title must not push the outcome off the screen."""
    result = _batch_success(
        DraftType.TASK,
        items=[{"title": "T" * 300}],
        lang="fr",
    )
    rendered = render_execution_result(result)
    assert "..." in rendered
    assert "T" * 300 not in rendered


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
    rendered = render_execution_result(result)

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
    rendered = render_execution_result(result)

    assert "❌" in rendered
    assert "Something broke" in rendered


def test_non_batch_partial_error_states_the_count() -> None:
    """The defensive non-batch partial branch keeps its ``X/Y``."""
    result = {
        "status": "partial_error",
        "message": "Half done",
        "draft_type": DraftType.EMAIL.value,
        "data": {"success_count": 1, "total_count": 3},
    }
    rendered = render_execution_result(result)
    assert "⚠️" in rendered
    assert "1/3" in rendered


# =============================================================================
# URL-valued detail fields (lot A, 2026-08: conference_link)
# =============================================================================


class TestUrlDetailFieldsRenderAsLinks:
    def test_conference_link_renders_as_markdown_link_not_raw_url(self) -> None:
        """A raw meet URL in the confirmation is unreadable — URL-valued detail
        fields must render as [label](url), like the html_link line does."""
        result = _single_success(
            DraftType.EVENT,
            draft_content={
                "summary": "Point avec Marc",
                "start_datetime": "2026-08-27T10:00:00",
                "end_datetime": "2026-08-27T10:30:00",
                "user_language": "fr",
            },
        )
        result["data"]["conference_link"] = "https://meet.google.com/abc-defg-hij"

        text = render_execution_result(result)

        assert "[Visioconférence](https://meet.google.com/abc-defg-hij)" in text
        assert "** : https://meet.google.com" not in text

    def test_html_link_renders_as_its_own_labelled_row(self) -> None:
        result = _single_success(
            DraftType.EVENT,
            draft_content={"summary": "X", "user_language": "en"},
        )
        result["data"]["html_link"] = "https://calendar.example.com/e/1"

        text = render_execution_result(result)
        assert "🔗 [Link](https://calendar.example.com/e/1)" in text


# =============================================================================
# THE FORM — one vocabulary, and it is Markdown (ADR-276 lot 13)
# =============================================================================


def _every_shape() -> list[str]:
    """One rendering of every branch, for the property assertions below."""
    return [
        render_execution_result(
            _single_success(
                DraftType.EMAIL,
                draft_content={
                    "to": ["paul@example.com", "marie@example.com"],
                    "subject": "Bonjour",
                    "body": "Un mot.",
                    "user_language": language,
                },
            )
        )
        for language in ("fr", "en", "es", "de", "it", "zh-CN")
    ] + [
        render_execution_result(
            _batch_success(
                DraftType.REMINDER_DELETE,
                items=[{"content": "a", "user_timezone": "UTC"}],
                lang="fr",
            )
        ),
        render_execution_result(
            _batch_partial(
                DraftType.TASK,
                items=[({"title": "a"}, "success"), ({"title": "b"}, "error")],
                lang="fr",
            )
        ),
        render_execution_result(
            {
                "status": "cancelled",
                "message": "Annulé",
                "draft_type": DraftType.EMAIL.value,
                "data": {},
            }
        ),
    ]


class TestTheFormIsMarkdownAndOnlyMarkdown:
    """The properties lot 13 established for the card, now true of the result."""

    def test_no_shape_ever_emits_a_hard_break(self) -> None:
        """``<br/>`` is what made every field sit two lines apart in the chat
        and what a ticket comment read out as typed."""
        for rendered in _every_shape():
            assert "<br" not in rendered, rendered

    def test_no_shape_opens_or_closes_on_whitespace(self) -> None:
        """The caller used to ``.strip()`` a leading ``\\n\\n`` back off; the
        renderer owns its own edges."""
        for rendered in _every_shape():
            assert rendered == rendered.strip(), repr(rendered)

    def test_the_header_is_followed_by_exactly_one_blank_line(self) -> None:
        for rendered in _every_shape():
            lines = rendered.split("\n")
            if len(lines) > 1:
                assert lines[1] == "", rendered

    def test_no_shape_leaves_a_blank_line_between_two_rows(self) -> None:
        """One field per line, no gaps — a list, not a stack of paragraphs."""
        for rendered in _every_shape():
            lines = rendered.split("\n")
            for index, line in enumerate(lines[:-1]):
                if line.startswith("- ") and lines[index + 1].startswith("- "):
                    continue
                assert not (line.startswith("- ") and lines[index + 1] == ""), rendered

    def test_every_detail_field_is_a_list_item(self) -> None:
        rendered = render_execution_result(
            _single_success(
                DraftType.EMAIL,
                draft_content={
                    "to": ["paul@example.com"],
                    "subject": "Bonjour",
                    "user_language": "fr",
                },
            )
        )
        body_lines = [line for line in rendered.split("\n")[2:] if line]
        assert body_lines, rendered
        assert all(line.startswith("- ") for line in body_lines), rendered


class TestTheHeaderNamesTheOutcome:
    def test_a_plain_message_is_emphasised(self) -> None:
        rendered = render_execution_result(
            _single_success(
                DraftType.TASK,
                draft_content={"title": "X", "user_language": "fr"},
                message="Tâche créée",
            )
        )
        assert rendered.startswith("✅ **Tâche créée**") or "✅ **Tâche créée**" in rendered

    def test_a_message_that_formats_itself_is_left_alone(self) -> None:
        """``phone_call`` ships its own emphasis; wrapping it in another pair
        produces ``**J'appelle **Marie** …**``, which renders as broken markup."""
        rendered = render_execution_result(
            _single_success(
                DraftType.PHONE_CALL,
                draft_content={"user_language": "fr"},
                message="J'appelle **Marie** maintenant.",
            )
        )
        assert "J'appelle **Marie** maintenant." in rendered
        assert "**J'appelle" not in rendered

    def test_a_missing_message_does_not_leave_an_empty_emphasis(self) -> None:
        rendered = render_execution_result(
            {
                "status": "success",
                "message": "",
                "draft_type": DraftType.TASK.value,
                "action": DraftAction.CONFIRM.value,
                "data": {"_draft_content": {"title": "X", "user_language": "fr"}},
            }
        )
        assert "****" not in rendered


class TestLongValuesAreBounded:
    @pytest.mark.parametrize("field", ["body"])
    def test_a_long_text_field_is_truncated_with_an_ellipsis(self, field: str) -> None:
        content = {
            "to": ["paul@example.com"],
            "subject": "S",
            field: "Z" * 500,
            "user_language": "fr",
        }
        rendered = render_execution_result(_single_success(DraftType.EMAIL, draft_content=content))
        assert "Z" * 500 not in rendered
        if "Z" in rendered:
            assert "…" in rendered


class TestATextValueLeavesTheList:
    """The rule the CARD already obeys, applied to the outcome (lot 13).

    An email body carries its own paragraphs. Folded into a list item, the
    second paragraph escapes the item and the list ends there — measured on a
    two-paragraph mail, which is most of them. The card renders such a value as
    its own block; the result must agree, or the same mail reads one way before
    confirmation and another after.
    """

    def _sent_mail(self, body: str, language: str = "fr") -> str:
        return render_execution_result(
            _single_success(
                DraftType.EMAIL,
                draft_content={
                    "to": ["paul@example.com"],
                    "subject": "Point de lundi",
                    "body": body,
                    "user_language": language,
                },
                message="Envoye",
            )
        )

    def test_a_multi_paragraph_body_becomes_its_own_block(self) -> None:
        rendered = self._sent_mail("Bonjour,\n\nOn se voit lundi.")
        assert "\n**" in rendered, rendered
        assert "- **" + chr(0x1F4AC) not in rendered, rendered

    def test_a_single_line_body_stays_a_row(self) -> None:
        """One line reads better inline than under a heading of its own."""
        rendered = self._sent_mail("On se voit lundi.")
        body_part = rendered.split("\n\n", 1)[1]
        assert "\n\n**" not in body_part, rendered

    def test_every_row_still_precedes_every_block(self) -> None:
        rendered = self._sent_mail("Bonjour,\n\nOn se voit lundi.")
        lines = rendered.split("\n")
        last_row = max(i for i, line in enumerate(lines) if line.startswith("- "))
        first_block = min(i for i, line in enumerate(lines) if line.startswith("**") and i > 0)
        assert last_row < first_block, rendered

    def test_the_block_keeps_the_paragraphs_of_the_message(self) -> None:
        rendered = self._sent_mail("Bonjour,\n\nOn se voit lundi.")
        assert "Bonjour,\n\nOn se voit lundi." in rendered

    def test_a_long_multi_paragraph_body_is_still_bounded(self) -> None:
        rendered = self._sent_mail("A\n\n" + "Z" * 500)
        assert "Z" * 500 not in rendered
        assert chr(0x2026) in rendered
