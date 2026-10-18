"""Typed read-only port; bootstrap supplies the native implementation once."""

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol
from uuid import UUID

from src.core.content_classification import ContentClassification


class SelectedContentQualifier(Protocol):
    async def __call__(
        self,
        *,
        records: Sequence[Mapping[str, object]],
        kind: Literal["email", "event"],
        user_id: UUID,
        provider: str,
        binding: str,
        timezone: str,
        container: str = "",
    ) -> dict[str, ContentClassification]: ...


_qualifier: SelectedContentQualifier | None = None


def configure_content_qualifier(qualifier: SelectedContentQualifier | None) -> None:
    global _qualifier
    _qualifier = qualifier


async def qualify_selected(
    *,
    records: Sequence[Mapping[str, object]],
    kind: Literal["email", "event"],
    user_id: UUID,
    provider: str,
    binding: str,
    timezone: str,
    container: str = "",
) -> dict[str, ContentClassification]:
    if _qualifier is None:
        return {}
    return await _qualifier(
        records=records,
        kind=kind,
        user_id=user_id,
        provider=provider,
        binding=binding,
        timezone=timezone,
        container=container,
    )
