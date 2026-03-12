"""
TaskItem Component - Modern Task Display v3.0.

Renders tasks with:
- Wrapper for assistant comment + suggested actions
- Checkbox visual with animation
- Due date with overdue warning
- Priority indicator
- Collapsible details (notes, subtasks, parent, links)
- Action buttons (View, Complete)
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.core.time_utils import is_past
from src.domains.agents.constants import CONTEXT_DOMAIN_TASKS
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    Viewport,
    escape_html,
    format_full_date,
    format_relative_date,
    render_collapsible,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon


class TaskItem(BaseComponent):
    """
    Modern task item component v3.0.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Checkbox visual (completed/pending) with animation
    - Title with strike-through if done
    - Due date with overdue warning (pulsing)
    - Priority indicator
    - Collapsible details (notes, subtasks, parent, links)
    - Action buttons (View, Complete)
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
        notes = data.get("notes", "")
        priority = data.get("priority", "")
        task_list_name = data.get("taskListName", "")
        completed_date = data.get("completed", "")

        is_completed = status == "completed"
        is_overdue = self._is_overdue(due)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(url, is_completed, ctx)

        # Render based on viewport (mobile vs desktop)
        if ctx.viewport == Viewport.MOBILE:
            card_html = self._render_mobile(
                title, url, due, is_completed, is_overdue, task_list_name, completed_date, ctx
            )
        else:
            # Desktop (and tablet)
            card_html = self._render_desktop(
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

    def _render_mobile(
        self,
        title: str,
        url: str,
        due: str,
        is_completed: bool,
        is_overdue: bool,
        task_list_name: str,
        completed_date: str,
        ctx: RenderContext,
    ) -> str:
        """Compact mobile task."""
        nested_class = self._nested_class(ctx)
        status_class = "lia-task--completed" if is_completed else ""
        overdue_class = "lia-task--overdue" if is_overdue and not is_completed else ""

        checkbox_icon = icon(Icons.TASK) if is_completed else icon(Icons.CHECKBOX_BLANK)

        # Task list badge (always visible)
        list_badge_html = self._render_list_badge(task_list_name, compact=True)

        # Date badge: completion date for completed tasks, due date otherwise
        date_html = ""
        if is_completed and completed_date:
            completed_str = format_full_date(
                completed_date, ctx.language, ctx.timezone, include_time=True
            )
            date_html = f'<span class="lia-badge lia-badge--success">{icon(Icons.CHECK)} {escape_html(completed_str)}</span>'
        elif due and not is_completed:
            due_str = format_relative_date(due, ctx.language, ctx.timezone)
            due_class = "lia-task__due--overdue" if is_overdue else ""
            date_html = f'<span class="lia-task__due {due_class}">{escape_html(due_str)}</span>'

        return f"""<div class="lia-card lia-task {status_class} {overdue_class} {nested_class}">
<span class="lia-task__checkbox">{checkbox_icon}</span>
<div class="lia-task__content">
<a href="{escape_html(url)}" class="lia-task__title" target="_blank">{escape_html(title)}</a>
<div class="lia-task__badges">{list_badge_html}{date_html}</div>
</div>
</div>"""

    def _render_desktop(
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
        """Full desktop task card with collapsible details."""
        nested_class = self._nested_class(ctx)
        status_class = "lia-task--completed" if is_completed else ""
        overdue_class = "lia-task--overdue" if is_overdue and not is_completed else ""

        # Checkbox
        if is_completed:
            checkbox_html = f'<div class="lia-task__checkbox lia-task__checkbox--checked">{icon(Icons.CHECK)}</div>'
        else:
            checkbox_html = '<div class="lia-task__checkbox"></div>'

        # Task list badge (always visible)
        list_badge_html = self._render_list_badge(task_list_name)

        # Date badge: completion date for completed tasks, due date otherwise
        date_html = ""
        if is_completed and completed_date:
            completed_str = format_full_date(
                completed_date, ctx.language, ctx.timezone, include_time=True
            )
            date_html = f'<span class="lia-badge lia-badge--success">{icon(Icons.CHECK)} {escape_html(completed_str)}</span>'
        elif due:
            due_str = format_relative_date(due, ctx.language, ctx.timezone)
            if is_overdue and not is_completed:
                date_html = f'<span class="lia-badge lia-badge--danger">{icon(Icons.WARNING)} {escape_html(due_str)}</span>'
            elif not is_completed:
                date_html = f'<span class="lia-badge lia-badge--subtle">{icon(Icons.CALENDAR)} {escape_html(due_str)}</span>'

        # Priority badge
        priority_html = self._render_priority_badge(priority, is_completed, ctx)

        # Notes preview
        notes_html = ""
        if notes and ctx.show_secondary and len(notes) <= 100:
            notes_html = f'<p class="lia-task__notes">{escape_html(notes)}</p>'

        # Collapsible extended details
        collapsible_html = self._render_collapsible_details(data, is_completed, ctx)

        return f"""<div class="lia-card lia-task {status_class} {overdue_class} {nested_class}">
{checkbox_html}
<div class="lia-task__main">
<div class="lia-task__header">
<a href="{escape_html(url)}" class="lia-task__title" target="_blank">{escape_html(title)}</a>
<div class="lia-task__badges">
{list_badge_html}
{priority_html}
{date_html}
</div>
</div>
{notes_html}
{collapsible_html}
</div>
</div>"""

    def _render_priority_badge(
        self, priority: str, is_completed: bool, ctx: RenderContext, compact: bool = False
    ) -> str:
        """Render priority badge."""
        if not priority or is_completed:
            return ""

        priority_lower = priority.lower()
        if compact:
            priority_map = {
                "high": ("lia-badge--danger", "!"),
                "medium": ("lia-badge--warning", "·"),
                "low": ("lia-badge--subtle", ""),
            }
            badge_class, badge_icon = priority_map.get(priority_lower, ("", ""))
            if badge_class and badge_icon:
                return f'<span class="lia-badge {badge_class}">{badge_icon}</span>'
        else:
            priority_map = {
                "high": "lia-badge--danger",  # type: ignore
                "medium": "lia-badge--warning",  # type: ignore
                "low": "lia-badge--subtle",  # type: ignore
            }
            badge_class = priority_map.get(priority_lower, "")  # type: ignore
            if badge_class:
                priority_label = V3Messages.get_priority(ctx.language, priority)
                return f'<span class="lia-badge {badge_class}">{escape_html(priority_label)}</span>'

        return ""

    def _render_list_badge(self, task_list_name: str, compact: bool = False) -> str:
        """Render task list name badge (always visible to avoid confusion)."""
        if not task_list_name:
            return ""

        # Clean up default list name
        display_name = task_list_name
        if task_list_name == "@default":
            display_name = "Tasks"

        if compact:
            # Mobile/tablet: icon + short name
            return f'<span class="lia-badge lia-badge--info">{icon(Icons.CHECKLIST)} {escape_html(display_name)}</span>'
        else:
            # Desktop: icon + full name
            return f'<span class="lia-badge lia-badge--info">{icon(Icons.CHECKLIST)} {escape_html(display_name)}</span>'

    def _render_collapsible_details(
        self, data: dict[str, Any], is_completed: bool, ctx: RenderContext
    ) -> str:
        """Render collapsible section with extended details."""
        detail_sections = []

        # Full notes (longer than 100 chars)
        full_notes = data.get("notes", "")
        if full_notes and len(full_notes) > 100:
            notes_preview = full_notes[:300] + "..." if len(full_notes) > 300 else full_notes
            detail_sections.append(
                f'<div class="lia-task__full-notes">'
                f"{icon(Icons.NOTE)}"
                f"<span>{escape_html(notes_preview)}</span>"
                f"</div>"
            )

        # Parent task
        parent_title = data.get("parentTitle", "")
        if parent_title:
            subtask_of_label = V3Messages.get_subtask_of(ctx.language)
            detail_sections.append(
                f'<div class="lia-task__detail-item">'
                f"{icon(Icons.REPLY)}"
                f"<span>{escape_html(subtask_of_label)} : {escape_html(parent_title)}</span>"
                f"</div>"
            )

        # Links
        links = data.get("links", [])
        if links:
            link_items = []
            link_default_label = V3Messages.get_link(ctx.language)
            for link in links[:3]:
                if isinstance(link, dict):
                    link_desc = link.get("description", link_default_label)
                    link_url = link.get("link", "")
                    if link_url:
                        link_items.append(
                            f'<a href="{escape_html(link_url)}" target="_blank">{escape_html(link_desc)}</a>'
                        )
            if link_items:
                links_label = V3Messages.get_links(ctx.language)
                detail_sections.append(
                    f'<div class="lia-task__detail-item">'
                    f"{icon(Icons.LINK)}"
                    f'<span>{escape_html(links_label)} : {", ".join(link_items)}</span>'
                    f"</div>"
                )

        # Note: Completion date is now displayed directly on the card header (with full date/time)
        # Note: Task list name is now always displayed in header badge, no need to repeat here

        # Subtasks with progress
        subtasks = data.get("subtasks", [])
        if subtasks:
            subtask_items = []
            completed_count = 0
            for subtask in subtasks[:10]:
                if isinstance(subtask, dict):
                    st_title = subtask.get("title", "")
                    st_status = subtask.get("status", "needsAction")
                    if st_title:
                        if st_status == "completed":
                            completed_count += 1
                            subtask_items.append(
                                f'<div class="lia-task__subtask lia-task__subtask--done">'
                                f"{icon(Icons.TASK)}"
                                f"<span><s>{escape_html(st_title)}</s></span>"
                                f"</div>"
                            )
                        else:
                            subtask_items.append(
                                f'<div class="lia-task__subtask">'
                                f"{icon(Icons.CHECKBOX_BLANK)}"
                                f"<span>{escape_html(st_title)}</span>"
                                f"</div>"
                            )

            if subtask_items:
                total_count = len(subtasks)
                progress_pct = (completed_count / total_count) * 100 if total_count > 0 else 0
                subtasks_label = V3Messages.get_subtasks(ctx.language)

                # Progress bar
                progress_html = (
                    f'<div class="lia-task__progress">'
                    f'<div class="lia-task__progress-bar" style="width: {progress_pct:.0f}%"></div>'
                    f"</div>"
                )

                detail_sections.append(
                    f'<div class="lia-task__subtasks">'
                    f'<div class="lia-task__subtasks-header">'
                    f"{icon(Icons.CHECKLIST)}"
                    f"<span>{escape_html(subtasks_label)} ({completed_count}/{total_count})</span>"
                    f"{progress_html}"
                    f"</div>"
                    f'<div class="lia-task__subtasks-list">{"".join(subtask_items)}</div>'
                    f"</div>"
                )

        # If we have details, wrap in collapsible
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=f'<div class="lia-task__extended">{content_html}</div>',
                initially_open=False,
                language=ctx.language,
            )

        return ""

    def _is_overdue(self, due: str | None) -> bool:
        """Check if task is overdue using timezone-safe comparison."""
        if not due:
            return False
        # Use time_utils.is_past() for safe timezone-aware comparison
        return is_past(due)
