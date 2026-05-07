"""Unit tests for LLMModelService (transactional model+pricing orchestration).

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def`` test functions are run automatically
without an explicit ``@pytest.mark.asyncio`` marker.
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.domains.llm.service import LLMModelService, UnknownReasoningTemplateError

# Default Custom-mode payload: non-reasoning chat model with full sampling.
# Tests that exercise template-mode behavior override ``reasoning_template``
# and clear the explicit reasoning fields via _make_create overrides.
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
    "reasoning_widget": "none",
}


def _make_create(model_name: str, **overrides) -> ModelPriceCreate:
    return ModelPriceCreate(
        provider="openai",
        model_name=model_name,
        input_unit_price=Decimal("1.0"),
        cached_input_unit_price=None,
        output_unit_price=Decimal("3.0"),
        **{**_BASE_CREATE_FIELDS, **overrides},
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
async def test_list_templates_dedupes_by_reasoning_shape(
    async_session: AsyncSession,
) -> None:
    """Two rows with identical reasoning shape but different sampling caps
    collapse into a single template — sampling/kind/doc_i18n_key are NOT
    part of the fingerprint."""
    service = LLMModelService(async_session)
    # Same shape (widget=none, no reasoning) but different sampling caps.
    await service.create(
        _make_create("svc-dedup-a", supports_temperature=True, supports_top_p=True)
    )
    await service.create(
        _make_create("svc-dedup-b", supports_temperature=False, supports_top_p=False)
    )
    await async_session.commit()

    templates = await service.list_templates()
    matching = [t for t in templates if t.template_model_name in {"svc-dedup-a", "svc-dedup-b"}]
    # Both rows share the same fingerprint (is_reasoning=False, widget=none,
    # no enum, no budget), so only ONE template appears with count=2.
    assert len(matching) == 1
    assert matching[0].matching_count >= 2


@pytest.mark.unit
async def test_list_templates_separates_reasoning_shapes(
    async_session: AsyncSession,
) -> None:
    """Different widgets => different templates."""
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-shape-none"))  # widget=none
    await service.create(
        _make_create(
            "svc-shape-enum",
            is_reasoning_model=True,
            reasoning_widget="enum",
            reasoning_enum_values=["low", "medium", "high"],
        )
    )
    await async_session.commit()

    templates = await service.list_templates()
    template_names = {t.template_model_name for t in templates}
    assert "svc-shape-none" in template_names or any(not t.is_reasoning_model for t in templates)
    assert any(
        t.reasoning_widget == "enum" and t.reasoning_enum_values == ["low", "medium", "high"]
        for t in templates
    )


@pytest.mark.unit
async def test_create_template_mode_copies_reasoning_shape(
    async_session: AsyncSession,
) -> None:
    """Template mode copies the 4 reasoning shape fields from the template row."""
    service = LLMModelService(async_session)
    # Create the source template — a reasoning model with enum widget.
    await service.create(
        _make_create(
            "svc-tmpl-source",
            is_reasoning_model=True,
            reasoning_widget="enum",
            reasoning_enum_values=["minimal", "low", "medium", "high"],
        )
    )
    await async_session.commit()

    # Create the new model in Template mode — most fields come from the payload,
    # only the 4 reasoning shape fields are inherited.
    payload = ModelPriceCreate(
        provider="openai",
        model_name="svc-tmpl-target",
        kind="chat",
        max_input_tokens=2000,
        max_output_tokens=500,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        # Sampling caps explicit and DIFFERENT from the source — proving they
        # are NOT copied from the template.
        supports_temperature=False,
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        reasoning_template="svc-tmpl-source",
        input_unit_price=Decimal("1.0"),
        cached_input_unit_price=None,
        output_unit_price=Decimal("3.0"),
    )
    target, _ = await service.create(payload)

    # Reasoning shape inherited from the template.
    assert target.is_reasoning_model is True
    assert target.reasoning_widget.value == "enum"
    assert target.reasoning_enum_values == ["minimal", "low", "medium", "high"]
    # Sampling caps come from the explicit payload — NOT from the template.
    assert target.supports_temperature is False
    assert target.supports_top_p is False
    assert target.supports_frequency_penalty is False
    assert target.supports_presence_penalty is False


@pytest.mark.unit
async def test_create_template_mode_unknown_template_raises(
    async_session: AsyncSession,
) -> None:
    """Template mode with a non-existent template name surfaces a ValueError."""
    service = LLMModelService(async_session)
    payload = ModelPriceCreate(
        provider="openai",
        model_name="svc-tmpl-bad",
        kind="chat",
        max_input_tokens=2000,
        max_output_tokens=500,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        reasoning_template="does-not-exist",
        input_unit_price=Decimal("1.0"),
        cached_input_unit_price=None,
        output_unit_price=Decimal("3.0"),
    )
    with pytest.raises(UnknownReasoningTemplateError, match="does-not-exist"):
        await service.create(payload)


@pytest.mark.unit
async def test_unknown_template_error_is_lookup_error_subclass() -> None:
    """``UnknownReasoningTemplateError`` IS a ``LookupError`` — guarantees
    that legacy ``except LookupError:`` catches still work and avoids
    silently breaking callers that rely on the broad parent class."""
    assert issubclass(UnknownReasoningTemplateError, LookupError)


@pytest.mark.unit
async def test_update_template_mode_unknown_template_raises(
    async_session: AsyncSession,
) -> None:
    """``update()`` with an unknown ``reasoning_template`` surfaces the
    distinct subclass so the router can translate to 400 instead of 404
    (which is reserved for "the model being updated does not exist")."""
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-upd-bad-tmpl"))
    await async_session.commit()

    with pytest.raises(UnknownReasoningTemplateError, match="no-such-template"):
        await service.update(
            "svc-upd-bad-tmpl",
            ModelPriceUpdate(reasoning_template="no-such-template"),
        )


@pytest.mark.unit
async def test_update_template_mode_resets_reasoning_shape(
    async_session: AsyncSession,
) -> None:
    """Update with reasoning_template re-copies the 4 shape fields on an
    existing row."""
    service = LLMModelService(async_session)
    # Source template — enum widget.
    await service.create(
        _make_create(
            "svc-upd-source",
            is_reasoning_model=True,
            reasoning_widget="enum",
            reasoning_enum_values=["low", "medium"],
        )
    )
    # Target — non-reasoning at first.
    target, _ = await service.create(_make_create("svc-upd-target"))
    await async_session.commit()

    new_target, _ = await service.update(
        "svc-upd-target", ModelPriceUpdate(reasoning_template="svc-upd-source")
    )
    assert new_target.is_reasoning_model is True
    assert new_target.reasoning_widget.value == "enum"
    assert new_target.reasoning_enum_values == ["low", "medium"]


@pytest.mark.unit
async def test_update_partial_widget_change_validates_cohesion(
    async_session: AsyncSession,
) -> None:
    """Updating reasoning_widget without enum_values when target=enum raises."""
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-cohesion"))  # widget=none initially
    await async_session.commit()

    # Trying to switch to enum without supplying enum_values must fail.
    with pytest.raises(ValueError, match="reasoning_enum_values"):
        await service.update(
            "svc-cohesion",
            ModelPriceUpdate(is_reasoning_model=True, reasoning_widget="enum"),
        )


@pytest.mark.unit
async def test_update_widget_none_with_enum_values_rejected(
    async_session: AsyncSession,
) -> None:
    """Updating to widget='none' while keeping enum_values raises."""
    service = LLMModelService(async_session)
    await service.create(
        _make_create(
            "svc-cohesion-2",
            is_reasoning_model=True,
            reasoning_widget="enum",
            reasoning_enum_values=["low", "high"],
        )
    )
    await async_session.commit()

    # Switching widget back to 'none' without clearing enum_values is invalid.
    with pytest.raises(ValueError, match="must NOT have"):
        await service.update("svc-cohesion-2", ModelPriceUpdate(reasoning_widget="none"))


@pytest.mark.unit
async def test_update_doc_i18n_key_alone_does_not_trigger_cohesion_check(
    async_session: AsyncSession,
) -> None:
    """``reasoning_doc_i18n_key`` is independent — updating only it must
    NOT trigger widget-cohesion validation."""
    service = LLMModelService(async_session)
    await service.create(
        _make_create(
            "svc-doc-only",
            is_reasoning_model=True,
            reasoning_widget="enum",
            reasoning_enum_values=["low"],
        )
    )
    await async_session.commit()

    # Pure doc_i18n_key update — no widget cohesion needed, must succeed.
    new_model, _ = await service.update(
        "svc-doc-only", ModelPriceUpdate(reasoning_doc_i18n_key="new_key")
    )
    assert new_model.reasoning_doc_i18n_key == "new_key"
    assert new_model.reasoning_widget.value == "enum"  # unchanged
    assert new_model.reasoning_enum_values == ["low"]  # unchanged
