# ADR-005: Sequential Fallback Execution

**Status**: ✅ IMPLEMENTED (2025-11-14) — toujours en vigueur (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Éviter l'exécution parallèle des branches conditionnelles d'un plan

> **Note de provenance (2026-07-21)** : fichier **reconstitué** depuis le résumé de
> `ADR_INDEX.md` (original jamais committé). Confirmé contre le code : le filtrage
> des étapes ignorées avant exécution vit dans
> `src/domains/agents/orchestration/parallel_executor.py`. Dates d'origine conservées.

---

## Context and Problem Statement

L'exécuteur parallèle lançait toutes les étapes d'une vague via `asyncio.gather()`,
y compris les branches de **fallback conditionnel**. Conséquence : le plan principal
ET son fallback s'exécutaient en parallèle — double appel API, double coût, et
comportement non déterministe.

## Decision

**Filtrer les étapes ignorées (skipped) AVANT** `asyncio.gather()`, pour n'exécuter
que la vague réellement retenue :

```python
skipped_steps = _identify_skipped_steps(execution_plan, completed_steps)
next_wave_filtered = next_wave - skipped_steps
step_results = await asyncio.gather(*[... for step_id in next_wave_filtered])
```

## Alternatives Considered

- ❌ **Exécuter puis ignorer les résultats fallback** — coût et appels API déjà payés.
- ✅ **Filtrer avant `gather`** — aucune exécution superflue, déterministe.

## Consequences

- ✅ Réduction de coût : ~50 % sur les plans comportant un fallback.
- ✅ Déterminisme : plus de course entre branche principale et fallback.
- ✅ Observabilité : métrique `langgraph_plan_steps_skipped_total`.

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · [GRAPH_AND_AGENTS_ARCHITECTURE.md](../technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) (parallel_executor)
