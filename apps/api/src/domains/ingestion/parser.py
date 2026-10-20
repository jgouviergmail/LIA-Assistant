"""Bounded Shortcuts envelopes with explicit compatibility for legacy health.

Errors carry only fixed codes and line numbers: input may contain access secrets.
Strict batches retain every position so an invalid element cannot disappear from
acknowledgement counts. Health keeps its historical dictionary-only projection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
from dataclasses import dataclass

from pydantic import JsonValue, TypeAdapter, ValidationError

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class IngestionBodyError(ValueError):
    """Safe diagnostic suitable for an external ingestion response."""

    def __init__(self, code: str, *, line: int | None = None) -> None:
        self.code = code
        self.line = line
        super().__init__(f"line {line} {code}" if line is not None else code)


@dataclass(frozen=True, slots=True)
class ParsedBody:
    items: tuple[JsonValue, ...]
    single: bool


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise IngestionBodyError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise IngestionBodyError("invalid_json_constant")


def _decode(text: str, *, strict: bool) -> JsonValue:
    if strict:
        return _JSON.validate_python(
            json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        )
    return _JSON.validate_python(json.loads(text))


def _items(values: list[JsonValue], *, legacy: bool) -> tuple[JsonValue, ...]:
    return tuple(value for value in values if not legacy or isinstance(value, dict))


def _ndjson(text: str, *, legacy: bool) -> ParsedBody:
    values: list[JsonValue] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            values.append(_decode(line, strict=not legacy))
        except (ValueError, RecursionError) as exc:
            code = exc.code if isinstance(exc, IngestionBodyError) else "not valid JSON"
            raise IngestionBodyError(code, line=line_no) from None
    return ParsedBody(_items(values, legacy=legacy), single=False)


def parse_body(
    raw_body: bytes,
    *,
    max_bytes: int | None = 256 * 1024,
    legacy_fields: frozenset[str] | None = None,
) -> ParsedBody:
    """Parse a singleton, array, data envelope, NDJSON or Shortcuts dictionary.

    ``legacy_fields`` explicitly selects health's historical shape policy. Its
    route owns the legacy byte limit; strict callers use the shared bound.
    """
    if max_bytes is not None and len(raw_body) > max_bytes:
        raise IngestionBodyError("body_too_large")
    try:
        text = raw_body.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise IngestionBodyError("body not valid UTF-8") from None
    if not text:
        raise IngestionBodyError("empty body")
    legacy = legacy_fields is not None
    try:
        parsed = _decode(text, strict=not legacy)
    except json.JSONDecodeError:
        return _ndjson(text, legacy=legacy)
    except IngestionBodyError:
        raise
    except ValidationError, RecursionError, ValueError:
        raise IngestionBodyError("invalid_json") from None
    return _shape(parsed, legacy_fields=legacy_fields)


def _shape(parsed: JsonValue, *, legacy_fields: frozenset[str] | None) -> ParsedBody:
    legacy = legacy_fields is not None
    if isinstance(parsed, list):
        return ParsedBody(_items(parsed, legacy=legacy), single=False)
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, list):
            if not legacy and len(parsed) != 1:
                raise IngestionBodyError("unsupported envelope fields")
            return ParsedBody(_items(data, legacy=legacy), single=False)
        if len(parsed) == 1:
            key = next(iter(parsed))
            if "\n" in key and not parsed[key]:
                return _ndjson(key, legacy=legacy)
        if legacy_fields is None or legacy_fields.issubset(parsed):
            return ParsedBody((parsed,), single=True)
    raise IngestionBodyError("unsupported payload shape")


async def read_bounded_body(chunks: AsyncIterable[bytes], *, max_bytes: int) -> bytes:
    """Stop a chunked request before accumulating bytes beyond the resource cap."""
    result = bytearray()
    async for chunk in chunks:
        if len(result) + len(chunk) > max_bytes:
            raise IngestionBodyError("body_too_large")
        result.extend(chunk)
    return bytes(result)
