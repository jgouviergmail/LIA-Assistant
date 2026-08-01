"""Cross-domain shape for "one raw name, how often, how recently".

Three independent sources feed the personal-CRM overview — open loops, phone
calls and relayed peer messages — and all three answer the same question. The
shape is declared once, in a leaf module, so the aggregating domain can consume
the three without any of them importing another (F009 cycle discipline).

Aggregates carry the RAW spelling, never a folded key: folding is the
consumer's business and there is exactly one implementation of it
(``shared.text_normalization.fold_name``). A source that folded on its own
would be a second, silently diverging authority on identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NameActivity:
    """Exact activity of ONE raw spelling of a name.

    Attributes:
        raw_name: The name exactly as the source stores it. Two spellings of
            the same person yield two rows — the consumer folds and merges
            them, which is also how it learns the spellings disagree.
        count: Exact number of rows for that spelling. Never a capped or
            sampled figure: a count the UI shows is a claim.
        last_at: Most recent instant for that spelling, or None when the
            source has no timestamp to offer.
    """

    raw_name: str
    count: int
    last_at: datetime | None
