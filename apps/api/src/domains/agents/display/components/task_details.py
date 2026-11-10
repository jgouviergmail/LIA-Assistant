"""Complete task details and progress, derived from renderable subtasks."""

from collections.abc import Mapping

from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_d_item,
    safe_url,
)
from src.domains.agents.display.components.card_content import render_details, render_text_content
from src.domains.agents.display.components.source_details import task_native_details
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.display.values import scalar_text


def task_checklist(data: Mapping[str, object]) -> list[object]:
    """Keep both native lists, without treating an absent completion flag as false."""
    result: list[object] = []
    subtasks = data.get("subtasks")
    if isinstance(subtasks, list):
        result.extend(subtasks)
    steps = data.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            state = step.get("checked")
            result.append(
                {
                    "title": step.get("title"),
                    **(
                        {"status": "completed" if state else "needsAction"}
                        if isinstance(state, bool)
                        else {}
                    ),
                }
            )
    return result


def _links(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, list):
        return ""
    links: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        target = safe_url(scalar_text(item.get("link")))
        if target:
            label = scalar_text(item.get("description")) or V3Messages.get_link(ctx.language)
            links.append(
                f'<a href="{target}" target="_blank" rel="noopener noreferrer">{escape_html(label)}</a>'
            )
    return render_d_item(Icons.LINK, ", ".join(links)) if links else ""


def render_task_subtasks(value: object, ctx: RenderContext) -> str:
    """Render the supplied checklist and its exact read-only completion measure."""
    if not isinstance(value, list):
        return ""
    items: list[str] = []
    completed = 0
    known = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        title = scalar_text(item.get("title"))
        if not title:
            continue
        status = scalar_text(item.get("status"))
        done = status == "completed"
        explicit = status in {"completed", "needsAction"}
        known += int(explicit)
        completed += int(done)
        text = f"<s>{escape_html(title)}</s>" if done else escape_html(title)
        state_class = " lia-task__subtask--done" if done else ""
        symbol = Icons.TASK if done else Icons.CHECKBOX_BLANK if explicit else "help_outline"
        items.append(
            f'<li class="lia-task__subtask{state_class}">{icon(symbol)}<span>{text}</span></li>'
        )
    if not items:
        return ""
    total = len(items)
    label = escape_html(V3Messages.get_subtasks(ctx.language))
    progress = (
        f'<progress class="lia-task__completion" value="{completed}" max="{total}" '
        f'aria-label="{label}">{completed}/{total}</progress>'
        if known == total
        else ""
    )
    count = f"{completed}/{total}" if known == total else str(total)
    return (
        f'<div class="lia-task__subtasks"><div class="lia-task__subtasks-header">'
        f"{icon(Icons.CHECKLIST)}<span>{label} ({count})</span>{progress}</div>"
        f'<ul class="lia-task__subtasks-list">{"".join(items)}</ul></div>'
    )


def render_task_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    """No provider request: only the task facts already supplied on this item."""
    parts: list[str] = []
    notes = scalar_text(data.get("notes"))
    if len(notes) > 100:
        parts.append(render_text_content(notes))
    parent = scalar_text(data.get("parentTitle"))
    if parent:
        label = V3Messages.get_subtask_of(ctx.language)
        parts.append(
            render_d_item(
                Icons.REPLY,
                f"{escape_html(label)}{label_separator(ctx.language)}{escape_html(parent)}",
            )
        )
    parts.append(_links(data.get("links"), ctx))
    parts.extend(task_native_details(data, ctx))
    content = "".join(parts)
    return (
        render_details(f'<div class="lia-task__extended">{content}</div>', ctx) if content else ""
    )
