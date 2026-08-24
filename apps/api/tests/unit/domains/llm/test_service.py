"""Unit tests for LLMModelService (transactional model+pricing orchestration).

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def`` test functions are run automatically
without an explicit ``@pytest.mark.asyncio`` marker.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import (
    LLMModelKindEnum,
    LLMModelPricing,
    LLMProviderEnum,
)
from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.domains.llm.service import LLMModelService

# Default payload: a non-reasoning chat model with full sampling. The
# template mode these tests used to exercise is gone -- the reasoning identity
# is written directly, on both surfaces that edit it.
_BASE_CREATE_FIELDS = {
    "kind": "chat",
    "max_input_tokens": 1000,
    "max_output_tokens": 200,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
    # Custom mode by default — non-reasoning chat with widget='none'.
    "is_reasoning_model": False,
}


def _make_create(model_name: str, **overrides) -> ModelPriceCreate:
    return ModelPriceCreate(
        provider="openai",
        model_name=model_name,
        **{
            "input_unit_price": Decimal("1.0"),
            "cached_input_unit_price": None,
            "output_unit_price": Decimal("3.0"),
            **_BASE_CREATE_FIELDS,
            **overrides,
        },
    )


@pytest.mark.unit
async def test_create_inserts_model_and_pricing_atomically(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-1"))

    assert model.model_name == "svc-1"
    assert model.is_active is True
    assert pricing.model_id == model.id
    assert pricing.is_active is True
    assert pricing.input_unit_price == Decimal("1.0")


@pytest.mark.unit
async def test_create_raises_value_error_when_model_name_already_exists(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-dup"))
    await async_session.commit()
    with pytest.raises(ValueError, match="already exists"):
        await service.create(_make_create("svc-dup"))


@pytest.mark.unit
async def test_update_capabilities_only_mutates_in_place_no_new_pricing_row(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-cap"))
    await async_session.commit()

    update = ModelPriceUpdate(max_output_tokens=9999, supports_vision=True)
    new_model, new_pricing = await service.update("svc-cap", update)

    assert new_model.max_output_tokens == 9999
    assert new_model.supports_vision is True
    assert new_pricing is None  # no pricing row created
    # Original pricing row still active
    await async_session.refresh(pricing)
    assert pricing.is_active is True


@pytest.mark.unit
async def test_update_pricing_only_creates_new_versioned_row_and_deactivates_old(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, old_pricing = await service.create(_make_create("svc-price"))
    await async_session.commit()

    update = ModelPriceUpdate(input_unit_price=Decimal("2.5"))
    new_model, new_pricing = await service.update("svc-price", update)

    assert new_pricing is not None
    assert new_pricing.input_unit_price == Decimal("2.5")
    assert new_pricing.is_active is True
    # Output price preserved from old row (only input changed)
    assert new_pricing.output_unit_price == Decimal("3.0")
    # Old row deactivated
    await async_session.refresh(old_pricing)
    assert old_pricing.is_active is False


@pytest.mark.unit
async def test_update_mixed_does_both_in_one_transaction(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, old_pricing = await service.create(_make_create("svc-mixed"))
    await async_session.commit()

    update = ModelPriceUpdate(
        max_output_tokens=4242,
        input_unit_price=Decimal("5.0"),
    )
    new_model, new_pricing = await service.update("svc-mixed", update)

    assert new_model.max_output_tokens == 4242
    assert new_pricing is not None
    assert new_pricing.input_unit_price == Decimal("5.0")
    await async_session.refresh(old_pricing)
    assert old_pricing.is_active is False


@pytest.mark.unit
async def test_update_renames_model_on_llm_models(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, _ = await service.create(_make_create("svc-rename-old"))
    await async_session.commit()

    update = ModelPriceUpdate(model_name="svc-rename-new")
    new_model, new_pricing = await service.update("svc-rename-old", update)

    assert new_model.model_name == "svc-rename-new"
    # Pure rename → no new pricing row
    assert new_pricing is None


@pytest.mark.unit
async def test_update_rename_conflict_raises_value_error(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-existing"))
    await service.create(_make_create("svc-other"))
    await async_session.commit()

    with pytest.raises(ValueError, match="already exists"):
        await service.update("svc-other", ModelPriceUpdate(model_name="svc-existing"))


@pytest.mark.unit
async def test_update_raises_lookup_error_when_model_missing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    with pytest.raises(LookupError):
        await service.update("no-such-model", ModelPriceUpdate(input_unit_price=Decimal("1.0")))


@pytest.mark.unit
async def test_deactivate_disables_model_and_active_pricing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-deact"))
    await async_session.commit()

    await service.deactivate("svc-deact")

    await async_session.refresh(model)
    await async_session.refresh(pricing)
    assert model.is_active is False
    assert pricing.is_active is False


@pytest.mark.unit
async def test_deactivate_raises_lookup_error_when_missing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    with pytest.raises(LookupError):
        await service.deactivate("no-such-model")


# --- Reasoning template tests ---


@pytest.mark.unit
async def test_a_widget_change_no_longer_constrains_anything(
    async_session: AsyncSession,
) -> None:
    """The widget stopped discriminating a shape, so it stopped having rules.

    Before ADR-245 this exact call raised: switching to ``enum`` without
    supplying ``reasoning_enum_values`` was incoherent, because the widget
    decided how the stored value would be READ. Nothing reads it now -- the
    translator family comes from (provider, model) -- so the only thing the
    rule still did was refuse edits.
    """
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-cohesion"))  # widget=none initially
    await async_session.commit()

    model, _ = await service.update(
        "svc-cohesion",
        ModelPriceUpdate(is_reasoning_model=True),
    )
    assert model.is_reasoning_model is True


@pytest.mark.unit
async def test_a_narrowed_ladder_survives_a_widget_reset(
    async_session: AsyncSession,
) -> None:
    """The rule removed here actively forbade the most useful catalogue row.

    "widget='none' must NOT have reasoning_enum_values" meant an operator could
    not say "this model reasons, and these are the depths it accepts" without
    also maintaining a widget column nothing consults. The narrowing is the ONE
    catalogue value the runtime still reads (ADR-245), so it must survive.
    """
    service = LLMModelService(async_session)
    await service.create(
        _make_create(
            "svc-cohesion-2",
            is_reasoning_model=True,
            reasoning_enum_values=["low", "high"],
        )
    )
    await async_session.commit()

    model, _ = await service.update(
        "svc-cohesion-2", ModelPriceUpdate(reasoning_enum_values=["low", "high"])
    )
    assert model.reasoning_enum_values == ["low", "high"]

    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    # And the runtime still narrows the family ladder with it, whatever the
    # widget column now says.
    profile = resolve_reasoning_profile(
        "openai", "gpt-5.2", model_levels=tuple(model.reasoning_enum_values)
    )
    assert profile.levels == ("low", "high")


@pytest.mark.unit
async def test_update_doc_i18n_key_alone_touches_nothing_else(
    async_session: AsyncSession,
) -> None:
    """``reasoning_doc_i18n_key`` is independent of the reasoning identity.

    It never entered the template fingerprint (it would explode the template
    count for the same shape), and editing it alone must leave the rest of the
    row untouched.
    """
    service = LLMModelService(async_session)
    await service.create(
        _make_create(
            "svc-doc-only",
            is_reasoning_model=True,
            reasoning_enum_values=["low"],
        )
    )
    await async_session.commit()

    # Pure doc_i18n_key update — no widget cohesion needed, must succeed.
    new_model, _ = await service.update(
        "svc-doc-only", ModelPriceUpdate(reasoning_doc_i18n_key="new_key")
    )
    assert new_model.reasoning_doc_i18n_key == "new_key"
    assert new_model.reasoning_enum_values == ["low"]  # unchanged


# ============================================================================
# Time-slot tariffs (ADR-223)
# ============================================================================

_SLOT_PAYLOAD = {
    "start_utc": "01:00",
    "end_utc": "04:00",
    "input_unit_price": "0.44",
    "cached_input_unit_price": "0.014",
    "output_unit_price": "1.32",
}


@pytest.mark.unit
async def test_create_persists_time_slots_as_plain_json(
    async_session: AsyncSession,
) -> None:
    """Slots land in JSONB as floats (psycopg refuses Decimal) and read
    back verbatim — the runtime resolver consumes exactly this shape."""
    service = LLMModelService(async_session)
    _, pricing = await service.create(_make_create("svc-slots", time_slots=[_SLOT_PAYLOAD]))

    assert pricing.time_slots == [
        {
            "start_utc": "01:00",
            "end_utc": "04:00",
            "input_unit_price": 0.44,
            "cached_input_unit_price": 0.014,
            "output_unit_price": 1.32,
        }
    ]


@pytest.mark.unit
async def test_create_normalizes_empty_slots_to_null(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    _, pricing = await service.create(_make_create("svc-slots-empty", time_slots=[]))
    assert pricing.time_slots is None


@pytest.mark.unit
async def test_update_without_time_slots_inherits_them(
    async_session: AsyncSession,
) -> None:
    """A price bump that does not mention slots must carry them onto the
    new temporal version — otherwise every unrelated edit silently
    reverts the model to flat pricing."""
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-slots-inherit", time_slots=[_SLOT_PAYLOAD]))
    await async_session.commit()

    _, new_pricing = await service.update(
        "svc-slots-inherit", ModelPriceUpdate(input_unit_price=Decimal("9.99"))
    )

    assert new_pricing is not None
    assert new_pricing.time_slots is not None
    assert new_pricing.time_slots[0]["start_utc"] == "01:00"


@pytest.mark.unit
async def test_update_with_empty_list_clears_the_slots(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-slots-clear", time_slots=[_SLOT_PAYLOAD]))
    await async_session.commit()

    _, new_pricing = await service.update("svc-slots-clear", ModelPriceUpdate(time_slots=[]))

    assert new_pricing is not None
    assert new_pricing.time_slots is None


@pytest.mark.unit
async def test_update_can_set_slots_on_a_flat_priced_model(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-slots-add"))
    await async_session.commit()

    _, new_pricing = await service.update(
        "svc-slots-add", ModelPriceUpdate(time_slots=[_SLOT_PAYLOAD])
    )

    assert new_pricing is not None
    assert new_pricing.time_slots is not None
    # Base prices inherited from the previous version.
    assert new_pricing.input_unit_price == Decimal("1.0")


@pytest.mark.unit
async def test_update_rejects_switching_to_audio_unit_while_slots_survive(
    async_session: AsyncSession,
) -> None:
    """The schema can only see what the payload carries; switching the unit
    while the CURRENT row holds slots would smuggle a windowed tariff onto
    an audio row. The merged state is validated service-side; the admin
    must clear the slots explicitly (time_slots=[]) in the same call."""
    from src.domains.llm.service import TimeSlotsUnitMismatchError

    service = LLMModelService(async_session)
    await service.create(_make_create("svc-slots-unit", time_slots=[_SLOT_PAYLOAD]))
    await async_session.commit()

    with pytest.raises(TimeSlotsUnitMismatchError):
        await service.update("svc-slots-unit", ModelPriceUpdate(pricing_unit="per_audio_hour"))

    # Clearing alongside the switch is the legal one-call form.
    _, new_pricing = await service.update(
        "svc-slots-unit",
        ModelPriceUpdate(pricing_unit="per_audio_hour", time_slots=[]),
    )
    assert new_pricing is not None
    assert new_pricing.time_slots is None


# ============================================================================
# Reactivation — the inverse of deactivate, which never existed
# ============================================================================


async def test_reactivate_restores_the_model_and_its_last_tariff(
    async_session: AsyncSession,
) -> None:
    """``deactivate`` was a dead end: nothing could bring a model back."""
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("revive-me"))
    await service.deactivate("revive-me")

    restored, restored_pricing = await service.reactivate("revive-me")

    assert restored.is_active is True
    assert restored_pricing is not None and restored_pricing.is_active is True
    assert restored_pricing.id == pricing.id


async def test_reactivate_reports_a_model_that_never_existed(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)

    with pytest.raises(LookupError):
        await service.reactivate("never-existed-at-all")


async def test_reactivate_an_already_active_model_is_a_no_op(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("already-on"))

    model, pricing = await service.reactivate("already-on")

    assert model.is_active is True
    assert pricing is not None and pricing.is_active is True


async def test_reactivate_restores_the_most_recent_tariff(
    async_session: AsyncSession,
) -> None:
    """Several superseded versions may exist; the latest is the one that applies."""
    service = LLMModelService(async_session)
    await service.create(_make_create("many-versions"))
    _, second = await service.update(
        "many-versions", ModelPriceUpdate(input_unit_price=Decimal("5"))
    )
    await service.deactivate("many-versions")

    _, restored = await service.reactivate("many-versions")

    assert second is not None and restored is not None
    assert restored.id == second.id


async def test_reactivate_a_model_without_any_tariff_says_so(
    async_session: AsyncSession,
) -> None:
    """Honest outcome: the model is back, but it would be billed zero."""
    service = LLMModelService(async_session)
    model = await service.repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="no-tariff-ever",
        max_input_tokens=10,
        max_output_tokens=10,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        kind=LLMModelKindEnum.chat,
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        reasoning_doc_i18n_key=None,
        is_reasoning_model=False,
        reasoning_enum_values=None,
    )
    model.is_active = False
    await async_session.flush()

    restored, pricing = await service.reactivate("no-tariff-ever")

    assert restored.is_active is True
    assert pricing is None


async def test_reactivate_leaves_exactly_one_active_tariff(
    async_session: AsyncSession,
) -> None:
    """The partial unique index turns any slip into an IntegrityError."""
    service = LLMModelService(async_session)
    await service.create(_make_create("one-active-only"))
    await service.update("one-active-only", ModelPriceUpdate(input_unit_price=Decimal("7")))
    await service.deactivate("one-active-only")

    await service.reactivate("one-active-only")
    await async_session.flush()

    model = await service.repo.get_by_name("one-active-only")
    assert model is not None
    rows = await async_session.scalars(
        select(LLMModelPricing).where(
            LLMModelPricing.model_id == model.id, LLMModelPricing.is_active
        )
    )
    assert len(list(rows)) == 1


# ============================================================================
# Clearing a cached price — impossible through the current contract
# ============================================================================


async def test_a_cached_price_can_be_cleared_to_null(
    async_session: AsyncSession,
) -> None:
    """``exclude_none`` swallowed a None, so an emptied cell kept its old value.

    73 of 206 active rows carry NULL here: an administrator must be able to
    say "this model has no cached price" and be believed.
    """
    service = LLMModelService(async_session)
    await service.create(_make_create("clear-me", cached_input_unit_price=Decimal("0.5")))

    _, updated = await service.update("clear-me", ModelPriceUpdate(clear_cached_input_price=True))

    assert updated is not None
    assert updated.cached_input_unit_price is None


async def test_clearing_supersedes_the_tariff_like_any_price_change(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    _, first = await service.create(
        _make_create("clear-supersedes", cached_input_unit_price=Decimal("0.5"))
    )

    _, updated = await service.update(
        "clear-supersedes", ModelPriceUpdate(clear_cached_input_price=True)
    )

    assert updated is not None and updated.id != first.id
    assert first.is_active is False


async def test_clearing_preserves_the_other_prices(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("clear-keeps-rest", cached_input_unit_price=Decimal("0.5")))

    _, updated = await service.update(
        "clear-keeps-rest", ModelPriceUpdate(clear_cached_input_price=True)
    )

    assert updated is not None
    assert updated.input_unit_price == Decimal("1.0")
    assert updated.output_unit_price == Decimal("3.0")


async def test_clearing_and_setting_at_once_is_refused(
    async_session: AsyncSession,
) -> None:
    """Two contradictory intents in one payload must not be silently ranked."""
    with pytest.raises(ValidationError):
        ModelPriceUpdate(clear_cached_input_price=True, cached_input_unit_price=Decimal("0.5"))


async def test_not_clearing_leaves_the_cached_price_untouched(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("clear-absent", cached_input_unit_price=Decimal("0.5")))

    _, updated = await service.update(
        "clear-absent", ModelPriceUpdate(input_unit_price=Decimal("9"))
    )

    assert updated is not None
    assert updated.cached_input_unit_price == Decimal("0.5")


async def test_the_update_log_reports_the_outcome_not_the_payload(
    async_session: AsyncSession,
) -> None:
    """Clearing carries no value, yet writes a new tariff version.

    Reporting ``pricing_changed=False`` there would send an operator hunting
    for a write that did happen.
    """
    import contextlib

    import structlog

    from src.domains.llm import service as service_module
    from tests.support.structlog_capture import fresh_module_logger

    restore = fresh_module_logger(service_module)
    next(restore)
    try:
        service = LLMModelService(async_session)
        await service.create(_make_create("log-honesty", cached_input_unit_price=Decimal("0.5")))

        with structlog.testing.capture_logs() as logs:
            await service.update("log-honesty", ModelPriceUpdate(clear_cached_input_price=True))

        entry = next(e for e in logs if e["event"] == "llm_model_updated")
        assert entry["pricing_changed"] is True
    finally:
        with contextlib.suppress(StopIteration):
            next(restore)
