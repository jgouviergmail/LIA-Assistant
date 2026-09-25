"""The facts a log line carries in place of the words: a length, a host."""

from __future__ import annotations

import pytest

from src.infrastructure.observability.log_facts import (
    UnreadableLevel,
    log_unreadable_text,
    url_host,
)

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, dict[str, object]]] = []

    def debug(self, event: str, **fields: object) -> None:
        self.lines.append(("debug", event, fields))

    def info(self, event: str, **fields: object) -> None:
        self.lines.append(("info", event, fields))

    def warning(self, event: str, **fields: object) -> None:
        self.lines.append(("warning", event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.lines.append(("error", event, fields))


@pytest.mark.parametrize("level", ["info", "warning", "error"])
def test_the_report_carries_the_length_never_the_words(level: UnreadableLevel) -> None:
    logger = _Recorder()

    log_unreadable_text(logger, "draft_parse_error", "Cher Jean,", level=level, error="bad")

    reported_level, event, fields = logger.lines[0]
    assert (reported_level, event) == (level, "draft_parse_error")
    assert fields == {"text_length": 10, "error": "bad"}


def test_the_words_go_to_a_debug_line_of_their_own() -> None:
    logger = _Recorder()

    log_unreadable_text(logger, "draft_parse_error", "Cher Jean,")

    assert logger.lines[1] == ("debug", "draft_parse_error_text", {"text": "Cher Jean,"})


def test_a_non_string_output_is_rendered() -> None:
    logger = _Recorder()

    log_unreadable_text(logger, "result_parse_error", {"items": [1, 2]})

    assert logger.lines[0][2]["text_length"] == len("{'items': [1, 2]}")


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://Example.ORG/path?q=Jean+Dupont", "example.org"),
        ("http://[::1]:8080/x", "::1"),
        ("/api/v1/attachments/3f2a", None),
        ("", None),
    ],
)
def test_url_host_keeps_the_host_alone(url: str, host: str | None) -> None:
    assert url_host(url) == host


def test_url_host_never_raises_on_a_malformed_url() -> None:
    """Lines that log a host often handle a URL that failed validation."""
    assert url_host("http://[::1") is None


@pytest.mark.parametrize("value", [None, 42, b"https://example.org"])
def test_url_host_reads_only_strings(value: object) -> None:
    assert url_host(value) is None
