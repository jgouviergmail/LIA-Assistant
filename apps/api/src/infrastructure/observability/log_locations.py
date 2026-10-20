"""URL locations and relative personal routes, without retaining private labels."""

import re

_URL_LOCATION_PATTERN = re.compile(
    r"\b(?P<scheme>https?|wss?)://(?P<authority>[^/?#\s\"'<>]+)" r"(?P<location>[/?#][^\s\"'<>]*)?",
    re.IGNORECASE,
)
_FIRECRAWL_PATH_CREDENTIAL_PATTERN = re.compile(r"^/fc-[A-Za-z0-9_-]+(?=/|[?#]|$)")


def sanitize_url_locations(text: str, *, redact_content: bool) -> str:
    """Keep URL origins above DEBUG; credentials never survive at any level.

    Args:
        text: A structured value or a foreign logger's free-text message.
        redact_content: Whether paths, queries and fragments must be withheld.

    Returns:
        Text with locations reduced to origins, or safe DEBUG locations.
    """
    if redact_content and text.startswith("/api/v1/relations/"):
        suffix = text.removeprefix("/api/v1/relations/")
        if suffix not in {"settings", "overview-scope", "favorites", "merges"}:
            text = "/api/v1/relations/[PRIVATE]"
    if "://" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        authority = match.group("authority").rsplit("@", 1)[-1]
        origin = f"{match.group('scheme')}://{authority}"
        if redact_content:
            return origin
        location = match.group("location") or ""
        if authority.lower().split(":", 1)[0] == "mcp.firecrawl.dev":
            location = _FIRECRAWL_PATH_CREDENTIAL_PATTERN.sub("/[REDACTED]", location)
        return origin + location

    return _URL_LOCATION_PATTERN.sub(_replace, text)
