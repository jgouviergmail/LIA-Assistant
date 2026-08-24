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
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.llm.models import (
    LLMCapabilityProvenanceEnum,
    LLMModel,
    LLMModelKindEnum,
    LLMModelPricing,
    LLMProviderEnum,
    PricingUnitEnum,
)
from src.domains.llm.pricing_time_slots import slots_to_jsonb
from src.domains.llm.repository import LLMModelRepository
from src.domains.llm.schemas import (
    ModelPriceCreate,
    ModelPriceUpdate,
)
from src.infrastructure.llm.catalogue.sync_diff import CORRECTABLE_FIELDS
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TimeSlotsUnitMismatchError(ValueError):
    """Raised when the merged pricing state pairs time slots with an audio unit.

    The schema can only validate what a single payload carries; switching
    ``pricing_unit`` away from ``per_1m_tokens`` while the current row's
    slots would be inherited (or setting slots while inheriting an audio
    unit) is only detectable here. Subclass of :class:`ValueError`, but the
    router must catch it FIRST — the generic ``ValueError`` handler answers
    ``409 already_exists``, which would misdiagnose this 400.
    """


#: Capability columns the public registries can correct (ADR-244). A human
#: edit to any of them is what turns a row ``verified``: they are exactly the
#: fields the catalogue sync would otherwise rewrite on its own. The single
#: declaration lives in the catalogue package so the sync, the migration and
#: this service cannot disagree about the list.
_REGISTRY_OWNED_FIELDS: frozenset[str] = frozenset(
    column for column, _attribute in CORRECTABLE_FIELDS
)

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
        "kind",
        "reasoning_enum_values",
        "reasoning_doc_i18n_key",
        "supports_temperature",
        "supports_top_p",
        "supports_frequency_penalty",
        "supports_presence_penalty",
    }
)
_PRICING_FIELDS: frozenset[str] = frozenset(
    {
        "input_unit_price",
        "cached_input_unit_price",
        "output_unit_price",
        "pricing_unit",
        "time_slots",
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
            ValueError: if a model with the same ``model_name`` already
                exists. Translated by the router to ``409 already_exists``.
        """
        existing = await self.repo.get_by_name(data.model_name)
        if existing is not None:
            raise ValueError(f"Model {data.model_name!r} already exists")

        # Resolve the reasoning identity (template-copy or explicit
        # custom-mode fields, XOR enforced by the schema validator). ``kind``
        # and the four ``supports_*`` sampling flags are passed straight from
        # the payload — they are independent of the template choice.
        reasoning_block = self._reasoning_block(data)

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
            kind=LLMModelKindEnum(data.kind),
            supports_temperature=data.supports_temperature,
            supports_top_p=data.supports_top_p,
            supports_frequency_penalty=data.supports_frequency_penalty,
            supports_presence_penalty=data.supports_presence_penalty,
            reasoning_doc_i18n_key=data.reasoning_doc_i18n_key,
            **reasoning_block,
        )

        pricing = LLMModelPricing(
            model_id=model.id,
            input_unit_price=data.input_unit_price,
            cached_input_unit_price=data.cached_input_unit_price,
            output_unit_price=data.output_unit_price,
            pricing_unit=PricingUnitEnum(data.pricing_unit),
            # [] normalizes to NULL: both mean flat pricing, and NULL keeps
            # the runtime resolver's fast "no slots" exit.
            time_slots=slots_to_jsonb(data.time_slots) if data.time_slots else None,
            is_active=True,
        )
        # Pre-populate the relationship so callers reading pricing.model.model_name
        # don't trigger a lazy-load (LLMModelPricing.model uses lazy="raise").
        # Do NOT call db.refresh() afterwards: refresh re-reads ALL attributes
        # from the DB and clears the manually-set relationship, which would
        # then fail with InvalidRequestError when read by the router. All
        # column defaults on LLMModelPricing are Python-side (id via uuid4,
        # effective_from via datetime.now), so flush() is sufficient.
        pricing.model = model

        self.db.add(pricing)
        await self.db.flush()
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
                Translated by the router to ``404 not_found``.
            ValueError: if a rename target conflicts with an existing model.
                Translated by the router to ``409 already_exists``.
        """
        model = await self.repo.get_by_name(model_name)
        if model is None:
            raise LookupError(f"Model {model_name!r} not found")

        provided = data.model_dump(exclude_unset=True, exclude_none=True)

        # Clearing the narrowing travels as an intent, not as a null: the
        # change-set above drops nulls, so "no narrowing" had no way to reach
        # the row and a restriction could never be widened back.
        if data.clear_reasoning_enum_values:
            provided["reasoning_enum_values"] = None

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
            # A human editing one of the registry-correctable fields takes
            # ownership of them: the row stops being registry-owned and the
            # catalogue sync may only PROPOSE to it afterwards (ADR-244). This
            # is the one path that produces ``verified``; creation deliberately
            # does not, because the creation form's untouched defaults are
            # exactly what ``declared`` means and stamping them verified would
            # make ``get_effective_context_window`` trust an 8 192 placeholder.
            if cap_changes.keys() & _REGISTRY_OWNED_FIELDS:
                cap_changes["capability_provenance"] = LLMCapabilityProvenanceEnum.verified
            await self.repo.update_capabilities(model.id, **cap_changes)

        if new_name is not None or cap_changes:
            await self.db.flush()

        # 2. Pricing → deactivate old active row, insert new active row.
        # Clearing the cached price is a pricing change in its own right: the
        # payload carries no value, so it would otherwise leave price_changes
        # empty and the intent would evaporate.
        new_pricing: LLMModelPricing | None = None
        if price_changes or data.clear_cached_input_price:
            current = await self._get_active_pricing(model.id)
            if current is None:
                raise LookupError(f"Model {model.model_name!r} has no active pricing row to update")

            new_pricing_unit_value = price_changes.get("pricing_unit", current.pricing_unit.value)
            # Time slots: replace when the payload carries them ([] clears →
            # NULL), inherit the current row's slots otherwise — an unrelated
            # price bump must not silently revert a model to flat pricing.
            # Read from `data` (typed TimeSlotPrice), not from the dumped
            # change set, so JSONB gets the canonical float shape. Validate
            # the MERGED state before mutating anything.
            if "time_slots" in price_changes:
                new_time_slots = slots_to_jsonb(data.time_slots) if data.time_slots else None
            else:
                new_time_slots = current.time_slots or None
            if new_time_slots and new_pricing_unit_value != PricingUnitEnum.per_1m_tokens.value:
                raise TimeSlotsUnitMismatchError(
                    "time_slots are only supported with pricing_unit='per_1m_tokens'; "
                    f"the merged state pairs {len(new_time_slots)} slot(s) with "
                    f"{new_pricing_unit_value!r}. Pass time_slots=[] to clear them "
                    "in the same update."
                )

            current.is_active = False
            await self.db.flush()

            cached_price = (
                None
                if data.clear_cached_input_price
                else price_changes.get("cached_input_unit_price", current.cached_input_unit_price)
            )
            new_pricing = LLMModelPricing(
                model_id=model.id,
                input_unit_price=price_changes.get("input_unit_price", current.input_unit_price),
                cached_input_unit_price=cached_price,
                output_unit_price=price_changes.get("output_unit_price", current.output_unit_price),
                pricing_unit=PricingUnitEnum(new_pricing_unit_value),
                time_slots=new_time_slots,
                is_active=True,
            )
            # Pre-populate relationship; do NOT refresh (would clear it and
            # crash on the lazy="raise" attribute when the router builds the
            # response). flush() alone is sufficient — all defaults are
            # Python-side. See create() for the same reasoning.
            new_pricing.model = model
            self.db.add(new_pricing)
            await self.db.flush()

        # Report the outcome, not the input: clearing the cached price carries
        # no value in the payload, so `price_changes` stays empty while a new
        # tariff version really was written. A log that says otherwise sends an
        # operator looking in the wrong place.
        logger.info(
            "llm_model_updated",
            model_name=model.model_name,
            renamed=new_name is not None,
            capabilities_changed=bool(cap_changes),
            pricing_changed=new_pricing is not None,
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

    async def reactivate(self, model_name: str) -> tuple[LLMModel, LLMModelPricing | None]:
        """Bring a soft-deleted model back, with the tariff it had when retired.

        ``deactivate`` had no inverse: once a model was switched off, nothing in
        the application could switch it back on. The repository docstring
        anticipated the need ("the admin UI may legitimately want to surface a
        deactivated model to re-enable it") — this is it.

        The most recent pricing row is restored, whatever its state, so the
        model resumes at the tariff it was retired on. A model that never had
        one comes back priced at nothing, and the caller is told so by the
        ``None`` rather than left to assume.

        Args:
            model_name: Model to bring back.

        Returns:
            The model and the pricing row now active, or ``None`` when the
            model has no tariff at all.

        Raises:
            LookupError: if no model carries that name.
        """
        model = await self.repo.get_by_name(model_name)
        if model is None:
            raise LookupError(f"Model {model_name!r} not found")

        model.is_active = True

        # Retire anything still flagged active before restoring the latest row:
        # the partial unique index (migration 6e7f8a9b0c1d) tolerates exactly
        # one, and the UPDATE must reach the database before the restore.
        await self.db.execute(
            update(LLMModelPricing)
            .where(
                LLMModelPricing.model_id == model.id,
                LLMModelPricing.is_active,
            )
            .values(is_active=False)
        )
        await self.db.flush()

        latest = (
            await self.db.scalars(
                select(LLMModelPricing)
                .where(LLMModelPricing.model_id == model.id)
                .order_by(
                    LLMModelPricing.effective_from.desc(),
                    LLMModelPricing.id.desc(),
                )
                .limit(1)
            )
        ).first()

        if latest is not None:
            latest.is_active = True
            latest.model = model
        await self.db.flush()

        logger.info(
            "llm_model_reactivated",
            model_name=model_name,
            tariff_restored=latest is not None,
        )
        return model, latest

    async def get_active_pricing_for(self, model_id: uuid.UUID) -> LLMModelPricing | None:
        """Public helper: return the active pricing row for a model, or ``None``."""
        return await self._get_active_pricing(model_id)

    @staticmethod
    def _normalise_shape_value(value: Any) -> Any:
        """Convert a shape attribute to a hashable form for fingerprinting.

        - JSONB lists are converted to tuples (preserving order).
        - Everything else (bool / str / None) passes through.
        """
        if isinstance(value, list):
            return tuple(value)
        return value

    @staticmethod
    def _reasoning_block(data: ModelPriceCreate) -> dict[str, Any]:
        """The reasoning kwargs to pass to ``create_model``.

        It used to have a second branch, copying the identity from another
        row named by ``reasoning_template``. Both surfaces that offered that
        write the ladder themselves now, and copying it across families could
        only remove depths -- silently, since a template groups models by
        their stored ladder rather than by family.

        ``reasoning_doc_i18n_key`` is NOT in this block: the caller passes it.
        """
        return {
            "is_reasoning_model": data.is_reasoning_model,
            "reasoning_enum_values": data.reasoning_enum_values,
        }

    async def _get_active_pricing(self, model_id: uuid.UUID) -> LLMModelPricing | None:
        # Deterministic order: the most recent active row is the one an update
        # supersedes. Without it, an update on a database holding legacy
        # duplicates deactivated an arbitrary row and left the others active.
        stmt = (
            select(LLMModelPricing)
            .options(selectinload(LLMModelPricing.model))
            .where(
                LLMModelPricing.model_id == model_id,
                LLMModelPricing.is_active,
            )
            .order_by(
                LLMModelPricing.effective_from.desc(),
                LLMModelPricing.id.desc(),
            )
        )
        return (await self.db.execute(stmt)).scalars().first()
