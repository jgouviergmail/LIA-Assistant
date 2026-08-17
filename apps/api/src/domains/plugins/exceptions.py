"""Plugins domain exceptions — centralized raisers (ADR-225).

Thin wrappers around ``src.core.exceptions`` mirroring the skills domain
pattern (``src/domains/skills/exceptions.py``), so HTTP responses and
structured logs stay consistent and routers never raise raw HTTPException
(CLAUDE.md §18).
"""

from __future__ import annotations

from typing import NoReturn

from src.core.exceptions import ResourceNotFoundError, ValidationError


def raise_plugin_invalid_package(detail: str) -> NoReturn:
    """Raise 400 for a package that violates the Agent Plugins contract.

    Args:
        detail: Technical reason (English; the API layer localizes).

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(f"Invalid plugin package: {detail}")


def raise_plugin_file_too_large(size_bytes: int, max_kb: int) -> NoReturn:
    """Raise 400 when the uploaded package exceeds the size budget.

    Args:
        size_bytes: Actual upload size.
        max_kb: Configured ceiling in kilobytes.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(f"Plugin package too large: {size_bytes} bytes (max {max_kb}KB)")


def raise_plugin_quota_exceeded(max_plugins: int) -> NoReturn:
    """Raise 400 when the per-user installed-plugin quota is reached.

    Args:
        max_plugins: Configured per-user ceiling.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(f"Maximum of {max_plugins} installed plugins per user")


def raise_plugin_not_found(plugin_id: str) -> NoReturn:
    """Raise 404 for a missing installed plugin.

    Args:
        plugin_id: Plugin row identifier from the URL path.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    raise ResourceNotFoundError(
        resource_type="plugin",
        resource_id=plugin_id,
        detail=f"Plugin '{plugin_id}' not found",
    )


# NOTE: the arbitrage-F component locks live in the CONSUMING domains
# (skills/exceptions.raise_skill_locked_by_plugin, user_mcp service) — a
# raiser here would give this domain's only inbound edges and create the
# plugins<->skills / plugins<->user_mcp runtime cycles the coupling ratchet
# forbids (F009). Orchestration stays strictly one-way: plugins → components.
