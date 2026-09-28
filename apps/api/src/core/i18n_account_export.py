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
