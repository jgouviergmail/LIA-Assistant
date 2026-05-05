"""Repository for LLMModel CRUD operations.

The catalogue table ``llm_models`` is mutated in place (no temporal versioning
at this layer). Pricing operations live on ``LLMModelPricing`` and keep their
own temporal versioning.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.llm.models import LLMModel, LLMProviderEnum
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Fields the admin UI is allowed to mutate in place. ``provider`` and
# ``model_name`` are intrinsic identifiers and must NOT be changed via this
# code path (rename happens at the service layer through a dedicated flow).
_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {"provider", "model_name", "id", "created_at", "updated_at"}
)

# Set of column names actually present on LLMModel. Used to fail loud on
# typos in update_capabilities() rather than silently no-op via setattr()
# on a non-instrumented attribute.
#
# IMPORTANT: read from __table__.columns rather than mapper.column_attrs.
# The latter triggers eager mapper configuration on import, which fires
# before all domain models are loaded — leading to "expression 'X' failed
# to locate a name" errors for cross-domain relationships (e.g. User →
# UserSkillState). Table-level introspection has no such side effect.
_LLM_MODEL_COLUMNS: frozenset[str] = frozenset(LLMModel.__table__.columns.keys())


class LLMModelRepository(BaseRepository[LLMModel]):
    """Repository for the ``llm_models`` catalogue table.

    Inherits soft-delete-aware ``get_by_id`` / ``get_all``, ``create`` (with
    refresh + Prometheus metrics) and ``soft_delete`` from ``BaseRepository``.
    Adds domain-specific lookup by ``model_name`` and a guarded
    ``update_capabilities`` for partial in-place mutation.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, LLMModel)

    async def create_model(
        self,
        *,
        provider: LLMProviderEnum,
        model_name: str,
        max_input_tokens: int,
        max_output_tokens: int,
        supports_tools: bool,
        supports_structured_output: bool,
        supports_strict_mode: bool,
        supports_streaming: bool,
        supports_vision: bool,
        is_reasoning_model: bool,
    ) -> LLMModel:
        """Insert a new active llm_models row and return it (flushed + refreshed).

        Wrapper around ``BaseRepository.create`` that exposes a typed keyword
        signature instead of a free-form dict. ``id`` is generated server-side
        via ``gen_random_uuid()``.
        """
        return await self.create(
            {
                "provider": provider,
                "model_name": model_name,
                "max_input_tokens": max_input_tokens,
                "max_output_tokens": max_output_tokens,
                "supports_tools": supports_tools,
                "supports_structured_output": supports_structured_output,
                "supports_strict_mode": supports_strict_mode,
                "supports_streaming": supports_streaming,
                "supports_vision": supports_vision,
                "is_reasoning_model": is_reasoning_model,
                "is_active": True,
            }
        )

    async def get_by_name(self, model_name: str) -> LLMModel | None:
        """Return the row by globally unique ``model_name``, or ``None`` if missing.

        Returns inactive rows too (the catalogue is small; soft-delete-awareness
        for lookup-by-name is the caller's responsibility — the admin UI may
        legitimately want to surface a deactivated model to re-enable it).
        """
        stmt = select(LLMModel).where(LLMModel.model_name == model_name)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_active(self) -> list[LLMModel]:
        """Return all active rows, ordered by ``model_name`` (cache-friendly).

        The parent's ``get_all()`` excludes inactive rows by default but does
        not order; we add an explicit ORDER BY because the
        ``ModelCapabilitiesCache`` relies on a stable iteration order to log
        deterministically.
        """
        stmt = select(LLMModel).where(LLMModel.is_active).order_by(LLMModel.model_name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_capabilities(self, model_id: uuid.UUID, **fields: Any) -> LLMModel:
        """Mutate-in-place update of capability columns.

        Args:
            model_id: target row identifier.
            **fields: column → new value. Only capability columns are accepted;
                attempts to mutate ``provider``, ``model_name``, ``id``,
                ``created_at`` or ``updated_at`` raise ``ValueError``. Unknown
                keys (typos) also raise ``ValueError`` — never silently no-op.

        Returns:
            The refreshed model.

        Raises:
            ValueError: if any forbidden or unknown field is in ``fields``.
            LookupError: if no active row matches ``model_id``.
        """
        forbidden = _IMMUTABLE_FIELDS & fields.keys()
        if forbidden:
            raise ValueError(f"Cannot update immutable fields: {sorted(forbidden)}")

        unknown = fields.keys() - _LLM_MODEL_COLUMNS
        if unknown:
            raise ValueError(f"Unknown LLMModel fields: {sorted(unknown)}")

        # get_by_id from BaseRepository excludes inactive rows by default —
        # callers should not be able to silently mutate a deactivated model.
        model = await self.get_by_id(model_id)
        if model is None:
            raise LookupError(f"LLMModel not found or inactive: {model_id}")

        return await self.update(model, fields)

    async def deactivate_by_id(self, model_id: uuid.UUID) -> None:
        """Soft-delete by ID: set ``is_active=False``.

        Raises:
            LookupError: if no active row matches ``model_id``.
        """
        model = await self.get_by_id(model_id)
        if model is None:
            raise LookupError(f"LLMModel not found or inactive: {model_id}")
        await self.soft_delete(model)
