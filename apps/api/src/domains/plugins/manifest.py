"""Agent Plugins manifest (``plugin.json``) validation (§5, ADR-225).

Implements the closed-manifest contract of the Agent Plugins specification
v1.0.0 with its exactly-two non-fatal exceptions (§5.2): an unknown top-level
field and a non-object ``extensions`` field are reported and ignored; every
other schema violation is fatal and rejects the whole plugin.

Metadata fields are validated by JSON type only (§5.4) — a non-SemVer
``version`` or a non-URL ``homepage`` never rejects a manifest.
"""

import re
from typing import Any

from src.core.constants import (
    AGENT_PLUGINS_NAME_MAX_LENGTH,
    AGENT_PLUGINS_NAME_PATTERN,
    AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
)
from src.domains.plugins.schemas import (
    ManifestValidationResult,
    PluginAuthor,
    PluginIssue,
    PluginIssueCode,
    PluginManifest,
)

_ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
)
_STRING_METADATA_FIELDS = ("version", "description", "homepage", "repository", "license")
_AUTHOR_FIELDS = frozenset({"name", "email", "url"})
_NAME_RE = re.compile(AGENT_PLUGINS_NAME_PATTERN)


def is_valid_plugin_name(name: Any) -> bool:
    """Check a candidate plugin name against the §5.5 contract.

    Uses the official pattern from ``plugin.schema.json`` (proven equivalent
    to the normative text) plus the explicit 1-64 length bounds.

    Args:
        name: Candidate value (any type; non-strings are invalid).

    Returns:
        True when the name satisfies every §5.5 constraint.
    """
    return (
        isinstance(name, str)
        and 1 <= len(name) <= AGENT_PLUGINS_NAME_MAX_LENGTH
        and _NAME_RE.match(name) is not None
    )


def validate_plugin_manifest(raw: Any) -> ManifestValidationResult:
    """Validate a parsed ``plugin.json`` document against the v1.0.0 contract.

    Args:
        raw: The JSON-decoded document (any JSON value).

    Returns:
        A :class:`ManifestValidationResult`; ``valid=False`` means the plugin
        MUST be rejected entirely and none of its components discovered.
    """
    if not isinstance(raw, dict):
        return ManifestValidationResult(
            valid=False,
            errors=[PluginIssue(code=PluginIssueCode.MANIFEST_NOT_AN_OBJECT)],
        )

    data = dict(raw)
    warnings = _strip_unknown_fields(data)
    errors = _required_field_errors(data) + _metadata_type_errors(data)
    extensions, extension_errors = _validate_extensions(data.get("extensions"), warnings)
    errors += extension_errors

    author = data.get("author")
    if any(issue.field == "author" for issue in errors):
        author = None

    if errors:
        return ManifestValidationResult(valid=False, errors=errors, warnings=warnings)

    schema_id = data.get("$schema")
    name = data.get("name")
    keywords = data.get("keywords")
    manifest = PluginManifest(
        schema_id=str(schema_id),
        name=str(name),
        version=data.get("version"),
        description=data.get("description"),
        author=PluginAuthor(**author) if author else None,
        homepage=data.get("homepage"),
        repository=data.get("repository"),
        license=data.get("license"),
        keywords=list(keywords) if keywords else [],
        extensions=extensions,
    )
    return ManifestValidationResult(valid=True, manifest=manifest, warnings=warnings)


def _strip_unknown_fields(data: dict[str, Any]) -> list[PluginIssue]:
    """§5.2 non-fatal exception 1: unknown top-level fields → report and ignore."""
    warnings: list[PluginIssue] = []
    for field in sorted(set(data) - _ALLOWED_TOP_LEVEL_FIELDS):
        warnings.append(PluginIssue(code=PluginIssueCode.MANIFEST_UNKNOWN_FIELD, field=field))
        data.pop(field)
    return warnings


def _required_field_errors(data: dict[str, Any]) -> list[PluginIssue]:
    """§5.3: $schema selects the validation rules (never fetched), name is §5.5."""
    errors: list[PluginIssue] = []
    schema_id = data.get("$schema")
    if schema_id != AGENT_PLUGINS_PLUGIN_SCHEMA_ID:
        errors.append(
            PluginIssue(
                code=PluginIssueCode.MANIFEST_SCHEMA_UNSUPPORTED,
                field="$schema",
                detail=f"expected {AGENT_PLUGINS_PLUGIN_SCHEMA_ID}, got {schema_id!r}",
            )
        )
    name = data.get("name")
    if not is_valid_plugin_name(name):
        errors.append(
            PluginIssue(
                code=PluginIssueCode.MANIFEST_NAME_INVALID,
                field="name",
                detail=f"invalid plugin name: {name!r}",
            )
        )
    return errors


def _metadata_type_errors(data: dict[str, Any]) -> list[PluginIssue]:
    """§5.4: metadata fields are validated by JSON type only."""

    def invalid(field: str, detail: str) -> PluginIssue:
        return PluginIssue(code=PluginIssueCode.MANIFEST_FIELD_INVALID, field=field, detail=detail)

    errors: list[PluginIssue] = []
    for field in _STRING_METADATA_FIELDS:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(invalid(field, f"expected string, got {type(value).__name__}"))

    keywords = data.get("keywords")
    if keywords is not None and (
        not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords)
    ):
        errors.append(invalid("keywords", "expected array of strings"))

    author = data.get("author")
    if author is not None and (
        not isinstance(author, dict)
        or set(author) - _AUTHOR_FIELDS
        or any(not isinstance(v, str) for v in author.values())
    ):
        errors.append(invalid("author", "author object allows only string name/email/url"))
    return errors


def _validate_extensions(
    raw_extensions: Any, warnings: list[PluginIssue]
) -> tuple[dict[str, dict], list[PluginIssue]]:
    """§5.2/§8.1: a non-object extensions FIELD is reported and ignored; an
    object whose member value is not an object is an ordinary (fatal) schema
    violation."""
    if raw_extensions is None:
        return {}, []
    if not isinstance(raw_extensions, dict):
        warnings.append(
            PluginIssue(
                code=PluginIssueCode.MANIFEST_EXTENSIONS_NOT_OBJECT,
                field="extensions",
                detail=f"expected object, got {type(raw_extensions).__name__}",
            )
        )
        return {}, []
    flat_members = sorted(
        key for key, value in raw_extensions.items() if not isinstance(value, dict)
    )
    if flat_members:
        return {}, [
            PluginIssue(
                code=PluginIssueCode.MANIFEST_FIELD_INVALID,
                field="extensions",
                detail="extension namespace values must be objects: " + ", ".join(flat_members),
            )
        ]
    return raw_extensions, []
