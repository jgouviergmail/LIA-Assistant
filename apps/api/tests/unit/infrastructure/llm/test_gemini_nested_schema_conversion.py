"""Gemini function conversion keeps nested Pydantic schemas whole.

``langchain_google_genai`` logs ``Key '$defs' is not supported in schema,
ignoring`` for every structured-output schema that nests a model (Pydantic
puts the nested definition in ``$defs``). Measured on 4.3.4 (2026-09-02,
prod ``open_loop_extraction`` on gemini-3.7-flash): the warning is NOISE —
the converter dereferences local ``$ref``s BEFORE discarding the residual
``$defs`` key, so every nested field, ``required`` list and ``enum``
survives. This guard pins that verdict: if a future version of the
converter starts actually amputating nested schemas, this test goes red
before production quietly loses extraction fields.
"""

import warnings
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field


class _NestedItem(BaseModel):
    """Same shape class as OpenLoopItem: enums, optionals, required fields."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["open", "close"] = Field(description="open or close")
    subject: str = Field(description="What the commitment is about")
    counterparty: str | None = Field(default=None, description="Other side")
    direction: Literal["user_owes", "waiting_on_other"] = Field(default="user_owes")
    due_hint_iso: str | None = Field(default=None, description="ISO deadline")


class _Extraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_NestedItem] = Field(default_factory=list)


@pytest.mark.unit
class TestGeminiNestedSchemaConversion:
    def _converted_item_schema(self):
        from langchain_google_genai import _function_utils as fu

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tools = fu.convert_to_genai_function_declarations([_Extraction])
        declaration = tools[0].function_declarations[0]
        return declaration.parameters.properties["items"].items

    def test_nested_fields_survive_the_defs_discard(self) -> None:
        item = self._converted_item_schema()
        assert sorted(item.properties.keys()) == [
            "action",
            "counterparty",
            "direction",
            "due_hint_iso",
            "subject",
        ]

    def test_required_and_enums_survive(self) -> None:
        item = self._converted_item_schema()
        assert list(item.required) == ["action", "subject"]
        assert list(item.properties["action"].enum) == ["open", "close"]
        assert list(item.properties["direction"].enum) == [
            "user_owes",
            "waiting_on_other",
        ]
