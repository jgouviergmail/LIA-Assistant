"""The identity of a minutes template (ADR-259).

Two kinds of template exist and are told apart by their reference:

- ``builtin:<key>`` — a catalogue template (code + six-language data), read-only,
  localized live, improvable by a release;
- ``user:<uuid>`` — a ``meeting_templates`` row the user owns.

The reference is what a meeting stores, what a preference stores and what the
API exchanges. Parsing is strict: any other shape is a ``ValueError`` (the API
turns it into 422 before a repository is touched).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

BUILTIN_PREFIX = "builtin:"
USER_PREFIX = "user:"
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,59}$")

TemplateKind = Literal["builtin", "user"]


@dataclass(frozen=True)
class TemplateRef:
    """A parsed template reference; build it with :meth:`parse`, :meth:`builtin` or :meth:`user`."""

    kind: TemplateKind
    key: str | None = None
    id: uuid.UUID | None = None

    @classmethod
    def parse(cls, value: str) -> TemplateRef:
        """Parse ``builtin:<key>`` or ``user:<uuid>``.

        Raises:
            ValueError: on any other shape (empty, unknown prefix, bad key or uuid).
        """
        if value.startswith(BUILTIN_PREFIX):
            key = value[len(BUILTIN_PREFIX) :]
            if not _KEY_PATTERN.match(key):
                raise ValueError(f"invalid builtin template key: {key!r}")
            return cls(kind="builtin", key=key)
        if value.startswith(USER_PREFIX):
            raw = value[len(USER_PREFIX) :]
            try:
                return cls(kind="user", id=uuid.UUID(raw))
            except ValueError as exc:
                raise ValueError(f"invalid user template id: {raw!r}") from exc
        raise ValueError(f"unknown template reference: {value!r}")

    @classmethod
    def builtin(cls, key: str) -> TemplateRef:
        """The reference of a catalogue template."""
        return cls.parse(f"{BUILTIN_PREFIX}{key}")

    @classmethod
    def user(cls, template_id: uuid.UUID) -> TemplateRef:
        """The reference of a user template row."""
        return cls(kind="user", id=template_id)

    def __str__(self) -> str:
        if self.kind == "builtin":
            return f"{BUILTIN_PREFIX}{self.key}"
        return f"{USER_PREFIX}{self.id}"


__all__ = ["BUILTIN_PREFIX", "USER_PREFIX", "TemplateKind", "TemplateRef"]
