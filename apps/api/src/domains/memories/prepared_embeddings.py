"""An ephemeral, closed set of provider results for a short write transaction."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

MemoryVectors = tuple[list[float] | None, list[float] | None]
MemoryEmbedder = Callable[[str, str], Awaitable[MemoryVectors]]


@dataclass(frozen=True)
class PreparedMemoryEmbeddings:
    vectors: Mapping[tuple[str, str], MemoryVectors]

    async def resolve(self, content: str, trigger_topic: str) -> MemoryVectors:
        try:
            return self.vectors[(content, trigger_topic)]
        except KeyError:
            # No paid fallback under the consent lock if a current fact changed.
            raise ValueError("Memory write inputs changed after preparation") from None
