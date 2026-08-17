"""Unit tests for Agent Plugins manifest validation (ADR-225).

Covers the normative requirements of the Agent Plugins specification v1.0.0
sections 5 (Manifest) and 8.1 (Manifest extension data):

- closed schema with exactly two non-fatal exceptions (unknown top-level
  field, non-object ``extensions``) — everything else is fatal;
- required ``$schema`` (canonical identifier, never fetched) and ``name``
  (official name pattern from plugin.schema.json);
- metadata fields validated by JSON type only (a non-semver ``version`` or a
  non-URL ``homepage`` MUST NOT be rejected).

The valid/invalid name fixtures are the specification's own examples (§5.5).
"""

from typing import Any

import pytest

from src.core.constants import AGENT_PLUGINS_PLUGIN_SCHEMA_ID
from src.domains.plugins.manifest import validate_plugin_manifest
from src.domains.plugins.schemas import PluginIssueCode


def _minimal(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid manifest dict, with optional field overrides."""
    manifest: dict[str, Any] = {
        "$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID,
        "name": "my-plugin",
    }
    manifest.update(overrides)
    return manifest


class TestValidManifests:
    def test_minimal_manifest_is_valid(self) -> None:
        result = validate_plugin_manifest(_minimal())

        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.manifest is not None
        assert result.manifest.name == "my-plugin"
        assert result.manifest.schema_id == AGENT_PLUGINS_PLUGIN_SCHEMA_ID

    def test_full_manifest_parses_every_metadata_field(self) -> None:
        result = validate_plugin_manifest(
            _minimal(
                version="1.2.0",
                description="Brief plugin description",
                author={
                    "name": "Author Name",
                    "email": "author@example.com",
                    "url": "https://example.com",
                },
                homepage="https://docs.example.com/plugin",
                repository="https://github.com/example/plugin",
                license="MIT",
                keywords=["keyword1", "keyword2"],
                extensions={"com.example.client": {"setting": True}},
            )
        )

        assert result.valid is True
        manifest = result.manifest
        assert manifest is not None
        assert manifest.version == "1.2.0"
        assert manifest.description == "Brief plugin description"
        assert manifest.author is not None
        assert manifest.author.name == "Author Name"
        assert manifest.homepage == "https://docs.example.com/plugin"
        assert manifest.repository == "https://github.com/example/plugin"
        assert manifest.license == "MIT"
        assert manifest.keywords == ["keyword1", "keyword2"]
        assert manifest.extensions == {"com.example.client": {"setting": True}}

    @pytest.mark.parametrize("name", ["my-plugin", "acme.tools", "lint3r", "a"])
    def test_spec_valid_name_examples_are_accepted(self, name: str) -> None:
        result = validate_plugin_manifest(_minimal(name=name))

        assert result.valid is True, f"spec-valid name rejected: {name!r}"

    def test_64_char_name_is_accepted(self) -> None:
        result = validate_plugin_manifest(_minimal(name="a" * 64))

        assert result.valid is True

    def test_non_semver_version_must_not_be_rejected(self) -> None:
        # §5.4: metadata fields are validated only by their JSON types.
        result = validate_plugin_manifest(_minimal(version="not-semver!!"))

        assert result.valid is True

    def test_non_url_homepage_must_not_be_rejected(self) -> None:
        result = validate_plugin_manifest(_minimal(homepage="not a url"))

        assert result.valid is True


class TestNonFatalExceptions:
    """§5.2: exactly two schema violations are non-fatal — report and ignore."""

    def test_unknown_top_level_field_is_reported_and_ignored(self) -> None:
        result = validate_plugin_manifest(_minimal(commands="./cmd"))

        assert result.valid is True
        assert [w.code for w in result.warnings] == [PluginIssueCode.MANIFEST_UNKNOWN_FIELD]
        assert result.warnings[0].field == "commands"

    def test_multiple_unknown_fields_each_reported(self) -> None:
        result = validate_plugin_manifest(_minimal(foo=1, bar=2))

        assert result.valid is True
        assert {w.field for w in result.warnings} == {"foo", "bar"}

    def test_non_object_extensions_is_reported_and_ignored(self) -> None:
        result = validate_plugin_manifest(_minimal(extensions="oops"))

        assert result.valid is True
        assert [w.code for w in result.warnings] == [PluginIssueCode.MANIFEST_EXTENSIONS_NOT_OBJECT]
        assert result.manifest is not None
        assert result.manifest.extensions == {}


class TestFatalViolations:
    def test_non_object_document_is_fatal(self) -> None:
        result = validate_plugin_manifest(["not", "an", "object"])

        assert result.valid is False
        assert result.manifest is None
        assert [e.code for e in result.errors] == [PluginIssueCode.MANIFEST_NOT_AN_OBJECT]

    def test_missing_schema_is_fatal(self) -> None:
        result = validate_plugin_manifest({"name": "my-plugin"})

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_SCHEMA_UNSUPPORTED in [e.code for e in result.errors]

    def test_unrecognized_schema_version_is_fatal(self) -> None:
        # §5.2: unsupported declared version → reject, never fetch the schema.
        result = validate_plugin_manifest(
            _minimal(**{"$schema": "https://agent-plugins.org/schemas/9.9.9/plugin.schema.json"})
        )

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_SCHEMA_UNSUPPORTED in [e.code for e in result.errors]

    def test_missing_name_is_fatal(self) -> None:
        result = validate_plugin_manifest({"$schema": AGENT_PLUGINS_PLUGIN_SCHEMA_ID})

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_NAME_INVALID in [e.code for e in result.errors]

    @pytest.mark.parametrize(
        "name",
        ["My-Plugin", "-start", "has--double", "too.many..dots", "", "a" * 65, ".dot", "dot."],
    )
    def test_spec_invalid_name_examples_are_fatal(self, name: str) -> None:
        result = validate_plugin_manifest(_minimal(name=name))

        assert result.valid is False, f"spec-invalid name accepted: {name!r}"
        assert PluginIssueCode.MANIFEST_NAME_INVALID in [e.code for e in result.errors]

    def test_name_with_wrong_type_is_fatal(self) -> None:
        result = validate_plugin_manifest(_minimal(name=123))

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_NAME_INVALID in [e.code for e in result.errors]

    @pytest.mark.parametrize(
        "field,value",
        [
            ("version", 12),
            ("description", ["x"]),
            ("homepage", 1),
            ("repository", {}),
            ("license", 0),
            ("keywords", "not-a-list"),
            ("keywords", ["ok", 42]),
        ],
    )
    def test_metadata_field_with_wrong_json_type_is_fatal(self, field: str, value: Any) -> None:
        result = validate_plugin_manifest(_minimal(**{field: value}))

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_FIELD_INVALID in [e.code for e in result.errors]

    def test_author_with_extra_field_is_fatal(self) -> None:
        # §5.4: the author object MAY contain only name, email and url.
        result = validate_plugin_manifest(_minimal(author={"name": "x", "twitter": "@x"}))

        assert result.valid is False
        assert PluginIssueCode.MANIFEST_FIELD_INVALID in [e.code for e in result.errors]

    def test_author_with_non_string_value_is_fatal(self) -> None:
        result = validate_plugin_manifest(_minimal(author={"name": 42}))

        assert result.valid is False

    def test_extensions_member_value_not_object_is_fatal(self) -> None:
        # §5.2/§8.1: only a non-object extensions FIELD is non-fatal; an
        # object whose member value is not an object is a plain schema
        # violation, hence fatal.
        result = validate_plugin_manifest(_minimal(extensions={"com.example": "flat"}))

        assert result.valid is False

    def test_fatal_manifest_reports_no_parsed_manifest(self) -> None:
        result = validate_plugin_manifest(_minimal(name="-bad-", version=42))

        assert result.valid is False
        assert result.manifest is None
