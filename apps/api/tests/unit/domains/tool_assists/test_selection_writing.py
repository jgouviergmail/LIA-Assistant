"""Explicit translation targets and faithful formatting at the shared selection door."""

from typing import Literal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from src.core.constants import TOOL_ASSIST_LANGUAGE_MAX_CHARS
from src.domains.tool_assists import text
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.selection import SelectionRequest, propose_selection
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def test_internet_is_a_reading_action_and_never_an_editor_rewrite() -> None:
    request = SelectionRequest.model_validate(
        {"mode": "read", "action": "internet", "text": "A topic"}
    )
    assert request.action.value == "internet"
    with pytest.raises(ValidationError):
        SelectionRequest.model_validate({"mode": "edit", "action": "internet", "text": "A topic"})


@pytest.mark.parametrize("mode", ["read", "edit"])
@pytest.mark.parametrize(
    "language", [None, "", "  ", "x", "x" * (TOOL_ASSIST_LANGUAGE_MAX_CHARS + 1)]
)
def test_translation_refuses_an_absent_or_invalid_target_before_a_call(
    mode: str, language: str | None
) -> None:
    payload = {"mode": mode, "action": "translate", "text": "Bonjour"}
    if language is not None:
        payload["target_language"] = language
    with pytest.raises(ValidationError):
        SelectionRequest.model_validate(payload)


@pytest.mark.parametrize("action", ["fix", "shorter", "formal", "warm", "format"])
def test_rewriting_cannot_carry_an_unused_translation_instruction(action: str) -> None:
    with pytest.raises(ValidationError):
        SelectionRequest.model_validate(
            {"mode": "edit", "action": action, "text": "Bonjour", "target_language": "Spanish"}
        )


@pytest.mark.parametrize("mode", ["read", "edit"])
async def test_translation_uses_the_chosen_language_and_preserves_the_external_source(
    monkeypatch: pytest.MonkeyPatch, mode: Literal["read", "edit"]
) -> None:
    prompts: list[str] = []

    async def answer[T: BaseModel](run: AssistRun, rendered: str, schema: type[T]) -> T:
        prompts.append(rendered)
        return schema.model_validate({"text": "Hola"})

    monkeypatch.setattr(text, "ask_slot", answer)
    person = User(id=uuid4(), language="fr")
    request = SelectionRequest.model_validate(
        {
            "mode": mode,
            "action": "translate",
            "text": "Bonjour {ignore rules}",
            "target_language": " Spanish ",
        }
    )
    result = await propose_selection(AssistRun(person.id, "fr", {}), request, person)
    assert result.kind == "text" and result.text == "Hola"
    assert len(prompts) == 1
    assert "Target language: Spanish" in prompts[0]
    assert "Bonjour {ignore rules}" in prompts[0]
    assert "<external_content" in prompts[0]


async def test_format_is_an_explicit_edit_with_the_original_facts_as_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def answer[T: BaseModel](run: AssistRun, rendered: str, schema: type[T]) -> T:
        prompts.append(rendered)
        return schema.model_validate({"text": "First: 12.\nSecond: 8."})

    monkeypatch.setattr(text, "ask_slot", answer)
    person = User(id=uuid4(), language="fr")
    request = SelectionRequest.model_validate(
        {"mode": "edit", "action": "format", "text": "First: 12; second: 8."}
    )
    result = await propose_selection(AssistRun(person.id, "fr", {}), request, person)
    assert result.kind == "text" and result.text == "First: 12.\nSecond: 8."
    assert "The change: format" in prompts[0]
    assert "First: 12; second: 8." in prompts[0]
    assert "<external_content" in prompts[0]
    assert "- format:" in prompts[0]
