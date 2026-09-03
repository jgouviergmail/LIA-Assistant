"""ONE serializer, three outputs (ADR-258): the Markdown the space indexes, the
sectioned document the PDF is built from, and the escaped HTML of the email
all carry the same content, localized headers included."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.domains.meetings.render import (
    action_display,
    build_header,
    format_duration,
    minutes_filename_stem,
    participant_display,
    render_html,
    render_markdown,
    render_sectioned,
)
from src.domains.meetings.schemas import (
    ActionItem,
    MeetingReport,
    Participant,
    ReportSection,
    SectionKind,
    TopicItem,
)

pytestmark = pytest.mark.unit


def _meeting(**over):
    base = {
        "client_timezone": "Europe/Paris",
        "started_at": datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
        "stopped_at": datetime(2026, 9, 2, 9, 5, tzinfo=UTC),
        "audio_duration_seconds": 3900.0,
        "location_label": "Salle B",
    }
    base.update(over)
    return SimpleNamespace(**base)


def _report() -> MeetingReport:
    return MeetingReport(
        title="Point <projet> & budget",
        participants=[
            Participant(label="S1", name="Marie", role="Chef de projet"),
            Participant(label="S2", name=None, role=None),
        ],
        sections=[
            ReportSection(
                key="summary", label="Résumé", kind=SectionKind.PARAGRAPH, paragraph="Tout va bien."
            ),
            ReportSection(
                key="decisions",
                label="Décisions",
                kind=SectionKind.BULLETS,
                bullets=["Go", "<b>pas</b> de no-go"],
            ),
            ReportSection(
                key="topics",
                label="Sujets",
                kind=SectionKind.TOPICS,
                topics=[TopicItem(title="Budget", summary="Validé.")],
            ),
            ReportSection(
                key="actions",
                label="Actions",
                kind=SectionKind.ACTION_ITEMS,
                action_items=[
                    ActionItem(description="Relancer", owner="S2", due_date="2026-09-05")
                ],
            ),
            ReportSection(key="risks", label="Risques", kind=SectionKind.BULLETS, bullets=[]),
        ],
    )


def test_header_is_localized_and_says_the_gaps_and_the_numbering() -> None:
    report = MeetingReport(title="T", participants=[Participant(label="S1")], sections=[])
    header = build_header(_meeting(), report, language="fr", gaps=2)
    assert header.minutes_label == "Compte rendu de réunion"
    assert header.date_label == "Date" and "2026" in header.date
    assert header.time_range == "10:00 – 11:05"  # Paris, September
    assert header.duration == "1:05:00" and header.location == "Salle B"
    assert header.participants == ["S1"]
    assert header.notices == [
        "L'enregistrement a été interrompu un moment ; une partie du contenu peut manquer.",
        "Les interlocuteurs sont numérotés ; leurs noms n'ont pas pu être établis.",
    ]


def test_header_without_end_or_location_omits_those_rows() -> None:
    header = build_header(
        _meeting(stopped_at=None, location_label=None, audio_duration_seconds=None),
        _report(),
        language="en",
    )
    assert header.time_range is None and header.duration is None and header.location is None
    assert header.notices == []  # one named participant is enough to drop the numbering notice


def test_markdown_carries_every_section_in_order_with_localized_headers() -> None:
    report = _report()
    markdown = render_markdown(report, build_header(_meeting(), report, language="fr"))
    assert markdown.startswith("# Point <projet> & budget\n\n*Compte rendu de réunion*\n")
    assert "- **Participants** : Marie (Chef de projet), S2" in markdown
    assert (
        markdown.index("## Résumé")
        < markdown.index("## Décisions")
        < markdown.index("## Sujets")
        < markdown.index("## Actions")
    )
    assert "### Budget\n\nValidé." in markdown
    assert "- Relancer · S2 · 2026-09-05" in markdown
    assert "## Risques" in markdown  # an empty section keeps its heading
    assert markdown.rstrip().endswith("_Compte rendu généré par LIA à partir d'un enregistrement_")


def test_sectioned_document_maps_every_kind_to_blocks() -> None:
    report = _report()
    content = render_sectioned(
        report, build_header(_meeting(), report, language="en"), filename_stem="x"
    )
    kinds = [
        (block.kind, block.level if block.kind == "heading" else None) for block in content.blocks
    ]
    assert content.title == report.title
    assert ("heading", 2) in kinds and ("heading", 3) in kinds  # section + topic
    bullets = [block for block in content.blocks if block.kind == "bullets"]
    assert any(block.items == ["Go", "<b>pas</b> de no-go"] for block in bullets)
    assert any(block.items == ["Relancer · S2 · 2026-09-05"] for block in bullets)


def test_html_escapes_everything_the_model_or_the_user_typed() -> None:
    report = _report()
    html = render_html(report, build_header(_meeting(), report, language="en"))
    assert "<b>" not in html and "&lt;b&gt;pas&lt;/b&gt;" in html
    assert "Point &lt;projet&gt; &amp; budget" in html
    assert "<h3>Budget</h3><p>Validé.</p>" in html
    assert "Meeting minutes" in html


def test_display_helpers_and_filename() -> None:
    assert participant_display(Participant(label="S1", name="Marie", role="Chef")) == "Marie (Chef)"
    assert participant_display(Participant(label="S1")) == "S1"
    assert action_display(ActionItem(description="Faire")) == "Faire"
    assert (
        format_duration(59) == "0:00:59"
        and format_duration(None) is None
        and format_duration(0) is None
    )
    stem = minutes_filename_stem(
        _meeting(), MeetingReport(title="Point / budget: Q3?", sections=[])
    )
    assert stem.startswith("2026-09-02 Point")
    assert "/" not in stem and ":" not in stem and "?" not in stem
