# ADR-006: Prevent Unbounded List Operations

**Status**: ✅ IMPLEMENTED (2025-11-14) — toujours en vigueur (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Éviter l'explosion de tokens sur les opérations de listing sans filtre

> **Note de provenance (2026-07-21)** : fichier **reconstitué** depuis le résumé de
> `ADR_INDEX.md` (original jamais committé). Confirmé contre le code : le garde-fou
> de listing vit dans `src/domains/agents/tools/google_contacts_tools.py`. Dates
> d'origine conservées.

---

## Context and Problem Statement

Le planner pouvait générer `list_contacts(query=None)`, renvoyant l'annuaire complet
(450+ contacts). Conséquence : explosion de tokens (100k+), coût, et une expérience
utilisateur dégradée (listes ingérables).

## Decision

Prévention **multi-couches** des listings non bornés :

1. **Validation planner** — avertissement (soft) si `list_contacts` est planifié sans `query`.
2. **Garde-fou outil** — plafond dur (hard cap) des résultats en l'absence de `query`.
3. **Logging** — trace d'avertissement pour le débogage.

## Alternatives Considered

- ❌ **Aucune limite** — explosion de tokens, listes ingérables.
- ❌ **Interdire le listing sans query** — casse des cas d'usage légitimes (petit annuaire).
- ✅ **Soft warning + hard cap** — protège sans interdire.

## Consequences

- ✅ Gaspillage de ressources : ~-95 % (plafond de résultats vs annuaire complet).
- ✅ Satisfaction utilisateur : plus de listes écrasantes.
- ✅ Observabilité : métrique `langgraph_plan_validation_warnings_total`.

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · [TOOLS.md](../technical/TOOLS.md) · [PLANNER.md](../technical/PLANNER.md)
