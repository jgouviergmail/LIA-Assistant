"""Built-in templates — category ``transcript`` (ADR-259).

A transcript template rewrites the whole exchange and costs an output the size
of the meeting: never picked automatically (``auto_selectable=False``).
"""

from __future__ import annotations

from src.domains.meetings.schemas import TemplateCategory
from src.domains.meetings.template_catalogue._shared import (
    SUMMARY,
    TR,
    TRANSCRIPT_CLEAN,
    TRANSCRIPT_PRO,
    BuiltinSection,
    BuiltinTemplate,
    P,
)

_C = TemplateCategory.TRANSCRIPT

TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        "transcript_clean", _C, False, (BuiltinSection("transcript", TR, TRANSCRIPT_CLEAN),)
    ),
    BuiltinTemplate(
        "transcript_professional", _C, False, (BuiltinSection("transcript", TR, TRANSCRIPT_PRO),)
    ),
    BuiltinTemplate(
        "transcript_with_summary",
        _C,
        False,
        (
            BuiltinSection("summary", P, SUMMARY),
            BuiltinSection("transcript", TR, TRANSCRIPT_CLEAN),
        ),
    ),
)
