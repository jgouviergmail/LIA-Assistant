"""Above DEBUG, the PII filter withholds what a line quotes, not only what it names.

The field-name net (``CONTENT_FIELD_NAMES``) redacts ``subject=`` or ``body=``,
but three channels carried the person's words past it (inventory of
2026-09-24):

* an ``error=str(e)`` or a traceback of a database or validation failure —
  PostgreSQL quotes the row it rejects, Pydantic the input it refused;
* a logged URL whose free-text parameter IS the search (``?q=``, ``$search=``);
* field names the net did not know: ``query=`` alone was on 43 lines above
  DEBUG, ``topic=`` — a person's interests, health included — on 35.

DEBUG keeps everything whole: contents at DEBUG is the policy (CLAUDE.md).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import structlog

from src.infrastructure.observability.pii_filter import add_pii_filter, sanitize_url_query

pytestmark = pytest.mark.unit

_NAME = "Jean Dupont"
_UNIQUE_VIOLATION = (
    "(sqlalchemy.dialects.postgresql.asyncpg.IntegrityError) <class "
    "'asyncpg.exceptions.UniqueViolationError'>: duplicate key value violates unique "
    'constraint "users_name_key"\n'
    "DETAIL:  Key (name)=(Jean Dupont) already exists.\n"
    "[SQL: INSERT INTO users (name) VALUES ($1)]"
)


def _filtered(level: str, **fields: object) -> dict[str, object]:
    return add_pii_filter(None, level, {"event": "probe", **fields})


class TestQuotedErrorTextAboveDebug:
    @pytest.mark.parametrize("level", ["info", "warning", "error", "critical"])
    def test_an_error_value_loses_the_quoted_row(self, level: str) -> None:
        result = _filtered(level, error=_UNIQUE_VIOLATION)

        assert _NAME not in str(result["error"])
        assert "users_name_key" in str(result["error"])

    def test_a_rendered_traceback_loses_it_too(self) -> None:
        traceback_text = (
            "Traceback (most recent call last):\n"
            '  File "/app/src/core/repository.py", line 330, in create\n'
            "    await self.db.flush()\n"
            f"sqlalchemy.exc.IntegrityError: {_UNIQUE_VIOLATION}"
        )

        result = _filtered("error", exception=traceback_text)

        assert _NAME not in str(result["exception"])
        assert "repository.py" in str(result["exception"])

    def test_nested_and_listed_values_are_covered(self) -> None:
        result = _filtered(
            "warning", failures=[_UNIQUE_VIOLATION], context={"e": _UNIQUE_VIOLATION}
        )

        assert _NAME not in json.dumps(result)

    def test_debug_keeps_the_text_whole(self) -> None:
        assert _filtered("debug", error=_UNIQUE_VIOLATION)["error"] == _UNIQUE_VIOLATION


class TestSearchParametersInUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=from%3Ajean+cancer&maxResults=10",
            "https://api.search.brave.com/res/v1/web/search?count=5&q=Jean+Dupont+avocat",
            "https://fr.wikipedia.org/w/api.php?action=query&srsearch=Jean+Dupont",
            "https://graph.microsoft.com/v1.0/me/messages?$search=%22Jean%20Dupont%22",
            "https://api.openweathermap.org/geo/1.0/direct?limit=1&q=Montreuil",
        ],
    )
    def test_the_search_term_is_withheld_above_debug(self, url: str) -> None:
        redacted = sanitize_url_query(url, redact_content=True)

        assert "Jean" not in redacted
        assert "Montreuil" not in redacted
        assert "cancer" not in redacted

    def test_other_parameters_and_the_path_stay_readable(self) -> None:
        url = "https://api.search.brave.com/res/v1/web/search?count=5&q=Jean"

        assert sanitize_url_query(url, redact_content=True) == (
            "https://api.search.brave.com/res/v1/web/search?count=5&q=[REDACTED]"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://maps.googleapis.com/maps/api/geocode/json?address=x&key=AIzaSyFAKEKEY123",
            "https://api.openweathermap.org/data/2.5/weather?lat=1&appid=0123456789abcdef",
        ],
    )
    def test_a_provider_key_in_the_query_string_is_a_credential(self, url: str) -> None:
        """An httpx status error renders the full URL — the platform's key with it."""
        for level in ("debug", "error"):
            rendered = str(_filtered(level, error=f"Client error '403' for url '{url}'")["error"])
            assert "AIzaSyFAKEKEY123" not in rendered
            assert "0123456789abcdef" not in rendered

    def test_debug_keeps_the_search_but_never_a_credential(self) -> None:
        url = "https://example.org/cb?q=Jean&code=4/0AY0e-g7SECRET"

        assert sanitize_url_query(url) == "https://example.org/cb?q=Jean&code=[REDACTED]"

    def test_a_field_value_is_covered(self) -> None:
        result = _filtered("info", url="https://api.search.brave.com/res/v1/web/search?q=Jean")

        assert "Jean" not in str(result["url"])


class TestContentFieldNames:
    @pytest.mark.parametrize(
        "field",
        [
            "query",
            "topic",
            "keyword",
            "input",
            "question",
            "reasoning",
            "instructions",
            "stdout",
            "stderr",
            "purpose",
            "display_name",
            "full_name",
            "label_name",
            "folder_name",
            "file_name",
            "filename",
            "entity_name",
            "resolved_name",
        ],
    )
    def test_a_content_name_is_redacted_above_debug(self, field: str) -> None:
        assert _filtered("info", **{field: _NAME})[field] == "[REDACTED]"
        assert _filtered("debug", **{field: _NAME})[field] == _NAME

    @pytest.mark.parametrize(
        "field",
        [
            "user_query_preview",
            "feedback_preview",
            "detection_query",
            "clarification_question",
            "new_topic",
            "result_content",
            "response_text",
            "original_input",
            "system_prompt",
        ],
    )
    def test_a_content_suffix_redacts_text(self, field: str) -> None:
        assert _filtered("warning", **{field: _NAME})[field] == "[REDACTED]"

    def test_a_content_suffix_redacts_a_list_of_texts(self) -> None:
        assert _filtered("info", queries_preview=[_NAME])["queries_preview"] == "[REDACTED]"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("has_query", True),
            ("has_content", False),
            ("user_id_preview", "3f2a9c1b"),
            ("query_length", 42),
            ("extra_body", {"enable_thinking": False}),
        ],
    )
    def test_metadata_about_content_is_kept(self, field: str, value: object) -> None:
        """A flag, a length, an id prefix or a config dict says nothing of the words."""
        assert _filtered("info", **{field: value})[field] == value


@pytest.fixture()
def configured_json_logging() -> Iterator[io.StringIO]:
    """The production chain, captured — restored afterwards like test_logging.py does."""
    from src.infrastructure.observability.logging import configure_logging

    saved = structlog.get_config()
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    try:
        with patch("src.infrastructure.observability.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"
            mock_settings.environment = "test"
            mock_settings.log_level_uvicorn = "WARNING"
            mock_settings.log_level_uvicorn_access = "ERROR"
            mock_settings.log_level_sqlalchemy = "WARNING"
            mock_settings.log_level_httpx = "INFO"
            mock_settings.is_production = False
            configure_logging()
        buffer = io.StringIO()
        root.handlers[0].stream = buffer  # type: ignore[attr-defined]
        yield buffer
    finally:
        structlog.configure(**saved)
        root.handlers = saved_handlers
        root.setLevel(saved_level)


class TestEndToEndThroughTheProductionChain:
    def test_a_logged_database_failure_keeps_its_facts_and_loses_the_row(
        self, configured_json_logging: io.StringIO
    ) -> None:
        from asyncpg.exceptions import UniqueViolationError
        from sqlalchemy.exc import IntegrityError

        driver = UniqueViolationError(
            'duplicate key value violates unique constraint "users_name_key"'
        )
        driver.detail = f"Key (name)=({_NAME}) already exists."
        logger = structlog.get_logger("probe.repository")
        try:
            raise IntegrityError("INSERT INTO users (name) VALUES ($1)", (_NAME,), driver)
        except IntegrityError as exc:
            logger.error("repository_query_error", error=str(exc), exc_info=True)

        line = configured_json_logging.getvalue().strip()
        payload = json.loads(line)
        assert _NAME not in line
        assert "users_name_key" in payload["error"]
        assert "IntegrityError" in payload["exception"]

    def test_a_stdlib_http_line_loses_its_search_term(
        self, configured_json_logging: io.StringIO
    ) -> None:
        logging.getLogger("httpx").info(
            'HTTP Request: GET https://api.search.brave.com/res/v1/web/search?q=Jean+Dupont "HTTP/1.1 200 OK"'
        )

        payload = json.loads(configured_json_logging.getvalue().strip())
        assert "Jean" not in payload["event"]
        assert "q=[REDACTED]" in payload["event"]
