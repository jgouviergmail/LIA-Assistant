"""Validate the explicit disposable Redis endpoint without importing the app."""

from urllib.parse import parse_qsl, urlsplit


def validated_test_redis_url(raw: str | None) -> str | None:
    """Accept Redis endpoints on DB 15 only, without echoing URL credentials."""
    if raw is None:
        return None
    try:
        parsed = urlsplit(raw)
        valid = (
            parsed.scheme in {"redis", "rediss"}
            and bool(parsed.hostname)
            and parsed.path == "/15"
            and not parsed.fragment
            and not any(key == "db" for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
        )
        # Accessing port validates its syntax and range; never relay its error.
        _port = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "TEST_REDIS_URL must use redis/rediss with a host and explicit /15; "
            "database query overrides and fragments are forbidden"
        ) from None
    return raw
