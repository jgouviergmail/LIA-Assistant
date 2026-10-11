"""Shared localized option projections and exact UI-name normalization.

The packaged vocabulary is generated from the actual UI translations. No
frontend filesystem, network, model call or translation heuristic at runtime.
"""

import unicodedata
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from src.core.i18n import resolve_language

_CATALOGUE = TypeAdapter(dict[str, dict[str, dict[str, str]]])
_VALUES = TypeAdapter(dict[str, JsonValue])
_STATIC_VOCABULARY_OPERATIONS = frozenset({"preferences.read", "assistant_preferences.read"})


@cache
def setting_choices() -> dict[str, dict[str, dict[str, str]]]:
    return _CATALOGUE.validate_json(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_setting_value(field: str, value: object) -> object:
    if not isinstance(value, str):
        return value
    translations = setting_choices().get(field)
    if translations is None or any(value in labels for labels in translations.values()):
        return value
    folded = _fold(value)
    matches = {
        identifier
        for labels in translations.values()
        for identifier, label in labels.items()
        if folded in {_fold(identifier), _fold(label)}
    }
    if len(matches) > 1:
        raise ValueError("Ambiguous setting label; select an offered value")
    return next(iter(matches)) if matches else value


def describe_setting_values(values: dict[str, JsonValue], language: str) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for field, value in values.items():
        boolean = type(value) is bool
        translated = setting_choices().get("__boolean__" if boolean else field)
        if translated is None:
            continue
        labels = translated[resolve_language(language)]
        result[field] = {
            "label": labels.get(str(value).lower() if boolean else str(value), str(value)),
            "options": [
                {
                    "value": (identifier == "true") if boolean else identifier,
                    "label": label,
                }
                for identifier, label in labels.items()
            ],
        }
    return result


def with_read_setting_labels(output: object, *, tool_name: str | None = None) -> object:
    """Uniform display projection for native settings reads; original data stays intact."""
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.context.runtime_context import runtime_context_if_running
    from src.domains.agents.tools.output import UnifiedToolOutput

    if not isinstance(output, UnifiedToolOutput) or not output.success:
        return output
    if "setting_choices" in output.structured_data:
        return output
    context = runtime_context_if_running()
    values = _read_values(output.structured_data)
    operation = APPLICATION_OPERATIONS.get_by_tool_name(tool_name) if tool_name else None
    if operation is None or operation.operation_id not in _STATIC_VOCABULARY_OPERATIONS:
        # Equal field names do not imply equal domains (account/transcription
        # languages differ). Only Boolean labels are universal to these reads.
        values = {field: value for field, value in values.items() if type(value) is bool}
    descriptions = describe_setting_values(
        values, resolve_language(context.language if context else None)
    )
    if not descriptions:
        return output
    return output.model_copy(
        update={
            "structured_data": {
                **output.structured_data,
                "setting_choices": descriptions,
            }
        }
    )


def _read_values(data: Mapping[str, object]) -> dict[str, JsonValue]:
    values: dict[str, JsonValue] = {}
    for key in ("settings", "preferences"):
        group = data.get(key)
        if isinstance(group, dict):
            fields = group.get("values", group)
            if isinstance(fields, dict):
                try:
                    values.update(_VALUES.validate_python(fields))
                except ValidationError:
                    continue  # Display enrichment never breaks an otherwise usable source read.
    return values
