"""Tests for ``format_hitl_item_preview`` — unified HITL item preview renderer.

Verifies that both HITL paths (DraftCritiqueInteraction batch +
ForEachConfirmationInteraction item previews) now share a single rendering
function that emits the same structured format::

    {emoji} {Noun} : {label} - {date_with_day_name}

Covers:
- The originally-reported bug: ``reminder_delete`` no longer renders as
  ``🔔 Médecin\n  🔔 dimanche ...`` (duplicate emoji on two lines), but as
  ``🔔 Rappel : Médecin - dimanche ...`` (single line, single emoji).
- Per-language correctness: capitalized noun, localized date with day name.
- Per-draft-type coverage: every ``DraftType`` produces a sensible row.
- Edge cases: missing label, missing datetime, unknown draft type, nested
  field resolution (e.g. ``file.name``).
"""

from __future__ import annotations

import pytest

from src.core.i18n_drafts import format_hitl_item_preview
from src.domains.agents.drafts.models import DraftType

ALL_LANGUAGES: tuple[str, ...] = ("fr", "en", "es", "de", "it", "zh-CN")


# =============================================================================
# Regression — the originally-broken case
# =============================================================================


def test_reminder_delete_no_duplicate_emoji_and_localized_noun() -> None:
    """Reminder rows show one emoji, the capitalized noun, the label, and the date."""
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={
            "content": "Médecin",
            "trigger_at": "2026-05-17T19:00:00+02:00",
        },
        language="fr",
        user_timezone="Europe/Paris",
    )

    assert row is not None
    assert row.count("🔔") == 1, f"Expected exactly 1 reminder emoji, got: {row}"
    assert row.startswith("🔔 Rappel : Médecin"), row
    assert " - " in row, "Dash separator missing"
    assert "mai" in row.lower(), "Localized month should appear"


def test_reminder_delete_includes_weekday_name_in_french() -> None:
    """Date in fr includes the weekday name (dimanche, lundi, ...)."""
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={
            "content": "Médecin",
            "trigger_at": "2026-05-17T19:00:00+02:00",  # a Sunday
        },
        language="fr",
        user_timezone="Europe/Paris",
    )

    assert row is not None
    # Sunday in French is "dimanche" — the localizer should include it.
    assert "dimanche" in row.lower(), row


# =============================================================================
# Per-language correctness
# =============================================================================


@pytest.mark.parametrize(
    "language,expected_noun",
    [
        ("fr", "Rappel"),
        ("en", "Reminder"),
        ("es", "Recordatorio"),
        ("de", "Erinnerung"),
        ("it", "Promemoria"),
        ("zh-CN", "提醒"),  # Chinese has no case; just the noun.
    ],
)
def test_reminder_noun_capitalized_per_language(language: str, expected_noun: str) -> None:
    """The localized noun is properly capitalized and present in the row."""
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={"content": "Médecin"},
        language=language,
    )
    assert row is not None
    assert expected_noun in row, row


# =============================================================================
# Other draft types
# =============================================================================


def test_email_delete_uses_subject_as_label() -> None:
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL_DELETE.value,
        content={
            "subject": "Confirmation rdv",
            "date": "2026-05-16T14:00:00+02:00",
        },
        language="fr",
        user_timezone="Europe/Paris",
    )
    assert row is not None
    assert "📧" in row  # email_delete uses 🗑️📧 composite, still contains 📧
    assert "Email : Confirmation rdv" in row, row
    assert " - " in row


def test_event_delete_uses_summary_and_start_datetime() -> None:
    row = format_hitl_item_preview(
        draft_type=DraftType.EVENT_DELETE.value,
        content={
            "summary": "Réunion équipe",
            "start_datetime": "2026-05-20T10:00:00+02:00",
        },
        language="fr",
        user_timezone="Europe/Paris",
    )
    assert row is not None
    assert "Événement : Réunion équipe" in row
    assert " - " in row


def test_contact_create_no_secondary_datetime() -> None:
    """Contact creation has no secondary datetime → row without trailing date."""
    row = format_hitl_item_preview(
        draft_type=DraftType.CONTACT.value,
        content={"name": "Marie Dupont"},
        language="fr",
    )
    assert row is not None
    assert "Contact : Marie Dupont" in row
    assert " - " not in row, "No datetime field → no dash separator"


def test_task_create_uses_title_and_due() -> None:
    row = format_hitl_item_preview(
        draft_type=DraftType.TASK.value,
        content={
            "title": "Préparer démo",
            "due": "2026-05-20T17:00:00+02:00",
        },
        language="fr",
        user_timezone="Europe/Paris",
    )
    assert row is not None
    assert "Tâche : Préparer démo" in row
    assert " - " in row


def test_file_delete_resolves_nested_name() -> None:
    """``file.name`` dotted key resolves through nested dict."""
    row = format_hitl_item_preview(
        draft_type=DraftType.FILE_DELETE.value,
        content={"file": {"name": "report.pdf"}},
        language="fr",
    )
    assert row is not None
    assert "Fichier : report.pdf" in row


def test_label_delete_uses_label_name() -> None:
    row = format_hitl_item_preview(
        draft_type=DraftType.LABEL_DELETE.value,
        content={"label_name": "pro/clients"},
        language="fr",
    )
    assert row is not None
    assert "Label : pro/clients" in row


# =============================================================================
# Recipient prefix — send-type drafts (email / reply / forward)
# =============================================================================
# The critical HITL bug: a batch email confirmation must show WHO each email
# goes to, otherwise two rows with the same subject are indistinguishable.


def test_email_send_shows_recipient_and_subject() -> None:
    """A send email row shows "Email à {to} : {subject}" (recipient + subject)."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": "matheo@example.com", "subject": "Je t'aime"},
        language="fr",
    )
    assert row is not None
    assert row.startswith("📧 Email à matheo@example.com : Je t'aime"), row


def test_email_send_two_recipients_are_distinguishable() -> None:
    """Two emails with the same subject render as DISTINCT rows (the bug's core)."""
    matheo = format_hitl_item_preview(
        DraftType.EMAIL.value, {"to": "matheo@example.com", "subject": "Je t'aime"}, language="fr"
    )
    hua = format_hitl_item_preview(
        DraftType.EMAIL.value, {"to": "hua@example.com", "subject": "Je t'aime"}, language="fr"
    )
    assert matheo != hua, "Rows must differ by recipient"
    assert "matheo@example.com" in (matheo or "")
    assert "hua@example.com" in (hua or "")


@pytest.mark.parametrize(
    "language,connector",
    [("fr", "à"), ("en", "to"), ("es", "a"), ("de", "an"), ("it", "a"), ("zh-CN", "给")],
)
def test_email_send_recipient_connector_per_language(language: str, connector: str) -> None:
    """The recipient is introduced by the correct localized connector."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": "marie@example.com", "subject": "Sujet"},
        language=language,
    )
    assert row is not None
    assert f"{connector} marie@example.com" in row, row


def test_email_send_recipient_as_list_is_joined() -> None:
    """A list ``to`` is joined with commas, not rendered as a Python list repr."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": ["a@example.com", "b@example.com"], "subject": "Sujet"},
        language="fr",
    )
    assert row is not None
    assert "a@example.com, b@example.com" in row, row
    assert "[" not in row and "]" not in row


def test_email_send_without_recipient_falls_back_to_noun_label() -> None:
    """No ``to`` field → plain "Email : {subject}" with no dangling connector."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"subject": "Sujet seul"},
        language="fr",
    )
    assert row is not None
    assert row.startswith("📧 Email : Sujet seul"), row
    assert " à " not in row, "No recipient → no connector"


@pytest.mark.parametrize("draft_type", [DraftType.EMAIL_REPLY, DraftType.EMAIL_FORWARD])
def test_email_reply_forward_show_recipient(draft_type: DraftType) -> None:
    """Reply and forward drafts also surface the recipient."""
    row = format_hitl_item_preview(
        draft_type=draft_type.value,
        content={"to": "contact@example.com", "subject": "Re: Sujet"},
        language="fr",
    )
    assert row is not None
    assert "à contact@example.com" in row, row


def test_email_delete_ignores_recipient_field() -> None:
    """email_delete has no recipient prefix even if a ``to`` is present."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL_DELETE.value,
        content={"to": "someone@example.com", "subject": "Facture", "date": None},
        language="fr",
    )
    assert row is not None
    assert "someone@example.com" not in row, row
    assert "Email : Facture" in row, row


# =============================================================================
# Edge cases
# =============================================================================


def test_unknown_draft_type_returns_none() -> None:
    """Unknown draft types return None so the caller can fall back."""
    assert format_hitl_item_preview("not_a_draft_type", {}, language="fr") is None
    assert format_hitl_item_preview("", {}, language="fr") is None


def test_missing_label_yields_noun_only() -> None:
    """When the label fields are empty, the row still shows emoji + noun."""
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={},  # no content, no trigger_at
        language="fr",
    )
    assert row is not None
    assert "🔔" in row
    assert "Rappel" in row
    # No " - " when no date is provided.
    assert " - " not in row


def test_label_whitespace_is_sanitized() -> None:
    """Newlines and tabs in the label are collapsed to single spaces."""
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={"content": "Médecin\n\trappel important"},
        language="fr",
    )
    assert row is not None
    assert "\n" not in row
    assert "\t" not in row
    # Multiple spaces collapsed.
    assert "Médecin rappel important" in row


@pytest.mark.parametrize("language", ALL_LANGUAGES)
@pytest.mark.parametrize("draft_type", list(DraftType))
def test_every_draft_type_yields_non_empty_row_in_every_language(
    language: str, draft_type: DraftType
) -> None:
    """Smoke test: with a generic content dict, every type produces a non-empty row."""
    content = {
        "content": "Sample",
        "subject": "Sample subject",
        "summary": "Sample summary",
        "title": "Sample title",
        "name": "Sample name",
        "label_name": "sample/label",
        "file": {"name": "sample.pdf"},
        "trigger_at": "2026-05-17T10:00:00+00:00",
        "start_datetime": "2026-05-17T10:00:00+00:00",
        "due": "2026-05-17T10:00:00+00:00",
        "date": "2026-05-17T10:00:00+00:00",
    }
    row = format_hitl_item_preview(
        draft_type=draft_type.value,
        content=content,
        language=language,
    )
    assert row is not None and row.strip(), f"Empty row for {draft_type.value} in {language}"
