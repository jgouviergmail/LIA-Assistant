"""Who is the same person — folding, plus the merges the user declared.

``fold_name`` is the repository's ONE implementation of "literally the same
spelling" (ADR-185). It cannot know that a raw phone number and a name are one
relationship, or that "Papa" is "Jean Dupont": only the user knows, so only the
user may say it. This module is where that declaration is applied — and the
only place it is, so the list, the card and the tools cannot end up with three
different opinions about who someone is.

Two rules make reading cheap and safe:

- the alias table is **flat**: an alias never points at another alias, so
  resolution is ONE dictionary lookup. Merging B into C rewrites the rows that
  pointed at B — path compression paid once, at write time;
- resolution is **total**: an unknown key resolves to itself, so a relationship
  that was never merged behaves exactly as before.

Deliberately NOT applied to the peer directory. ``peers_tools`` resolves a
recipient by ``fold_name`` to decide whose assistant receives a message; a CRM
merge is a display decision by one user and must never redirect a message to
another account.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.domains.shared.text_normalization import fold_name


@dataclass(frozen=True)
class IdentityResolver:
    """Folds a raw name into the identity key the CRM groups it under.

    Attributes:
        aliases: Folded alias key -> folded canonical key. Flat: no value of
            this mapping is also one of its keys (enforced by the writer).
    """

    aliases: Mapping[str, str]

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, str]]) -> IdentityResolver:
        """Build a resolver from ``(alias_key, canonical_key)`` rows.

        Args:
            pairs: Stored merges, already folded.

        Returns:
            An immutable resolver. Two kinds of row are dropped:

            - **self-referencing** — an alias pointing at itself is not a
              merge, and keeping it would make ``keys_of`` report an identity
              as its own alias;
            - **half-blank** — the writer refuses blank names, so a blank side
              can only come from a corrupted row. Keeping ``papa -> ""`` would
              fold a real relationship into the EMPTY identity, where it would
              silently join every other broken row.
        """
        mapping = {
            alias: canonical
            for alias, canonical in pairs
            if alias and canonical and alias != canonical
        }
        return cls(aliases=MappingProxyType(mapping))

    def canonical(self, folded_key: str) -> str:
        """The identity a FOLDED key belongs to.

        One lookup, never a walk: the table is flat, and a malformed chain (an
        alias pointing at another alias) must still terminate — a read is not
        the place to discover a cycle.

        Args:
            folded_key: Key already produced by ``fold_name``.

        Returns:
            The canonical key, or the input when nothing was merged.
        """
        return self.aliases.get(folded_key, folded_key)

    def key(self, raw_name: str) -> str:
        """The identity key of a RAW spelling: fold first, then apply merges.

        Args:
            raw_name: A name as a source stored it.

        Returns:
            The canonical identity key (``""`` for a blank name — never a
            phantom identity).
        """
        return self.canonical(fold_name(raw_name))

    def keys_of(self, folded_key: str) -> frozenset[str]:
        """Every folded key belonging to one identity — canonical and aliases.

        SQL matches raw spellings EXACTLY (``IN (...)``), so a caller filtering
        source rows needs the whole set: after a merge, the rows of the
        merged-away side are still stored under their own spelling.

        Args:
            folded_key: Either half of the identity — canonical or alias.

        Returns:
            The canonical key plus every alias pointing at it.
        """
        canonical = self.canonical(folded_key)
        return frozenset(
            {canonical, *(alias for alias, target in self.aliases.items() if target == canonical)}
        )


#: A resolver with no merge at all — the behaviour that predates this module.
NO_MERGES = IdentityResolver.from_pairs([])

__all__ = ["NO_MERGES", "IdentityResolver"]
