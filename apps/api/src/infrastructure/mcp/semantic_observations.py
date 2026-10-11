"""Observe known usable value formats without replacing a received MCP value."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlsplit

from src.core.validators import validate_email
from src.infrastructure.mcp.json_schema import resolve_property
from src.infrastructure.mcp.semantic_schema import normalized_schema, output_fields_from_schema
from src.infrastructure.observability.metrics_mcp import mcp_semantic_unusable_values_total

_FORMATS = {"email_address": "email", "Date": "date", "datetime": "date-time", "URL": "uri"}
_MAX_PATHS = 64


def _descend(states: list[tuple[str, object]], token: str) -> list[tuple[str, object]]:
    children: list[tuple[str, object]] = []
    for path, value in states:
        if token == "[]" and isinstance(value, list):
            children.extend((f"{path}[{index}]", child) for index, child in enumerate(value))
        elif isinstance(value, dict) and token in value:
            children.append((f"{path}.{token}", value[token]))
    return children


def _path_values(payload: object, path: str) -> list[tuple[str, object]]:
    states = [("result", payload)]
    for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\[\]", path)[1:]:
        states = _descend(states, token)
    return states


def _child_schemas(
    spec: object, token: str, root: object, depth: int = 0
) -> list[dict[str, object]]:
    if not isinstance(spec, dict) or depth >= 8:
        return []
    branches = spec.get("anyOf", spec.get("oneOf"))
    if isinstance(branches, list):
        return [
            child for branch in branches for child in _child_schemas(branch, token, root, depth + 1)
        ]
    resolved = resolve_property(spec, root)
    if token == "[]":
        child = resolved.spec.get("items")
    else:
        properties = resolved.spec.get("properties")
        child = properties.get(token) if isinstance(properties, dict) else None
    if isinstance(child, dict):
        return [child]
    return []


def _allows_null_at_path(schema: object, path: str) -> bool:
    specs: list[object] = [normalized_schema(schema, schema)]
    for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\[\]", path)[1:]:
        specs = [child for spec in specs for child in _child_schemas(spec, token, schema)]
    return any(resolve_property(spec, schema).nullable for spec in specs)


def _usable(value: object, semantic_type: str) -> bool:
    if not isinstance(value, str):
        return False
    if semantic_type == "email_address":
        return validate_email(value)
    if semantic_type == "URL":
        return _usable_uri(value)
    return _usable_date(value, semantic_type)


def _usable_uri(value: str) -> bool:
    if re.search(r"\s|%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        return bool(urlsplit(value).scheme)
    except ValueError:
        return False


def _usable_date(value: str, semantic_type: str) -> bool:
    try:
        if semantic_type == "Date":
            return (
                bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
                and date.fromisoformat(value) is not None
            )
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value
        ):
            return False
        return datetime.fromisoformat(value.replace("z", "Z")).tzinfo is not None
    except ValueError:
        return False


@dataclass
class _Observations:
    paths: list[dict[str, str]] = field(default_factory=list)
    count: int = 0

    def record(self, path: str, semantic_type: str, value: object) -> None:
        if _usable(value, semantic_type):
            return
        reason = "invalid_format" if isinstance(value, str) else "invalid_type"
        self.count += 1
        mcp_semantic_unusable_values_total.labels(reason=reason).inc()
        if len(self.paths) < _MAX_PATHS:
            self.paths.append({"path": path, "semantic_type": semantic_type, "reason": reason})


def semantic_observation_data(payload: object, schema: object) -> dict[str, object]:
    """Published observations are read beside the full canonical result by both modes."""
    observations = _Observations()
    for declared in output_fields_from_schema(schema):
        semantic_type = declared.semantic_type
        if semantic_type not in _FORMATS or semantic_type is None or declared.type == "array":
            continue
        for path, value in _path_values(payload, declared.path):
            if value is None and _allows_null_at_path(schema, declared.path):
                continue
            observations.record(path, semantic_type, value)
    if not observations.count:
        return {}
    return {
        "mcp_semantic_observations": {
            "unusable_paths": observations.paths,
            "unusable_count": observations.count,
            "paths_truncated": observations.count > len(observations.paths),
        }
    }


def observation_notice(data: dict[str, object]) -> str:
    observation = data.get("mcp_semantic_observations")
    if not isinstance(observation, dict):
        return ""
    return (
        f"; {observation['unusable_count']} declared semantic values are unusable. "
        "Read mcp_semantic_observations before reusing typed fields; received values remain unchanged."
    )
