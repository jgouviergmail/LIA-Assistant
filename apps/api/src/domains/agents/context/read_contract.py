"""Optional live read authority for persisted contexts, never serialized with them."""

from collections.abc import Awaitable, Callable, Mapping, Sequence

ContextReadGuard = Callable[[str, Sequence[Mapping[str, object]]], Awaitable[bool]]
