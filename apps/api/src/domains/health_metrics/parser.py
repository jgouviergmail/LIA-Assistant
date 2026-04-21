"""Flexible body parser for the Health Metrics ingestion endpoints.

iOS Shortcuts produces different envelope shapes depending on how the
Raccourci is authored (Dictionnaire vs Texte vs Liste). To stay robust
across all iOS versions and user setups, the ingestion endpoints accept
the raw body through this parser, which recognizes four shapes:

1. **iOS Shortcuts "Dictionnaire" wrapping** — the NDJSON blob is stored
   as the single key of an outer dict with an empty-dict value::

       {"{\\"date_start\\":…}\\n{\\"date_start\\":…}\\n…": {}}

   → we extract the single key (detected by its newline content) and
   parse each line as a JSON object.

2. **Newline-delimited JSON (NDJSON)** — each line is a standalone JSON
   object::

       {"date_start":…}
       {"date_start":…}

3. **JSON array** — a canonical array of samples::

       [{"date_start":…}, {"date_start":…}]

4. **JSON wrapper** — classic ``{"data": [...]}`` envelope::

       {"data": [{"date_start":…}, …]}

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-21
"""

from __future__ import annotations

import json
from typing import Any


class HealthSamplesBodyParseError(ValueError):
    """Raised when the ingestion body cannot be interpreted as a sample batch."""


def parse_samples_body(raw_body: bytes) -> list[dict[str, Any]]:
    """Extract a list of sample dicts from the raw HTTP body.

    Accepts four envelope shapes (see module docstring). The returned list
    is NOT validated against the per-kind schema — that validation happens
    in the service layer so each sample can be rejected individually with
    its index.

    Args:
        raw_body: Request body bytes as received by FastAPI.

    Returns:
        A list of raw sample dicts.

    Raises:
        HealthSamplesBodyParseError: If the body is empty or cannot be
            interpreted as any of the supported shapes.
    """
    try:
        text = raw_body.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise HealthSamplesBodyParseError(f"body not valid UTF-8: {exc}") from exc
    if not text:
        raise HealthSamplesBodyParseError("empty body")

    # Fast path: try a single JSON parse first.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: try NDJSON (multiple JSON objects on separate lines).
        return _parse_ndjson_lines(text)

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    if isinstance(parsed, dict):
        # Shape 4: {"data": [...]}
        data = parsed.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        # Shape 1: iOS Shortcuts wrapping — {"<ndjson_blob>": {}}
        # Heuristic: a single key whose content contains at least one newline
        # and whose value is empty / matches the iOS pattern.
        if len(parsed) == 1:
            only_key = next(iter(parsed.keys()))
            only_value = parsed[only_key]
            if isinstance(only_key, str) and "\n" in only_key and not only_value:
                return _parse_ndjson_lines(only_key)

        # Shape "single sample wrapped" — a dict that actually looks like a
        # sample on its own. Detected by presence of date_start / date_end.
        if "date_start" in parsed and "date_end" in parsed:
            return [parsed]

    raise HealthSamplesBodyParseError(f"unsupported payload shape: {type(parsed).__name__}")


def _parse_ndjson_lines(text: str) -> list[dict[str, Any]]:
    """Parse a block of newline-delimited JSON objects.

    Args:
        text: Text where each non-empty line is a standalone JSON object.

    Returns:
        A list of dicts (non-dict lines are silently skipped).

    Raises:
        HealthSamplesBodyParseError: If any non-empty line fails to parse
            as JSON (we surface the line number for debugging).
    """
    samples: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise HealthSamplesBodyParseError(f"line {line_no} not valid JSON: {exc.msg}") from exc
        if isinstance(obj, dict):
            samples.append(obj)
    return samples
