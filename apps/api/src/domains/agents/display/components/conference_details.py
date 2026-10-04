"""Every supplied public join point, without provider signatures or conference ids."""

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    html_to_text,
    render_d_item,
    safe_url,
)
from src.domains.agents.display.values import list_values, scalar_text

_CODES: tuple[tuple[str, CardLabel], ...] = (
    ("meetingCode", "meeting_code"),
    ("accessCode", "access_code"),
    ("passcode", "passcode"),
    ("pin", "pin"),
    ("password", "meeting_password"),
)
_SYMBOLS = {"video": "videocam", "phone": "call", "sip": "call", "more": "link"}


def _join_point(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    kind = value.get("entryPointType")
    if not isinstance(kind, str) or kind not in _SYMBOLS:
        return ""
    uri = scalar_text(value.get("uri"))
    label = scalar_text(value.get("label")) or (
        V3Messages.get_join_meet(ctx.language) if kind == "video" else uri
    )
    target = safe_url(uri)
    if target:
        content = f'<a class="lia-conference-point" href="{target}" target="_blank" rel="noopener noreferrer">{escape_html(label)}</a>'
    elif kind == "sip" and uri.startswith("sip:"):
        content = escape_html(label) + " · " + escape_html(uri)
    else:
        return ""
    codes = [
        escape_html(f"{card_label(label_key, ctx.language)}{label_separator(ctx.language)}{text}")
        for key, label_key in _CODES
        if (text := scalar_text(value.get(key)))
    ]
    if codes:
        content += '<span class="lia-conference-codes">' + " · ".join(codes) + "</span>"
    return render_d_item(_SYMBOLS[kind], f'<span class="lia-conference-entry">{content}</span>')


def render_conference_details(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    parts = [_join_point(point, ctx) for point in list_values(value.get("entryPoints"))]
    solution = value.get("conferenceSolution")
    if isinstance(solution, dict) and (name := scalar_text(solution.get("name"))):
        parts.insert(0, render_d_item("videocam", escape_html(name)))
    if notes := scalar_text(value.get("notes")):
        parts.append(render_d_item("info", escape_html(html_to_text(notes))))
    # Google explicitly declares conferenceId unsuitable for display.
    # The signature is provider bookkeeping; only join-point access codes are user data.
    return "".join(parts)
