"""Shared text-normalization helpers.

``fold_name`` is the single identity-folding chokepoint used by the relations
CRM grouping and the peers discovery exact-match search. Hoisted from
``relations/service.py`` (peer-connections program, Lot 1) — behavior
unchanged: NFKD accent stripping + aggressive casefold + outer strip.
"""

from __future__ import annotations

import unicodedata


def fold_name(name: str) -> str:
    """Fold a display name for exact-match comparison and grouping.

    NFKD strips diacritics; casefold lowercases aggressively. Only leading and
    trailing whitespace is stripped — inner spacing is preserved on purpose
    (exact-match semantics). Empty or whitespace-only input folds to ``""``.

    Args:
        name: Raw display name.

    Returns:
        The folded name.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    return stripped.casefold().strip()
