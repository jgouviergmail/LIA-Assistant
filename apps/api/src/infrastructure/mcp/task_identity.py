"""Bind a delegation callable to the exact MCP identity carried by its alias."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from inspect import Signature, signature, unwrap
from typing import get_type_hints

from langchain_core.tools import StructuredTool

from src.domains.agents.effects.runtime import EFFECT_GATED_ATTR, EFFECT_GATED_NAME_ATTR
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput

MCP_TASK_IDENTITY_METADATA_KEY = "mcp_task_identity"
_IDENTITY_GUARD_ATTR = "__mcp_task_identity_guard__"
_IDENTITY_BINDING_ATTR = "__mcp_task_identity_binding__"
_WRAPPED_ATTR = "__wrapped__"


def _already_bound(function: Callable[..., object], expected: Mapping[str, str], name: str) -> bool:
    return getattr(function, _IDENTITY_GUARD_ATTR, None) is function and getattr(
        function, _IDENTITY_BINDING_ATTR, None
    ) == (name, tuple(sorted(expected.items())))


def _preserve_gate(
    checked: Callable[..., object],
    original: Callable[..., object],
    expected: Mapping[str, str],
    name: str,
) -> None:
    setattr(checked, _IDENTITY_GUARD_ATTR, checked)
    setattr(checked, _IDENTITY_BINDING_ATTR, (name, tuple(sorted(expected.items()))))
    if (
        getattr(original, EFFECT_GATED_ATTR, False)
        and getattr(original, EFFECT_GATED_NAME_ATTR, None) == name
    ):
        setattr(checked, EFFECT_GATED_ATTR, True)
        setattr(checked, EFFECT_GATED_NAME_ATTR, name)
        # Re-gating a renamed copy unwraps to the ungated guarded body, rather
        # than nesting the previous alias's gate. The closure still calls that
        # original gate until the registry rebinds under the new alias.
        setattr(checked, _WRAPPED_ATTR, getattr(original, _WRAPPED_ATTR, original))


def _contract(function: Callable[..., object], expected: Mapping[str, str]) -> Signature:
    declared = signature(function)
    if not expected or not expected.keys() <= declared.parameters.keys():
        raise ValueError("MCP task identity must name declared callable parameters")
    return declared


def _matches(
    declared: Signature,
    expected: Mapping[str, str],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> bool:
    try:
        supplied = declared.bind(*args, **kwargs)
    except TypeError:
        return False
    supplied.apply_defaults()
    return all(
        isinstance(value := supplied.arguments.get(name), str) and value == expected_value
        for name, expected_value in expected.items()
    )


def _invalid_identity(expected: Mapping[str, str]) -> UnifiedToolOutput:
    accepted = "; ".join(f"{name} must be exactly {value!r}" for name, value in expected.items())
    return UnifiedToolOutput.failure(
        message="This MCP task is bound to one server. " + accepted,
        error_code=ToolErrorCode.INVALID_INPUT.value,
    )


def _sync_bound(
    function: Callable[..., object],
    expected: Mapping[str, str],
    name: str,
) -> Callable[..., object]:
    if _already_bound(function, expected, name):
        return function
    declared = _contract(function, expected)

    @wraps(function, updated=())
    def checked(*args: object, **kwargs: object) -> object:
        if not _matches(declared, expected, args, kwargs):
            return _invalid_identity(expected)
        return function(*args, **kwargs)

    # Resolved annotations retain config/runtime injection across module globals.
    checked.__annotations__ = get_type_hints(unwrap(function), include_extras=True)
    _preserve_gate(checked, function, expected, name)
    return checked


def _async_bound(
    function: Callable[..., Awaitable[object]],
    expected: Mapping[str, str],
    name: str,
) -> Callable[..., Awaitable[object]]:
    if _already_bound(function, expected, name):
        return function
    declared = _contract(function, expected)

    @wraps(function, updated=())
    async def checked(*args: object, **kwargs: object) -> object:
        if not _matches(declared, expected, args, kwargs):
            return _invalid_identity(expected)
        return await function(*args, **kwargs)

    checked.__annotations__ = get_type_hints(unwrap(function), include_extras=True)
    _preserve_gate(checked, function, expected, name)
    return checked


def bind_task_identity(task: StructuredTool, expected: Mapping[str, str]) -> StructuredTool:
    """Copy a task while guarding every callable entry before its original body.

    Args:
        task: The named per-server task copy, with its original callable and schema.
        expected: Exact declared server target fields, never inferred from an alias.

    Returns:
        A copy preserving schema, metadata, injected parameters and existing gates.

    Raises:
        ValueError: The task has no callable or the identity names undeclared fields.
    """
    identity = dict(expected)
    if task.func is None and task.coroutine is None:
        raise ValueError("MCP task identity requires a callable")
    metadata = {**(task.metadata or {}), MCP_TASK_IDENTITY_METADATA_KEY: dict(identity)}
    updates: dict[str, object] = {"metadata": metadata}
    if task.func is not None:
        updates["func"] = _sync_bound(task.func, identity, task.name)
    if task.coroutine is not None:
        updates["coroutine"] = _async_bound(task.coroutine, identity, task.name)
    return task.model_copy(update=updates)
