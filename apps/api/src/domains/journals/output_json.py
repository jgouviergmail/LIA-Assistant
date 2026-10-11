"""Complete JSON decoding shared by journal mutation boundaries."""

import json
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def load_complete_json(raw: str, *, allow_fence: bool = False) -> Any:
    """Decode the entire payload without repair or silent duplicate-key replacement."""
    if allow_fence:
        lines = raw.strip().splitlines()
        if len(lines) >= 3 and lines[0].lower() in ("```", "```json") and lines[-1] == "```":
            raw = "\n".join(lines[1:-1])
    return json.loads(raw, object_pairs_hook=_unique_object)
