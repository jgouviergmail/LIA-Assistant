"""Catalogue manifests for the calculation tools (ADR-318).

Three read-only tools for what a model must not do in its head: arithmetic,
date and time arithmetic, currency conversion. No personal data, no OAuth, no
confirmation. Every bound and every vocabulary published here is READ from the
engine or the setting that enforces it (ADR-184): the functions and constants
from the evaluator, the operations and units from the date engine, the length
and precision from settings. The parameter wordings are constants read by the
manifests AND by the ``@tool`` signatures, because the ReAct loop binds the
schema and never the manifest (ADR-310).
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.core.date_contract import ISO_MOMENT_DESCRIPTION
from src.domains.agents.calculation.dates import DATE_OPERATIONS, DATE_UNITS
from src.domains.agents.calculation.evaluator import CONSTANTS, FUNCTIONS
from src.domains.agents.constants import AGENT_CALCULATION
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: The wording of the calculator's one parameter.
CALCULATE_EXPRESSION_DESCRIPTION = (
    f"The arithmetic expression, at most {settings.calculator_expression_max_chars} "
    "characters, e.g. '1234.56 * 17.5 / 100' or '(1200 + 350) / 4'. "
    "Numbers with a dot as the decimal separator; operators + - * / // % ** and "
    "parentheses; % is the remainder, so a percentage is x * p / 100. Functions: "
    f"{', '.join(FUNCTIONS)} (trigonometry in radians); constants: {', '.join(CONSTANTS)}."
)

#: The wording of the date tool's parameters.
DATE_OPERATION_DESCRIPTION = (
    "What to compute: now (the current moment in a timezone), difference (between "
    "'date' and 'other_date'), add ('amount' of 'unit' to 'date'), weekday (of "
    "'date'), business_days (Monday to Friday between 'date' and 'other_date', both "
    "included), convert_timezone ('date' shown in 'to_timezone')."
)
DATE_DATE_DESCRIPTION = (
    f"{ISO_MOMENT_DESCRIPTION} Omitted: today (the current moment for convert_timezone)."
)
DATE_OTHER_DATE_DESCRIPTION = (
    f"The second moment of difference and business_days. {ISO_MOMENT_DESCRIPTION}"
)
DATE_AMOUNT_DESCRIPTION = "How much to add, for add; negative to subtract."
DATE_UNIT_DESCRIPTION = f"The unit of 'amount', for add: {', '.join(DATE_UNITS)}."
DATE_TIMEZONE_DESCRIPTION = (
    "IANA timezone (e.g. 'America/New_York') the dates without an offset are read in, "
    "and the zone 'now' reports. Omitted: the user's timezone."
)
DATE_TO_TIMEZONE_DESCRIPTION = "Target IANA timezone of convert_timezone (e.g. 'Asia/Tokyo')."

#: The wording of the conversion's parameters.
CURRENCY_AMOUNT_DESCRIPTION = "The amount to convert, in the source currency."
CURRENCY_CODE_DESCRIPTION = "ISO 4217 currency code (EUR, USD, GBP, JPY, CHF…)."

#: The currency code format the conversion enforces (and publishes).
CURRENCY_CODE_PATTERN = r"^[A-Za-z]{3}$"

_INTERNAL = PermissionProfile(
    required_scopes=[], data_classification="INTERNAL", hitl_required=False
)


# =============================================================================
# Agent Manifest: calculation_agent
# =============================================================================

CALCULATION_AGENT_MANIFEST = AgentManifest(
    name=AGENT_CALCULATION,
    description=(
        "Agent for the computations a language model must not do in its head: exact "
        "arithmetic, date and time arithmetic across timezones, and currency "
        "conversion at the published reference rate. Read-only."
    ),
    tools=["calculate_tool", "date_time_tool", "convert_currency_tool"],
    max_parallel_runs=3,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="🧮", i18n_key="calculation_agent", visible=True, category="agent"
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: calculate_tool
# =============================================================================

calculate_catalogue_manifest = ToolManifest(
    name="calculate_tool",
    agent=AGENT_CALCULATION,
    mutation_policy="read",
    # Computes, reads nothing and writes nothing (ADR-256 category).
    tool_category="readonly",
    description=(
        "**Tool: calculate_tool** - Evaluate an arithmetic expression EXACTLY, in "
        "decimal: totals, percentages, VAT, unit prices, splits, averages, growth, "
        "interest. Use it for EVERY figure you state that has to be computed — never "
        "compute in your head. The result is exact unless 'approximate' is true (a "
        "division that does not terminate, an irrational function, more than "
        f"{settings.calculator_precision_digits} significant digits). Dates: "
        "date_time_tool. Money between currencies: convert_currency_tool."
    ),
    parameters=[
        ParameterSchema(
            name="expression",
            type="string",
            required=True,
            description=CALCULATE_EXPRESSION_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(
                    kind="max_length", value=settings.calculator_expression_max_chars
                ),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="result", type="string", description="The value, as text"),
        OutputFieldSchema(
            path="expression", type="string", description="The expression as it was read"
        ),
        OutputFieldSchema(
            path="approximate",
            type="boolean",
            description="True when a step had to round: say 'about'",
        ),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=40, est_cost_usd=0.0, est_latency_ms=5),
    permissions=_INTERNAL,
    semantic_keywords=[
        "calculate the total of these amounts",
        "what is fifteen percent of this price",
        "compute the price per unit",
        "split the bill between several people",
        "how much is it with tax included",
        "compound interest over several years",
    ],
    reference_examples=["result"],
    display=DisplayMetadata(emoji="🧮", i18n_key="calculate", visible=True, category="tool"),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: date_time_tool
# =============================================================================

date_time_catalogue_manifest = ToolManifest(
    name="date_time_tool",
    agent=AGENT_CALCULATION,
    mutation_policy="read",
    tool_category="readonly",
    description=(
        "**Tool: date_time_tool** - Date and time arithmetic, exact. Operations: "
        "now (current moment in a timezone); difference (days, weeks, years/months/"
        "days and elapsed hours/minutes between two moments — ages, countdowns, "
        "durations); add (a date plus or minus years, months, weeks, days, "
        "business_days, hours or minutes — a missing day clamps to the month's end "
        "and says so); weekday (weekday, ISO week and day of the year); "
        "business_days (Monday to Friday between two dates, both included — public "
        "holidays are NOT excluded); convert_timezone (a time in one zone shown in "
        "another). Dates are ISO 8601: resolve 'tomorrow' or 'next Friday' yourself "
        "from the current date first. Never count days in your head."
    ),
    parameters=[
        ParameterSchema(
            name="operation",
            type="string",
            required=True,
            description=DATE_OPERATION_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(DATE_OPERATIONS))],
        ),
        ParameterSchema(
            name="date",
            type="string",
            required=False,
            description=DATE_DATE_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="other_date",
            type="string",
            required=False,
            description=DATE_OTHER_DATE_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="amount", type="integer", required=False, description=DATE_AMOUNT_DESCRIPTION
        ),
        ParameterSchema(
            name="unit",
            type="string",
            required=False,
            description=DATE_UNIT_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(DATE_UNITS))],
        ),
        ParameterSchema(
            name="timezone", type="string", required=False, description=DATE_TIMEZONE_DESCRIPTION
        ),
        ParameterSchema(
            name="to_timezone",
            type="string",
            required=False,
            description=DATE_TO_TIMEZONE_DESCRIPTION,
        ),
    ],
    outputs=[
        OutputFieldSchema(path="operation", type="string", description="The operation"),
        OutputFieldSchema(
            path="result",
            type="string",
            description="The answer, as text (a date, a weekday, a count, a duration)",
        ),
        OutputFieldSchema(
            path="days",
            type="integer",
            nullable=True,
            description="difference: signed days between the dates (a time: see duration)",
        ),
        OutputFieldSchema(
            path="calendar",
            type="object",
            nullable=True,
            description="difference: years, months, days (and hours, minutes with a time)",
        ),
        OutputFieldSchema(
            path="duration",
            type="object",
            nullable=True,
            description="difference with a time: hours, minutes and total minutes elapsed",
        ),
        OutputFieldSchema(
            path="weekday", type="string", nullable=True, description="The weekday concerned"
        ),
        OutputFieldSchema(
            path="business_days",
            type="integer",
            nullable=True,
            description="business_days: the count",
        ),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=80, est_cost_usd=0.0, est_latency_ms=5),
    permissions=_INTERNAL,
    semantic_keywords=[
        "how many days until this date",
        "what day of the week is this date",
        "add ten working days to today",
        "how old is someone born on this date",
        "what time is it now in another city",
        "how many business days between two dates",
    ],
    reference_examples=["result", "days"],
    display=DisplayMetadata(emoji="📅", i18n_key="date_time", visible=True, category="tool"),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: convert_currency_tool
# =============================================================================

convert_currency_catalogue_manifest = ToolManifest(
    name="convert_currency_tool",
    agent=AGENT_CALCULATION,
    mutation_policy="read",
    tool_category="readonly",
    description=(
        "**Tool: convert_currency_tool** - Convert an amount between two currencies at "
        "the European Central Bank reference rate of its latest publication day; the "
        "rate and its day are returned — a bank or a card applies its own rate and "
        "fees, say so. Use it for any conversion you state; never estimate a rate. "
        "An unsupported code is refused with the list of published currencies."
    ),
    parameters=[
        ParameterSchema(
            name="amount",
            type="number",
            required=True,
            description=CURRENCY_AMOUNT_DESCRIPTION,
            constraints=[ParameterConstraint(kind="minimum", value=0)],
        ),
        ParameterSchema(
            name="from_currency",
            type="string",
            required=True,
            description=CURRENCY_CODE_DESCRIPTION,
            constraints=[ParameterConstraint(kind="pattern", value=CURRENCY_CODE_PATTERN)],
        ),
        ParameterSchema(
            name="to_currency",
            type="string",
            required=True,
            description=CURRENCY_CODE_DESCRIPTION,
            constraints=[ParameterConstraint(kind="pattern", value=CURRENCY_CODE_PATTERN)],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="result", type="string", description="The converted amount, 2 decimals"
        ),
        OutputFieldSchema(
            path="rate", type="string", description="1 unit of the source in the target"
        ),
        OutputFieldSchema(
            path="rate_date",
            type="string",
            nullable=True,
            description="ISO day the reference rate was published",
        ),
        OutputFieldSchema(path="from_currency", type="string", description="Source code"),
        OutputFieldSchema(path="to_currency", type="string", description="Target code"),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=60, est_cost_usd=0.0, est_latency_ms=400),
    permissions=_INTERNAL,
    semantic_keywords=[
        "convert this amount from dollars to euros",
        "how much is this price in another currency",
        "exchange rate between two currencies today",
        "what is this sum worth in yen",
    ],
    reference_examples=["result", "rate"],
    display=DisplayMetadata(emoji="💱", i18n_key="convert_currency", visible=True, category="tool"),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "CALCULATE_EXPRESSION_DESCRIPTION",
    "CALCULATION_AGENT_MANIFEST",
    "CURRENCY_AMOUNT_DESCRIPTION",
    "CURRENCY_CODE_DESCRIPTION",
    "CURRENCY_CODE_PATTERN",
    "DATE_AMOUNT_DESCRIPTION",
    "DATE_DATE_DESCRIPTION",
    "DATE_OPERATION_DESCRIPTION",
    "DATE_OTHER_DATE_DESCRIPTION",
    "DATE_TIMEZONE_DESCRIPTION",
    "DATE_TO_TIMEZONE_DESCRIPTION",
    "DATE_UNIT_DESCRIPTION",
    "calculate_catalogue_manifest",
    "convert_currency_catalogue_manifest",
    "date_time_catalogue_manifest",
]
