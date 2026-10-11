"""Canonical identities for MCP declarations and effective connection settings."""

from __future__ import annotations

import hashlib
import json


def canonical_fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def connection_fingerprint(
    url: str, auth: object, timeout_seconds: int, headers: dict[str, str] | None
) -> str:
    """Account/server owns auth; a handler exports only a digest of its identity."""
    auth_identity = getattr(auth, "catalogue_identity", None)
    return canonical_fingerprint(
        {
            "url": url,
            "auth_handler": type(auth).__qualname__,
            "auth_identity": auth_identity if isinstance(auth_identity, str) else None,
            "timeout_seconds": timeout_seconds,
            "headers": headers or {},
        }
    )
