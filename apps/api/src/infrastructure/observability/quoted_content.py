"""Error texts that QUOTE the data they refused — the quotation withheld above DEBUG.

Some third-party error texts reproduce the input they rejected, and that input
is whatever the person wrote or the row held. Measured on the dev stack on
2026-09-24 (temporary tables, the value « Jean Dupont »):

* PostgreSQL, rendered alike by asyncpg and psycopg: a unique violation's
  ``DETAIL`` names the duplicated key, a not-null or check violation's prints
  the WHOLE failing row, a JSON error's ``CONTEXT`` quotes the document, and a
  refused cast ends by quoting its input (``invalid input syntax for type
  integer: "Jean Dupont"``, ``no operand in tsquery: "…"``);
* asyncpg, when it cannot encode a parameter: ``invalid input for query
  argument $1: 'Jean Dupont' (…)``;
* SQLAlchemy: ``[parameters: (…)]`` after the statement — the application's
  engine hides them (``hide_parameters``), another engine may not;
* Pydantic: every error line carries ``input_value=<the input>``.

These texts reach a log line through ``error=str(e)`` and through tracebacks,
whatever the call site. None of them is ours to reword, so each shape is
recognised by the fixed LAYOUT its producer writes — never by natural language —
and only the quotation is replaced: the constraint, the table, the statement and
the error class stay, because they are what makes the line diagnosable.

``pii_filter`` applies this to every string value above DEBUG, the rendered
traceback included; DEBUG keeps the text whole (contents at DEBUG, CLAUDE.md).
"""

import re

_REDACTED = "[REDACTED]"

#: Substrings without which no rule below can match — the cheap pre-filter that
#: keeps the common case (a short identifier) at one scan.
_MARKERS: tuple[str, ...] = (
    "DETAIL:  ",
    "CONTEXT:  ",
    "[parameters: ",
    "query argument",
    "input_value=",
    "invalid input",
    "out of range",
    "malformed",
    "tsquery",
    "invalid regular expression",
)

# PostgreSQL's DETAIL and CONTEXT fields. A field runs to the next field, to
# SQLAlchemy's own trailer, or to the junction Python writes between chained
# exceptions of a rendered traceback — a failing row can itself contain line
# breaks, and the frames of the NEXT exception are not part of the field.
_SERVER_FIELD = re.compile(
    r"(?P<field>DETAIL|CONTEXT):  .*?"
    r"(?=\n(?:DETAIL|HINT|CONTEXT|QUERY):  |\n\[SQL[: ]|\n\[parameters: "
    r"|\n\(Background on this error|\n\nThe above exception was the direct cause"
    r"|\n\nDuring handling of the above exception|\nTraceback \(most recent call last\):"
    r"|\Z)",
    re.DOTALL,
)

# SQLAlchemy's rendering of the bound values (one line: each value is a repr).
_SQLALCHEMY_PARAMETERS = re.compile(r"\[parameters: [^\n]*")

# asyncpg: the value's repr, then an encoder message that may quote it again.
_QUERY_ARGUMENT = re.compile(r"(invalid input for query argument \$\d+: )[^\n]*")

# PostgreSQL message families that end by quoting the input they refused.
_QUOTED_INPUT = re.compile(
    r"((?:invalid input syntax for|invalid input value for|date/time field value out of range"
    r"|malformed [^:\n]* literal|(?:no operand|syntax error) in tsquery"
    r"|invalid regular expression)[^:\n]*: )[^\n]*"
)
_OUT_OF_RANGE = re.compile(r'(value )"[^\n]*"( is out of range for type)')

# Pydantic writes `input_value=<repr>, input_type=<type>]` on each error line. A
# value can itself contain `, input_type=…]`, so the match runs to the LAST
# marker of the line (greedy, and `.` never crosses a line).
_PYDANTIC_INPUT = re.compile(r"(input_value=).*(, input_type=[^,\]\n]*\])")


def redact_quoted_content(text: str) -> str:
    """Replace the data an error text quotes, keeping everything around it.

    Args:
        text: A log value — an ``error=str(e)``, a rendered traceback, a stdlib
            message.

    Returns:
        The text with every recognised quotation replaced by ``[REDACTED]``;
        unchanged when it carries none.
    """
    if not any(marker in text for marker in _MARKERS):
        return text
    text = _SERVER_FIELD.sub(lambda match: f"{match['field']}:  {_REDACTED}", text)
    text = _SQLALCHEMY_PARAMETERS.sub(f"[parameters: {_REDACTED}]", text)
    text = _QUERY_ARGUMENT.sub(rf"\g<1>{_REDACTED}", text)
    text = _QUOTED_INPUT.sub(rf"\g<1>{_REDACTED}", text)
    text = _OUT_OF_RANGE.sub(rf"\g<1>{_REDACTED}\g<2>", text)
    return _PYDANTIC_INPUT.sub(rf"\g<1>{_REDACTED}\g<2>", text)
