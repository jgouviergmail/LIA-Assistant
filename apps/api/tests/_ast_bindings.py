"""The one name an assignment binds, and its value — for the AST guards.

Two guards follow a value through the local it is bound to (the locale guard,
the log content guard). Read on ``x = …`` alone, both missed ``x: str = …`` and
``(x := …)``, while their docstrings promised any local. Still not followed: a
chained ``a = b = …``, a tuple target, and a ``for`` or ``with`` target — a
value bound there is not traced to its uses.
"""

from __future__ import annotations

import ast


def binding(node: ast.AST) -> tuple[str, ast.expr] | None:
    """The name an assignment binds and the value it binds to it.

    Args:
        node: Any node of a module.

    Returns:
        ``(name, value)`` for ``x = …``, ``x: T = …`` and ``(x := …)``; None for
        anything else — a tuple target, an attribute, an annotation without a
        value.
    """
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id, node.value
    if (
        isinstance(node, (ast.AnnAssign, ast.NamedExpr))
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        return node.target.id, node.value
    return None
