"""Calculation tools — exact arithmetic, dates and currency conversion (ADR-318).

A model computes badly and says nothing when it is wrong. These three tools
answer what it must not do in its head, in both execution modes — the ReAct
loop had ``run_python_tool`` for arithmetic, the pipeline had nothing, and
neither had a calendar or a rate:

- ``calculate_tool`` evaluates an expression exactly (``calculation/evaluator``);
- ``date_time_tool`` answers six date questions (``calculation/dates``);
- ``convert_currency_tool`` converts at the ECB reference rate and states the
  day of that rate (``infrastructure/external/currency_api``).

Read-only, no personal data, no confirmation. Every refusal carries a code
(ADR-303 reads codes, never prose) and a technical English message the model
corrects its call from (ADR-256). The logs carry lengths and codes only: an
expression or an amount is the person's own figure.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any, Final

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.date_contract import UnreadableDateError, unreadable_date_message
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.calculation.catalogue_manifests import (
    CALCULATE_EXPRESSION_DESCRIPTION,
    CURRENCY_AMOUNT_DESCRIPTION,
    CURRENCY_CODE_DESCRIPTION,
    CURRENCY_CODE_PATTERN,
    DATE_AMOUNT_DESCRIPTION,
    DATE_DATE_DESCRIPTION,
    DATE_OPERATION_DESCRIPTION,
    DATE_OTHER_DATE_DESCRIPTION,
    DATE_TIMEZONE_DESCRIPTION,
    DATE_TO_TIMEZONE_DESCRIPTION,
    DATE_UNIT_DESCRIPTION,
)
from src.domains.agents.calculation.dates import (
    DateArithmeticError,
    DateFailure,
    DateOperation,
    DateRequest,
    DateUnit,
    answer_date_request,
)
from src.domains.agents.calculation.evaluator import (
    CalculationError,
    CalculationFailure,
    evaluate,
)
from src.domains.agents.constants import AGENT_CALCULATION
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.external.currency_api import CurrencyRateService, UnsupportedCurrencyError

logger = structlog.get_logger(__name__)

#: How each calculator refusal reads to the model (ADR-303: a code, never prose).
_CALCULATION_CODES: Final[dict[CalculationFailure, ToolErrorCode]] = {
    "too_long": ToolErrorCode.CONSTRAINT_VIOLATION,
    "syntax": ToolErrorCode.INVALID_INPUT,
    "unsupported": ToolErrorCode.INVALID_INPUT,
    "domain": ToolErrorCode.INVALID_PARAM_VALUE,
    "division_by_zero": ToolErrorCode.INVALID_PARAM_VALUE,
    "overflow": ToolErrorCode.INVALID_PARAM_VALUE,
}

#: How each date refusal reads to the model.
_DATE_CODES: Final[dict[DateFailure, ToolErrorCode]] = {
    "missing_parameter": ToolErrorCode.MISSING_REQUIRED_PARAM,
    "invalid_parameter": ToolErrorCode.INVALID_PARAM_VALUE,
    "unknown_timezone": ToolErrorCode.INVALID_PARAM_VALUE,
    "out_of_range": ToolErrorCode.INVALID_PARAM_VALUE,
}

_CURRENCY_CODE: Final = re.compile(CURRENCY_CODE_PATTERN)
#: A converted amount is shown to the cent.
_CENT: Final = Decimal("0.01")
_ECB_SOURCE: Final = "European Central Bank reference rate"
_NO_CONVERSION: Final = "none: same currency"


def _refusal(message: str, code: ToolErrorCode) -> UnifiedToolOutput:
    return UnifiedToolOutput.failure(message=message, error_code=code.value)


@read_tool(name="calculate", agent_name=AGENT_CALCULATION)
async def calculate_tool(
    expression: Annotated[str, CALCULATE_EXPRESSION_DESCRIPTION],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
) -> UnifiedToolOutput:
    """Evaluate an arithmetic expression EXACTLY, in decimal — never compute in your head.

    Use it for every computed figure you state: totals, percentages, VAT, unit
    prices, splits, averages, interest. The result is exact unless
    ``approximate`` is true. Dates: date_time_tool. Money between currencies:
    convert_currency_tool.

    Args:
        expression: The arithmetic expression.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with ``{result, expression, approximate}``, or a
        typed refusal naming what the model must correct.
    """
    try:
        calculation = evaluate(
            expression,
            max_chars=settings.calculator_expression_max_chars,
            precision=settings.calculator_precision_digits,
        )
    except CalculationError as error:
        logger.info("calculation_refused", reason=error.reason, expression_length=len(expression))
        return _refusal(str(error), _CALCULATION_CODES[error.reason])

    # Lengths and flags only: the figures are the person's own.
    logger.info(
        "calculation_completed",
        expression_length=len(calculation.expression),
        exact=calculation.exact,
    )
    qualifier = (
        ""
        if calculation.exact
        else (
            f" (approximate: rounded, to at most {settings.calculator_precision_digits} "
            "significant digits — say 'about')"
        )
    )
    return UnifiedToolOutput.data_success(
        message=f"{calculation.expression} = {calculation.text}{qualifier}",
        structured_data={
            "result": calculation.text,
            "expression": calculation.expression,
            "approximate": not calculation.exact,
        },
    )


@read_tool(name="date_time", agent_name=AGENT_CALCULATION)
async def date_time_tool(
    operation: Annotated[DateOperation, DATE_OPERATION_DESCRIPTION],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    date: Annotated[str | None, DATE_DATE_DESCRIPTION] = None,
    other_date: Annotated[str | None, DATE_OTHER_DATE_DESCRIPTION] = None,
    amount: Annotated[int | None, DATE_AMOUNT_DESCRIPTION] = None,
    unit: Annotated[DateUnit | None, DATE_UNIT_DESCRIPTION] = None,
    timezone: Annotated[str | None, DATE_TIMEZONE_DESCRIPTION] = None,
    to_timezone: Annotated[str | None, DATE_TO_TIMEZONE_DESCRIPTION] = None,
) -> UnifiedToolOutput:
    """Date and time arithmetic, exact — never count days in your head.

    Operations: now, difference (days, weeks, years/months/days, elapsed time),
    add (years, months, weeks, days, business_days, hours, minutes), weekday,
    business_days (Monday to Friday, both dates included, public holidays NOT
    excluded), convert_timezone. Dates are ISO 8601, resolved by you from the
    current date first.

    Args:
        operation: What to compute.
        runtime: LangChain tool runtime (injected).
        date: The moment the question is about (today when omitted).
        other_date: The second moment of difference and business_days.
        amount: How much add adds (negative subtracts).
        unit: The unit of amount.
        timezone: Where dates without an offset are read (the user's by default).
        to_timezone: The target zone of convert_timezone.

    Returns:
        UnifiedToolOutput with ``{operation, result, ...facts}``, or a typed
        refusal; an unreadable date is refused with the accepted format and
        today's date (ADR-310).
    """
    user_zone = resolve_user_timezone(tool_runtime_context(runtime))
    request = DateRequest(
        operation=operation,
        date=date,
        other_date=other_date,
        amount=amount,
        unit=unit,
        timezone=timezone,
        to_timezone=to_timezone,
    )
    try:
        answer = answer_date_request(request, user_zone=user_zone, now=datetime.now(UTC))
    except UnreadableDateError as error:
        logger.info("date_time_refused", operation=operation, reason="unreadable_date")
        return _refusal(
            unreadable_date_message(error.reference, user_zone.key), ToolErrorCode.INVALID_INPUT
        )
    except DateArithmeticError as error:
        logger.info("date_time_refused", operation=operation, reason=error.reason)
        return _refusal(str(error), _DATE_CODES[error.reason])

    logger.info("date_time_completed", operation=operation)
    return UnifiedToolOutput.data_success(message=answer.summary, structured_data=answer.facts)


def _currency_code(raw: str) -> str | None:
    code = (raw or "").strip()
    return code.upper() if _CURRENCY_CODE.match(code) else None


def _amount(raw: float) -> Decimal | None:
    try:
        value = Decimal(str(raw))
    except InvalidOperation, ValueError:
        return None
    return value if value.is_finite() and value >= 0 else None


async def _unsupported_pair(source: str, target: str) -> UnifiedToolOutput:
    """The refusal of a pair the source does not publish, naming what it does."""
    published = await CurrencyRateService().supported_currencies()
    listing = f" Published currencies: {', '.join(published)}." if published else ""
    return _refusal(
        f"No reference rate is published for {source} to {target}.{listing}",
        ToolErrorCode.INVALID_PARAM_VALUE,
    )


@read_tool(name="convert_currency", agent_name=AGENT_CALCULATION)
async def convert_currency_tool(
    amount: Annotated[float, CURRENCY_AMOUNT_DESCRIPTION],
    from_currency: Annotated[str, CURRENCY_CODE_DESCRIPTION],
    to_currency: Annotated[str, CURRENCY_CODE_DESCRIPTION],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
) -> UnifiedToolOutput:
    """Convert an amount between currencies at the ECB reference rate — never estimate a rate.

    The rate and the day it was published are returned; a bank or a card
    applies its own rate and fees, say so.

    Args:
        amount: The amount in the source currency.
        from_currency: ISO 4217 code of the source currency.
        to_currency: ISO 4217 code of the target currency.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with ``{amount, from_currency, to_currency, result,
        rate, rate_date, source}``, or a typed refusal.
    """
    source, target = _currency_code(from_currency), _currency_code(to_currency)
    if source is None or target is None:
        return _refusal(
            "A currency is an ISO 4217 code of three letters (EUR, USD, GBP, JPY, CHF…).",
            ToolErrorCode.INVALID_PARAM_VALUE,
        )
    value = _amount(amount)
    if value is None:
        return _refusal(
            "The amount must be a finite number, zero or more.", ToolErrorCode.INVALID_PARAM_VALUE
        )

    if source == target:
        rate, rate_date, origin = Decimal(1), None, _NO_CONVERSION
    else:
        try:
            quote = await CurrencyRateService().get_quote(source, target)
        except UnsupportedCurrencyError:
            logger.info("currency_conversion_refused", reason="unsupported_pair")
            return await _unsupported_pair(source, target)
        if quote is None:
            logger.warning("currency_conversion_refused", reason="rate_unavailable")
            return _refusal(
                "The reference rate could not be obtained right now. Say the conversion "
                "could not be done; never estimate a rate.",
                ToolErrorCode.EXTERNAL_API_ERROR,
            )
        rate, rate_date, origin = quote.rate, quote.rate_date, _ECB_SOURCE

    try:
        converted = (value * rate).quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        # To the cent, past decimal's 28 significant digits: no such sum exists.
        return _refusal(
            "The amount is too large to convert to the cent.", ToolErrorCode.INVALID_PARAM_VALUE
        )
    day = rate_date.isoformat() if rate_date else None
    logger.info("currency_conversion_completed", rate_published=day is not None)
    published = f" (reference rate of {day})" if day else ""
    return UnifiedToolOutput.data_success(
        message=f"{value} {source} = {converted} {target} at {rate}{published}.",
        structured_data={
            "amount": str(value),
            "from_currency": source,
            "to_currency": target,
            "result": str(converted),
            "rate": str(rate),
            "rate_date": day,
            "source": origin,
        },
    )


__all__ = ["calculate_tool", "convert_currency_tool", "date_time_tool"]
