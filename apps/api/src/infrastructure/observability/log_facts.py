"""The facts a log line carries in place of a person's words (ADR-317).

Above DEBUG a log line carries counts, lengths, identifiers, codes — never the
text a person wrote or a model wrote about them. Two shapes recur often enough
to be written once:

* an OUTPUT the code could not parse (a model's structured answer, a provider's
  error body): its length at the caller's level, its words on a DEBUG line of
  their own, for a developer reproducing the failure;
* a URL: its host, never its path or query — and without ever raising, because
  the lines that need it are often the ones handling a URL that did not parse.
"""

from typing import Literal, Protocol
from urllib.parse import urlparse

UnreadableLevel = Literal["info", "warning", "error"]


class _Logger(Protocol):
    """The structlog methods this module calls."""

    def debug(self, event: str, **fields: object) -> object: ...

    def info(self, event: str, **fields: object) -> object: ...

    def warning(self, event: str, **fields: object) -> object: ...

    def error(self, event: str, **fields: object) -> object: ...


def log_unreadable_text(
    logger: _Logger,
    event: str,
    text: object,
    *,
    level: UnreadableLevel = "warning",
    **fields: object,
) -> None:
    """Report an output the code could not parse, without repeating its words.

    When a model's structured answer does not parse, the failure used to be
    logged with the first 100 to 500 characters of the answer — and that answer
    is whatever the model wrote about the person (a modified draft, a
    classification of their reply, the items of their list). The length still
    says whether it was empty, cut or merely malformed.

    Args:
        logger: The caller's module logger.
        event: The event name, logged at ``level`` with the text's length.
        text: The unreadable output (rendered with ``str`` when not a string).
        level: The level of the reporting line.
        **fields: The caller's own metadata (an error type, a run id).
    """
    rendered = text if isinstance(text, str) else str(text)
    report = {"info": logger.info, "warning": logger.warning, "error": logger.error}[level]
    report(event, text_length=len(rendered), **fields)
    logger.debug(f"{event}_text", text=rendered)


def url_host(url: object) -> str | None:
    """The host of a URL, for a log line — never its path or query.

    ``urlparse`` raises ``ValueError`` on some malformed URLs (an unclosed IPv6
    bracket), and the lines that log a host are often the ones handling a URL
    that failed validation: the raise would replace the original error.

    Args:
        url: What the caller holds (a URL string, or anything else).

    Returns:
        The lower-cased host, or ``None`` when there is none to read.
    """
    if not isinstance(url, str):
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None
