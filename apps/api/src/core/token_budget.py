"""Literal external-data budgets, never a claim about provider billing."""

import tiktoken

from src.core.config import get_settings


def count_external_tokens(text: str) -> int:
    """Count literal external text without logging it; fallback bounds byte-BPE tokens.

    Special-token-looking SMS text is data. A failed tokenizer must not turn
    CJK or emoji into the legacy Latin-only chars/4 underestimate.
    This is a prompt budget, never a claim about provider-billed usage.
    """
    try:
        return len(
            tiktoken.get_encoding(get_settings().token_encoding_name).encode(
                text, disallowed_special=()
            )
        )
    except Exception:
        return len(text.encode("utf-8"))
