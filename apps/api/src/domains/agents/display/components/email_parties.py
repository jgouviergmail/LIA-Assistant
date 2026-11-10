"""Received mail parties through the shared address parser, without RSVP implications."""

from collections.abc import Mapping

from src.domains.agents.display.escaping import escape_html
from src.domains.agents.display.values import scalar_text
from src.infrastructure.email.recipients import read_recipients, recipient_segments


def _party(name: str, email: str) -> str:
    """Render the literal identity and the original mail destination when supplied."""
    text = escape_html(name or email)
    identity = f'<a href="mailto:{escape_html(email)}">{text}</a>' if email else text
    address = (
        f'<span class="lia-part-item__email">{escape_html(email)}</span>'
        if name and email and email != name
        else ""
    )
    return f'<div class="lia-part-item">{identity} {address}</div>'


def _received_party(value: object) -> str:
    """Keep malformed header segments as literal text instead of silently dropping them."""
    if isinstance(value, Mapping):
        email = scalar_text(value.get("email"))
        name = scalar_text(value.get("name")) or scalar_text(value.get("displayName"))
        return _party(name, email) if name or email else ""
    rows: list[str] = []
    for segment, valid in recipient_segments(scalar_text(value)):
        pairs = read_recipients(segment) if valid else [(segment, "")]
        rows.extend(_party(name, address) for name, address in pairs)
    return "".join(rows)


def render_email_parties(value: object) -> str:
    """Render every supplied address without interpreting a comma inside a quoted name."""
    values = value if isinstance(value, list) else [value]
    content = "".join(_received_party(item) for item in values)
    return f'<div class="lia-part-list">{content}</div>' if content else ""
