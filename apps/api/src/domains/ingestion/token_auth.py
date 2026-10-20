"""Wire and storage primitives shared with legacy health credentials."""

from hashlib import sha256


def extract_token(authorization: str | None, *, prefix: str) -> str | None:
    """Accept bearer or bare credentials, scoped by a mandatory resource prefix."""
    if not authorization:
        return None
    stripped = authorization.strip()
    candidate = stripped[7:].strip() if stripped.lower().startswith("bearer ") else stripped
    return candidate if candidate.startswith(prefix) else None


def hash_token(raw_token: str) -> str:
    """Only the digest is persisted; high-entropy credentials are issued once."""
    return sha256(raw_token.encode("utf-8")).hexdigest()
