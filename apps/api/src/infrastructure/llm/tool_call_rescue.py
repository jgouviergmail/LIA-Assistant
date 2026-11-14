"""Recover a tool call the parser or the schema refused for a mechanical reason.

Five shapes, each a complete answer a door threw away:

- **Nulls where the schema has a default** (production 2026-09-05,
  ``deepseek-v4-flash``, a complete minutes payload, ``"bullets": null`` on a
  paragraph section, three identical rejections). A model that fills every
  property writes ``null`` where it has nothing to say, and Pydantic refuses
  ``null`` on a ``list[str]`` field even when the field has a default. The rule
  is structural, never per schema: a ``null`` under a key whose field HAS a
  default and does NOT admit ``None`` is the model's spelling of « absent » and
  the key is dropped so the default applies; a ``null`` on an Optional field is
  a value and stays; a ``null`` on a required field is an error and stays.
  Nested models and lists of models are walked the same way.
- **An undeclared key that says nothing** (dev 2026-10-22, Haiku 5.5 with
  thinking on the auto-tool door, ``"source_quote_note": ""`` inside a requested
  outcome: the whole query analysis was refused). On a model that FORBIDS extras,
  an undeclared key whose value is null, blank or an empty collection is
  dropped: nothing could read it. A key that says something stays, because it
  may be a declared field misspelled, and dropping it would let a default
  replace what the model meant. Where extras are ignored Pydantic drops the key
  itself; where they are allowed the key is data.
- **A bare word where a JSON string belongs** (dev replay 2026-09-20,
  ``deepseek-flash``, ``"primary_domain": mcp`` on 11 of 24 query-analyzer
  calls; production lost 4 of 26 analyses in 48 h to it). LangChain cannot parse
  the arguments, files the call under ``invalid_tool_calls`` with ``tool_calls``
  EMPTY, and the door read « no tool call, empty answer » — a wrong diagnosis
  of a complete answer, which cost the whole turn (the analyzer's fallback is a
  bare conversation). What is mechanically repairable is repaired before
  validation (ADR-184): a bare token in VALUE position, outside any string, is
  quoted; nothing else moves. A truncated answer is never rescued here — the
  door consults ADR-275's verdict before it reaches this module.
- **A bracket that closes nothing** (bench 2026-11-13, a fast model without
  reasoning, a long report: three of ten calls refused, « Extra data »). The
  arguments held a whole value, valid against the schema, then one ``}``. Only
  brackets may follow the value for it to be kept: they carry nothing, while
  anything else may be content.
- **A structure written as text** (bench 2026-11-13, a reasoning model through
  the auto-tool door, a workbook: 4 of 9 lost, each refusal paid up to three
  times). Where the schema expects a list or an object, the model wrote JSON
  TEXT — and stopped it between two values, writing the rest of the open object
  (``columns``, ``chart``) as keys of the call itself. The text is read back
  (``json_recovery.close_cut_structure``: only the brackets it owes are added,
  never after a cut inside a string), and each key the call's schema does not
  declare goes back into the innermost object the text left open whose schema
  declares it — nothing is guessed: what fits nowhere stays where it was. The
  same text may also close once too often (a third model, the same day: 5 of
  its 7 refusals in 8 workbooks): the whole value is kept, as for a call.
  Strict tool use, which would prevent the defect at the source, holds a
  request to 24 optional parameters across its strict tools: two of the three
  document schemas declare 33 and 36, and the door never bends a schema to fit
  (``strict_schema``).
"""

from __future__ import annotations

import json
import types
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from src.infrastructure.llm.json_recovery import close_cut_structure, drop_trailing_closers
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: How a repair settled a refused answer — an ``outcome`` of
#: ``llm_structured_output_outcomes_total`` (the doors add ``parsed`` and ``truncated``).
RepairOutcome = Literal[
    "absent_values_dropped",
    "structures_decoded",
    "invalid_call_repaired",
    "text_rescued",
    "rejected",
]

#: Paths listed in a rejection reason before the list is cut (a log line, not a report).
_REASON_PATHS_MAX = 8

#: Bare tokens JSON itself accepts in value position — never quoted.
_JSON_LITERALS = frozenset({"true", "false", "null", "NaN", "Infinity"})

#: Characters a bare token may carry (``mcp_excalidraw``, ``gemini-3.6``, ``v1.2``).
_BARE_TOKEN_CHARS = frozenset("_-.")

#: The parser's own words, kept out of a log line that would otherwise carry the payload.
_REASON_DETAIL_MAX = 120


def _admits_none(annotation: Any) -> bool:
    """Whether ``None`` is a legitimate value for this annotation."""
    if annotation is Any or annotation is None or annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return any(_admits_none(arg) for arg in get_args(annotation))
    return False


def _model_of(annotation: Any) -> type[BaseModel] | None:
    """The BaseModel behind ``Model`` or ``Model | None``, if any."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        for arg in get_args(annotation):
            model = _model_of(arg)
            if model is not None:
                return model
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _item_annotation(annotation: Any) -> Any:
    """What one item of ``list[X]`` / ``Sequence[X]`` is (Optional tolerated), or ``None``."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        for arg in get_args(annotation):
            item = _item_annotation(arg)
            if item is not None:
                return item
        return None
    if origin in (list, Sequence, tuple) or (
        isinstance(origin, type) and issubclass(origin, Sequence)
    ):
        args = get_args(annotation)
        return args[0] if args else None
    return None


def _list_item_model(annotation: Any) -> type[BaseModel] | None:
    """The BaseModel behind ``list[Model]`` / ``Sequence[Model]`` (Optional tolerated)."""
    item = _item_annotation(annotation)
    return _model_of(item) if item is not None else None


@dataclass(frozen=True, slots=True)
class AbsentValues:
    """What a payload spelled « absent » and the normaliser removed, by shape."""

    nulls: int = 0
    extras: int = 0

    @property
    def total(self) -> int:
        """Every key removed, whatever its shape."""
        return self.nulls + self.extras

    def __add__(self, other: AbsentValues) -> AbsentValues:
        return AbsentValues(self.nulls + other.nulls, self.extras + other.extras)


def _declared_field(schema: type[BaseModel], key: str) -> FieldInfo | None:
    """The field ``key`` names: by its name, or by a string alias it validates under."""
    field = schema.model_fields.get(key)
    if field is not None:
        return field
    for candidate in schema.model_fields.values():
        if key in (candidate.alias, candidate.validation_alias):
            return candidate
    return None


def _says_nothing(value: Any) -> bool:
    """Whether a value carries nothing to read: null, blank text, an empty collection."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, list | dict) and not value


def _cleaned_value(annotation: Any, value: Any) -> tuple[Any, AbsentValues]:
    """``value`` with the absent values of the model(s) its annotation names removed."""
    nested = _model_of(annotation)
    if nested is not None and isinstance(value, dict):
        return drop_absent_values(nested, value)
    item_model = _list_item_model(annotation)
    if item_model is None or not isinstance(value, list):
        return value, AbsentValues()
    absent = AbsentValues()
    items: list[Any] = []
    for item in value:
        item, found = drop_absent_values(item_model, item)
        absent += found
        items.append(item)
    return items, absent


def drop_absent_values(schema: type[BaseModel], payload: Any) -> tuple[Any, AbsentValues]:
    """A copy of ``payload`` without the values that only spell « absent ».

    The two shapes of the module docstring: a ``null`` that ``schema`` would
    default, and an undeclared key that says nothing on a model forbidding extras.

    Args:
        schema: The Pydantic model the payload is meant for.
        payload: The model's arguments (anything that is not a dict comes back as is).

    Returns:
        ``(payload, absent)`` — the cleaned copy and what was removed.
    """
    if not isinstance(payload, dict):
        return payload, AbsentValues()
    forbids_extras = schema.model_config.get("extra") == "forbid"
    absent = AbsentValues()
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        field = _declared_field(schema, key)
        if field is None:
            if forbids_extras and _says_nothing(value):
                absent += AbsentValues(extras=1)
                continue
            cleaned[key] = value
        elif value is None:
            if not field.is_required() and not _admits_none(field.annotation):
                absent += AbsentValues(nulls=1)
                continue
            cleaned[key] = value
        else:
            cleaned[key], found = _cleaned_value(field.annotation, value)
            absent += found
    return cleaned, absent


def validate_without_absent_values[T: BaseModel](
    schema: type[T], payload: Any
) -> tuple[T, AbsentValues]:
    """Validate ``payload`` against ``schema`` once its absent values are removed.

    Raises:
        ValidationError: When the payload is still invalid once they are gone.
    """
    cleaned, absent = drop_absent_values(schema, payload)
    return schema.model_validate(cleaned), absent


def rescue_payload[T: BaseModel](schema: type[T], payload: Any) -> tuple[T | None, AbsentValues]:
    """``payload`` validated once its absent values are removed — if that is the repair.

    Answers only for what it changed: a payload with nothing absent was the
    parser's verdict to keep, and one still invalid once cleaned is not rescued.

    Returns:
        ``(instance, absent)``, or ``(None, AbsentValues())`` when nothing was rescued.
    """
    cleaned, absent = drop_absent_values(schema, payload)
    if not absent.total:
        return None, AbsentValues()
    try:
        return schema.model_validate(cleaned), absent
    except ValidationError:
        return None, AbsentValues()


def rescue_tool_call[T: BaseModel](
    raw_message: Any, schema: type[T]
) -> tuple[T | None, AbsentValues]:
    """The first tool call of ``raw_message`` validated once its absent values are removed.

    Returns:
        ``(instance, absent)``, or ``(None, AbsentValues())`` when nothing was rescued.
    """
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    if not tool_calls:
        return None, AbsentValues()
    return rescue_payload(schema, tool_calls[0].get("args"))


def log_absent_values_dropped(provider: str, schema_name: str, absent: AbsentValues) -> None:
    """The one log line every door writes when the absent values made an answer valid."""
    logger.warning(
        "structured_output_absent_values_dropped",
        provider=provider,
        schema=schema_name,
        nulls_defaulted=absent.nulls,
        empty_extras_dropped=absent.extras,
    )


# ---------------------------------------------------------------------------
# A structure written as text
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TextStructures:
    """What a parsed call wrote as text where its schema expects a structure, read back."""

    decoded: int = 0
    closed: int = 0
    rehomed: int = 0
    closers: int = 0

    def __add__(self, other: TextStructures) -> TextStructures:
        return TextStructures(
            self.decoded + other.decoded,
            self.closed + other.closed,
            self.rehomed + other.rehomed,
            self.closers + other.closers,
        )


_Kind = type[list[Any]] | type[dict[str, Any]]


def _union_kind(members: tuple[Any, ...]) -> _Kind | None:
    """The one structure a union expects — none when one of its members is a text."""
    members = tuple(member for member in members if member is not type(None))
    if any(member in (str, Any) for member in members):
        return None  # a text is a value of this field: never read it as JSON
    kinds = {kind for member in members if (kind := _structure_kind(member)) is not None}
    return kinds.pop() if len(kinds) == 1 else None


def _structure_kind(annotation: Any) -> _Kind | None:
    """``list`` or ``dict`` when the annotation expects that structure and admits no text."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return _union_kind(get_args(annotation))
    if _model_of(annotation) is not None or dict in (origin, annotation):
        return dict
    if origin in (list, tuple, Sequence) or annotation in (list, tuple):
        return list
    return None


def _open_objects(
    value: Any, annotation: Any, depth: int
) -> list[tuple[dict[str, Any], type[BaseModel]]]:
    """The objects a text left open, outermost first, each with the model it is meant for.

    The text stopped inside its last element at every level: the last item of a
    list, the value of the last key of an object.
    """
    objects: list[tuple[dict[str, Any], type[BaseModel]]] = []
    node, hint = value, annotation
    for _level in range(depth):
        if isinstance(node, dict) and (model := _model_of(hint)) is not None:
            objects.append((node, model))
            last = next(reversed(node), None)
            field = _declared_field(model, last) if last is not None else None
            if last is None or field is None:
                break
            node, hint = node[last], field.annotation
        elif isinstance(node, list) and node:
            node, hint = node[-1], _item_annotation(hint)
        else:
            break
    return objects


def _rehome(
    value: Any, annotation: Any, depth: int, siblings: dict[str, Any], schema: type[BaseModel]
) -> int:
    """Put back the keys written beside a cut structure into the object they continue.

    A key the schema of ``siblings`` does not declare goes into the innermost
    object the text left open whose model declares it and lacks it; a key that
    fits nowhere stays where the model wrote it.
    """
    objects = _open_objects(value, annotation, depth)
    moved = 0
    for key in [key for key in siblings if _declared_field(schema, key) is None]:
        for target, model in reversed(objects):
            if key not in target and _declared_field(model, key) is not None:
                target[key] = siblings.pop(key)
                moved += 1
                break
    return moved


def _read_text(
    annotation: Any, text: str, siblings: dict[str, Any], schema: type[BaseModel] | None
) -> tuple[Any, TextStructures]:
    """A value written as JSON text where ``annotation`` expects a structure, read back.

    A whole value followed by brackets only keeps the value; a value cut between
    two values is closed, and what was written beside it put back.
    """
    kind = _structure_kind(annotation)
    if kind is None:
        return text, TextStructures()
    whole, closers = drop_trailing_closers(text)
    cut = close_cut_structure(whole)
    if cut is None:
        return text, TextStructures()
    closed, depth = cut
    value = json.loads(closed)
    if not isinstance(value, kind):
        return text, TextStructures()
    rehomed = _rehome(value, annotation, depth, siblings, schema) if depth and schema else 0
    return value, TextStructures(decoded=1, closed=int(depth > 0), rehomed=rehomed, closers=closers)


def _decoded_value(annotation: Any, value: Any) -> tuple[Any, TextStructures]:
    """``value`` with the structures its nested model(s) received as text read back."""
    model = _model_of(annotation)
    if model is not None and isinstance(value, dict):
        return decode_text_structures(model, value)
    item = _item_annotation(annotation)
    if item is None or not isinstance(value, list):
        return value, TextStructures()
    found = TextStructures()
    items: list[Any] = []
    for element in value:
        if isinstance(element, str):
            element, read = _read_text(item, element, {}, None)
            found += read
        element, nested = _decoded_value(item, element)
        found += nested
        items.append(element)
    return items, found


def decode_text_structures(schema: type[BaseModel], payload: Any) -> tuple[Any, TextStructures]:
    """A copy of ``payload`` with every structure written as JSON text read back.

    Only where ``schema`` expects a list or an object and admits no text; nested
    models and lists of models are walked the same way. A text the model stopped
    between two values is closed, and the keys it wrote beside it go back into
    the object they continue (module docstring).

    Args:
        schema: The Pydantic model the payload is meant for.
        payload: The model's arguments (anything that is not a dict comes back as is).

    Returns:
        ``(payload, found)`` — the copy and what was read back.
    """
    if not isinstance(payload, dict):
        return payload, TextStructures()
    out = dict(payload)
    found = TextStructures()
    for key, value in payload.items():
        field = _declared_field(schema, key)
        if field is None:
            continue
        if isinstance(value, str):
            value, read = _read_text(field.annotation, value, out, schema)
            found += read
        out[key], nested = _decoded_value(field.annotation, value)
        found += nested
    return out, found


def rescue_text_structures[T: BaseModel](
    raw_message: Any, schema: type[T]
) -> tuple[T | None, TextStructures]:
    """The first tool call of ``raw_message``, validated once its text structures are read.

    Answers only for what it changed, its absent values removed on the way.

    Returns:
        ``(instance, found)``, or ``(None, TextStructures())`` when nothing was rescued.
    """
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    if not tool_calls:
        return None, TextStructures()
    payload, found = decode_text_structures(schema, tool_calls[0].get("args"))
    if not found.decoded:
        return None, TextStructures()
    try:
        instance, _absent = validate_without_absent_values(schema, payload)
    except ValidationError:
        return None, TextStructures()
    return instance, found


def repair_refused_answer[T: BaseModel](
    raw_message: Any, schema: type[T], provider: str, schema_name: str
) -> tuple[T | None, RepairOutcome]:
    """The first mechanical repair that makes a refused answer valid (ADR-184, ADR-100).

    ONE chain for every door that receives a message, in this order: the absent
    values of a parsed call, its structures written as text, the bare words and
    the closing brackets of a call the parser refused, an object written as
    text. The caller has consulted the truncation verdict first (ADR-275): a cut
    answer must never reach a repair, which would close it into a shorter object
    announced as complete.

    Args:
        raw_message: The ``AIMessage`` the model returned (``None`` tolerated).
        schema: Target Pydantic schema.
        provider: Provider name (logging only).
        schema_name: Schema name (logging only).

    Returns:
        ``(instance, outcome)``, or ``(None, "rejected")`` when nothing applies.
    """
    instance, absent = rescue_tool_call(raw_message, schema)
    if instance is not None:
        log_absent_values_dropped(provider, schema_name, absent)
        return instance, "absent_values_dropped"
    decoded, found = rescue_text_structures(raw_message, schema)
    if decoded is not None:
        logger.warning(
            "structured_output_text_structures_decoded",
            provider=provider,
            schema=schema_name,
            decoded=found.decoded,
            closed=found.closed,
            rehomed=found.rehomed,
            closers_dropped=found.closers,
        )
        return decoded, "structures_decoded"
    repaired, call = rescue_invalid_tool_call(raw_message, schema)
    if repaired is not None:
        logger.warning(
            "structured_output_invalid_call_repaired",
            provider=provider,
            schema=schema_name,
            quoted=call.quoted,
            closers_dropped=call.closers,
        )
        return repaired, "invalid_call_repaired"
    rescued = rescue_from_text(raw_message, schema, provider, schema_name)
    if rescued is not None:
        return rescued, "text_rescued"
    return None, "rejected"


def _string_end(text: str, start: int) -> int:
    """Index just past the string opened at ``start`` (escapes honoured, EOF tolerated)."""
    j = start + 1
    while j < len(text) and text[j] != '"':
        j += 2 if text[j] == "\\" else 1
    return j + 1


def _bare_token(text: str, start: int) -> tuple[str, int, bool]:
    """The bare token at ``start``, where it ends, and whether it needs quoting.

    A token is quoted when it is not a JSON literal and the next non-space
    character closes its value — quoting anything else would only move the
    syntax error.
    """
    j = start
    while j < len(text) and (text[j].isalnum() or text[j] in _BARE_TOKEN_CHARS):
        j += 1
    word = text[start:j]
    k = j
    while k < len(text) and text[k].isspace():
        k += 1
    closes = k >= len(text) or text[k] in ",}]"
    return word, j, word not in _JSON_LITERALS and closes


def _opens_value(char: str, stack: list[str]) -> bool | None:
    """Whether ``char`` opens a value position, or None when it says nothing about it.

    ``:`` does inside an object, ``[`` and ``,`` inside an array; a closing
    bracket ends one. The stack is updated for the brackets.
    """
    if char in "{[":
        stack.append(char)
        return char == "["
    if char in "}]":
        if stack:
            stack.pop()
        return False
    if char == ":":
        return bool(stack) and stack[-1] == "{"
    if char == ",":
        return bool(stack) and stack[-1] == "["
    return None


def quote_bare_values(text: str) -> tuple[str, int]:
    """``text`` with every bare token in JSON value position quoted.

    A value position is what follows ``:`` inside an object, or ``[`` / ``,``
    inside an array. Strings are skipped whole (escapes honoured), so a colon
    or a comma INSIDE a string never opens a value position. JSON's own bare
    literals and numbers are left alone; a bare token that is not followed by
    the end of its value (``,``, ``}``, ``]`` or the end of the text) is left
    alone too, because quoting it would only move the syntax error.

    Args:
        text: The arguments a tool call carried, as the provider spelled them.

    Returns:
        ``(text, quoted)`` — the repaired text and how many tokens were quoted.
    """
    out: list[str] = []
    stack: list[str] = []
    quoted = 0
    expect_value = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            end = _string_end(text, i)
            out.append(text[i:end])
            i, expect_value = end, False
            continue
        if expect_value and (ch.isalpha() or ch == "_"):
            word, end, quote = _bare_token(text, i)
            out.append(f'"{word}"' if quote else word)
            quoted += int(quote)
            i, expect_value = end, False
            continue
        opens = _opens_value(ch, stack)
        if opens is not None:
            expect_value = opens
        elif not ch.isspace():
            expect_value = False
        out.append(ch)
        i += 1
    return "".join(out), quoted


def rescue_from_text[T: BaseModel](
    raw_message: Any,
    schema: type[T],
    provider: str,
    schema_name: str,
) -> T | None:
    """Salvage a structured output from a model that answered in text.

    Some models resolve the conflict between a forced tool call and prompt
    instructions by answering with raw JSON text instead of calling the tool
    (observed on deepseek-v4-flash with legacy "Output JSON only" prompts —
    audit D5, ADR-100). When ``with_structured_output(include_raw=True)``
    yields no parsed object, this helper tries to recover the payload from the
    raw ``AIMessage`` content before the caller gives up.

    Args:
        raw_message: The raw ``AIMessage`` returned by the model (``None``
            tolerated — returns ``None``).
        schema: Target Pydantic schema.
        provider: Provider name (logging only).
        schema_name: Schema name (logging only).

    Returns:
        A validated schema instance, or ``None`` when no JSON object could
        be extracted and validated from the text content.
    """
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    if not text:
        return None

    # Shared extraction (ADR-220): fences, prose on either side, truncation
    # and trailing commas are handled in ONE place — json_recovery carries the
    # corpus the old find("{")/rfind("}") delimiter failed on.
    from src.infrastructure.llm.json_recovery import extract_json_payload

    payload_text = extract_json_payload(text)
    if payload_text is None:
        return None

    try:
        instance, _absent = validate_without_absent_values(schema, json.loads(payload_text))
    except json.JSONDecodeError, ValidationError:
        return None

    logger.warning(
        "structured_output_rescued_from_text",
        provider=provider,
        schema=schema_name,
        msg="Model answered in raw JSON text instead of calling the forced tool — "
        "payload salvaged; check the prompt for legacy 'output JSON' instructions",
    )
    return instance


def _first_invalid_call(raw_message: Any) -> dict[str, Any] | None:
    calls = getattr(raw_message, "invalid_tool_calls", None) or []
    first = calls[0] if calls else None
    return first if isinstance(first, dict) else None


def invalid_call_arguments(raw_message: Any) -> str:
    """The arguments of the first call the parser refused, for a diagnosis to read."""
    call = _first_invalid_call(raw_message)
    args = call.get("args") if call else None
    return args if isinstance(args, str) else ""


@dataclass(frozen=True, slots=True)
class CallRepair:
    """What a refused call's arguments needed to parse: bare words quoted, brackets dropped."""

    quoted: int = 0
    closers: int = 0


def rescue_invalid_tool_call[T: BaseModel](
    raw_message: Any, schema: type[T]
) -> tuple[T | None, CallRepair]:
    """The first call the parser refused, validated once its text is mechanically repaired.

    Its bare values are quoted, then the brackets that close nothing after a
    whole value are dropped. Answers only for what it changed: arguments that
    need neither are the parser's verdict to keep, and a payload the schema
    still refuses once it parses is not rescued. The payload's absent values
    are removed on the way, as for a parsed call.

    Returns:
        ``(instance, repair)``, or ``(None, CallRepair())`` when nothing was rescued.
    """
    arguments = invalid_call_arguments(raw_message)
    if not arguments:
        return None, CallRepair()
    quoted_text, quoted = quote_bare_values(arguments)
    repaired, closers = drop_trailing_closers(quoted_text)
    if not (quoted or closers):
        return None, CallRepair()
    try:
        instance, _absent = validate_without_absent_values(schema, json.loads(repaired))
    except ValueError, ValidationError:
        return None, CallRepair()
    return instance, CallRepair(quoted=quoted, closers=closers)


def refusal_verdict(raw_message: Any, parsing_error: BaseException | None) -> str:
    """Why a structured answer yielded nothing, in facts a log line may carry.

    A rejected tool call is named as such, with the schema paths that failed,
    and a call whose arguments the parser refused is named too, with the
    parser's own verdict; neither is ever reported as « no tool call ». No
    value the model wrote is ever quoted: the result is logged above DEBUG.
    """
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    if tool_calls:
        if isinstance(parsing_error, ValidationError):
            errors = parsing_error.errors()
            paths = ", ".join(
                ".".join(str(part) for part in error["loc"]) for error in errors[:_REASON_PATHS_MAX]
            )
            return f"tool call rejected by schema ({len(errors)} errors: {paths})"
        kind = type(parsing_error).__name__ if parsing_error is not None else "unparsed"
        return f"tool call rejected ({kind})"
    invalid = _first_invalid_call(raw_message)
    if invalid is not None:
        # LangChain's message ends with the parser's verdict after « Received »;
        # everything before it is the payload, which does not belong in a log
        # line — and an error with no verdict is the payload alone (ADR-317).
        error = str(invalid.get("error") or "")
        detail = error.rsplit("Received ", 1)[-1].strip() if "Received " in error else ""
        detail = detail[:_REASON_DETAIL_MAX]
        suffix = f" ({detail})" if detail else ""
        return f"tool call arguments not valid JSON{suffix}"
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    return "no tool call, text rescue failed" if text else "no tool call, empty answer"
