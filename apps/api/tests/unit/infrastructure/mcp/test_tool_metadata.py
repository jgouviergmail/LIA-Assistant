"""Tool metadata the MCP spec publishes and this codebase reads.

Two distinct concerns, both taken from ``tools/list`` and both previously
ignored: the display name (``title``) and the behaviour hints
(``annotations``). They are extracted at the two discovery sites — admin and
per-user — so the helpers live beside ``extract_app_meta`` and are shared.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infrastructure.mcp.utils import extract_tool_annotations, extract_tool_title


def _tool(**attributes: object) -> SimpleNamespace:
    """An SDK-shaped tool object, defaulting every field to absent."""
    base: dict[str, object] = {"name": "t", "title": None, "annotations": None, "meta": None}
    base.update(attributes)
    return SimpleNamespace(**base)


class TestExtractToolTitle:
    """Spec: "Display name precedence order is: `title`, `annotations.title`, then `name`."

    The ``name`` fallback belongs to the display layer, so this helper answers
    for the first two and returns None when the server named neither.
    """

    def test_the_tool_title_wins(self):
        tool = _tool(title="Financial accounts", annotations=SimpleNamespace(title="Other"))
        assert extract_tool_title(tool) == "Financial accounts"

    def test_the_annotation_title_is_the_fallback(self):
        assert extract_tool_title(_tool(annotations=SimpleNamespace(title="From annotations"))) == (
            "From annotations"
        )

    def test_no_declared_title_returns_none(self):
        assert extract_tool_title(_tool()) is None
        assert extract_tool_title(_tool(annotations=SimpleNamespace(title=None))) is None

    @pytest.mark.parametrize("value", [42, [], {}, b"bytes"])
    def test_a_non_string_title_is_refused(self, value):
        """It would reach a UI and an LLM prompt verbatim."""
        assert extract_tool_title(_tool(title=value)) is None

    def test_a_blank_title_is_refused(self):
        """An empty display name is worse than the tool name it would replace."""
        assert extract_tool_title(_tool(title="   ")) is None

    def test_a_title_is_stripped(self):
        assert extract_tool_title(_tool(title="  Padded  ")) == "Padded"

    def test_an_object_without_the_attributes_does_not_raise(self):
        assert extract_tool_title(SimpleNamespace()) is None


class TestExtractToolAnnotations:
    """The hints are normalised to a plain dict: they cross a Pydantic schema,
    a pool cache and a manifest builder, and an SDK model would not survive it.
    """

    def test_declared_hints_become_a_dict(self):
        tool = _tool(
            annotations=SimpleNamespace(
                title="T", read_only_hint=True, destructive_hint=None, idempotent_hint=False
            )
        )
        assert extract_tool_annotations(tool) == {
            "title": "T",
            "read_only_hint": True,
            "idempotent_hint": False,
        }

    def test_absent_annotations_return_none(self):
        assert extract_tool_annotations(_tool()) is None

    def test_all_hints_undeclared_returns_none(self):
        """A server that sends an empty annotations object declared nothing."""
        tool = _tool(annotations=SimpleNamespace(title=None, read_only_hint=None))
        assert extract_tool_annotations(tool) is None

    def test_a_dict_of_camel_case_hints_is_accepted(self):
        """Not every client hands us an SDK model; the wire form is camelCase."""
        tool = _tool(annotations={"readOnlyHint": False, "destructiveHint": True})
        assert extract_tool_annotations(tool) == {
            "read_only_hint": False,
            "destructive_hint": True,
        }

    @pytest.mark.parametrize("value", ["junk", 42, []])
    def test_a_malformed_annotations_value_returns_none(self, value):
        assert extract_tool_annotations(_tool(annotations=value)) is None

    def test_unknown_hint_keys_are_dropped(self):
        """Only the vocabulary the spec defines travels onward."""
        tool = _tool(annotations={"readOnlyHint": True, "somethingElse": "x"})
        assert extract_tool_annotations(tool) == {"read_only_hint": True}


class TestAgainstTheRealSdkModel:
    """The helpers read a real ``mcp.types.Tool``, not a shape we invented.

    Every other test here builds a stand-in, which cannot catch the one failure
    that matters at the discovery sites: the SDK renaming a field, or exposing
    it under the wire name instead of the snake_case one.
    """

    @staticmethod
    def _sdk_tool(**overrides: object):
        from mcp.types import Tool

        payload: dict[str, object] = {
            "name": "knowledge__forget",
            "description": "Forget a stored fact",
            "input_schema": {"type": "object"},
        }
        payload.update(overrides)
        return Tool(**payload)  # type: ignore[arg-type]

    def test_a_real_tool_title_is_read(self):
        assert extract_tool_title(self._sdk_tool(title="Forget a fact")) == "Forget a fact"

    def test_a_real_annotations_model_is_read(self):
        from mcp.types import ToolAnnotations

        tool = self._sdk_tool(
            annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True)
        )
        assert extract_tool_annotations(tool) == {
            "read_only_hint": False,
            "destructive_hint": True,
        }

    def test_a_real_annotations_title_is_the_display_fallback(self):
        from mcp.types import ToolAnnotations

        tool = self._sdk_tool(annotations=ToolAnnotations(title="From annotations"))
        assert extract_tool_title(tool) == "From annotations"

    def test_a_real_tool_without_metadata_declares_nothing(self):
        tool = self._sdk_tool()
        assert extract_tool_title(tool) is None
        assert extract_tool_annotations(tool) is None

    def test_the_declared_destructive_predicate_closes_the_loop(self):
        """Discovery to decision, on the real model."""
        from mcp.types import ToolAnnotations

        from src.infrastructure.mcp.registration import declares_destructive_tool

        destructive = self._sdk_tool(annotations=ToolAnnotations(destructive_hint=True))
        harmless = self._sdk_tool(annotations=ToolAnnotations(read_only_hint=True))

        assert declares_destructive_tool(extract_tool_annotations(destructive)) is True
        assert declares_destructive_tool(extract_tool_annotations(harmless)) is False
