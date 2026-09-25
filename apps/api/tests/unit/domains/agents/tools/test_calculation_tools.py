"""The calculation tools — what the model gets back, and what it is refused (ADR-318).

The engines are tested on their own (``tests/unit/domains/agents/calculation``);
here the TOOL is: the payload the loop and the planner read, the error code of
every refusal (ADR-303 reads codes, never prose), the person's timezone as the
default zone, the ADR-310 wording of an unreadable date, and the currency
source faked at its own boundary — no network in a unit test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import get_args
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.domains.agents.calculation.catalogue_manifests import (
    CALCULATE_EXPRESSION_DESCRIPTION,
    CURRENCY_CODE_DESCRIPTION,
    DATE_DATE_DESCRIPTION,
    DATE_OPERATION_DESCRIPTION,
    calculate_catalogue_manifest,
)
from src.domains.agents.calculation.dates import DateFailure
from src.domains.agents.calculation.evaluator import CalculationFailure
from src.domains.agents.tools import calculation_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.external.currency_api import CurrencyQuote, UnsupportedCurrencyError
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


def _data(output: UnifiedToolOutput) -> dict[str, object]:
    assert output.success, output.message
    return dict(output.structured_data or {})


def _refused(output: UnifiedToolOutput, code: ToolErrorCode) -> str:
    assert output.success is False
    assert output.error_code == code.value
    return output.message


class TestCalculate:
    async def test_an_exact_result(self) -> None:
        output = await calculation_tools.calculate_tool.coroutine(
            expression="1234.56 * 17.5 / 100", runtime=make_tool_runtime()
        )

        assert _data(output) == {
            "result": "216.048",
            "expression": "1234.56 * 17.5 / 100",
            "approximate": False,
        }
        assert "216.048" in output.message

    async def test_a_rounded_result_is_said_to_be_approximate(self) -> None:
        output = await calculation_tools.calculate_tool.coroutine(
            expression="10 / 3", runtime=make_tool_runtime()
        )

        assert _data(output)["approximate"] is True
        assert "approximate" in output.message
        assert f"at most {settings.calculator_precision_digits}" in output.message

    def test_every_refusal_reason_has_a_code(self) -> None:
        """A reason with no code would raise inside the tool instead of refusing."""
        assert set(calculation_tools._CALCULATION_CODES) == set(get_args(CalculationFailure))
        assert set(calculation_tools._DATE_CODES) == set(get_args(DateFailure))

    @pytest.mark.parametrize(
        ("expression", "code"),
        [
            ("__import__('os')", ToolErrorCode.INVALID_INPUT),
            ("2 +", ToolErrorCode.INVALID_INPUT),
            ("1 / 0", ToolErrorCode.INVALID_PARAM_VALUE),
            ("sqrt(-4)", ToolErrorCode.INVALID_PARAM_VALUE),
            ("9 ** 9 ** 9", ToolErrorCode.INVALID_PARAM_VALUE),
        ],
    )
    async def test_every_refusal_has_its_code(self, expression: str, code: ToolErrorCode) -> None:
        output = await calculation_tools.calculate_tool.coroutine(
            expression=expression, runtime=make_tool_runtime()
        )

        _refused(output, code)

    async def test_the_published_length_is_the_enforced_one(self) -> None:
        bound = settings.calculator_expression_max_chars
        published = {
            constraint.kind: constraint.value
            for constraint in calculate_catalogue_manifest.parameters[0].constraints
        }
        assert published["max_length"] == bound

        output = await calculation_tools.calculate_tool.coroutine(
            expression="1+" * bound + "1", runtime=make_tool_runtime()
        )

        assert str(bound) in _refused(output, ToolErrorCode.CONSTRAINT_VIOLATION)


class TestDateTime:
    async def test_the_person_s_timezone_is_the_default(self) -> None:
        output = await calculation_tools.date_time_tool.coroutine(
            operation="now", runtime=make_tool_runtime(timezone="Asia/Tokyo")
        )

        assert str(_data(output)["result"]).endswith("+09:00")

    async def test_an_answer(self) -> None:
        output = await calculation_tools.date_time_tool.coroutine(
            operation="weekday", date="2026-07-14", runtime=make_tool_runtime()
        )

        assert _data(output)["result"] == "Tuesday"
        assert "Tuesday" in output.message

    async def test_an_unreadable_date_is_refused_with_the_format_and_today(self) -> None:
        output = await calculation_tools.date_time_tool.coroutine(
            operation="weekday",
            date="demain",
            runtime=make_tool_runtime(timezone="Europe/Paris"),
        )

        message = _refused(output, ToolErrorCode.INVALID_INPUT)
        assert "'demain'" in message and "YYYY-MM-DD" in message and "Europe/Paris" in message

    @pytest.mark.parametrize(
        ("operation", "fields", "code"),
        [
            ("difference", {"date": "2026-09-24"}, ToolErrorCode.MISSING_REQUIRED_PARAM),
            ("add", {"date": "2026-09-24", "amount": 1}, ToolErrorCode.MISSING_REQUIRED_PARAM),
            ("sunrise", {}, ToolErrorCode.INVALID_PARAM_VALUE),
            (
                "convert_timezone",
                {"date": "2026-09-24T09:00", "to_timezone": "Mars/Olympus"},
                ToolErrorCode.INVALID_PARAM_VALUE,
            ),
            (
                "add",
                {"date": "9999-12-31", "amount": 1, "unit": "days"},
                ToolErrorCode.INVALID_PARAM_VALUE,
            ),
            ("now", {"timezone": "a" * 300}, ToolErrorCode.INVALID_PARAM_VALUE),
        ],
    )
    async def test_every_refusal_has_its_code(
        self, operation: str, fields: dict[str, object], code: ToolErrorCode
    ) -> None:
        output = await calculation_tools.date_time_tool.coroutine(
            operation=operation, runtime=make_tool_runtime(), **fields
        )

        _refused(output, code)


def _currency_service(
    *,
    quote: CurrencyQuote | None = None,
    unsupported: bool = False,
    supported: tuple[str, ...] | None = ("EUR", "JPY", "USD"),
) -> AsyncMock:
    service = AsyncMock()
    service.get_quote = AsyncMock(
        side_effect=UnsupportedCurrencyError("USD->XYZ") if unsupported else None,
        return_value=quote,
    )
    service.supported_currencies = AsyncMock(return_value=supported)
    return service


class TestConvertCurrency:
    async def _convert(
        self, service: AsyncMock, *, amount: float = 100, source: str = "usd", target: str = "EUR"
    ) -> UnifiedToolOutput:
        with patch.object(calculation_tools, "CurrencyRateService", return_value=service):
            output: UnifiedToolOutput = await calculation_tools.convert_currency_tool.coroutine(
                amount=amount,
                from_currency=source,
                to_currency=target,
                runtime=make_tool_runtime(),
            )
        return output

    async def test_the_amount_the_rate_and_its_day(self) -> None:
        service = _currency_service(
            quote=CurrencyQuote(rate=Decimal("0.87974"), rate_date=date(2026, 9, 24))
        )

        output = await self._convert(service, amount=250.5)

        assert _data(output) == {
            "amount": "250.5",
            "from_currency": "USD",
            "to_currency": "EUR",
            "result": "220.37",
            "rate": "0.87974",
            "rate_date": "2026-09-24",
            "source": "European Central Bank reference rate",
        }
        service.get_quote.assert_awaited_once_with("USD", "EUR")
        assert "2026-09-24" in output.message

    async def test_the_same_currency_asks_nobody(self) -> None:
        service = _currency_service()

        output = await self._convert(service, source="EUR", target="eur")

        assert _data(output)["result"] == "100.00"
        service.get_quote.assert_not_awaited()

    @pytest.mark.parametrize("code", ["EURO", "E1", "", "€"])
    async def test_a_malformed_code_is_refused(self, code: str) -> None:
        output = await self._convert(_currency_service(), target=code)

        assert "ISO 4217" in _refused(output, ToolErrorCode.INVALID_PARAM_VALUE)

    @pytest.mark.parametrize("amount", [-1.0, float("nan"), float("inf")])
    async def test_an_impossible_amount_is_refused(self, amount: float) -> None:
        output = await self._convert(_currency_service(), amount=amount)

        _refused(output, ToolErrorCode.INVALID_PARAM_VALUE)

    async def test_an_unpublished_pair_names_the_published_currencies(self) -> None:
        output = await self._convert(_currency_service(unsupported=True), target="XYZ")

        message = _refused(output, ToolErrorCode.INVALID_PARAM_VALUE)
        assert "EUR, JPY, USD" in message

    async def test_an_unpublished_pair_without_the_list_still_refuses(self) -> None:
        output = await self._convert(
            _currency_service(unsupported=True, supported=None), target="XYZ"
        )

        _refused(output, ToolErrorCode.INVALID_PARAM_VALUE)

    async def test_an_amount_past_decimal_s_digits_is_refused(self) -> None:
        """To the cent, 1e30 needs 33 significant digits: decimal holds 28."""
        output = await self._convert(_currency_service(), source="EUR", target="EUR", amount=1e30)

        assert "too large" in _refused(output, ToolErrorCode.INVALID_PARAM_VALUE)

    async def test_an_outage_is_never_an_estimated_rate(self) -> None:
        output = await self._convert(_currency_service(quote=None))

        message = _refused(output, ToolErrorCode.EXTERNAL_API_ERROR)
        assert "never" in message.lower()


@pytest.mark.parametrize(
    ("tool_name", "parameter", "wording"),
    [
        ("calculate_tool", "expression", CALCULATE_EXPRESSION_DESCRIPTION),
        ("date_time_tool", "operation", DATE_OPERATION_DESCRIPTION),
        ("date_time_tool", "date", DATE_DATE_DESCRIPTION),
        ("convert_currency_tool", "to_currency", CURRENCY_CODE_DESCRIPTION),
    ],
)
def test_the_react_schema_publishes_the_manifest_s_wording(
    tool_name: str, parameter: str, wording: str
) -> None:
    """The ReAct loop binds the tool's own schema, never the manifest (ADR-310)."""
    schema = getattr(calculation_tools, tool_name).args_schema
    description = schema.model_fields[parameter].description

    assert description is not None and description.startswith(wording)
