"""Tests for ``format_hitl_item_preview`` — unified HITL item preview renderer.

Verifies that both HITL paths (DraftCritiqueInteraction batch +
ForEachConfirmationInteraction item previews) now share a single rendering
function that emits the same structured format::

    {emoji} {Noun}{separator}{label} - {date_with_day_name}

The separator is the reader's (``label_separator``) — asserted below through the
door itself, since French puts a no-break space before its colon. A
row is Markdown whose values are drawn as themselves, so what a person
reads is asserted through ``read_as_markdown`` — the chat's own reading.

Covers:
- The originally-reported bug: ``reminder_delete`` no longer renders as
  ``🔔 Médecin\n  🔔 dimanche ...`` (duplicate emoji on two lines), but as
  ``🔔 Rappel{separator}Médecin - dimanche ...`` (single line, single emoji).
- Per-language correctness: capitalized noun, localized date with day name.
- Per-draft-type coverage: every ``DraftType`` produces a sensible row.
- Edge cases: missing label, missing datetime, unknown draft type, nested
  field resolution (e.g. ``file.name``).
"""

from __future__ import annotations

import pytest

from src.core.i18n_drafts import format_hitl_item_preview, label_separator
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator
from src.domains.shared.markdown_literal import read_as_markdown

ALL_LANGUAGES: tuple[str, ...] = ("fr", "en", "es", "de", "it", "zh-CN")


class _NoModelQuestions(HitlQuestionGenerator):
    """A question generator with no model: the rows under test are drawn without one."""

    def __init__(self) -> None:
        """The real one builds two model clients; nothing here calls them."""


#: What joins a label to its value for a French reader.
_SEP = label_separator("fr")


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
    assert row.startswith(f"🔔 Rappel{_SEP}Médecin"), row
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
    assert f"Email{_SEP}Confirmation rdv" in row, row
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
    assert f"Événement{_SEP}Réunion équipe" in row
    assert " - " in row


def test_contact_create_no_secondary_datetime() -> None:
    """Contact creation has no secondary datetime → row without trailing date."""
    row = format_hitl_item_preview(
        draft_type=DraftType.CONTACT.value,
        content={"name": "Marie Dupont"},
        language="fr",
    )
    assert row is not None
    assert f"Contact{_SEP}Marie Dupont" in row
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
    assert f"Tâche{_SEP}Préparer démo" in row
    assert " - " in row


def test_file_delete_resolves_nested_name() -> None:
    """``file.name`` dotted key resolves through nested dict."""
    row = format_hitl_item_preview(
        draft_type=DraftType.FILE_DELETE.value,
        content={"file": {"name": "report.pdf"}},
        language="fr",
    )
    assert row is not None
    assert f"Fichier{_SEP}report.pdf" in row


def test_label_delete_uses_label_name() -> None:
    row = format_hitl_item_preview(
        draft_type=DraftType.LABEL_DELETE.value,
        content={"label_name": "pro/clients"},
        language="fr",
    )
    assert row is not None
    assert f"Label{_SEP}pro/clients" in row


# =============================================================================
# Recipient prefix — send-type drafts (email / reply / forward)
# =============================================================================
# The critical HITL bug: a batch email confirmation must show WHO each email
# goes to, otherwise two rows with the same subject are indistinguishable.


def test_email_send_shows_recipient_and_subject() -> None:
    """A send email row shows "Email à {to}{separator}{subject}" (recipient + subject)."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": "matheo@example.com", "subject": "Je t'aime"},
        language="fr",
    )
    assert row is not None
    assert read_as_markdown(row).startswith(f"📧 Email à matheo@example.com{_SEP}Je t'aime"), row


def test_email_send_two_recipients_are_distinguishable() -> None:
    """Two emails with the same subject render as DISTINCT rows (the bug's core)."""
    matheo = format_hitl_item_preview(
        DraftType.EMAIL.value, {"to": "matheo@example.com", "subject": "Je t'aime"}, language="fr"
    )
    hua = format_hitl_item_preview(
        DraftType.EMAIL.value, {"to": "hua@example.com", "subject": "Je t'aime"}, language="fr"
    )
    assert matheo != hua, "Rows must differ by recipient"
    assert "matheo@example.com" in read_as_markdown(matheo or "")
    assert "hua@example.com" in read_as_markdown(hua or "")


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
    assert f"{connector} marie@example.com" in read_as_markdown(row), row


def test_email_send_recipient_as_list_is_joined() -> None:
    """A list ``to`` is joined with commas, not rendered as a Python list repr."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": ["a@example.com", "b@example.com"], "subject": "Sujet"},
        language="fr",
    )
    assert row is not None
    assert "a@example.com, b@example.com" in read_as_markdown(row), row
    assert "[" not in row and "]" not in row


def test_email_send_without_recipient_falls_back_to_noun_label() -> None:
    """No ``to`` field → plain "Email{separator}{subject}" with no dangling connector."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"subject": "Sujet seul"},
        language="fr",
    )
    assert row is not None
    assert row.startswith(f"📧 Email{_SEP}Sujet seul"), row
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
    assert "à contact@example.com" in read_as_markdown(row), row


def test_email_delete_ignores_recipient_field() -> None:
    """email_delete has no recipient prefix even if a ``to`` is present."""
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL_DELETE.value,
        content={"to": "someone@example.com", "subject": "Facture", "date": None},
        language="fr",
    )
    assert row is not None
    assert "someone@example.com" not in read_as_markdown(row), row
    assert f"Email{_SEP}Facture" in row, row


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


def test_a_label_keeps_its_no_break_and_ideographic_spaces() -> None:
    """``" ".join(x.split())`` folded them into ordinary spaces: the preferred
    preview of a FOR_EACH or a draft batch lost the typography the one-line
    helper was written to keep."""
    nbsp, ideographic = chr(0xA0), chr(0x3000)
    row = format_hitl_item_preview(
        draft_type=DraftType.REMINDER_DELETE.value,
        content={"content": f"Rendez-vous{nbsp}: médecin{chr(0x2028)}suivi{ideographic}x"},
        language="fr",
    )
    assert row is not None
    assert f"Rendez-vous{nbsp}: médecin suivi{ideographic}x" in row, row


def test_a_long_recipient_list_counts_what_it_leaves_out() -> None:
    """Every recipient is shown whole or counted — none is cut: cut on a
    word, a display name pushed the address it names out of the row."""
    recipients = [f"person{i}@example.com" for i in range(6)]
    row = format_hitl_item_preview(
        draft_type=DraftType.EMAIL.value,
        content={"to": recipients, "subject": "Sujet"},
        language="fr",
    )
    assert row is not None
    shown = read_as_markdown(row)
    assert f"à person0@example.com, person1@example.com, … (+4){_SEP}Sujet" in shown, row
    assert "..." not in row


def test_a_display_name_never_hides_its_address() -> None:
    """A reply takes its recipient from the From header: « support@your-bank
    .example Customer Service Team… » was all the row showed of a reply going
    to attacker@evil.example (review 14)."""
    sender = "support@your-bank.example Customer Service Team <attacker@evil.example>"
    row = format_hitl_item_preview(
        DraftType.EMAIL_REPLY.value, {"to": sender, "subject": "Re: Votre compte"}, language="fr"
    )

    assert row is not None
    assert f"à {sender}{_SEP}Re: Votre compte" in read_as_markdown(row), row


def test_a_first_recipient_longer_than_the_bound_is_shown_whole() -> None:
    long_one = "x" * 70 + "@example.com"
    row = format_hitl_item_preview(
        DraftType.EMAIL.value, {"to": [long_one, "b@example.com"], "subject": "S"}, language="en"
    )

    assert row is not None
    assert f"to {long_one}, … (+1)" in read_as_markdown(row), row


def test_a_recipient_is_spelled_where_it_would_mislead() -> None:
    """A right-to-left override reorders what follows it: spelled, never drawn."""
    row = format_hitl_item_preview(
        DraftType.EMAIL.value,
        {"to": "a" + chr(0x202E) + "b@example.com", "subject": "S"},
        language="en",
    )

    assert row is not None
    assert chr(0x202E) not in row and "⟨U+202E⟩" in row


@pytest.mark.parametrize("language", ALL_LANGUAGES)
@pytest.mark.parametrize("draft_type", list(DraftType))
def test_every_draft_type_yields_non_empty_row_in_every_language(
    language: str, draft_type: DraftType
) -> None:
    """Smoke test: with a generic content dict, every type produces a non-empty row."""
    content: dict[str, object] = {
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


#: A subject that is a link to another host and a tracking image, as a sender types it.
_HOSTILE = "[Urgent](https://evil.example/login) <img src=https://evil.example/p.png>"
_DRAWN = (
    "&#91;Urgent&#93;(https&#58;//evil.example/login) "
    "&#60;img src=https&#58;//evil.example/p.png&#62;"
)


def test_the_label_and_the_recipient_are_drawn_as_themselves() -> None:
    """The row is streamed as Markdown into the question: a subject spelled as a
    link drew one, and an image loaded before anyone answered (review 13)."""
    row = format_hitl_item_preview(
        DraftType.EMAIL.value,
        {"to": "a_b@example.org *x*", "subject": _HOSTILE},
        language="en",
    )

    assert row is not None
    assert _DRAWN in row
    assert "a_b&#64;example.org &#42;x&#42;" in row


def test_the_for_each_fallback_row_is_drawn_as_itself() -> None:
    """A domain no draft names falls back to the preview's own values: data too."""
    from src.core.i18n_hitl import HitlMessages
    from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
        ForEachConfirmationInteraction,
    )

    interaction = ForEachConfirmationInteraction(question_generator=_NoModelQuestions())
    section = interaction._build_item_previews_section(
        item_previews=[{"name": _HOSTILE}],
        total_affected=1,
        translations=HitlMessages.get_for_each_confirm_translations("en"),
        user_language="en",
    )

    assert "&#91;Urgent&#93;(https&#58;//evil.example/login)" in section
    assert "<img" not in section


def test_the_batch_fallback_row_is_drawn_as_itself() -> None:
    """A draft type the registry does not know still lists its item as data."""
    from src.domains.agents.services.hitl.interactions.draft_critique import (
        DraftCritiqueInteraction,
    )

    interaction = DraftCritiqueInteraction(question_generator=_NoModelQuestions())
    message = interaction._generate_batch_critique(
        draft_type="no_such_type",
        batch_drafts=[{"draft_content": {"subject": _HOSTILE}}],
        batch_total=1,
        user_language="en",
    )

    assert _DRAWN in message


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_the_noun_joins_its_label_with_the_reader_s_punctuation(language: str) -> None:
    """Each language's own separator — never the French spacing for everyone."""
    row = format_hitl_item_preview(
        DraftType.REMINDER_DELETE.value, {"content": "Label"}, language=language
    )

    assert row is not None
    assert f"{label_separator(language)}Label" in row, row
    if language != "fr":
        assert " : " not in row, row


def test_a_step_s_tool_name_is_drawn_as_itself() -> None:
    """A step's tool name may be an MCP server's own: Telegram drew
    ``- send<i>x</i>tool`` from ``send_*x*_tool`` (review 14)."""
    from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
        ForEachConfirmationInteraction,
    )

    interaction = ForEachConfirmationInteraction(question_generator=_NoModelQuestions())
    message = interaction._build_confirmation_message(
        steps=[
            {"tool_name": "send_*x*_tool", "item_count": 2},
            {"tool_name": "[a](https://evil.example)", "item_count": 1},
        ],
        total_affected=3,
        user_language="en",
    )

    assert "send&#95;&#42;x&#42;&#95;tool" in message
    assert "&#91;a&#93;(https&#58;//evil.example)" in message


def test_a_fallback_value_is_spelled_before_it_is_cut() -> None:
    """Cut, then spelled, a value's markers passed the bound (review 14)."""
    from src.core.i18n_hitl import HitlMessages
    from src.core.text_clip import clip_spelled
    from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
        ForEachConfirmationInteraction,
    )

    padded = ("a" + chr(0x202E)) * 40
    interaction = ForEachConfirmationInteraction(question_generator=_NoModelQuestions())
    section = interaction._build_item_previews_section(
        item_previews=[{"name": padded}],
        total_affected=1,
        translations=HitlMessages.get_for_each_confirm_translations("en"),
        user_language="en",
    )

    assert clip_spelled(padded, 50) in section
    assert chr(0x202E) not in section


def _batch_fallback(subject: str) -> str:
    """The batch question for a draft type the registry does not know."""
    from src.domains.agents.services.hitl.interactions.draft_critique import (
        DraftCritiqueInteraction,
    )

    interaction = DraftCritiqueInteraction(question_generator=_NoModelQuestions())
    return interaction._generate_batch_critique(
        draft_type="no_such_type",
        batch_drafts=[{"draft_content": {"subject": subject}}],
        batch_total=1,
        user_language="en",
    )


def test_the_batch_fallback_row_is_spelled_and_on_one_line() -> None:
    """The fallback drew its label as typed: an override reordered it, a line
    break wrote a row of its own (review 13, pinned in review 14)."""
    message = _batch_fallback("a" + chr(0x202E) + "b" + chr(10) + "- c")

    assert "a⟨U+202E⟩b - c" in message
    assert chr(0x202E) not in message


def test_a_batch_fallback_row_with_nothing_to_show_reads_a_question_mark() -> None:
    rows = [line for line in _batch_fallback("   ").splitlines() if line.startswith("- ")]

    assert len(rows) == 1 and rows[0].endswith(" ?")
