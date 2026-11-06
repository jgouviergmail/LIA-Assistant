"""PageAppSentinel — placeholder for an interactive page (ADR-370).

Renders the ``<div>`` the frontend intercepts and replaces with ``PageAppWidget``.
It holds no text of its own: a copy, an export or a voice reading the message has
nothing to read here, and nothing shows before the widget mounts.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
)


class PageAppSentinel(BaseComponent):
    """Renders the placeholder ``PageAppWidget`` replaces on the frontend."""

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render the sentinel.

        Args:
            data: The registry payload, which carries the registry id.
            ctx: The render context (unused: the sentinel says nothing).
            assistant_comment: Unused.
            suggested_actions: Unused.
            with_wrapper: Unused.
            is_first_item: Unused.
            is_last_item: Unused.

        Returns:
            The sentinel ``<div>``.
        """
        registry_id = escape_html(str(data.get(FIELD_REGISTRY_ID, "")))
        return f'<div class="lia-page-app" data-registry-id="{registry_id}"></div>'
