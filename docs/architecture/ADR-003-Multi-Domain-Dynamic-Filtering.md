# ADR-003: Multi-Domain Dynamic Filtering

**Status**: ✅ ACCEPTED (2025-11-09, finalisé 2025-11-11) — principe toujours en vigueur, implémentation évoluée (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Maîtrise du coût de prompt au scaling multi-domaines

> **Note de provenance (2026-07-21)** : fichier **reconstitué** depuis le résumé de
> `ADR_INDEX.md` (original jamais committé). Le principe — ne charger que le
> catalogue d'outils pertinent — est toujours actif, mais l'implémentation a évolué
> vers des **stratégies de filtrage** (`services/catalogue/strategies/` :
> `normal_filtering.py`, `panic_filtering.py`) plutôt que le « hybrid pattern »
> décrit à l'origine. Contenu confirmé contre le code courant à cette date.

---

## Context and Problem Statement

Le catalogue d'outils grandit avec les domaines : ~3 outils (contacts seuls) →
30+ outils (10 domaines). Charger tout le catalogue dans le prompt à chaque requête
multiplie la taille du prompt (~10×) et le coût (~10×). Il faut ne charger que ce
qui est pertinent pour la requête.

## Decision

Filtrer dynamiquement le catalogue **par domaine détecté**, avec repli sûr :

1. Le router détecte les domaines pertinents (ex. `["contacts", "email"]`).
2. Le catalogue est filtré aux outils de ces domaines (8 au lieu de 30+).
3. **Fallback** vers le catalogue complet si la confiance de détection est basse.

## Alternatives Considered

- ❌ **Catalogue complet systématique** — explosion de tokens et de coût.
- ❌ **Filtrage statique par règles** — non générique, à maintenir par domaine.
- ✅ **Filtrage dynamique + fallback** — générique (aucun code par domaine), sûr.

## Consequences

- ✅ Réduction de tokens : 60-90 % mesurée.
- ✅ Architecture générique : un nouveau domaine n'exige aucun changement de code de filtrage.
- ✅ Sûr : fallback sur confiance basse + métriques.
- ⚠️ Dépend de la qualité de détection de domaine (d'où le fallback).

## Évolution depuis l'acceptation

Le filtrage est aujourd'hui porté par des stratégies explicites sous
`src/domains/agents/services/catalogue/strategies/` (`normal_filtering`,
`panic_filtering`), intégrées à l'analyse de requête LLM-native — et non plus par le
« hybrid pattern » router→planner décrit initialement. Le principe (charger le
minimum pertinent, se rabattre sur le complet en cas de doute) est inchangé.

## Metrics (à l'acceptation)

- Taille de catalogue : 30 outils → 5-8 (73-83 % de réduction).
- Taux de cache : ~35 % (TTL 5 min).
- Fallback confiance basse : < 10 %.

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · [SEMANTIC_ROUTER.md](../technical/SEMANTIC_ROUTER.md) · [SMART_SERVICES.md](../technical/SMART_SERVICES.md)
