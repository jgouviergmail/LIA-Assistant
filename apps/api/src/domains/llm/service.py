"""Service that orchestrates llm_models + llm_model_pricing transactions.

Glue layer between admin endpoints and the two repositories. Encapsulates the
three update patterns:

- **Capabilities only** → mutate the ``llm_models`` row in place.
- **Pricing only** → temporal versioning on ``llm_model_pricing`` (deactivate
  the old active row, insert a new active row pointing to the same model).
- **Mixed** → both, in a single transaction.

The service does NOT commit on its own; the caller (router) controls the
transaction boundary so audit logging stays consistent with the data write.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.llm.models import LLMModel, LLMModelPricing, LLMProviderEnum
from src.domains.llm.repository import LLMModelRepository
from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Field partition between the two tables.
_CAPABILITY_FIELDS: frozenset[str] = frozenset(
    {
        "max_input_tokens",
        "max_output_tokens",
        "supports_tools",
        "supports_structured_output",
        "supports_strict_mode",
        "supports_streaming",
        "supports_vision",
        "is_reasoning_model",
    }
)
_PRICING_FIELDS: frozenset[str] = frozenset(
    {
        "input_price_per_1m_tokens",
        "cached_input_price_per_1m_tokens",
        "output_price_per_1m_tokens",
    }
)


class LLMModelService:
    """Transactional orchestration of llm_models + llm_model_pricing writes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = LLMModelRepository(db)

    async def create(self, data: ModelPriceCreate) -> tuple[LLMModel, LLMModelPricing]:
        """Create a new model + its initial active pricing row in one transaction.

        Raises:
            ValueError: if a model with the same ``model_name`` already exists.
        """
        existing = await self.repo.get_by_name(data.model_name)
        if existing is not None:
            raise ValueError(f"Model {data.model_name!r} already exists")

        model = await self.repo.create_model(
            provider=LLMProviderEnum(data.provider),
            model_name=data.model_name,
            max_input_tokens=data.max_input_tokens,
            max_output_tokens=data.max_output_tokens,
            supports_tools=data.supports_tools,
            supports_structured_output=data.supports_structured_output,
            supports_strict_mode=data.supports_strict_mode,
            supports_streaming=data.supports_streaming,
            supports_vision=data.supports_vision,
            is_reasoning_model=data.is_reasoning_model,
        )

        pricing = LLMModelPricing(
            model_id=model.id,
            input_price_per_1m_tokens=data.input_price_per_1m_tokens,
            cached_input_price_per_1m_tokens=data.cached_input_price_per_1m_tokens,
            output_price_per_1m_tokens=data.output_price_per_1m_tokens,
            is_active=True,
        )
        # Pre-populate the relationship so callers reading pricing.model.model_name
        # don't trigger a lazy-load (LLMModelPricing.model uses lazy="raise").
        pricing.model = model

        self.db.add(pricing)
        await self.db.flush()
        await self.db.refresh(pricing)
        return model, pricing

    async def update(
        self,
        model_name: str,
        data: ModelPriceUpdate,
    ) -> tuple[LLMModel, LLMModelPricing | None]:
        """Update capabilities (in place) and/or pricing (temporal versioning).

        Args:
            model_name: lookup key (current name on llm_models).
            data: partial update payload. ``data.model_name``, if provided and
                different from ``model_name``, renames the model.

        Returns:
            (updated_model, new_pricing_or_None)
            - ``new_pricing_or_None`` is ``None`` when the update only touched
              capabilities or only renamed the model.

        Raises:
            LookupError: if no active model matches ``model_name``.
            ValueError: if a rename target conflicts with an existing model.
        """
        model = await self.repo.get_by_name(model_name)
        if model is None:
            raise LookupError(f"Model {model_name!r} not found")

        provided = data.model_dump(exclude_unset=True, exclude_none=True)
        cap_changes = {k: v for k, v in provided.items() if k in _CAPABILITY_FIELDS}
        price_changes = {k: v for k, v in provided.items() if k in _PRICING_FIELDS}
        new_name = data.model_name if data.model_name and data.model_name != model_name else None

        # 1. Rename + capability mutations on llm_models (in place).
        if new_name is not None:
            conflict = await self.repo.get_by_name(new_name)
            if conflict is not None:
                raise ValueError(f"Model {new_name!r} already exists")
            model.model_name = new_name

        if cap_changes:
            await self.repo.update_capabilities(model.id, **cap_changes)

        if new_name is not None or cap_changes:
            await self.db.flush()

        # 2. Pricing → deactivate old active row, insert new active row.
        new_pricing: LLMModelPricing | None = None
        if price_changes:
            current = await self._get_active_pricing(model.id)
            if current is None:
                raise LookupError(f"Model {model.model_name!r} has no active pricing row to update")
            current.is_active = False
            await self.db.flush()

            new_pricing = LLMModelPricing(
                model_id=model.id,
                input_price_per_1m_tokens=price_changes.get(
                    "input_price_per_1m_tokens", current.input_price_per_1m_tokens
                ),
                cached_input_price_per_1m_tokens=price_changes.get(
                    "cached_input_price_per_1m_tokens",
                    current.cached_input_price_per_1m_tokens,
                ),
                output_price_per_1m_tokens=price_changes.get(
                    "output_price_per_1m_tokens", current.output_price_per_1m_tokens
                ),
                is_active=True,
            )
            new_pricing.model = model
            self.db.add(new_pricing)
            await self.db.flush()
            await self.db.refresh(new_pricing)

        logger.info(
            "llm_model_updated",
            model_name=model.model_name,
            renamed=new_name is not None,
            capabilities_changed=bool(cap_changes),
            pricing_changed=bool(price_changes),
        )
        return model, new_pricing

    async def deactivate(self, model_name: str) -> None:
        """Soft-delete the model AND its active pricing row, atomically.

        Past conversations keep their accurate cost-history because the
        deactivated pricing row stays in the table (only ``is_active`` flips).

        Raises:
            LookupError: if no active model matches ``model_name``.
        """
        model = await self.repo.get_by_name(model_name)
        if model is None:
            raise LookupError(f"Model {model_name!r} not found")

        model.is_active = False
        current = await self._get_active_pricing(model.id)
        if current is not None:
            current.is_active = False
        await self.db.flush()

        logger.info("llm_model_deactivated", model_name=model_name)

    async def get_active_pricing_for(self, model_id: uuid.UUID) -> LLMModelPricing | None:
        """Public helper: return the active pricing row for a model, or ``None``."""
        return await self._get_active_pricing(model_id)

    async def _get_active_pricing(self, model_id: uuid.UUID) -> LLMModelPricing | None:
        stmt = (
            select(LLMModelPricing)
            .options(selectinload(LLMModelPricing.model))
            .where(
                LLMModelPricing.model_id == model_id,
                LLMModelPricing.is_active,
            )
        )
        return (await self.db.execute(stmt)).scalars().first()
