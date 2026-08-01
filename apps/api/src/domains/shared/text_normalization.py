"""Shared text-normalization helpers.

The identity-folding chokepoints: ``fold_name`` for people, ``fold_email`` for
mailboxes. Each has exactly ONE implementation, here — re-expressing either in
SQL would make the database a second authority on who (or what) is the same.

The two folds differ on purpose, and the difference is load-bearing:

- a NAME is folded aggressively (NFKD accent stripping + casefold), because
  two spellings of a person are the same person;
- an ADDRESS is folded conservatively (strip + lowercase), because two
  spellings of a mailbox are NOT necessarily the same mailbox — folding
  ``jérôme@`` into ``jerome@`` would hand a searcher someone else's account.

``fold_name`` was hoisted from ``relations/service.py`` (peer-connections
program, Lot 1) with behavior unchanged.
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


def fold_email(email: str) -> str:
    """Fold an email address for exact-match comparison.

    Strip + ``lower()``, and nothing else. Case is the only difference no mail
    system distinguishes in practice, and the product's own storage produces
    it: registration keeps the local part's case (Pydantic ``EmailStr``
    lowercases the domain only), so ``Jean.Dupont@gmail.com`` must answer to
    ``jean.dupont@gmail.com``.

    Deliberately NOT ``casefold`` and NOT NFKD: casefold expands ``ß`` to
    ``ss`` and NFKD drops accents, either of which would merge two genuinely
    distinct mailboxes — a false positive that hands a searcher the wrong
    account. Under-matching here costs a "no result"; over-matching costs an
    identity.

    Args:
        email: Raw address.

    Returns:
        The folded address; ``""`` for empty or whitespace-only input.
    """
    return email.strip().lower()
