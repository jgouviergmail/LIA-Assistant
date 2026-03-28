"""
ReminderCard Component - Professional Reminder Display v3.2.

Responsive design using CSS Container Queries (modern pattern):
- Desktop (wide): Single-line layout with icon wrapper, label, meta, trigger badge
- Mobile (narrow): 2-row layout with dates on row 1, content on row 2

CSS handles responsive adaptation via @container card queries.
Backend generates unified HTML structure.

Created: 2025-01-05
Updated: 2026-02-05 - Migrated to CSS Container Queries (v3.2)
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.core.time_utils import now_utc, parse_datetime
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    render_chip,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon


class ReminderCard(BaseComponent):
    """
    Modern reminder card component v3.2.

    Design: Unified HTML with CSS Container Query responsive adaptation.
    - Desktop: Icon wrapper | Label | Created meta | Trigger badge
    - Mobile: Row 1 (dates) | Row 2 (icon + label)
    - Bell icon pulses if imminent (within 1 hour)
    """

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
        """
        Render reminder as responsive card.

        Args:
            data: Reminder data with id, content, trigger_at, created_at
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones

        Returns:
            HTML string for the reminder card
        """
        # Extract data
        reminder_id = data.get("id", "")
        content = data.get("content") or V3Messages.get_no_title(ctx.language)
        trigger_at = data.get("trigger_at", "")
        trigger_at_formatted = data.get("trigger_at_formatted", "")
        created_at_formatted = data.get("created_at_formatted", "")

        # Check if reminder is imminent (within 1 hour)
        is_imminent = self._is_imminent(trigger_at)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(reminder_id, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            reminder_id=reminder_id,
            content=content,
            created_at_formatted=created_at_formatted,
            trigger_at_formatted=trigger_at_formatted,
            is_imminent=is_imminent,
            ctx=ctx,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain="reminders",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self,
        reminder_id: str,
        ctx: RenderContext,
    ) -> list[dict[str, str]]:
        """Build default action buttons for reminder."""
        actions = []

        # Cancel reminder action
        if reminder_id:
            cancel_label = self._get_cancel_label(ctx.language)
            actions.append(
                {
                    "icon": Icons.DELETE,
                    "label": cancel_label,
                    "action": f"cancel_reminder:{reminder_id}",
                }
            )

        return actions

    def _render_card(
        self,
        reminder_id: str,
        content: str,
        created_at_formatted: str,
        trigger_at_formatted: str,
        is_imminent: bool,
        ctx: RenderContext,
    ) -> str:
        """
        Render unified reminder card with responsive structure.

        CSS Container Queries handle the layout switch via flex-wrap + order:
        - Desktop: icon | label | created | trigger (single line)
        - Mobile: Row 1 (icon + created + trigger) | Row 2 (label full width)

        Args:
            reminder_id: Unique reminder identifier
            content: Reminder text content
            created_at_formatted: Formatted creation date
            trigger_at_formatted: Formatted trigger date
            is_imminent: Whether reminder triggers within 1 hour
            ctx: Render context

        Returns:
            HTML string with unified responsive structure
        """
        nested_class = self._nested_class(ctx)
        imminent_class = "lia-reminder--imminent" if is_imminent else ""

        # v4 layout: illus + [trigger chip + title] on same line, created below
        illus_color = "red" if is_imminent else "amber"
        illus_icon = Icons.ALARM if is_imminent else Icons.REMINDER

        # Trigger chip
        trigger_chip = ""
        if trigger_at_formatted:
            chip_variant = "red" if is_imminent else "amber"
            trigger_chip = render_chip(trigger_at_formatted, chip_variant, Icons.SCHEDULE)

        # Created time with "Créé le" prefix
        created_html = ""
        if created_at_formatted:
            created_label = V3Messages.get_created(ctx.language)
            created_html = (
                f'<div style="font-size:var(--lia-text-xs);color:var(--lia-text-muted);'
                f'margin-top:var(--lia-space-xs)">'
                f"{icon(Icons.CALENDAR)} {created_label} : {escape_html(created_at_formatted)}</div>"
            )

        return f"""<div class="lia-card lia-reminder {imminent_class} {nested_class}" data-reminder-id="{escape_html(reminder_id)}">
<div style="display:flex;gap:var(--lia-space-md);align-items:flex-start">
<div class="lia-illus lia-illus--{illus_color}" style="width:36px;height:36px;border-radius:10px">
<span class="material-symbols-outlined" style="font-size:20px;font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20">{illus_icon}</span>
</div>
<div style="flex:1;min-width:0">
<div style="display:flex;align-items:center;gap:var(--lia-space-sm);flex-wrap:wrap">
{trigger_chip}
<span class="lia-reminder__label">{escape_html(content)}</span>
</div>
{created_html}
</div>
</div>
</div>"""

    def _is_imminent(self, trigger_at: str | None) -> bool:
        """Check if reminder is imminent (within 1 hour) using timezone-safe comparison."""
        if not trigger_at:
            return False
        # Use time_utils for safe timezone-aware parsing and comparison
        trigger_dt = parse_datetime(trigger_at)
        if trigger_dt is None:
            return False
        diff = trigger_dt - now_utc()
        # Within 1 hour (3600 seconds) and in the future
        return 0 < diff.total_seconds() < 3600

    def _get_cancel_label(self, language: str) -> str:
        """Get cancel button label based on language."""
        labels = {
            "fr": "Annuler",
            "en": "Cancel",
            "es": "Cancelar",
            "de": "Abbrechen",
            "it": "Annulla",
            "zh-CN": "取消",
        }
        lang = language.lower()[:2] if language else "fr"
        return labels.get(lang, labels["en"])
