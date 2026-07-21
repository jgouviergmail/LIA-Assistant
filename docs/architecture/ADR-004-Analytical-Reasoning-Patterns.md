# ADR-004: Analytical Reasoning Patterns (Planner)

**Status**: ✅ ACCEPTED (2025-11-10) — principe intégré au planner courant (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Qualité des plans générés par le planner

> **Note de provenance (2026-07-21)** : fichier **reconstitué** depuis le résumé de
> `ADR_INDEX.md` (original jamais committé). Le résumé parle de « Planner v5 » : il
> s'agit de la version du **prompt** planner de l'époque, à ne pas confondre avec le
> nœud courant `planner_node_v3.py` (versioning distinct). Le principe décrit —
> raisonnement analytique en phases avant génération du plan — est intégré au
> planner actuel et à ses prompts versionnés. Dates d'origine conservées.

---

## Context and Problem Statement

Les versions antérieures du prompt planner produisaient des plans trop simplistes :
peu de raisonnement analytique, pas de décomposition explicite de l'intention
utilisateur. Résultat : des plans qui échouaient et devaient être rejoués.

## Decision

Structurer le raisonnement du planner en **phases analytiques explicites** avant la
génération de l'`ExecutionPlan` :

1. **Analyse de l'intention** — quoi (WHAT) et pourquoi (WHY).
2. **Décomposition** en sous-tâches.
3. **Génération** de l'`ExecutionPlan` avec justifications par étape.

## Alternatives Considered

- ❌ **Plan direct sans analyse** — plans simplistes, taux de rejeu élevé.
- ✅ **Enrichissement progressif + analyse structurée** — meilleure qualité de plan.

## Consequences

- ✅ Qualité de plan : ~+25 % (mesure via taux d'approbation HITL).
- ✅ Succès au rejeu : ~80 % (contre ~60 %).
- ⚠️ Latence : ~+300 ms (compromis accepté pour la qualité).

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · [PLANNER.md](../technical/PLANNER.md) (planner courant, prompts versionnés)
