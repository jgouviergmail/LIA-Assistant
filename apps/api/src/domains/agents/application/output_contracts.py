"""Model-facing metadata comes from public projections, never private witnesses."""

from collections.abc import Mapping

from pydantic import BaseModel

from src.domains.agents.registry.catalogue import OutputFieldSchema


def pending_application_output_fields() -> list[OutputFieldSchema]:
    return [
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending exact human confirmation; no action has executed.",
        )
    ]


def _types(value: object, definitions: Mapping[str, object]) -> set[str]:
    if not isinstance(value, dict):
        return set()
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        return _types(definitions.get(reference.removeprefix("#/$defs/")), {})
    kind = value.get("type")
    if isinstance(kind, str):
        return {kind}
    alternatives = value.get("anyOf", value.get("oneOf", []))
    if not isinstance(alternatives, list):
        return set()
    return {kind for alternative in alternatives for kind in _types(alternative, definitions)}


def projection_output_fields(model: type[BaseModel]) -> list[OutputFieldSchema]:
    """Publish the exact top-level fields of the serialized public projection."""
    schema = model.model_json_schema(mode="serialization")
    definitions = schema.get("$defs", {})
    fields: list[OutputFieldSchema] = []
    for name, field in schema.get("properties", {}).items():
        kinds = _types(field, definitions)
        concrete = kinds - {"null"}
        fields.append(
            OutputFieldSchema(
                path=name,
                type=next(iter(concrete)) if len(concrete) == 1 else "any",
                nullable="null" in kinds,
                description=field.get("description") or field.get("title") or name,
            )
        )
    if not fields:
        raise ValueError("A public read projection must declare serialized fields")
    return fields
