"""Guard: a log line above DEBUG carries counts, identifiers and codes — never the words.

CLAUDE.md forbids personal content at INFO (« names, emails, GPS coordinates,
memory/journal content, message bodies »). The PII filter enforces it by field
NAME, and a name is a convention: measured on 2026-09-24, every log call of
``src`` above DEBUG read field by field, the person's words reached the logs
under names the filter did not know — search queries on 43 lines (``query=``),
interest topics (health included) on 35, a conversation excerpt of 500
characters, a draft's modification instructions, a script's stdout, the typed
answer to a clarification, a contact's name, a label's name.

This guard reads the VALUE instead: where it comes from, whatever it is called.
A value is content when it is

* a PREVIEW — a slice ``x[:n]`` of anything but an identifier;
* DERIVED from content — its leaf names (``msg.content``, ``state["query"]``,
  ``interest.topic``, a person's ``contact.name``) are content words.

Metadata about content is not content: ``len(query)``, ``bool(body)``,
``list(draft.keys())``, ``query_length``, ``has_query``, ``tool.name``.

A few fields hold text somebody TYPED under a name that reads like a code — an
administrator's ``disabled_reason``, a manual block's ``blocked_reason``, the
words a person rejected a plan with. They are declared by their full name
(``TYPED_TEXT_FIELDS``), whoever owns them: a row read as ``config`` is not
configuration. A generic ``reason`` that is typed text cannot be told from a code
by any rule, so the modules where it is typed are pinned
(``TYPED_REASON_MODULES``): whatever the event, the length, never the text —
pinning events let a NEW event log it under a generic name. A key read through
a field constant (``row[FIELD_BLOCKED_REASON]``) is read as the field it names.
A value that is a person's content but must stay (a security event keeping the
refused host, a system space's fixed name) is ALLOWED below with its reason; an
allowance that no longer matches a line fails, so the list only ever shrinks.

What a caught exception's text quotes (a database row, a refused input) is not
this guard's: ``error=str(e)`` is withheld by the filter's quotation rules
(``observability/quoted_content.py``). Nor is a splatted mapping
(``**fields``): its keys are built at run time, and the filter reads them there.

The rule has a reverse: a FACT logged under a name the filter withholds is lost.
An exact content name keeps a count, a flag or an absence and nothing else, so
twelve voice-session lines that logged their session's id as ``origin=`` read
``[REDACTED]`` above DEBUG (2026-09-25). A fact is named after what it is
(``origin_id=``) — the filter itself is asked what it would withhold.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from src.infrastructure.observability.pii_filter import CONTENT_FIELD_NAMES, sanitize_dict
from tests._ast_bindings import binding

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

_LEVELS = frozenset({"info", "warning", "warn", "error", "exception", "critical"})
_IGNORED_KEYWORDS = frozenset({"exc_info", "stack_info", "stacklevel"})

#: Last words that make a name the person's content (``detection_query``,
#: ``user_message``, ``resolved_value``). The LAST word decides: ``query_length``
#: is a length, ``hitl_question_generator_model`` a model. ``feedback`` is not
#: here: in this codebase it names a closed vote (``thumbs_up``/``block``).
_CONTENT_WORDS = frozenset(
    {
        "query",
        "queries",
        "content",
        "contents",
        "text",
        "texts",
        "body",
        "bodies",
        "subject",
        "subjects",
        "title",
        "titles",
        "summary",
        "summaries",
        "snippet",
        "snippets",
        "preview",
        "previews",
        "excerpt",
        "instruction",
        "instructions",
        "answer",
        "reply",
        "replies",
        "transcript",
        "question",
        "questions",
        "description",
        "note",
        "notes",
        "comment",
        "comments",
        "fact",
        "facts",
        "keyword",
        "keywords",
        "topic",
        "topics",
        "term",
        "terms",
        "phone",
        "address",
        "addresses",
        "location",
        "filename",
        "filenames",
        "sender",
        "recipient",
        "recipients",
        "url",
        "urls",
        "city",
        "destination",
        "utterance",
        "reasoning",
        "stderr",
        "stdout",
        "html",
        "markdown",
        "caption",
        "message",
        "messages",
        "msg",
        "value",
        "values",
        "conversation",
        "clarification",
        "purpose",
        "response",
    }
)

#: Full names of fields that hold text somebody typed, whatever their last word.
TYPED_TEXT_FIELDS = frozenset(
    {
        "disabled_reason",
        "blocked_reason",
        "rejection_reason",
        "plan_rejection_reason",
        "change_reason",
    }
)

#: Modules whose generic ``reason`` is text an administrator typed: no log
#: value above DEBUG in them carries a ``reason`` leaf, whatever the event.
TYPED_REASON_MODULES = frozenset(
    {"domains/users/service.py", "domains/users/account_deletion_service.py"}
)


@cache
def _field_constants() -> dict[str, str]:
    """The string each ``core/field_names.py`` constant names (``FIELD_X`` → ``x``)."""
    tree = ast.parse((SRC / "core" / "field_names.py").read_text(encoding="utf-8"))
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }


#: Last word parts that turn a content name into metadata about it.
_META_WORDS = frozenset(
    {
        "id",
        "ids",
        "count",
        "counts",
        "len",
        "length",
        "lengths",
        "chars",
        "size",
        "sizes",
        "tokens",
        "hash",
        "type",
        "types",
        "key",
        "keys",
        "version",
        "ms",
        "s",
        "seconds",
        "at",
        "status",
        "code",
        "codes",
        "index",
        "enabled",
        "found",
        "kind",
        "mode",
        "lang",
        "language",
        "format",
        "limit",
        "max",
        "min",
        "field",
        "fields",
        "ratio",
        "score",
        "scores",
        "total",
        "sha",
        "digest",
        "fingerprint",
        "prefix",
        "model",
        "models",
        "provider",
        "kept",
        "removed",
        "added",
        "dropped",
        "cancelled",
        "canceled",
        "requested",
        "needed",
        "required",
        "applied",
        "detected",
        "present",
        "skipped",
        "failed",
        "succeeded",
        "changed",
        "truncated",
        "capped",
        "matched",
        "time",
        "date",
        "duration",
    }
)

#: First words that make a name a flag about content (``has_query``).
_FLAG_WORDS = frozenset(
    {"has", "is", "should", "will", "can", "needs", "was", "with", "requires", "use"}
)

#: Words that make a name a quantity (``max_messages``, ``total_queries``).
_QUANTITY_WORDS = frozenset({"max", "min", "num", "total", "count", "number", "nb"})

#: First words that make a name an error's text — the filter's quotation rules own it.
_ERROR_WORDS = frozenset({"error", "errors", "exception", "exc", "err", "e", "ex"})

#: Owners whose ``.name`` is a person's, or an object a person named.
_PERSONAL_OWNERS = frozenset(
    {
        "contact",
        "person",
        "people",
        "sender",
        "recipient",
        "attendee",
        "organizer",
        "participant",
        "peer",
        "member",
        "user",
        "display",
        "full",
        "first",
        "last",
        "file",
        "document",
        "doc",
        "attachment",
        "folder",
        "label",
        "space",
        "event",
        "calendar",
        "place",
        "entity",
        "interest",
        "resolved",
        "original",
        "old",
        "new",
    }
)

#: Calls whose result is metadata about their argument.
_METADATA_CALLS = frozenset(
    {
        "len",
        "bool",
        "int",
        "float",
        "round",
        "sum",
        "any",
        "all",
        "isinstance",
        "hash",
        "id",
        "type",
    }
)
#: Calls whose result is their argument, reshaped.
_PASSTHROUGH_CALLS = frozenset({"str", "repr", "list", "tuple", "set", "sorted", "dict", "dumps"})
#: Methods whose result is their receiver's text.
_TEXT_METHODS = frozenset(
    {
        "strip",
        "lstrip",
        "rstrip",
        "lower",
        "upper",
        "title",
        "casefold",
        "replace",
        "split",
        "format",
    }
)


@dataclass(frozen=True)
class Offense:
    """A value above DEBUG that carries the person's words, or a fact the filter hides."""

    module: str
    line: int
    event: str
    keyword: str
    source: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.module, self.event, self.keyword)


_NUMERIC_BOUND = (
    "only a NUMBER reaches this line: `_clamp_value` returns every non-numeric value "
    "untouched and the caller skips it — a clamped bound, never text"
)
_SYSTEM_SPACE = (
    "a SYSTEM knowledge space: its name is a code constant "
    "(RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT), never a person's"
)
_INSTANCE_SETTING = (
    "an administrator's instance setting (a flag, a budget, a marker): configuration, "
    "never a person's content"
)
_OPERATOR_ADDRESS = "an address the operator configured for the deployment, never a person's"

#: (module, event, keyword) → why this value may stay above DEBUG.
ALLOWED: dict[tuple[str, str, str], str] = {
    **{
        (
            "domains/agents/services/planner/parameter_bounds.py",
            "planner_parameter_bound_corrected",
            key,
        ): _NUMERIC_BOUND
        for key in ("requested_value", "corrected_value", "msg")
    },
    ("domains/image_generation/image_store.py", "pending_image_stored", "url"): (
        "a relative attachment URL (`/api/v1/attachments/<uuid>`): an identifier"
    ),
    ("domains/rag_spaces/service.py", "rag_system_space_created", "name"): _SYSTEM_SPACE,
    **{
        ("domains/rag_spaces/system_indexer.py", event, "space_name"): _SYSTEM_SPACE
        for event in (
            "system_indexer_no_chunks_parsed",
            "system_indexer_claim_declined",
            "system_indexer_corpus_diverged",
            "system_indexer_complete",
            "system_indexer_failed",
            "system_indexer_adopted_concurrent_space",
            "system_indexer_up_to_date",
        )
    },
    (
        "domains/system_settings/router.py",
        "debug_panel_user_access_update_requested",
        "new_value",
    ): _INSTANCE_SETTING,
    (
        "domains/system_settings/service.py",
        "system_setting_updated",
        "old_value",
    ): _INSTANCE_SETTING,
    (
        "domains/system_settings/service.py",
        "system_setting_updated",
        "new_value",
    ): _INSTANCE_SETTING,
    (
        "domains/usage_limits/router.py",
        "instance_daily_budget_update_requested",
        "new_value",
    ): _INSTANCE_SETTING,
    ("domains/telephony/service.py", "telephony_initiate_call_rejected", "vendor_message"): (
        "the telephony vendor's refusal: an error text, scrubbed by the filter's quotation "
        "and phone rules like any `error=str(e)`"
    ),
    (
        "infrastructure/channels/telegram/bot.py",
        "telegram_bot_initialized_webhook",
        "webhook_url",
    ): (f"{_OPERATOR_ADDRESS} (the bot's public webhook; its secret travels in a header)"),
    ("infrastructure/channels/telegram/bot.py", "telegram_webhook_set", "webhook_url"): (
        f"{_OPERATOR_ADDRESS} (the bot's public webhook; its secret travels in a header)"
    ),
    **{
        ("infrastructure/llm/providers/ollama_discovery.py", event, "base_url"): _OPERATOR_ADDRESS
        for event in (
            "ollama_discovery_success",
            "ollama_discovery_timeout",
            "ollama_discovery_http_error",
            "ollama_discovery_parse_error",
        )
    },
    (
        "infrastructure/llm/providers/ollama_chat.py",
        "ollama_llm_configured",
        "base_url",
    ): _OPERATOR_ADDRESS,
    ("infrastructure/llm/providers/ollama_chat.py", "ollama_llm_configured", "reasoning_mode"): (
        "the reasoning SETTING sent to the model (a level or a flag), never its trace"
    ),
    ("infrastructure/mcp/oauth_flow.py", "mcp_oauth_token_exchange_http_error", "content_type"): (
        "the response's Content-Type header: a media type"
    ),
}


def _words(name: str) -> list[str]:
    return [part for part in name.lower().strip("_").split("_") if part]


def _is_metadata_name(name: str) -> bool:
    """A flag, a quantity, an identifier, a code object's name or an error's text."""
    words = _words(name)
    if not words:
        return False
    if words[-1] in {"value", "values"} and len(words) > 1 and words[-2] in _META_WORDS:
        return True  # `connector_type_value`: an enum member's value
    if words[-1] == "name" and len(words) > 1 and words[-2] not in _PERSONAL_OWNERS:
        return True  # `tool_name`, `schema_name`: a code object's name
    return (
        words[0] in _FLAG_WORDS
        or words[0] in _ERROR_WORDS
        or words[-1] in _META_WORDS
        or any(word in _QUANTITY_WORDS for word in words)
        or _is_identifier_leaf(name)
    )


def _is_content_name(name: str, owner: str | None = None) -> bool:
    """Whether a leaf name designates the person's words (not metadata about them)."""
    words = _words(name)
    if name.lower() in TYPED_TEXT_FIELDS:
        return True
    if not words or name.startswith("__") or _is_metadata_name(name):
        return False
    if words[-1] == "name":
        prefix = words[:-1] or ([owner] if owner else [])
        return bool(prefix) and prefix[-1] in _PERSONAL_OWNERS
    return words[-1] in _CONTENT_WORDS


def _owner_word(node: ast.expr) -> str | None:
    """The last word of what an attribute hangs off (``contact`` for ``contact.name``)."""
    if isinstance(node, ast.Name):
        return _words(node.id)[-1] if _words(node.id) else None
    if isinstance(node, ast.Attribute):
        return _words(node.attr)[-1] if _words(node.attr) else None
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return _words(str(node.slice.value))[-1] if _words(str(node.slice.value)) else None
    return None


def _leaves(node: ast.expr) -> Iterator[tuple[str, str | None]]:
    """Yield (leaf name, owner) of what a value is made of — metadata pruned."""
    if isinstance(node, ast.Name):
        yield node.id, None
    elif isinstance(node, ast.Attribute):
        if node.attr == "value" or (node.attr == "name" and not _personal_owner(node.value)):
            return  # an enum member's value, a code object's name
        if node.attr.lower() in TYPED_TEXT_FIELDS:
            yield node.attr, _owner_word(node.value)  # typed text, even on a config row
            return
        if _owner_word(node.value) in {"settings", "config"}:
            return  # configuration, never a person's words
        yield node.attr, _owner_word(node.value)
    elif isinstance(node, ast.Subscript):
        yield from _subscript_leaves(node)
    elif isinstance(node, ast.Call):
        yield from _call_leaves(node)
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                yield from _leaves(part.value)
    elif isinstance(node, ast.BinOp):
        yield from _leaves(node.left)
        yield from _leaves(node.right)
    elif isinstance(node, ast.BoolOp):
        for operand in node.values:
            yield from _leaves(operand)
    elif isinstance(node, ast.IfExp):
        yield from _leaves(node.body)
        yield from _leaves(node.orelse)
    elif isinstance(node, ast.List | ast.Tuple | ast.Set):
        for element in node.elts:
            yield from _leaves(element)
    elif isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp):
        yield from _leaves(node.elt)
    elif isinstance(node, ast.Dict):
        for value in node.values:
            yield from _leaves(value)
    elif isinstance(node, ast.DictComp):
        yield from _leaves(node.value)
    elif isinstance(node, ast.Starred | ast.Await):
        yield from _leaves(node.value)


def _subscript_leaves(node: ast.Subscript) -> Iterator[tuple[str, str | None]]:
    """A subscript read: the key it names, else what it is taken from."""
    index = node.slice
    if isinstance(index, ast.Constant) and isinstance(index.value, str):
        yield index.value, _owner_word(node.value)
    elif isinstance(index, ast.Name):
        # `row[FIELD_BLOCKED_REASON]` reads the field the constant names.
        yield _field_constants().get(index.id, index.id), _owner_word(node.value)
    else:
        yield from _leaves(node.value)


def _personal_owner(node: ast.expr) -> bool:
    return _owner_word(node) in _PERSONAL_OWNERS


def _call_leaves(node: ast.Call) -> Iterator[tuple[str, str | None]]:
    func = node.func
    name = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr if isinstance(func, ast.Attribute) else ""
    )
    if name in _METADATA_CALLS or name == "keys":
        return
    if name in _PASSTHROUGH_CALLS:
        for argument in node.args:
            yield from _leaves(argument)
        return
    if isinstance(func, ast.Attribute):
        if name == "get" and node.args:
            key = node.args[0]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                yield key.value, _owner_word(func.value)
            elif isinstance(key, ast.Name):
                # `row.get(FIELD_BLOCKED_REASON)` reads the field the constant names.
                yield _field_constants().get(key.id, key.id), _owner_word(func.value)
            else:
                yield from _leaves(func.value)
            return
        if name in {"values", "items"}:
            yield from _leaves(func.value)
            return
        if name == "join":
            for argument in node.args:
                yield from _leaves(argument)
            return
        if name in _TEXT_METHODS:
            yield from _leaves(func.value)
            return
    # Any other call: its result is named by the function, not by its input.
    yield name, None


def _sliced(node: ast.expr) -> Iterator[ast.expr]:
    """The bases of every slice in a value (comprehension iterables excluded)."""
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
        yield node.value
    if isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp):
        yield from _sliced(node.elt)
        return
    if isinstance(node, ast.Call):
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute) else ""
        )
        if name in _METADATA_CALLS:
            return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.expr):
            yield from _sliced(child)


def _is_identifier_leaf(name: str) -> bool:
    words = _words(name)
    return bool(words) and (
        words[-1]
        in {"id", "ids", "uuid", "hash", "token", "key", "ticket", "sha", "digest", "ref", "refs"}
        or "id" in words
    )


def _is_metadata(value: ast.expr) -> bool:
    """A comparison, a negation or a metadata call says nothing of the words."""
    if isinstance(value, ast.Constant | ast.Compare):
        return True
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else ""
        return name in _METADATA_CALLS
    return False


def _is_content_keyword(keyword: str) -> bool:
    """A field name that announces content. A bare ``name`` must say whose it is."""
    return keyword == "name" or _is_content_name(keyword)


def _carries_content(keyword: str, value: ast.expr) -> bool:
    """Whether a logged value is — or is cut from — the person's words."""
    if _is_metadata(value):
        return False
    if isinstance(value, ast.JoinedStr):
        # Developer text around the placeholders: only what is interpolated counts.
        return any(
            _carries_content("", part.value)
            for part in value.values
            if isinstance(part, ast.FormattedValue)
        )
    for base in _sliced(value):
        if not all(_is_metadata_name(leaf) for leaf, _ in _leaves(base)):
            return True  # a preview of something that is not an identifier
    leaves = list(_leaves(value))
    if any(_is_content_name(leaf, owner) for leaf, owner in leaves):
        return True
    if not leaves or all(_is_metadata_name(leaf) for leaf, _ in leaves):
        return False  # an enum, a count, a flag — whatever the field is called
    return bool(keyword) and _is_content_keyword(keyword)


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _LEVELS
        and "log" in ast.unparse(func.value).lower()
    )


#: The keyword under which an f-string event name is read.
_EVENT_KEYWORD = "<event>"

#: Calls whose result is an integer or a boolean.
_SCALAR_CALLS = frozenset({"len", "bool", "int", "any", "all", "isinstance", "hash", "id"})


@dataclass(frozen=True)
class LogValue:
    """One value a log call above DEBUG passes."""

    module: str
    line: int
    event: str
    keyword: str
    value: ast.expr

    def offense(self) -> Offense:
        return Offense(
            self.module, self.line, self.event, self.keyword, ast.unparse(self.value)[:120]
        )


@cache
def _log_values() -> tuple[LogValue, ...]:
    """Every value every log call of ``src`` passes above DEBUG, read once."""
    found: list[LogValue] = []
    for path in sorted(SRC.rglob("*.py")):
        module = str(path.relative_to(SRC)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_log_call(node)):
                continue
            first = node.args[0] if node.args else None
            event = (
                first.value
                if isinstance(first, ast.Constant) and isinstance(first.value, str)
                else ast.unparse(first) if first is not None else ""
            )
            found.extend(
                LogValue(module, node.lineno, event, keyword.arg, keyword.value)
                for keyword in node.keywords
                if keyword.arg is not None and keyword.arg not in _IGNORED_KEYWORDS
            )
            if isinstance(first, ast.JoinedStr):
                found.append(LogValue(module, node.lineno, event, _EVENT_KEYWORD, first))
    return tuple(found)


def _offenses() -> list[Offense]:
    return [
        logged.offense()
        for logged in _log_values()
        if _carries_content(
            "" if logged.keyword == _EVENT_KEYWORD else logged.keyword, logged.value
        )
    ]


def _is_scalar(value: ast.expr) -> bool:
    """Whether a value is, statically, an integer, a boolean or ``None``."""
    if isinstance(value, ast.Constant):
        return value.value is None or isinstance(value.value, int)
    if isinstance(value, ast.Compare) or (
        isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not)
    ):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _SCALAR_CALLS
    )


def _is_fact(value: ast.expr) -> bool:
    """A value made of identifiers, codes, quantities or configuration — no words."""
    if _is_metadata(value):
        return True
    if next(_sliced(value), None) is not None:
        return False  # a preview is the words, cut short
    return all(_is_metadata_name(leaf) for leaf, _ in _leaves(value))


def _withholds(keyword: str, value: ast.expr) -> bool:
    """Whether the filter withholds this value above DEBUG, by its field NAME.

    The filter itself is asked, with a stand-in of the value's shape. Only an
    EXACT content name withholds a fact: a suffix withholds text alone, and
    whether a value is text is not something the AST says.
    """
    if keyword.lower() not in CONTENT_FIELD_NAMES:
        return False
    stand_in: object = 0 if _is_scalar(value) else "fact"
    logged: object = sanitize_dict({keyword: stand_in}, redact_content=True)[keyword]
    return logged != stand_in


def _hidden_facts() -> list[Offense]:
    return [
        logged.offense()
        for logged in _log_values()
        if _withholds(logged.keyword, logged.value) and _is_fact(logged.value)
    ]


def _value(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


@pytest.mark.parametrize(
    ("keyword", "source"),
    [
        ("user_query_preview", "query[:50]"),
        ("detail", "message.content"),
        ("topic", "interest.topic"),
        ("query", "params.q"),
        ("contact", "contact.name"),
        ("name", "name"),
        ("sample", "instruction_value[:200]"),
        ("msg", "f'{tool}.{name}={value} clamped'"),
        ("reason", "config.disabled_reason"),
        ("blocked", "data.blocked_reason"),
        ("rejected_because", "state.get('plan_rejection_reason')"),
        ("blocked", "row[FIELD_BLOCKED_REASON]"),  # read as the field it names
        ("blocked", "row.get(FIELD_BLOCKED_REASON)"),  # through .get, too
        ("change_reason", "update.change_reason"),  # an administrator's words
    ],
)
def test_the_rule_sees_content(keyword: str, source: str) -> None:
    """A guard that finds nothing guards nothing: each shape it exists for is seen."""
    assert _carries_content(keyword, _value(source))


@pytest.mark.parametrize(
    ("keyword", "source"),
    [
        ("query_length", "len(query)"),
        ("has_query", "bool(query)"),
        ("tool", "manifest.name"),
        ("status", "result.status.value"),
        ("user_id_preview", "str(user_id)[:8]"),
        ("content_keys", "list(draft_content.keys())"),
        ("error", "str(exc)"),
        ("message", "'Service recovered, circuit closed'"),
        ("message", "f'Tool {manifest.name} registered'"),
        ("skill_name", "name"),
        ("disabled_reason_length", "len(config.disabled_reason or '')"),
    ],
)
def test_metadata_about_content_passes(keyword: str, source: str) -> None:
    assert not _carries_content(keyword, _value(source))


def test_no_log_line_above_debug_carries_the_person_s_words() -> None:
    offenses = [offense for offense in _offenses() if offense.key not in ALLOWED]
    listing = "\n".join(f"  {o.module}:{o.line} {o.event} {o.keyword}={o.source}" for o in offenses)
    assert not offenses, (
        f"{len(offenses)} log value(s) above DEBUG carry content — log a count, a length, "
        f"an identifier or a code, or move the line to DEBUG:\n{listing}"
    )


def _aliases_of(tree: ast.AST) -> dict[str, frozenset[str]]:
    """Every local name of a tree mapped to the leaves of what was bound to it —
    by ``=``, an annotation or ``:=``."""
    aliases: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if (bound := binding(node)) is not None:
            name, value = bound
            aliases.setdefault(name, set()).update(leaf for leaf, _owner in _leaves(value))
    return {name: frozenset(leaves) for name, leaves in aliases.items()}


@cache
def _local_aliases(module: str) -> dict[str, frozenset[str]]:
    """Every local name of a module mapped to the leaves of what was assigned to it."""
    return _aliases_of(ast.parse((SRC / module).read_text(encoding="utf-8")))


def _carries_a_reason(value: ast.expr, aliases: Mapping[str, frozenset[str]]) -> bool:
    """Whether a value reads a ``reason`` — directly, under any ``*_reason`` name,
    or through a local alias (``why = data.reason`` then ``why=why``)."""
    pending = [leaf for leaf, _owner in _leaves(value)]
    seen: set[str] = set()
    while pending:
        leaf = pending.pop()
        if leaf in seen:
            continue
        seen.add(leaf)
        words = _words(leaf)
        if words and words[-1] == "reason":
            return True
        pending.extend(aliases.get(leaf, ()))
    return False


@pytest.mark.parametrize(
    ("source", "aliases"),
    [
        ("update_data.reason", {}),
        ("deletion_reason", {}),
        ("why", {"why": frozenset({"reason"})}),
        ("note", {"note": frozenset({"why"}), "why": frozenset({"reason"})}),
    ],
)
def test_a_pinned_reason_is_seen_through_its_names(
    source: str, aliases: dict[str, frozenset[str]]
) -> None:
    assert _carries_a_reason(_value(source), aliases)


def test_a_reason_s_length_is_no_reason() -> None:
    assert not _carries_a_reason(_value("len(reason)"), {})


@pytest.mark.parametrize(
    "source",
    ["why: str = data.reason", "if (why := data.reason):\n    pass", "why = data.reason"],
)
def test_a_reason_is_followed_through_every_binding(source: str) -> None:
    """Read on ``x = …`` alone, an annotated or walrus alias carried the reason
    past the guard."""
    assert _carries_a_reason(_value("why"), _aliases_of(ast.parse(source)))


def test_a_typed_reason_is_logged_by_its_length_never_its_text() -> None:
    """An administrator's typed reason, under the generic name no rule can read:
    in the modules where ``reason`` is typed text, no log value carries it —
    whatever the event, a new one included."""
    pinned = [logged for logged in _log_values() if logged.module in TYPED_REASON_MODULES]
    gone = TYPED_REASON_MODULES - {logged.module for logged in pinned}
    assert not gone, f"pinned modules no line logs from any more — remove them: {sorted(gone)}"
    leaked = [
        f"  {logged.module}:{logged.line} {logged.event} {logged.keyword}"
        for logged in pinned
        if _carries_a_reason(logged.value, _local_aliases(logged.module))
    ]
    assert not leaked, "an administrator's reason reaches the logs:\n" + "\n".join(leaked)


def test_every_allowance_still_matches_a_line() -> None:
    live = {offense.key for offense in _offenses()}
    stale = sorted(key for key in ALLOWED if key not in live)
    assert not stale, f"allowances that match no line any more — remove them: {stale}"


@pytest.mark.parametrize(
    ("keyword", "source"),
    [
        ("origin", "session.origin_id"),
        ("topic", "settings.apns_topic"),
        ("content", "round(ratio, 2)"),
        ("title", "'Weekly digest'"),
        ("lat", "len(points)"),
    ],
)
def test_the_reverse_rule_sees_a_withheld_fact(keyword: str, source: str) -> None:
    """An identifier, a setting, a float, a constant, and a count under a coordinate."""
    value = _value(source)
    assert _withholds(keyword, value)
    assert _is_fact(value)


@pytest.mark.parametrize(
    ("keyword", "source"),
    [
        ("recipients", "len(message['toRecipients'])"),
        ("content", "bool(body)"),
        ("location", "None"),
        ("origin_id", "session.origin_id"),
        ("to", "to"),
        ("cost_prompt", "total_prompt_tokens"),
    ],
)
def test_the_reverse_rule_passes_what_is_kept_or_is_content(keyword: str, source: str) -> None:
    """Counts, flags and absences are kept; words are the filter's to hide; suffixes are out."""
    value = _value(source)
    assert not (_withholds(keyword, value) and _is_fact(value))


def test_no_fact_is_logged_under_a_name_the_filter_withholds() -> None:
    hidden = _hidden_facts()
    listing = "\n".join(f"  {o.module}:{o.line} {o.event} {o.keyword}={o.source}" for o in hidden)
    assert not hidden, (
        f"{len(hidden)} fact(s) logged above DEBUG under a content name the PII filter "
        f"withholds — they reach the logs as [REDACTED]; name the field after what it is "
        f"(`origin_id=`, `bundle_id=`, `location_count=`):\n{listing}"
    )
