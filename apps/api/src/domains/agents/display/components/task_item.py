"""
TaskItem Component - Modern Task Display v3.0.

Renders tasks with:
- Wrapper for assistant comment + suggested actions
- Checkbox visual with animation
- Due date with overdue warning
- Priority indicator
- Collapsible details (notes, subtasks, parent, links)
- Provider link when available; complete supplied notes and subtask progress
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.core.time_utils import is_past
from src.domains.agents.constants import CONTEXT_DOMAIN_TASKS
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_full_date,
    format_relative_date,
    render_card_top,
    render_chip,
    render_chip_row,
    render_d_item,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import render_linked_title
from src.domains.agents.display.components.source_details import task_native_chip
from src.domains.agents.display.components.task_details import render_task_details
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import scalar_text


class TaskItem(BaseComponent):
    """
    Modern task item component v3.0.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Status visual (completed/pending)
    - Title with strike-through if done
    - Due date with overdue warning
    - Priority indicator
    - Collapsible details (notes, subtasks, parent, links)
    - Provider link when available
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
        Render task as modern item with wrapper.

        Args:
            data: Task data from Google Tasks API
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones

        Returns:
            HTML string for the task item
        """
        # Extract data
        title = data.get("title") or V3Messages.get_no_title(ctx.language)
        url = data.get("url") or data.get("link") or data.get("selfLink", "")
        due = data.get("due", "")
        status = data.get("status", "needsAction")
        notes = scalar_text(data.get("notes"))
        priority = data.get("priority") or data.get("importance", "")
        if priority == "normal":
            priority = "medium"
        task_list_name = data.get("taskListName", "")
        completed_date = data.get("completed", "")

        is_completed = status == "completed"
        is_overdue = self._is_overdue(due)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(url, is_completed, ctx)

        # Unified render — CSS container queries handle responsive
        card_html = self._render_card_v4(
            title,
            url,
            due,
            notes,
            is_completed,
            is_overdue,
            priority,
            task_list_name,
            completed_date,
            ctx,
            data,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_TASKS,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self,
        url: str,
        is_completed: bool,
        ctx: RenderContext,
    ) -> list[dict[str, str]]:
        """Build default action buttons for task."""
        actions = []

        # View in Google Tasks
        if url:
            actions.append(
                {
                    "icon": Icons.CHECKLIST,
                    "label": V3Messages.get_view_details(ctx.language),
                    "url": url,
                }
            )

        return actions

    def _render_card_v4(
        self,
        title: str,
        url: str,
        due: str,
        notes: str,
        is_completed: bool,
        is_overdue: bool,
        priority: str,
        task_list_name: str,
        completed_date: str,
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified task card using Design System v4 components."""
        nested_class = self._nested_class(ctx)
        status_class = "lia-task--completed" if is_completed else ""
        overdue_class = "lia-task--overdue" if is_overdue and not is_completed else ""

        # --- Determine illus icon and color based on status ---
        if is_completed:
            illus_icon, illus_color = "check_circle", "green"
        elif is_overdue:
            illus_icon, illus_color = "error", "red"
        else:
            illus_icon, illus_color = "radio_button_unchecked", "amber"

        # --- Card top: illus + title ---
        title_html = render_linked_title(title, url)
        card_top_html = render_card_top(illus_icon, illus_color, title_html)

        # --- Chips: status/date + task list name ---
        chip_row_html = self._render_task_chips(
            priority,
            is_completed,
            is_overdue,
            due,
            completed_date,
            task_list_name,
            ctx,
            task_native_chip(data, ctx),
        )

        # --- Notes shown directly (no "Voir plus" for short notes) ---
        notes_html = ""
        if notes and len(notes) <= 100:
            notes_html = render_d_item(Icons.NOTE, escape_html(notes))

        # --- Collapsible for long notes + subtasks + parent + links ---
        collapsible_html = render_task_details(data, ctx)

        return f"""<div class="lia-card lia-task {status_class} {overdue_class} {nested_class}">
{card_top_html}
{chip_row_html}
{notes_html}
{collapsible_html}
</div>"""

    def _render_task_chips(
        self,
        priority: str,
        is_completed: bool,
        is_overdue: bool,
        due: str,
        completed_date: str,
        task_list_name: str,
        ctx: RenderContext,
        native_chip: str = "",
    ) -> str:
        """A task's actual priority, civil due date and source list."""
        chips: list[str] = []
        if native_chip:
            chips.append(native_chip)
        if priority in {"high", "medium", "low"} and not is_completed:
            color = {"high": "red", "medium": "amber", "low": "blue"}[priority]
            chips.append(
                render_chip(V3Messages.get_priority(ctx.language, priority), color, "flag")
            )
        if is_completed and completed_date:
            date = format_full_date(completed_date, ctx.language, ctx.timezone, include_time=True)
            chips.append(render_chip(date, "green", "event_available"))
        elif due and not is_completed:
            date = format_relative_date(due, ctx.language, ctx.timezone)
            chips.append(
                render_chip(
                    date,
                    "red" if is_overdue else "amber",
                    "warning" if is_overdue else Icons.CALENDAR,
                )
            )
        if task_list_name:
            name = (
                task_list_name
                if task_list_name != "@default"
                else V3Messages.get_domain_section_label("tasks", ctx.language)
            )
            chips.append(render_chip(name, "", Icons.CHECKLIST))
        return render_chip_row(" ".join(chips)) if chips else ""

    def _is_overdue(self, due: str | None) -> bool:
        """Check if task is overdue using timezone-safe comparison."""
        if not due:
            return False
        # Use time_utils.is_past() for safe timezone-aware comparison
        return is_past(due)
