"""Literal per-field search of current minutes, projected by the report schema.

Only static JSON paths enter PostgreSQL. Never search JSON keys, original audio
transcripts, inactive section payloads or previous versions of the report.
"""

import unicodedata

from sqlalchemy import (
    SQLColumnExpression,
    String,
    Text,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH, array
from sqlalchemy.sql.elements import ColumnElement

from src.core.meeting_templates import SectionKind
from src.core.sql_search import LIKE_ESCAPE, escape_like
from src.domains.meetings.models import Meeting

_SECTION_PATHS: dict[SectionKind, tuple[str, ...]] = {
    SectionKind.PARAGRAPH: ("paragraph",),
    SectionKind.BULLETS: ("bullets[*]",),
    SectionKind.TOPICS: ("topics[*].title", "topics[*].summary"),
    SectionKind.ACTION_ITEMS: (
        "action_items[*].description",
        "action_items[*].owner",
        "action_items[*].due_date",
    ),
    SectionKind.TRANSCRIPT: ("transcript[*].speaker", "transcript[*].text"),
}
assert set(_SECTION_PATHS) == set(SectionKind), "Search must cover every section kind"

_TEXT_PATHS = (
    "$.title",
    "$.participants[*].name",
    "$.participants[*].role",
    "$.sections[*].label",
    *(
        f'$.sections[*] ? (@.kind == "{kind.value}").{field}'
        for kind, fields in _SECTION_PATHS.items()
        for field in fields
    ),
)
_TYPOGRAPHY = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "\u00a0": " ", "\u202f": " "})


def normalize_minutes_query(query: str) -> str:
    """Match normalizeSearchText's NFD/combining-range/typography contract."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", query.lower())
        if not "\u0300" <= char <= "\u036f"
    ).translate(_TYPOGRAPHY)


def _normalized(value: SQLColumnExpression[str | None]) -> ColumnElement[str]:
    return func.translate(
        func.regexp_replace(
            func.normalize(func.lower(value), text("NFD")), "[\u0300-\u036f]", "", "g"
        ),
        "‘’ʼ\u00a0\u202f",
        "'''  ",
    )


def minutes_search_predicate(query: str, *, include_location: bool = True) -> ColumnElement[bool]:
    """One contiguous literal phrase must match inside one allowed text field."""
    pattern = f"%{escape_like(normalize_minutes_query(query.strip()))}%"
    predicates: list[ColumnElement[bool]] = []
    if include_location:
        predicates.append(_normalized(Meeting.location_label).like(pattern, escape=LIKE_ESCAPE))
    for path in _TEXT_PATHS:
        values = (
            func.jsonb_path_query(
                Meeting.report_current,
                cast(literal(f'strict {path} ? (@.type() == "string")'), JSONPATH),
                literal({}, type_=JSONB),
                true(),
            )
            .table_valued("value")
            .render_derived()
        )
        scalar = cast(values.c.value.op("#>>")(array([], type_=Text)), String)
        predicates.append(
            exists(
                select(1)
                .select_from(values)
                .where(_normalized(scalar).like(pattern, escape=LIKE_ESCAPE))
            )
        )
    return or_(*predicates)
