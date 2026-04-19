"""
SkillAppSentinel Component — Placeholder for Skill rich outputs (frames/images).

Renders a sentinel ``<div>`` that the frontend intercepts and replaces with
an interactive widget (``SkillAppWidget``) mounting an iframe or image card.

The sentinel carries a ``data-registry-id`` attribute that the frontend uses
to look up the full payload (HTML, frame URL, image, title) from the Data
Registry via ``RegistryContext``.

This mirrors ``McpAppSentinel`` (evolution F2.5) but is dedicated to skill
outputs and uses a different CSS class (``lia-skill-app``) to allow distinct
styling and detection.
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
)
from src.domains.agents.display.icons import Icons, icon


class SkillAppSentinel(BaseComponent):
    """Renders a placeholder div for Skill Apps — replaced by SkillAppWidget on the frontend."""

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
        """Render Skill App sentinel placeholder.

        The frontend detects ``<div class="lia-skill-app" data-registry-id="...">``
        and mounts the interactive ``SkillAppWidget`` component in its place.
        The widget looks up the registry payload to render either an iframe
        (frame.html via srcDoc, or frame.url via src) and/or an image card.
        """
        from src.core.field_names import FIELD_REGISTRY_ID

        registry_id = escape_html(str(data.get(FIELD_REGISTRY_ID, "")))
        skill_name = escape_html(str(data.get("skill_name", "Skill")))
        title = escape_html(str(data.get("title", skill_name)))
        loading_text = V3Messages.get_skill_app_loading(ctx.language)

        return (
            f'<div class="lia-skill-app" data-registry-id="{registry_id}">'
            f'<div class="lia-skill-app__placeholder">'
            f'<span class="lia-badge lia-badge--accent">'
            f"{icon(Icons.SKILLS)} {title}"
            f"</span>"
            f'<div class="lia-skill-app__loading">{escape_html(loading_text)}</div>'
            f"</div>"
            f"</div>"
        )
