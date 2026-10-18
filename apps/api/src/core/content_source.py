"""Opaque scope of the credentials that actually fetched the displayed content."""

import hashlib


def content_source_binding(client: object) -> str:
    credentials = getattr(client, "credentials", None)
    binding = getattr(credentials, "account_binding", None)
    if not isinstance(binding, str) or not binding:
        binding = getattr(credentials, "apple_id", None)
    if not isinstance(binding, str) or not binding:
        return ""
    return hashlib.sha256(binding.encode()).hexdigest()
