"""Error texts that QUOTE the data they refused lose the quotation above DEBUG.

Every fixture below is a rendering MEASURED on the dev stack on 2026-09-24
(temporary tables, the value « Jean Dupont ») — SQLAlchemy over asyncpg, raw
psycopg as the LangGraph checkpointer sees it, and Pydantic — not a guess at
what those libraries might write. The structure around the quotation (the
constraint, the table, the statement, the error type) is what makes a line
diagnosable, so it must survive intact.
"""

from __future__ import annotations

import pytest

from src.infrastructure.observability.quoted_content import redact_quoted_content

pytestmark = pytest.mark.unit

_NAME = "Jean Dupont"

SQLALCHEMY_UNIQUE = (
    "(sqlalchemy.dialects.postgresql.asyncpg.IntegrityError) <class "
    "'asyncpg.exceptions.UniqueViolationError'>: duplicate key value violates unique "
    'constraint "probe_t_name_key"\n'
    "DETAIL:  Key (name)=(Jean Dupont) already exists.\n"
    "[SQL: INSERT INTO probe_t VALUES ($1, $2)]\n"
    "[parameters: ('Jean Dupont', 'jean.dupont@example.org')]\n"
    "(Background on this error at: https://sqlalche.me/e/20/gkpj)"
)
SQLALCHEMY_CAST = (
    "(sqlalchemy.dialects.postgresql.asyncpg.Error) <class 'asyncpg.exceptions.DataError'>: "
    "invalid input for query argument $1: 'Jean Dupont' ('str' object cannot be interpreted "
    "as an integer)\n"
    "[SQL: SELECT CAST($1 AS integer)]\n"
    "[SQL parameters hidden due to hide_parameters=True]\n"
    "(Background on this error at: https://sqlalche.me/e/20/dbapi)"
)
PSYCOPG_NOT_NULL = (
    'null value in column "body" of relation "probe_p" violates not-null constraint\n'
    "DETAIL:  Failing row contains (Marie Curie, null)."
)
PSYCOPG_JSON = (
    "invalid input syntax for type json\n"
    'LINE 1: SELECT \'{"a": "x"\'::jsonb\n'
    "               ^\n"
    "DETAIL:  The input string ended unexpectedly.\n"
    'CONTEXT:  JSON data, line 1: {"a": "Jean Dupont"'
)
PYDANTIC = (
    "2 validation errors for M\n"
    "age\n"
    "  Input should be a valid integer, unable to parse string as an integer "
    "[type=int_parsing, input_value='Jean Dupont habite 3 rue de la Paix', input_type=str]\n"
    "    For further information visit https://errors.pydantic.dev/2.13/v/int_parsing\n"
    "tags.0\n"
    "  Input should be a valid integer, unable to parse string as an integer "
    "[type=int_parsing, input_value='x, input_type=str] Jean Dupont', input_type=str]\n"
    "    For further information visit https://errors.pydantic.dev/2.13/v/int_parsing"
)


class TestTheQuotationIsWithheld:
    @pytest.mark.parametrize(
        "text",
        [SQLALCHEMY_UNIQUE, SQLALCHEMY_CAST, PSYCOPG_NOT_NULL, PSYCOPG_JSON, PYDANTIC],
        ids=["unique-detail", "query-argument", "failing-row", "json-context", "pydantic"],
    )
    def test_no_quoted_value_survives(self, text: str) -> None:
        redacted = redact_quoted_content(text)

        for quoted in (_NAME, "Marie Curie", "jean.dupont@example.org", "rue de la Paix"):
            assert quoted not in redacted

    @pytest.mark.parametrize(
        "text",
        [
            'invalid input syntax for type integer: "Jean Dupont"',
            'invalid input syntax for type uuid: "Jean Dupont"',
            'invalid input syntax for type date: "Jean Dupont"',
            'invalid input value for enum mood: "Jean Dupont"',
            'no operand in tsquery: "Jean Dupont & "',
            'syntax error in tsquery: "Jean Dupont &"',
            'date/time field value out of range: "Jean Dupont"',
            'malformed array literal: "Jean Dupont"',
            'value "Jean Dupont" is out of range for type integer',
            "invalid regular expression: Jean Dupont(",
        ],
    )
    def test_a_server_message_quoting_its_input(self, text: str) -> None:
        assert _NAME not in redact_quoted_content(text)

    def test_a_failing_row_spanning_several_lines_is_withheld_whole(self) -> None:
        """A row value may itself contain line breaks: the field runs to the next field."""
        text = (
            'new row for relation "notes" violates check constraint "notes_len"\n'
            "DETAIL:  Failing row contains (1, Chère Marie,\nJean Dupont vous écrit).\n"
            "[SQL: INSERT INTO notes VALUES ($1, $2)]"
        )

        redacted = redact_quoted_content(text)

        assert _NAME not in redacted
        assert "[SQL: INSERT INTO notes VALUES ($1, $2)]" in redacted

    def test_a_pydantic_value_forging_the_marker_is_withheld_to_the_last_one(self) -> None:
        line = "[type=string_type, input_value='a, input_type=int] Jean Dupont', input_type=str]"

        assert redact_quoted_content(line) == (
            "[type=string_type, input_value=[REDACTED], input_type=str]"
        )


class TestARenderedTracebackKeepsItsFrames:
    """``format_exc_info`` renders the chain before the filter runs: frames must survive."""

    @staticmethod
    def _chained_traceback() -> str:
        import traceback

        class UniqueViolationError(Exception):
            def __str__(self) -> str:
                return (
                    'duplicate key value violates unique constraint "u_key"\n'
                    "DETAIL:  Key (name)=(Jean Dupont) already exists."
                )

        def flush_the_session() -> None:
            raise UniqueViolationError()

        def create_the_row() -> None:
            try:
                flush_the_session()
            except UniqueViolationError as exc:
                raise RuntimeError("the insert failed") from exc

        try:
            create_the_row()
        except RuntimeError as exc:
            return "".join(traceback.format_exception(exc))
        raise AssertionError("unreachable")

    def test_the_quotation_goes_and_the_outer_frames_stay(self) -> None:
        rendered = self._chained_traceback()
        assert _NAME in rendered, "precondition: the rendering quotes the row"

        redacted = redact_quoted_content(rendered)

        assert _NAME not in redacted
        assert "The above exception was the direct cause" in redacted
        assert "create_the_row" in redacted, "the next exception's frames were swallowed"
        assert "RuntimeError: the insert failed" in redacted


class TestTheStructureSurvives:
    def test_constraint_statement_and_error_class_are_kept(self) -> None:
        redacted = redact_quoted_content(SQLALCHEMY_UNIQUE)

        assert 'violates unique constraint "probe_t_name_key"' in redacted
        assert "[SQL: INSERT INTO probe_t VALUES ($1, $2)]" in redacted
        assert "UniqueViolationError" in redacted
        assert "https://sqlalche.me/e/20/gkpj" in redacted
        assert "DETAIL:  [REDACTED]" in redacted

    def test_the_hint_is_the_server_s_advice_and_is_kept(self) -> None:
        text = (
            "function lower(integer) does not exist\n"
            "HINT:  No function matches the given name and argument types."
        )

        assert redact_quoted_content(text) == text

    def test_the_failing_column_and_relation_are_kept(self) -> None:
        redacted = redact_quoted_content(PSYCOPG_NOT_NULL)

        assert 'null value in column "body" of relation "probe_p"' in redacted

    @pytest.mark.parametrize(
        "text",
        [
            "router_decision",
            "Connection refused",
            'relation "users" does not exist',
            "status: done",
            "HTTP 404: Not Found",
            "",
        ],
    )
    def test_text_without_a_quotation_is_returned_unchanged(self, text: str) -> None:
        assert redact_quoted_content(text) == text
