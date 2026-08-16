"""Shared JSON extraction from model text (ADR-220, ex-F5).

One implementation for every "the model answered in text instead of JSON"
path. The historical delimiter (``find("{")`` / ``rfind("}")``) failed on
three everyday shapes — prose after the JSON containing a closing brace, a
JSON example at the end of the message, a trailing comma — and the JSON-mode
fallback used a bare ``json.loads`` with no recovery at all. Divergent copies
are how each new model quirk gets fixed in one place and stays broken in the
other; ``test_json_recovery.py`` carries the shared corpus.

Doctrine boundary: this module repairs what is mechanically repairable
(fences, balanced-slice extraction, truncation closure, trailing commas). It
never invents content — a repair that yields an empty object or array from an
incomplete slice is rejected, because "nothing" recovered from garbage is a
claim, not a repair.
"""

from __future__ import annotations

import json
import re

_FENCED_BLOCK = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)
_OPENERS = "{["
_CLOSER_FOR = {"{": "}", "[": "]"}


def extract_json_payload(text: str) -> str | None:
    """Extract a directly-``json.loads``-able payload from model text.

    Tries, in order: the body of each markdown code fence, then the raw text.
    Within each source, every ``{`` / ``[`` position is a candidate start —
    a brace that belongs to prose cannot poison the scan, the next candidate
    is simply tried.

    Args:
        text: Raw model output (prose, fences and payload mixed).

    Returns:
        A string that ``json.loads`` accepts verbatim, or ``None`` when no
        object or array could be recovered without inventing content.
    """
    text = text.strip()
    if not text:
        return None

    for source in _candidate_sources(text):
        payload = _scan_source(source)
        if payload is not None:
            return payload
    return None


def _candidate_sources(text: str) -> list[str]:
    """Fence bodies first (most specific), then the whole text."""
    sources = [match.group(1) for match in _FENCED_BLOCK.finditer(text)]
    if text.startswith("```") and not sources:
        # Opening fence without a closing one (truncated completion): the body
        # is everything after the fence line, minus a dangling closing fence.
        first_newline = text.find("\n")
        if first_newline != -1:
            sources.append(text[first_newline + 1 :].removesuffix("```"))
    sources.append(text)
    return sources


def _scan_source(source: str) -> str | None:
    """Try every opener position until one yields a loadable payload."""
    for start, char in enumerate(source):
        if char not in _OPENERS:
            continue
        candidate = _balanced_slice(source, start)
        if candidate is None:
            continue
        payload, was_repaired = candidate
        payload = _strip_trailing_commas(payload)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        # An incomplete slice repaired down to an empty container recovered
        # nothing: "][", a lone "[", a dangling "{" must all stay None.
        if was_repaired and parsed in ({}, []):
            continue
        return payload
    return None


def _balanced_slice(source: str, start: int) -> tuple[str, bool] | None:
    """The balanced JSON slice starting at ``start``, string-aware.

    Walks the text tracking string boundaries and escapes so braces inside
    string values never count. When the text ends before the structure closes
    (truncated completion), the open string is closed and the bracket stack
    unwound — flagged as repaired so degenerate recoveries can be rejected.

    Returns:
        ``(slice, was_repaired)``, or ``None`` on a malformed nesting.
    """
    stack: list[str] = []
    in_string = False
    escaped = False

    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in _OPENERS:
            stack.append(_CLOSER_FOR[char])
        elif char in "}]":
            if not stack or stack[-1] != char:
                return None  # mismatched nesting — not a JSON structure
            stack.pop()
            if not stack:
                return source[start : index + 1], False

    # End of text with the structure still open: mechanical truncation repair.
    repaired = source[start:].rstrip()
    if in_string:
        repaired += '"'
    repaired += "".join(reversed(stack))
    return repaired, True


def _strip_trailing_commas(payload: str) -> str:
    """Drop commas whose next significant character closes a container.

    String-aware on purpose: a ``", }"`` inside a string value is content and
    must survive (the regex approach of most healers corrupts it).
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(payload):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            out.append(char)
            continue
        if char == ",":
            next_index = index + 1
            while next_index < len(payload) and payload[next_index] in " \t\r\n":
                next_index += 1
            if next_index < len(payload) and payload[next_index] in "}]":
                continue  # trailing comma — drop it
        out.append(char)
    return "".join(out)
