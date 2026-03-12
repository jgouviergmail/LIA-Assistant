"""
Unit tests for ResponsesLLM adapter input parameter handling.

Validates that the 'input' parameter is always sent to the Responses API,
not conditionally (defensive fix for openai pin removal).
"""

import inspect
import textwrap

import pytest

from src.infrastructure.llm.providers.responses_adapter import ResponsesLLM


@pytest.mark.unit
class TestResponsesApiInputParam:

    def test_call_responses_api_input_unconditional(self):
        """Verify _call_responses_api always assigns api_params['input']."""
        source = textwrap.dedent(inspect.getsource(ResponsesLLM._call_responses_api))

        # After fix: api_params["input"] = input_items (unconditional)
        assert (
            'api_params["input"] = input_items' in source
            or "api_params['input'] = input_items" in source
        ), "api_params['input'] assignment not found in _call_responses_api"
        assert (
            "if input_items:" not in source
        ), "api_params['input'] is still conditionally assigned in _call_responses_api"

    def test_structured_responses_input_unconditional(self):
        """Verify _StructuredResponsesRunnable.ainvoke always assigns api_params['input']."""
        from src.infrastructure.llm.providers.responses_adapter import (
            _StructuredResponsesRunnable,
        )

        source = textwrap.dedent(inspect.getsource(_StructuredResponsesRunnable.ainvoke))

        # After the early return for empty input_items (L1349),
        # the remaining code should NOT have a conditional on input_items
        api_section = source[source.index("api_params") :]

        assert (
            "if input_items:" not in api_section
        ), "api_params['input'] is still conditionally assigned in _StructuredResponsesRunnable"
