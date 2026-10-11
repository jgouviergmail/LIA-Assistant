"""Collect executable reference strings, including nested batch parameters."""

import re
from collections.abc import Iterator, Mapping

_STEP = re.compile(r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)")
_EMBEDDED_STEP = re.compile(r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.[a-zA-Z_]")


def step_reference_ids(value: str) -> tuple[str, ...]:
    """A bare prefix mentioned inside prose is not an executable field reference."""
    matches = _STEP.findall(value) if value.startswith("$steps.") else _EMBEDDED_STEP.findall(value)
    return tuple(dict.fromkeys(matches))


def parameter_strings(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    """Use the executor's recursive argument shape rather than top-level strings only."""
    if isinstance(value, str):
        yield f"parameter '{path}'", value
    elif isinstance(value, Mapping):
        for name, child in value.items():
            yield from parameter_strings(child, f"{path}.{name}" if path else str(name))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from parameter_strings(child, f"{path}[{index}]")
