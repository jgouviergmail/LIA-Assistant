"""
Tests for excalidraw iterative_builder module.

Tests the intent detection, JSON extraction, and the build flow
(with mocked LLM calls).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.mcp.excalidraw.iterative_builder import (
    _extract_json_array,
    build_from_intent,
    is_intent,
)

# ---------------------------------------------------------------------------
# is_intent() tests
# ---------------------------------------------------------------------------


class TestIsIntent:
    def test_valid_intent(self):
        intent_str = json.dumps(
            {
                "intent": True,
                "description": "Test diagram",
                "components": [{"name": "A", "shape": "rectangle", "color": "#a5d8ff"}],
                "connections": [],
            }
        )
        result = is_intent(intent_str)
        assert result is not None
        assert result["intent"] is True
        assert len(result["components"]) == 1

    def test_intent_without_marker(self):
        """Intent without 'intent: true' should not be detected."""
        intent_str = json.dumps(
            {
                "description": "Test",
                "components": [{"name": "A"}],
            }
        )
        assert is_intent(intent_str) is None

    def test_raw_elements_array(self):
        """JSON array should not be detected as intent."""
        assert is_intent('[{"type": "rectangle", "id": "r1"}]') is None

    def test_invalid_json(self):
        assert is_intent("not json") is None

    def test_empty_string(self):
        assert is_intent("") is None

    def test_none(self):
        assert is_intent(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _extract_json_array() tests
# ---------------------------------------------------------------------------


class TestExtractJsonArray:
    def test_plain_array(self):
        result = _extract_json_array('[{"type": "rectangle"}]')
        assert result == '[{"type": "rectangle"}]'

    def test_markdown_wrapped(self):
        text = '```json\n[{"type": "rectangle"}]\n```'
        result = _extract_json_array(text)
        assert result == '[{"type": "rectangle"}]'

    def test_text_before_array(self):
        text = 'Here are the elements: [{"type": "rectangle"}]'
        result = _extract_json_array(text)
        assert result == '[{"type": "rectangle"}]'

    def test_nested_arrays(self):
        text = '[{"points": [[0, 0], [100, 100]]}]'
        result = _extract_json_array(text)
        assert result is not None
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["points"] == [[0, 0], [100, 100]]

    def test_no_array(self):
        assert _extract_json_array("no array here") is None

    def test_empty_array(self):
        result = _extract_json_array("[]")
        assert result == "[]"


# ---------------------------------------------------------------------------
# build_from_intent() tests (mocked LLM)
# ---------------------------------------------------------------------------


class TestBuildFromIntent:
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM that returns valid Excalidraw JSON arrays."""
        llm = AsyncMock()
        return llm

    def _make_llm_response(self, elements: list) -> MagicMock:
        """Create a mock LLM response with content."""
        response = MagicMock()
        response.content = json.dumps(elements)
        return response

    @pytest.mark.asyncio
    async def test_basic_intent_single_call(self, mock_llm):
        """Test that build uses exactly 1 LLM call for shapes + arrows."""
        intent = {
            "intent": True,
            "description": "Simple diagram",
            "components": [
                {"name": "A", "shape": "rectangle", "color": "#a5d8ff"},
                {"name": "B", "shape": "ellipse", "color": "#b2f2bb"},
            ],
            "connections": [{"from": "A", "to": "B", "label": "connects"}],
            "layout": "top-to-bottom",
        }

        # Mock LLM response: all elements in a single call
        mock_llm.ainvoke = AsyncMock(
            return_value=self._make_llm_response(
                [
                    {"type": "cameraUpdate", "x": -50, "y": -50, "width": 800, "height": 600},
                    {
                        "type": "rectangle",
                        "id": "bg",
                        "x": 40,
                        "y": 40,
                        "width": 620,
                        "height": 420,
                        "backgroundColor": "#f0f4ff",
                        "strokeColor": "transparent",
                    },
                    {
                        "type": "rectangle",
                        "id": "a",
                        "x": 100,
                        "y": 100,
                        "width": 200,
                        "height": 80,
                        "backgroundColor": "#a5d8ff",
                        "strokeColor": "#1e3a5f",
                    },
                    {
                        "type": "text",
                        "id": "a_label",
                        "x": 170,
                        "y": 128,
                        "width": 60,
                        "height": 24,
                        "text": "A",
                        "fontSize": 20,
                        "fontFamily": 1,
                        "containerId": "a",
                    },
                    {
                        "type": "ellipse",
                        "id": "b",
                        "x": 100,
                        "y": 300,
                        "width": 200,
                        "height": 80,
                        "backgroundColor": "#b2f2bb",
                        "strokeColor": "#1e3a5f",
                    },
                    {
                        "type": "text",
                        "id": "b_label",
                        "x": 170,
                        "y": 328,
                        "width": 60,
                        "height": 24,
                        "text": "B",
                        "fontSize": 20,
                        "fontFamily": 1,
                        "containerId": "b",
                    },
                    {
                        "type": "arrow",
                        "id": "arrow_a_b",
                        "x": 200,
                        "y": 180,
                        "width": 0,
                        "height": 120,
                        "points": [[0, 0], [0, 120]],
                        "strokeColor": "#1e3a5f",
                        "endArrowhead": "arrow",
                    },
                ]
            ),
        )

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            result = await build_from_intent(intent, "mock cheat sheet")

        elements = json.loads(result)
        assert isinstance(elements, list)
        # Camera + bg + A shape + A label + B shape + B label + arrow = 7
        assert len(elements) == 7
        # Verify element types
        types = [el["type"] for el in elements]
        assert "cameraUpdate" in types
        assert "rectangle" in types
        assert "ellipse" in types
        assert "arrow" in types
        assert "text" in types
        # Verify exactly 1 LLM call (single pass)
        assert mock_llm.ainvoke.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_components_raises(self):
        intent = {"intent": True, "components": [], "connections": []}
        with pytest.raises(ValueError, match="at least one component"):
            await build_from_intent(intent, "cheat sheet")

    @pytest.mark.asyncio
    async def test_no_connections(self, mock_llm):
        """Test intent with no connections — still 1 LLM call."""
        intent = {
            "intent": True,
            "description": "Single node",
            "components": [{"name": "Solo", "shape": "rectangle", "color": "#a5d8ff"}],
            "connections": [],
            "layout": "top-to-bottom",
        }

        mock_llm.ainvoke = AsyncMock(
            return_value=self._make_llm_response(
                [
                    {"type": "cameraUpdate", "x": 0, "y": 0, "width": 600, "height": 450},
                    {
                        "type": "rectangle",
                        "id": "solo",
                        "x": 100,
                        "y": 100,
                        "width": 200,
                        "height": 80,
                    },
                    {
                        "type": "text",
                        "id": "solo_label",
                        "text": "Solo",
                        "containerId": "solo",
                        "x": 150,
                        "y": 128,
                        "width": 40,
                        "height": 24,
                        "fontSize": 20,
                        "fontFamily": 1,
                    },
                ]
            ),
        )

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            result = await build_from_intent(intent, "cheat sheet")

        elements = json.loads(result)
        # Camera + Solo shape + Solo label = 3 (no arrows)
        assert len(elements) == 3
        assert mock_llm.ainvoke.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_call_failure_returns_empty(self, mock_llm):
        """If the LLM call fails, builder returns empty list."""
        intent = {
            "intent": True,
            "components": [
                {"name": "A", "shape": "rectangle", "color": "#a5d8ff"},
            ],
            "connections": [],
        }

        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM call failed"))

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            result = await build_from_intent(intent, "cheat sheet")

        elements = json.loads(result)
        assert len(elements) == 0

    @pytest.mark.asyncio
    async def test_components_capped(self, mock_llm):
        """Components exceeding _MAX_COMPONENTS are capped."""
        intent = {
            "intent": True,
            "components": [
                {"name": f"C{i}", "shape": "rectangle", "color": "#a5d8ff"} for i in range(20)
            ],
            "connections": [],
        }

        mock_llm.ainvoke = AsyncMock(return_value=self._make_llm_response([]))

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            await build_from_intent(intent, "cheat sheet")

        assert mock_llm.ainvoke.call_count == 1
        # Verify the prompt mentions capped components (15 max)
        call_args = mock_llm.ainvoke.call_args
        prompt_content = str(call_args)
        # Should contain C0 through C14 but not C15+
        assert "C14" in prompt_content
        assert "C15" not in prompt_content

    @pytest.mark.asyncio
    async def test_prompt_contains_layout_and_description(self, mock_llm):
        """Verify LLM prompt includes layout direction and description."""
        intent = {
            "intent": True,
            "description": "My Architecture Diagram",
            "components": [
                {"name": "Input", "shape": "rectangle", "color": "#a5d8ff"},
                {"name": "Output", "shape": "ellipse", "color": "#b2f2bb"},
            ],
            "connections": [{"from": "Input", "to": "Output", "label": "data flow"}],
            "layout": "left-to-right",
        }

        mock_llm.ainvoke = AsyncMock(return_value=self._make_llm_response([]))

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            await build_from_intent(intent, "cheat sheet")

        call_args = mock_llm.ainvoke.call_args
        prompt_content = str(call_args)
        assert "left-to-right" in prompt_content
        assert "My Architecture Diagram" in prompt_content
        assert "Input" in prompt_content
        assert "Output" in prompt_content
        assert "data flow" in prompt_content

    @pytest.mark.asyncio
    async def test_connections_in_prompt(self, mock_llm):
        """Verify connections are included in the single LLM call prompt."""
        intent = {
            "intent": True,
            "components": [
                {"name": "A", "shape": "rectangle", "color": "#a5d8ff"},
                {"name": "B", "shape": "rectangle", "color": "#b2f2bb"},
            ],
            "connections": [{"from": "A", "to": "B", "label": "HTTP"}],
        }

        mock_llm.ainvoke = AsyncMock(return_value=self._make_llm_response([]))

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            await build_from_intent(intent, "cheat sheet")

        call_args = mock_llm.ainvoke.call_args
        prompt_content = str(call_args)
        # Arrow instructions should be in the single prompt
        assert "arrow" in prompt_content.lower()
        assert "startBinding" in prompt_content
        assert '"A"' in prompt_content
        assert '"B"' in prompt_content
        assert "HTTP" in prompt_content

    @pytest.mark.asyncio
    async def test_cheat_sheet_in_system_message(self, mock_llm):
        """Verify the cheat sheet is passed in the system message."""
        intent = {
            "intent": True,
            "components": [{"name": "A", "shape": "rectangle", "color": "#a5d8ff"}],
            "connections": [],
        }

        mock_llm.ainvoke = AsyncMock(return_value=self._make_llm_response([]))

        with patch(
            "src.infrastructure.mcp.excalidraw.iterative_builder._get_excalidraw_llm",
            return_value=mock_llm,
        ):
            await build_from_intent(intent, "CUSTOM CHEAT SHEET CONTENT")

        call_args = mock_llm.ainvoke.call_args
        messages = call_args[0][0]  # First positional arg is the messages list
        system_content = messages[0].content
        assert "CUSTOM CHEAT SHEET CONTENT" in system_content
        assert "EXCALIDRAW CHEAT SHEET" in system_content
