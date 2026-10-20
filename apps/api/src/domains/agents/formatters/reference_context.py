"""Ordinary resolved references, with stable field order and tool-ID aliases."""

from collections.abc import Callable, Mapping, Sequence

FormatValue = Callable[[object], str | None]
_EXCLUDED = frozenset(
    {
        "index",
        "_index",
        "meta",
        "_meta",
        "raw",
        "_raw",
        "etag",
        "kind",
        "selfLink",
        "iCalUID",
        "htmlLink",
        "creator",
        "organizer",
    }
)
_PRIORITY = (
    "id",
    "resource_name",
    "place_id",
    "message_id",
    "name",
    "summary",
    "title",
    "subject",
    "location",
    "address",
    "start",
    "end",
    "due",
    "date",
    "email",
    "phone",
    "attendees",
    "participants",
)
_CROSS_DOMAIN = frozenset({"location", "address", "email", "name", "summary", "subject"})


def _aliases(
    item: Mapping[str, object], aliases: Mapping[str, str], format_value: FormatValue
) -> list[str]:
    lines = []
    for field, parameter in aliases.items():
        if field in item and item[field] is not None:
            value = format_value(item[field])
            if value and parameter not in item:
                lines.append(
                    f"    - {parameter}: {value}" "  ← use this directly as tool parameter"
                )
    return lines


def _priority_fields(
    item: Mapping[str, object], format_value: FormatValue, ready: dict[str, str], single: bool
) -> tuple[list[str], set[str]]:
    lines = []
    shown = set()
    for field in _PRIORITY:
        if field in item and item[field] is not None:
            value = format_value(item[field])
            if value:
                lines.append(f"    - {field}: {value}")
                shown.add(field)
                if single and field in _CROSS_DOMAIN:
                    ready[field] = value
    return lines, shown


def _remaining_fields(
    item: Mapping[str, object], format_value: FormatValue, shown: set[str]
) -> list[str]:
    lines = []
    for field in sorted(item):
        if field in shown or field in _EXCLUDED or field.startswith("_"):
            continue
        value = format_value(item[field])
        if value:
            lines.append(f"    - {field}: {value}")
    return lines


def _ready_lines(ready: Mapping[str, str]) -> list[str]:
    if not ready:
        return []
    lines = [
        "\n" + "=" * 60,
        "READY-TO-USE VALUES (use these DIRECTLY in tool parameters):",
        "=" * 60,
    ]
    examples = {
        "location": '    → For places search: get_places_tool(query="{value}")',
        "email": '    → For email search: get_emails_tool(query="{value}")',
        "name": '    → For contacts: get_contacts_tool(query="{value}")',
    }
    for field, value in ready.items():
        lines.append(f'  {field.upper()}: "{value}"')
        example = examples.get(field)
        if example:
            lines.append(example.format(value=value))
    return lines


def render_reference_items(
    items: Sequence[object],
    domain: str | None,
    format_value: FormatValue,
    aliases: Mapping[str, str],
) -> str:
    if not items:
        return ""
    ready: dict[str, str] = {}
    lines = [
        "RESOLVED CONTEXT (items already fetched — use their IDs directly in parameters, DO NOT create any resolve/context/reference step):",
        f"Source domain: {domain or 'unknown'}",
        f"Items count: {len(items)}",
    ]
    for index, item in enumerate(items, 1):
        lines.append(f"\n  Item {index}:")
        if isinstance(item, dict):
            lines.extend(_aliases(item, aliases, format_value))
            priority, shown = _priority_fields(item, format_value, ready, len(items) == 1)
            lines.extend(priority)
            lines.extend(_remaining_fields(item, format_value, shown))
        else:
            lines.append(f"    {str(item)[:300]}")
    lines.extend(_ready_lines(ready))
    lines.extend(
        [
            "\n" + "-" * 60,
            "CRITICAL: These items are ALREADY RESOLVED from conversation history.",
            "DO NOT generate any 'resolve' or 'get_reference' tool - use values above DIRECTLY.",
            "-" * 60,
        ]
    )
    return "\n".join(lines)
