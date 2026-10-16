"""A Gmail-style mail query as ONE request Microsoft Graph accepts (RC3.1).

Graph serves a mail listing under three documented constraints, none of which
a Gmail query knows about:

* on ``/messages`` a ``$search`` (KQL) combines with neither ``$filter`` nor
  ``$orderby`` — its results come newest SENT first;
* a ``$filter`` with ``$orderby`` is accepted only when the sort property LEADS
  the filter — absent, or after another property, Graph answers
  ``InefficientFilter``;
* KQL documents ``from``/``to``/``cc``/``subject``, words and
  ``hasAttachments:true``, a ``received`` date only as a single day (no range
  is documented), and no read state at all.

The translation used to produce a search AND a filter and let the client drop
the SEARCH — the very criterion naming the mail — so « Marie's unread mails »
listed every unread mail, and a filter alone was refused for its order. It now
decides ONE request:

* nothing to search → a ``$filter`` led by the sort property;
* only a sender's exact address to search, beside another condition → the same
  ``$filter`` (``from/emailAddress/address eq`` is documented), so the sender,
  the dates and the read state are all the server's;
* otherwise → a ``$search`` carrying every term KQL documents.

What the request cannot carry — beside a search, a date or a read state; and
the star (Outlook's flag), which neither form is documented to carry — is
checked on each message of the page it returns. That page may hold fewer
messages than asked while more match further on: the caller is told how many
were set aside (:meth:`GraphMailQuery.screen`), never left to read a thin page
as the whole answer.

A NEGATED operator holds too (it used to be stripped: « not the newsletter »
listed the newsletter): a state or a date is its opposite clause, a person or a
subject is set aside on the page — KQL documents no ``NOT`` —, and a folder is
excluded by reading another one. Excluding the very folder the request reads is
said (:attr:`GraphMailQuery.excludes_its_folder`), never served as its opposite.

A date is always the SORT property's: a drafts listing sorts and filters on a
draft's last save, the mail on its reception.

A folder the query names is routed by endpoint: a well-known one by its Graph
id, a folder of the person's own by its NAME, which the client resolves among
the mailbox's folders (``mail_folders``) — never the inbox in its place.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from src.core.validators import validate_email
from src.domains.connectors.clients.mail_folders import MAIL_QUERY_DATE_FORMAT_ERROR

RECEIVED: Final = "receivedDateTime"

#: Every message postdates it: a filter naming no date is led by the sort
#: property through it (the documented InefficientFilter rules).
_EARLIEST: Final = "1900-01-01T00:00:00Z"
_STAMP: Final = "%Y-%m-%dT%H:%M:%SZ"

#: An operator, negated by a leading ``-`` — never a hyphen inside a word
#: (``reply-to:`` is a term, not a negated ``to:``).
_OPERATOR: Final = re.compile(
    r'(?<![\w-])(-?)(from|to|cc|subject|after|before|label|is|has|in):("(?:[^"\\]|\\.)*"|\S+)'
)
_PEOPLE_AND_SUBJECT: Final = frozenset({"from", "to", "cc", "subject"})
#: Where a people operator reads a Graph message.
_PEOPLE_FIELDS: Final[dict[str, str]] = {
    "from": "from",
    "to": "toRecipients",
    "cc": "ccRecipients",
}
#: A negated state is its opposite.
_OPPOSITES: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("is", "read"): ("is", "unread"),
    ("is", "unread"): ("is", "read"),
}
_DATE_FORMATS: Final = ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S")

#: Well-known folder names (the ``label:`` / ``in:`` values) → Graph folder ids.
_FOLDERS: Final[dict[str, str]] = {
    "inbox": "inbox",
    "sent": "sentitems",
    "sentitems": "sentitems",
    "sent messages": "sentitems",
    "drafts": "drafts",
    "draft": "drafts",
    "trash": "deleteditems",
    "deleted items": "deleteditems",
    "deleteditems": "deleteditems",
    "junk": "junkemail",
    "spam": "junkemail",
    "junkemail": "junkemail",
    "archive": "archive",
}

type _Check = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class _Condition:
    """One condition of a query: how a page checks it, and how Graph may carry it."""

    holds: _Check
    #: Its ``$filter`` clause, when Graph documents one.
    odata: str | None = None
    #: Its KQL term, when ``$search`` documents one.
    kql: str | None = None
    #: Whether a ``$filter`` must put it first (a date on the sort property).
    leads: bool = False


@dataclass(frozen=True, slots=True)
class GraphMailQuery:
    """One Graph request for a Gmail-style query, and what its pages still owe it.

    Attributes:
        folder: The well-known folder the request routes to.
        params: ``{"$search": …}``, or ``{"$filter": …, "$orderby": …}``, or
            ``{"$orderby": …}`` alone.
        folder_name: A folder of the person's own the query names, which the
            client must resolve; None when the folder is well-known.
        excludes_its_folder: Whether a negated ``in:``/``label:`` names the
            very folder the request reads — a question one folder cannot serve.
    """

    folder: str
    params: Mapping[str, str]
    folder_name: str | None = None
    excludes_its_folder: bool = False
    _unsent: tuple[_Condition, ...] = field(default=(), repr=False)

    def screen[M: Mapping[str, Any]](self, messages: Sequence[M]) -> tuple[list[M], int]:
        """The page's messages that meet what the request could not carry.

        Args:
            messages: A page of Graph messages, as the request returned them.

        Returns:
            The messages kept, in order, and how many were set aside.
        """
        kept = [m for m in messages if all(c.holds(m) for c in self._unsent)]
        return kept, len(messages) - len(kept)


@dataclass(slots=True)
class _Parsed:
    """What a query names, operator by operator."""

    terms: list[str] = field(default_factory=list)
    conditions: list[_Condition] = field(default_factory=list)
    folder: str = "inbox"
    folder_name: str | None = None
    excluded: list[str] = field(default_factory=list)

    @property
    def excludes_its_folder(self) -> bool:
        """Whether an excluded folder is the one the request reads."""
        return any(_routes_to(value, self.folder, self.folder_name) for value in self.excluded)


def graph_mail_query(text: str, *, sort_property: str = RECEIVED) -> GraphMailQuery:
    """Translate a Gmail-style query into one Graph request.

    Args:
        text: The query (``from:``, ``to:``, ``cc:``, ``subject:``, ``after:``,
            ``before:``, ``is:read``/``is:unread``/``is:starred``,
            ``has:attachment``, ``label:``/``in:``, each negated by a leading
            ``-``, and words).
        sort_property: The date the listing sorts on, newest first — and the
            one its date conditions read.

    Returns:
        The request's folder and parameters, and the page checks it leaves.

    Raises:
        ValueError: A date operator whose value is not a date.
    """
    parsed = _parse(text.strip(), sort_property)
    terms, conditions = parsed.terms, parsed.conditions
    order = f"{sort_property} desc"
    sender = _sole_sender(terms)
    if sender is not None and conditions:
        address = sender.replace("'", "''")
        conditions.append(
            _Condition(lambda _: True, odata=f"from/emailAddress/address eq '{address}'")
        )
        terms = []
    if not terms:
        unsent = tuple(c for c in conditions if c.odata is None)
        params = _filtered([c for c in conditions if c.odata], sort_property, order)
    else:
        kql = [*terms, *(c.kql for c in conditions if c.kql)]
        unsent = tuple(c for c in conditions if c.kql is None)
        params = {"$search": f'"{" ".join(kql)}"'}
    return GraphMailQuery(
        parsed.folder, params, parsed.folder_name, parsed.excludes_its_folder, unsent
    )


def _parse(text: str, sort_property: str) -> _Parsed:
    """The KQL terms, the conditions and the folders a query names."""
    parsed = _Parsed()
    last_end = 0
    for match in _OPERATOR.finditer(text):
        if words := text[last_end : match.start()].strip():
            parsed.terms.append(words)
        last_end = match.end()
        negated, operator, value = match.group(1) == "-", match.group(2), match.group(3)
        value = value.strip('"')
        if negated:
            _negate(parsed, operator, value, sort_property)
        elif operator in _PEOPLE_AND_SUBJECT:
            parsed.terms.append(f"{operator}:{value}")
        elif condition := _condition(operator, value, sort_property):
            parsed.conditions.append(condition)
        elif operator in ("label", "in"):
            well_known = _FOLDERS.get(value.lower())
            parsed.folder, parsed.folder_name = (
                (well_known, None) if well_known else ("inbox", value)
            )
    if words := text[last_end:].strip():
        parsed.terms.append(words)
    return parsed


def _negate(parsed: _Parsed, operator: str, value: str, sort_property: str) -> None:
    """What a negated operator states: a condition, or a folder the read excludes."""
    if operator in ("label", "in") and value.lower() != "starred":
        parsed.excluded.append(value)
    elif condition := _negation(operator, value, sort_property):
        parsed.conditions.append(condition)


def _condition(operator: str, value: str, sort_property: str) -> _Condition | None:
    """The condition a date, state or attachment operator states, if any."""
    if operator in ("after", "before"):
        bound = _bound(value)
        if operator == "after":
            return _Condition(
                _dated(sort_property, lambda instant: instant >= bound),
                odata=f"{sort_property} ge {bound.strftime(_STAMP)}",
                leads=True,
            )
        return _Condition(
            _dated(sort_property, lambda instant: instant < bound),
            odata=f"{sort_property} lt {bound.strftime(_STAMP)}",
            leads=True,
        )
    state = value.lower()
    if operator == "is" and state in ("read", "unread"):
        wanted = state == "read"
        return _Condition(
            lambda m: m.get("isRead") is wanted, odata=f"isRead eq {str(wanted).lower()}"
        )
    if (operator, state) in (("is", "starred"), ("label", "starred")):
        return _Condition(_flagged)
    if operator == "has" and state == "attachment":
        return _Condition(lambda _: True, odata="hasAttachments eq true", kql="hasAttachments:true")
    return None


def _negation(operator: str, value: str, sort_property: str) -> _Condition | None:
    """The condition a negated operator states, when its positive form has one."""
    if operator in ("after", "before"):
        return _condition("before" if operator == "after" else "after", value, sort_property)
    state = value.lower()
    if (operator, state) in _OPPOSITES:
        opposite, opposite_state = _OPPOSITES[(operator, state)]
        return _condition(opposite, opposite_state, sort_property)
    if (operator, state) in (("is", "starred"), ("label", "starred")):
        return _Condition(lambda m: not _flagged(m))
    if operator == "has" and state == "attachment":
        return _Condition(
            lambda m: m.get("hasAttachments") is False, odata="hasAttachments eq false"
        )
    if operator in _PEOPLE_AND_SUBJECT:
        return _Condition(_lacks(operator, value))
    return None


def _routes_to(value: str, folder: str, folder_name: str | None) -> bool:
    """Whether a ``label:`` / ``in:`` value names the folder the request reads."""
    if folder_name is not None:
        return value.casefold() == folder_name.casefold()
    return _FOLDERS.get(value.lower()) == folder


def _filtered(conditions: Sequence[_Condition], sort_property: str, order: str) -> dict[str, str]:
    """A ``$filter`` led by the sort property, or the sorted listing alone."""
    if not conditions:
        return {"$orderby": order}
    leading = [str(c.odata) for c in conditions if c.leads] or [f"{sort_property} ge {_EARLIEST}"]
    following = [str(c.odata) for c in conditions if not c.leads]
    return {"$filter": " and ".join([*leading, *following]), "$orderby": order}


def _sole_sender(terms: Sequence[str]) -> str | None:
    """The address a query searches for alone (``from:`` an exact address), else None."""
    if len(terms) != 1 or not terms[0].startswith("from:"):
        return None
    address = terms[0].removeprefix("from:")
    return address if validate_email(address) else None


def _bound(value: str) -> datetime:
    """The instant a date operator names: a day's UTC midnight, or Unix seconds.

    Raises:
        ValueError: The value is neither.
    """
    text = value.strip("'\"")
    if text.isdigit() and len(text) > len("YYYYMMDD"):
        # datetime's supported Unix range fits in twelve decimal digits.
        # Bound before integer conversion and normalize OS-specific failures.
        if not text.isascii() or len(text) > 12:
            raise ValueError(MAIL_QUERY_DATE_FORMAT_ERROR)
        try:
            return datetime.fromtimestamp(int(text), UTC)
        except ValueError, OverflowError, OSError:
            raise ValueError(MAIL_QUERY_DATE_FORMAT_ERROR) from None
    for date_format in _DATE_FORMATS:
        try:
            day = datetime.strptime(text, date_format)
        except ValueError:
            continue
        return datetime(day.year, day.month, day.day, tzinfo=UTC)
    try:
        day = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(MAIL_QUERY_DATE_FORMAT_ERROR) from None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _dated(sort_property: str, accepts: Callable[[datetime], bool]) -> _Check:
    """A page check on a message's ``sort_property`` date; an unreadable one never matches."""

    def holds(message: Mapping[str, Any]) -> bool:
        instant = _instant(message.get(sort_property))
        return instant is not None and accepts(instant)

    return holds


def _lacks(operator: str, value: str) -> _Check:
    """A page check: the message does not show ``value`` where ``operator`` reads."""
    needle = value.casefold()

    def holds(message: Mapping[str, Any]) -> bool:
        return needle not in _shown(message, operator)

    return holds


def _shown(message: Mapping[str, Any], operator: str) -> str:
    """What a people or subject operator reads on a Graph message, folded."""
    if operator == "subject":
        return str(message.get("subject") or "").casefold()
    people = message.get(_PEOPLE_FIELDS[operator])
    entries = people if isinstance(people, list) else [people]
    addresses = [
        entry["emailAddress"]
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("emailAddress"), Mapping)
    ]
    return " ".join(
        f"{address.get('name') or ''} {address.get('address') or ''}" for address in addresses
    ).casefold()


def _flagged(message: Mapping[str, Any]) -> bool:
    """Whether a Graph message carries Outlook's flag — Gmail's star."""
    flag = message.get("flag")
    return isinstance(flag, Mapping) and flag.get("flagStatus") == "flagged"


def _instant(value: Any) -> datetime | None:
    """A Graph timestamp, aware; None when absent or unreadable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


__all__ = ["RECEIVED", "GraphMailQuery", "graph_mail_query"]
