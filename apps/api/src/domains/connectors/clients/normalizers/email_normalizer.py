"""
Email normalizer: IMAP MailMessage → the provider-neutral e-mail vocabulary.

Converts imap_tools MailMessage objects to the flat dict every provider
produces (``normalizers/email_message.EmailMessage``, ADR-287): top-level
headers, a clean TEXT body (HTML converted by the shared door, structure and
links kept — a regex used to flatten it), an attachment list, a provider
marker. It fabricates no Gmail ``payload`` tree.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import structlog
from imap_tools.utils import DEFAULT_EMAIL_DATE

from src.domains.connectors.clients.normalizers.html_text import html_to_text, strip_html_to_line
from src.domains.connectors.clients.normalizers.imap_handles import message_handle
from src.domains.connectors.clients.normalizers.reply_trimming import clean_reply_body

logger = structlog.get_logger(__name__)

# A Gmail query operator → imap_tools criteria, negated by a leading ``-`` —
# never a hyphen inside a word (``reply-to:`` is text, not a negated ``to:``).
_GMAIL_OPERATOR_PATTERN = re.compile(
    r"(?<![\w-])(-?)(from|to|cc|subject|after|before|label|is|has|in):(\S+)"
)
#: The imap_tools criterion each people or subject operator states.
_IMAP_TEXT_CRITERIA: Final[dict[str, str]] = {
    "from": "from_",
    "to": "to",
    "cc": "cc",
    "subject": "subject",
}
#: The imap_tools flag each state names — ``label:starred`` is the star too.
_IMAP_STATES: Final[dict[str, tuple[str, bool]]] = {
    "unread": ("seen", False),
    "read": ("seen", True),
    "starred": ("flagged", True),
}

# HTML tag stripping for snippet generation
_HTML_TAG_RE = re.compile(r"<[^<>]+>")

_SNIPPET_MAX_LENGTH = 200


def _joined(addresses: Any) -> str:
    """imap_tools' address tuple as one header-like string."""
    return ", ".join(addresses) if isinstance(addresses, list | tuple) else str(addresses or "")


#: IMAP flags that speak a label of the vocabulary — present (or, for \\Seen,
#: ABSENT: IMAP marks what was read) — as Gmail and Graph label them.
_FLAG_LABELS: tuple[tuple[str, bool, str], ...] = (
    ("\\Seen", False, "UNREAD"),
    ("\\Flagged", True, "STARRED"),
    ("\\Draft", True, "DRAFT"),
)


def _label_ids(msg: Any, folder: str) -> list[str]:
    """The folder, then the labels the message's flags speak."""
    try:
        flags = msg.flags  # cached_property — must be accessed within MailBox context
    except Exception:
        flags = ()
    return [folder] + [label for flag, present, label in _FLAG_LABELS if (flag in flags) is present]


def _internal_date(value: Any) -> str | None:
    """UTC epoch milliseconds; an unparsed date remains unknown on every platform.

    imap_tools supplies DEFAULT_EMAIL_DATE when the header cannot be parsed.
    A naive mail date (-0000) represents UTC, not the host's local timezone.
    """
    if not isinstance(value, date) or value == DEFAULT_EMAIL_DATE:
        return None
    instant = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    try:
        return str(int(instant.timestamp() * 1000))
    except OSError, ValueError, OverflowError:
        return None


def normalize_imap_message(
    msg: Any, folder: str, *, keep_quoted: bool = False, scope: str | None = None
) -> dict[str, Any]:
    """
    Normalize an imap_tools MailMessage to Gmail API dict format.

    IMPORTANT: This must be called WITHIN the MailBox context manager,
    as MailMessage properties are cached_property that access the connection.

    Args:
        msg: imap_tools MailMessage object.
        folder: IMAP folder name the message was fetched from.
        keep_quoted: Keep the quoted history in the body — a mailbox draft is
            the person's own text, and an edit must not lose what it quotes
            (ADR-344).

    Returns:
        Dict matching Gmail API message format.
    """
    # A UID names a message within ONE folder: the id carries the folder too.
    message_id = message_handle(folder, str(msg.uid), scope=scope)

    # =========================================================================
    # Body: extract text, prefer plain text over HTML-stripped
    # Store at TOP-LEVEL to bypass GmailFormatter._extract_body_recursive()
    # which expects base64url-encoded data (Gmail API format)
    # =========================================================================
    body_text = msg.text or ""
    if not body_text and msg.html:
        body_text = html_to_text(msg.html)
    if not keep_quoted:
        body_text = clean_reply_body(body_text, subject=msg.subject or "")
    snippet = strip_html_to_line(body_text, max_length=_SNIPPET_MAX_LENGTH)

    # =========================================================================
    # Headers: top-level fields (the vocabulary), no fabricated Gmail tree
    # =========================================================================
    subject = msg.subject or ""
    from_value = msg.from_ or ""
    to_value = _joined(msg.to)
    cc_value = _joined(msg.cc)
    date_value = msg.date_str or ""
    # RFC 2822 Message-ID, for In-Reply-To / References on a reply. imap_tools
    # keys its headers in lower case; a test double may carry none.
    rfc_ids = (getattr(msg, "headers", None) or {}).get("message-id") or ()
    rfc_message_id = str(rfc_ids[0]).strip() if rfc_ids else None

    # =========================================================================
    # Attachments: top-level for direct access by _enrich_email()
    # =========================================================================
    # IMAP has no attachment handle: the part's INDEX is published as one, and
    # ``AppleEmailClient.download_attachment`` reads it back the same way.
    attachments = []
    for index, att in enumerate(msg.attachments):
        attachments.append(
            {
                "attachmentId": str(index),
                "filename": att.filename,
                "mimeType": att.content_type,
                "size": len(att.payload) if att.payload else 0,
            }
        )

    label_ids = _label_ids(msg, folder)
    internal_date = _internal_date(msg.date)

    return {
        "id": message_id,
        "threadId": message_id,  # IMAP has no thread concept
        "labelIds": label_ids,
        "snippet": snippet,
        "subject": subject,
        "from": from_value,
        "reply_to": _joined(getattr(msg, "reply_to", None)),
        "to": to_value,
        "cc": cc_value,
        # Present on what the mailbox stores for the person (a draft, a sent
        # message), as on Graph.
        "bcc": _joined(msg.bcc),
        "date": date_value,
        "rfc_message_id": rfc_message_id,
        "body": body_text,
        "unread": "UNREAD" in label_ids,
        "hasAttachment": len(attachments) > 0,
        "attachments": attachments,
        "internalDate": internal_date,
        # Provider marker for downstream formatters and display components.
        # Used to determine web URL availability and "read more" link text.
        "_provider": "apple",
    }


def normalize_imap_folder(folder_name: str) -> dict[str, Any]:
    """
    Normalize an IMAP folder to Gmail label format.

    Args:
        folder_name: IMAP folder name.

    Returns:
        Dict matching Gmail label format.
    """
    # Map common IMAP folders to Gmail system labels
    system_folders = {
        "INBOX": "system",
        "Sent": "system",
        "Sent Messages": "system",
        "Drafts": "system",
        "Trash": "system",
        "Junk": "system",
        "Spam": "system",
        "Archive": "system",
    }
    folder_type = system_folders.get(folder_name, "user")

    return {
        "id": folder_name,
        "name": folder_name,
        "type": folder_type,
    }


@dataclass(frozen=True)
class ImapQuery:
    """A Gmail-style query as ONE IMAP search, and the folders it names.

    Attributes:
        criteria: The imap_tools criteria.
        folder: The ``label:`` / ``in:`` value it reads, as written, or None —
            the client resolves it in its session: a system location by its
            role, a folder of the person's own by its name
            (``apple_imap.search_folder``).
        excluded_folders: The values its negated ``label:`` / ``in:`` exclude:
            reading one folder excludes every other.
    """

    criteria: Any
    folder: str | None
    excluded_folders: tuple[str, ...]

    @property
    def excludes_its_folder(self) -> bool:
        """Whether the query excludes the very folder it reads (the INBOX by default)."""
        read = (self.folder or "inbox").casefold()
        return any(value.casefold() == read for value in self.excluded_folders)


def parse_imap_query(gmail_query: str) -> ImapQuery:
    """Read a Gmail-style query as imap_tools criteria and the folders it names.

    A NEGATED operator holds — it used to be stripped, so « not the newsletter »
    listed the newsletter (2026-10-13): ``NOT`` for a person or a subject, the
    other side of a date, the opposite flag, and a folder excluded by reading
    another. What IMAP has no criterion for (``has:attachment``,
    ``is:important``) is set aside under either sign, as before.

    Args:
        gmail_query: Gmail query string (e.g., "from:user@example.com -is:read").

    Returns:
        The search and the folders it names.
    """
    from imap_tools import AND

    criteria: dict[str, Any] = {}
    negated_criteria: list[Any] = []
    folder: str | None = None
    excluded: list[str] = []
    remaining = gmail_query
    for match in _GMAIL_OPERATOR_PATTERN.finditer(gmail_query):
        remaining = remaining.replace(match.group(0), " ", 1)
        negated, operator, value = match.group(1) == "-", match.group(2).lower(), match.group(3)
        if operator not in ("label", "in") or (operator, value.lower()) == ("label", "starred"):
            _imap_criterion(operator, value, negated, criteria, negated_criteria)
        elif negated:
            excluded.append(value)
        elif value.lower() == "anywhere":
            logger.debug("imap_query_unsupported_operator", operator="in:anywhere")
        else:
            folder = value
    if text := " ".join(remaining.split()):
        criteria["text"] = text
    present = {key: wanted for key, wanted in criteria.items() if wanted is not None}
    combined = AND(*negated_criteria, **present) if present or negated_criteria else AND(all=True)
    return ImapQuery(combined, folder, tuple(excluded))


def _imap_criterion(
    operator: str,
    value: str,
    negated: bool,
    criteria: dict[str, Any],
    negated_criteria: list[Any],
) -> None:
    """Record the imap_tools criterion one operator states, under its sign."""
    from imap_tools import NOT

    if operator in _IMAP_TEXT_CRITERIA:
        # ``cc:`` is a real criterion, never free text: "sent to this person"
        # includes being in copy, and the full text would match the body.
        key = _IMAP_TEXT_CRITERIA[operator]
        if negated:
            negated_criteria.append(NOT(**{key: value}))
        else:
            criteria[key] = value
    elif operator in ("after", "before"):
        # NOT (on or after a day) is before it, and the other way round.
        side = "date_gte" if (operator == "after") != negated else "date_lt"
        criteria[side] = _parse_date(value)
    elif operator in ("is", "label") and value.lower() in _IMAP_STATES:
        key, wanted = _IMAP_STATES[value.lower()]
        criteria[key] = wanted != negated
    else:
        logger.debug("imap_query_unsupported_operator", operator=f"{operator}:{value}")


def convert_imap_query(gmail_query: str) -> tuple[Any, str | None]:
    """
    Convert a Gmail-style query string to imap_tools AND criteria.

    Args:
        gmail_query: Gmail query string (e.g., "from:user@example.com is:unread").

    Returns:
        Tuple of (imap_tools AND criteria, the folder the query names or None)
        — :func:`parse_imap_query`, for a reader that reads one folder of its
        own (the drafts listing).
    """
    parsed = parse_imap_query(gmail_query)
    return parsed.criteria, parsed.folder


def _parse_date(date_str: str) -> date | None:
    """Parse date from Gmail query format (YYYY/MM/DD or YYYY-MM-DD)."""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    logger.warning("imap_query_invalid_date", date_str=date_str)
    return None
