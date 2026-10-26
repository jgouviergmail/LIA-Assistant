"""One strict multi-language act using the native translator's quota and spend path."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import Field, field_validator

from src.core.i18n_types import Language
from src.core.prompt_store import read_prompt_file
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.world.messages import literal_text
from src.domains.world.public_models import PUBLIC_CHARS, PUBLIC_TRANSLATION_CHARS
from src.domains.world.schemas import StrictModel
from src.domains.world.translation import accounted_translation


class BatchInput(StrictModel):
    source_language: Language = Field(
        description="Canonical backend language code of the original human text."
    )
    target_languages: list[Language] = Field(
        min_length=1,
        max_length=5,
        description="Distinct target language codes for this single public translation batch.",
    )
    text: str = Field(
        description="Bounded literal human or translated text; never instructions or executable markup."
    )


class BatchText(StrictModel):
    language: Language = Field(
        description="Canonical backend language code for this account or translated view."
    )
    text: str = Field(
        min_length=1,
        max_length=PUBLIC_TRANSLATION_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        """Validate each translated public variant against the enforced character and UTF-8 budgets."""
        return literal_text(
            value, chars=PUBLIC_TRANSLATION_CHARS, size=PUBLIC_TRANSLATION_CHARS * 4
        )


class BatchOutput(StrictModel):
    translations: list[BatchText] = Field(
        min_length=1,
        max_length=5,
        description="Exactly one strict translated result for each requested target language.",
    )


@dataclass(frozen=True)
class TranslatedBatch:
    translations: Mapping[Language, str]
    usage: TokenSummaryDTO


class BatchTranslationPort(Protocol):
    async def __call__(
        self,
        text: str,
        *,
        source: Language,
        targets: tuple[Language, ...],
        user_id: UUID,
        request_id: UUID,
    ) -> TranslatedBatch:
        """Translate the exact target-language set once for this payer and request identifier."""
        ...


def batch_messages(text: str, source: Language, targets: tuple[Language, ...]) -> list[BaseMessage]:
    """Build an untrusted-data payload and render the enforced translation budget into its system prompt."""
    if len(set(targets)) != len(targets) or source in targets:
        raise ValueError("world_public_languages")
    data = BatchInput(
        source_language=source,
        target_languages=list(targets),
        text=literal_text(text, chars=PUBLIC_CHARS, size=PUBLIC_CHARS * 4),
    )
    return [
        SystemMessage(
            read_prompt_file("world_public_translator_prompt").format(
                translation_chars=PUBLIC_TRANSLATION_CHARS
            )
        ),
        HumanMessage(data.model_dump_json()),
    ]


def parse_batch(raw: str, targets: tuple[Language, ...]) -> dict[Language, str]:
    """Require one valid translation per target language, with no duplicates or extra targets."""
    data = BatchOutput.model_validate_json(raw)
    result = {item.language: item.text for item in data.translations}
    if len(result) != len(data.translations) or set(result) != set(targets):
        raise ValueError("world_public_languages")
    return result


async def translate_public_message(
    text: str,
    *,
    source: Language,
    targets: tuple[Language, ...],
    user_id: UUID,
    request_id: UUID,
) -> TranslatedBatch:
    """Run one native accounted batch and return its exact variants and usage receipt."""
    parsed, usage = await accounted_translation(
        batch_messages(text, source, targets),
        lambda raw: parse_batch(raw, targets),
        user_id=user_id,
        request_id=request_id,
    )
    return TranslatedBatch(parsed, usage)
