"""Reading the vocabulary a route actually accepts.

Two guards need it — « every export contract is reachable » and « every offered
format has a renderer » — and both exist because a half-wiring shipped: a value
the route refused with a 422 on one side, a contract nothing described on the
other. A second copy of this reader would be a third place for the same
question to be answered slightly differently.

Not a ``conftest`` fixture: it is a plain function over a plain annotation, and
importing it says where it comes from.
"""

from __future__ import annotations

import typing
from collections.abc import Callable
from typing import Any


def literal_values(endpoint: Callable[..., Any], parameter: str) -> set[str]:
    """Every value a route's ``Literal`` parameter accepts.

    Args:
        endpoint: The route function.
        parameter: The parameter to read.

    Returns:
        The accepted values. Handles both spellings FastAPI allows — a bare
        ``Literal[...]`` and an ``Annotated[Literal[...], Query(...)]`` — so a
        future migration to ``Annotated`` cannot quietly empty a guard.
    """
    annotation = typing.get_type_hints(endpoint, include_extras=True)[parameter]
    for arg in typing.get_args(annotation):
        if typing.get_origin(arg) is typing.Literal:
            return set(typing.get_args(arg))
    if typing.get_origin(annotation) is typing.Literal:
        return set(typing.get_args(annotation))
    return set()


__all__ = ["literal_values"]
