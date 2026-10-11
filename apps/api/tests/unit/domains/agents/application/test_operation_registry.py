"""Closed application operations cannot expand authority through their inputs."""

from datetime import UTC, datetime
from importlib import import_module
from types import ModuleType
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from src.core.exceptions import AuthorizationError
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def _module(name: str) -> ModuleType:
    try:
        return import_module(f"src.domains.agents.application.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"The closed application {name} contract is missing")


class Empty(BaseModel):
    pass


def actor(*, active: bool = True, administrator: bool = False) -> User:
    return User(id=uuid4(), is_active=active, is_superuser=administrator, deleted_at=None)


def test_operation_identity_is_unique_and_unknown_operations_are_refused() -> None:
    module = _module("operation_spec")
    registry = module.OperationRegistry()
    spec = module.ApplicationOperationSpec(
        operation_id="preferences.read",
        tool_name="get_lia_preferences_tool",
        sections=("font-size",),
        input_model=Empty,
        output_model=Empty,
        kind=module.OperationKind.READ,
    )
    registry.register(spec)
    assert registry.get("preferences.read") is spec
    with pytest.raises(ValueError):
        registry.register(spec)
    with pytest.raises(KeyError):
        registry.get("arbitrary.http")


def test_admin_and_disabled_operations_are_removed_before_selection() -> None:
    module = _module("operation_spec")
    registry = module.OperationRegistry()
    for name, administrative in [("preferences.read", False), ("users.read", True)]:
        registry.register(
            module.ApplicationOperationSpec(
                operation_id=name,
                tool_name=f"{name.replace('.', '_')}_tool",
                sections=("admin-users" if administrative else "font-size",),
                input_model=Empty,
                output_model=Empty,
                kind=module.OperationKind.READ,
                administrative=administrative,
            )
        )
    assert [spec.operation_id for spec in registry.visible(actor(), enabled=True)] == [
        "preferences.read"
    ]
    assert len(registry.visible(actor(administrator=True), enabled=True)) == 2
    assert registry.visible(actor(administrator=True), enabled=False) == ()
    assert registry.visible(actor(active=False), enabled=True) == ()


@pytest.mark.parametrize(
    "field",
    ["is_superuser", "is_active", "hashed_password", "provider_key", "full_name", "picture_url"],
)
def test_personal_patch_refuses_privileged_or_credential_fields(field: str) -> None:
    patch = _module("schemas").PreferencePatch
    with pytest.raises(ValidationError):
        patch.model_validate(
            {field: "Changed identity" if field in {"full_name", "picture_url"} else True}
        )


def test_patch_schema_does_not_offer_profile_identity_fields_without_ui_controls() -> None:
    properties = _module("schemas").PreferencePatch.model_json_schema()["properties"]
    assert "full_name" not in properties
    assert "picture_url" not in properties


@pytest.mark.parametrize("size", [True, "17", 17.5, None])
def test_font_size_keeps_the_existing_strict_type_and_null_contract(size: object) -> None:
    patch = _module("schemas").PreferencePatch
    with pytest.raises(ValidationError):
        patch.model_validate({"font_size": size})


def test_valid_patch_does_not_write_omitted_fields() -> None:
    patch = _module("schemas").PreferencePatch.model_validate({"font_size": 17})
    assert patch.model_dump(exclude_unset=True) == {"font_size": 17}


def test_unknown_user_preference_field_requires_explicit_coverage() -> None:
    registry = _module("preference_fields")
    registry.assert_preference_field_coverage(set(registry.PREFERENCE_FIELDS))
    with pytest.raises(AssertionError):
        registry.assert_preference_field_coverage(set(registry.PREFERENCE_FIELDS) | {"new_secret"})


@pytest.mark.parametrize("administrative", [False, True])
def test_missing_inactive_or_deleted_actor_cannot_invoke_an_adapter(administrative: bool) -> None:
    authorize = _module("authorization").authorize_actor
    deleted = actor()
    deleted.deleted_at = datetime.now(UTC)
    for user in [None, actor(active=False), deleted]:
        with pytest.raises(AuthorizationError):
            authorize(user, administrative=administrative)


def test_admin_authority_is_checked_inside_the_operation() -> None:
    authorize = _module("authorization").authorize_actor
    with pytest.raises(AuthorizationError):
        authorize(actor(), administrative=True)
    administrator = actor(administrator=True)
    assert authorize(administrator, administrative=True) is administrator


def test_a_resource_owner_is_independent_of_the_injected_actor() -> None:
    authorize = _module("authorization").authorize_actor
    user = actor()
    with pytest.raises(AuthorizationError):
        authorize(user, owner_id=uuid4())
    assert authorize(user, owner_id=user.id) is user
