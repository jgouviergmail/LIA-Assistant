"""A value the model gave and a tool cannot use is REFUSED, in words it can act on.

ADR-310's rule: a tool never replaces a value it cannot read — it refuses it,
with what it accepts. A refusal raised inside a connector tool used to reach
the model as « internal error (ToolValidationError) »: the words the tool wrote
for it were dropped by the handler that drops an arbitrary exception's words
(they may quote a provider or a mailbox). A typed refusal is not arbitrary —
its words are the tool's own.
"""

from __future__ import annotations

import pytest

from src.core.date_contract import UnreadableDateError
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.runtime_helpers import handle_tool_exception
from src.domains.agents.tools.validation_helpers import refuse_unreadable_input

pytestmark = pytest.mark.unit


class TestATypedRefusalIsSaid:
    def test_it_reaches_the_model_as_invalid_input_in_its_own_words(self) -> None:
        refusal = ToolValidationError("all_day=false needs both bounds", field="end_datetime")

        output = handle_tool_exception(refusal, "update_event_tool")

        assert output.success is False
        assert output.error_code == ToolErrorCode.INVALID_INPUT
        assert output.message == "all_day=false needs both bounds"

    def test_an_arbitrary_exception_still_keeps_its_words_out(self) -> None:
        output = handle_tool_exception(ValueError("mailbox alice@example.com"), "t")

        assert output.error_code == ToolErrorCode.INTERNAL_ERROR
        assert "alice@example.com" not in output.model_dump_json()


class TestReadingTheModelsValues:
    def test_an_unreadable_date_names_the_format_and_today(self) -> None:
        with pytest.raises(ToolValidationError) as caught, refuse_unreadable_input("UTC"):
            raise UnreadableDateError("tomorrow")

        words = str(caught.value)
        assert "'tomorrow'" in words
        assert "YYYY-MM-DD" in words
        assert "today is" in words

    def test_a_value_error_is_refused_in_the_words_it_carries(self) -> None:
        with (
            pytest.raises(ToolValidationError, match="needs both"),
            refuse_unreadable_input("UTC"),
        ):
            raise ValueError("all_day=false needs both start_datetime and end_datetime")

    def test_anything_else_is_not_a_refusal(self) -> None:
        with pytest.raises(KeyError), refuse_unreadable_input("UTC"):
            raise KeyError("start")
