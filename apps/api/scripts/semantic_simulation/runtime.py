"""DB-pinned clients, conservative monetary bounds and instance accounting."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from time import time
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from openai import AsyncOpenAI
from sqlalchemy import select

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.models import LLMConfigOverride
from src.domains.usage_limits.instance_spend import record_instance_llm_spend
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    PricingCacheData,
    PricingCacheService,
    capture_pricing_snapshot,
    get_cached_model_price,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.llm.usage_metadata import model_name_of, model_name_of_response

Slot = Literal["planner", "react_agent", "query_analyzer"]
SLOTS: tuple[Slot, ...] = ("planner", "react_agent", "query_analyzer")


@dataclass
class ProbeRuntime:
    clients: dict[Slot, BaseChatModel]
    configuration: dict[Slot, dict[str, object]]
    prices: dict[Slot, CachedModelPrice]
    snapshot: PricingCacheData
    budget_eur: float
    spent_eur: float = 0.0
    calls: list[dict[str, object]] = field(default_factory=list)


def _without_retries(client: BaseChatModel) -> BaseChatModel:
    """Disable both LangChain and the already constructed SDK transport retries."""
    transport = getattr(client, "root_async_client", None)
    if "max_retries" not in type(client).model_fields or not isinstance(transport, AsyncOpenAI):
        raise ValueError("This probe requires a verifiable OpenAI-compatible async transport")
    transport = transport.with_options(max_retries=0)
    return client.model_copy(
        update={
            "max_retries": 0,
            "root_async_client": transport,
            "async_client": transport.chat.completions,
        }
    )


async def _database_routing() -> dict[str, LLMConfigOverride]:
    """Load the same caches as runtime, requiring explicit DB routing."""
    import_all_models()
    async with get_db_context() as db:
        rows = (
            (
                await db.execute(
                    select(LLMConfigOverride).where(LLMConfigOverride.llm_type.in_(SLOTS))
                )
            )
            .scalars()
            .all()
        )
        configurations = {row.llm_type: row for row in rows}
        for slot in SLOTS:
            row = configurations.get(slot)
            if row is None or not row.model or not row.provider:
                raise ValueError(f"{slot} needs an explicit model AND provider in the database")
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    return configurations


async def prepare(budget_eur: float) -> ProbeRuntime:
    """Never accept a model/provider inherited solely from constants."""
    configurations = await _database_routing()
    # Require a fresh DB tariff; do not adopt an old Redis fallback for measurement.
    if not await PricingCacheService(await get_redis_cache()).refresh_from_database():
        raise ValueError("Fresh database pricing is unavailable")
    public: dict[Slot, dict[str, object]] = {}
    clients: dict[Slot, BaseChatModel] = {}
    prices: dict[Slot, CachedModelPrice] = {}
    for slot in SLOTS:
        row = configurations[slot]
        effective = get_llm_config_for_agent(settings, slot)
        if (effective.provider, effective.model) != (row.provider, row.model):
            raise ValueError(f"Effective {slot} model differs from its database row")
        client = get_llm(slot, config_override=effective)
        if model_name_of(client) != row.model:
            raise ValueError(f"Client {slot} model differs from its database row")
        clients[slot] = _without_retries(client)
        price = get_cached_model_price(effective.model)
        if price is None or price.pricing_unit != "per_1m_tokens":
            raise ValueError(f"No token price for database model {row.model}")
        prices[slot] = price
        public[slot] = {
            "provider": row.provider,
            "model": row.model,
            "db_updated_at": row.updated_at.isoformat(),
            "db_model_required": True,
            "effective": effective.model_dump(
                mode="json",
                include={
                    "provider",
                    "model",
                    "temperature",
                    "max_tokens",
                    "timeout_seconds",
                    "reasoning_effort",
                },
            ),
            "inherited_fields": [
                name
                for name in ("temperature", "max_tokens", "timeout_seconds", "reasoning_effort")
                if getattr(row, name) is None
            ],
            "experiment_max_retries": 0,
            "experiment_sdk_max_retries": 0,
            "price": asdict(price),
        }
    return ProbeRuntime(clients, public, prices, capture_pricing_snapshot(), budget_eur)


def upper_cost_eur(runtime: ProbeRuntime, slot: Slot, input_bytes: int) -> float:
    """One byte per input token plus framing reserve, worst declared time-slot rate."""
    price = runtime.prices[slot]
    input_rate = max(price.input_unit_price, price.cached_input_unit_price)
    output_rate = price.output_unit_price
    for window in price.time_slots or []:
        input_rate = max(input_rate, float(window.get("input_unit_price", 0)))
        cached_rate = window.get("cached_input_unit_price")
        if cached_rate is not None:
            input_rate = max(input_rate, float(cached_rate))
        output_rate = max(output_rate, float(window.get("output_unit_price", 0)))
    effective = runtime.configuration[slot]["effective"]
    if not isinstance(effective, dict):
        raise ValueError("Invalid effective configuration")
    max_tokens = effective.get("max_tokens")
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("Output tokens must have a finite configured bound")
    usd = (
        (input_bytes + 10_000) * input_rate * max(1.0, price.cache_write_multiplier)
        + max_tokens * output_rate
    ) / 1_000_000
    return float(usd * runtime.snapshot.usd_eur_rate)


async def _check_database_identity(runtime: ProbeRuntime, slot: Slot) -> None:
    async with get_db_context() as db:
        row = (
            await db.execute(select(LLMConfigOverride).where(LLMConfigOverride.llm_type == slot))
        ).scalar_one()
        if (row.provider, row.model) != (
            runtime.configuration[slot]["provider"],
            runtime.configuration[slot]["model"],
        ):
            raise ValueError("Database routing changed during the experiment; stop")


async def invoke(
    runtime: ProbeRuntime,
    slot: Slot,
    messages: list[BaseMessage],
    *,
    case: str,
    tools: list[dict[str, object]] | None = None,
    tool_choice: str | None = None,
) -> AIMessage:
    """One attempt, no retry or fallback; settle every captured paid attempt."""
    import json

    await _check_database_identity(runtime, slot)
    await enforce_usage_limit(None, layer="semantic_simulation")
    input_bytes = sum(len(message.model_dump_json().encode("utf-8")) for message in messages)
    input_bytes += len(json.dumps(tools or [], ensure_ascii=False).encode("utf-8"))
    bound = upper_cost_eur(runtime, slot, input_bytes)
    if runtime.spent_eur + bound > runtime.budget_eur:
        raise ValueError("Next attempt could exceed the authorized euro ceiling")
    client = runtime.clients[slot]
    model = str(runtime.configuration[slot]["model"])
    capture = TokenCaptureHandler(model)
    started_at = time()
    response: AIMessage | None = None
    error_type: str | None = None
    try:
        runnable = client.bind_tools(tools, tool_choice=tool_choice) if tools else client
        result = await runnable.ainvoke(messages, config={"callbacks": [capture]})
        if not isinstance(result, AIMessage):
            raise ValueError("Expected an AIMessage")
        response = result
        return response
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        await _settle(runtime, slot, case, capture, response, started_at, bound, error_type)


async def _settle(
    runtime: ProbeRuntime,
    slot: Slot,
    case: str,
    capture: TokenCaptureHandler,
    response: AIMessage | None,
    started_at: float,
    bound: float,
    error_type: str | None,
) -> None:
    model = str(runtime.configuration[slot]["model"])
    if response is not None:
        capture.ensure_response_record(
            response, model_name=model, started_at=started_at, snapshot=runtime.snapshot
        )
    records = capture.claim_billing_records(model)
    cost = sum(record.cost_eur for record in records)
    runtime.spent_eur += cost
    await record_instance_llm_spend(
        surface="semantic_simulation",
        model_name=model,
        tokens_in=capture.tokens_in,
        tokens_out=capture.tokens_out,
        billing_records=records,
    )
    runtime.calls.append(
        {
            "case": case,
            "slot": slot,
            "requested_model": model,
            "response_model": model_name_of_response(response),
            "started_at": datetime.fromtimestamp(started_at, UTC).isoformat(),
            "duration_seconds": time() - started_at,
            "upper_bound_eur": bound,
            "cost_eur": cost,
            "billing_records": [record.model_dump() for record in records],
            "error_type": error_type,
        }
    )
    if not capture.has_usage:
        # Unknown cost may be bounded, but may never authorize further spending.
        runtime.spent_eur += bound
        raise ValueError("Provider reported no usage; stop further paid probes")
