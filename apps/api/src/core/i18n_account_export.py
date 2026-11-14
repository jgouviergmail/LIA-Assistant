"""What the readable account archive says, in the reader's language (ADR-323).

The archive's three registers were already translated (``i18n_effects``,
``i18n_treatments``). Its other sections were not: every reader found English
headings above their own words, and each message opened on a stored role
(``user``, ``assistant``) rather than on who spoke. The words themselves — the
messages, journal entries and memories — are the person's, exported unchanged;
only what frames them is ours.

The names are the application's own: the section titles of the journals and
long-term memory settings, and the speakers the chat draws (``chat.message.you``,
``LIA``).
"""

from typing import Literal

from src.core.i18n import normalize_language
from src.core.i18n_drafts import label_separator

#: A section of the readable archive whose wording is ours.
ExportSection = Literal["conversations", "journals", "memories"]

#: language -> section -> heading.
EXPORT_SECTION_HEADINGS: dict[str, dict[ExportSection, str]] = {
    "fr": {
        "conversations": "Conversations",
        "journals": "Journaux personnels",
        "memories": "Mémoire long terme",
    },
    "en": {
        "conversations": "Conversations",
        "journals": "Personal Journals",
        "memories": "Long-term Memory",
    },
    "de": {
        "conversations": "Unterhaltungen",
        "journals": "Persönliche Tagebücher",
        "memories": "Langzeitgedächtnis",
    },
    "es": {
        "conversations": "Conversaciones",
        "journals": "Diarios personales",
        "memories": "Memoria a largo plazo",
    },
    "it": {
        "conversations": "Conversazioni",
        "journals": "Diari personali",
        "memories": "Memoria a lungo termine",
    },
    "zh-CN": {
        "conversations": "对话",
        "journals": "个人日记",
        "memories": "长期记忆",
    },
}

#: language -> stored role -> who spoke. A role with no name here (a technical
#: row) is shown as stored.
EXPORT_SPEAKERS: dict[str, dict[str, str]] = {
    "fr": {"user": "Toi", "assistant": "LIA"},
    "en": {"user": "You", "assistant": "LIA"},
    "de": {"user": "Du", "assistant": "LIA"},
    "es": {"user": "Tú", "assistant": "LIA"},
    "it": {"user": "Tu", "assistant": "LIA"},
    "zh-CN": {"user": "你", "assistant": "LIA"},
}


def render_export_heading(section: ExportSection, language: str) -> str:
    """Title a section of the readable archive in the reader's language.

    Args:
        section: The archive section.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The heading.
    """
    return EXPORT_SECTION_HEADINGS[normalize_language(language)][section]


def render_export_speaker(role: str, language: str) -> str:
    """Name who spoke a stored message, in the reader's language.

    Args:
        role: The message's stored role.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The speaker's name, or the role itself when it names nobody.
    """
    return EXPORT_SPEAKERS[normalize_language(language)].get(role, role)


def render_export_turn(role: str, stamp: object, content: str, language: str) -> str:
    """One message as a readable export writes it: who spoke, when, then the words.

    One shape for the account archive and for the export of one discussion.
    The reader's punctuation joins the speaker to the words (ADR-323); the
    separator ends the line, so its trailing space would be the line's last
    character and is dropped (the HITL headers strip it the same way).

    Args:
        role: The message's stored role.
        stamp: When it was written, as the caller chose to state it.
        content: The words, as the caller chose to export them.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The block, closed by a rule.
    """
    head = f"**{render_export_speaker(role, language)}** ({stamp})"
    return f"{head}{label_separator(language).rstrip()}\n\n{content}\n\n---\n"


#: What frames the export of ONE discussion.
DiscussionExportLabel = Literal["main", "exported_on", "empty"]

#: language -> label -> wording. ``main`` is the name the chat gives the
#: permanent discussion (``chat.discussions.main``), which stores no title.
EXPORT_DISCUSSION_LABELS: dict[str, dict[DiscussionExportLabel, str]] = {
    "fr": {
        "main": "Principale",
        "exported_on": "Exportée le {date}",
        "empty": "Aucun message.",
    },
    "en": {
        "main": "Main",
        "exported_on": "Exported on {date}",
        "empty": "No messages.",
    },
    "de": {
        "main": "Hauptunterhaltung",
        "exported_on": "Exportiert am {date}",
        "empty": "Keine Nachrichten.",
    },
    "es": {
        "main": "Principal",
        "exported_on": "Exportada el {date}",
        "empty": "Sin mensajes.",
    },
    "it": {
        "main": "Principale",
        "exported_on": "Esportata il {date}",
        "empty": "Nessun messaggio.",
    },
    "zh-CN": {
        "main": "主对话",
        "exported_on": "导出于 {date}",
        "empty": "没有消息。",
    },
}


def render_discussion_label(label: DiscussionExportLabel, language: str) -> str:
    """Word the frame of one exported discussion in the reader's language.

    Args:
        label: Which wording.
        language: Any locale spelling; normalised to the backend canon.

    Returns:
        The wording; ``exported_on`` carries a ``{date}`` placeholder.
    """
    return EXPORT_DISCUSSION_LABELS[normalize_language(language)][label]
