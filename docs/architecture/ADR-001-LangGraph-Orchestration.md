# ADR-001: LangGraph pour Orchestration Multi-Agents

**Status**: ✅ ACCEPTED (2025-10-15) — toujours en vigueur (vérifié 2026-07-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Fondation de l'orchestration conversationnelle

> **Note de provenance (2026-07-21)** : ce fichier a été **reconstitué** à partir du
> résumé porté par `ADR_INDEX.md`. L'ADR original n'avait jamais été committé
> (`git log --diff-filter=A` vide) alors que l'index le référençait. Le contenu
> ci-dessous développe ce résumé et a été confirmé contre le code courant
> (LangGraph est la dépendance d'orchestration, cf. `requirements.txt` et
> `src/domains/agents/`). Les dates d'origine sont celles du résumé.

---

## Context and Problem Statement

LIA doit orchestrer des agents conversationnels multi-tours avec état persistant,
reprise après interruption (HITL) et streaming SSE. Le besoin : un moteur qui gère
un graphe d'exécution avec cycles, checkpoints et interruptions, sans réinventer la
gestion d'état.

## Decision

Utiliser **LangGraph** comme moteur d'orchestration des agents.

L'état conversationnel est un `TypedDict` (`MessagesState`) checkpointé en PostgreSQL ;
les interruptions HITL passent par le pattern `interrupt()` ; le streaming des tokens
remonte via SSE.

## Alternatives Considered

- ❌ **LangChain seul** — pas de gestion d'état de graphe ni de cycles.
- ❌ **Orchestration maison** — réinventer checkpoints, reprise et interruptions.
- ✅ **LangGraph** — state management + cycles conditionnels + checkpoints natifs.

## Consequences

- ✅ Persistance d'état via checkpoints PostgreSQL (reprise de conversation).
- ✅ HITL via le pattern `interrupt()` (approbations avant exécution).
- ✅ Streaming SSE des réponses.
- ⚠️ Courbe d'apprentissage LangGraph et couplage au framework (versions pinnées).

## Metrics (à l'acceptation)

- Sauvegarde de checkpoint : P95 < 50 ms.
- Chargement de checkpoint : P95 < 100 ms.
- Taille d'état moyenne : ~15 Ko / conversation.

## Related

- [ADR_INDEX.md](./ADR_INDEX.md) · architecture LangGraph détaillée : [ARCHITECTURE_LANGRAPH.md](../ARCHITECTURE_LANGRAPH.md)
- [ADR-022](./ADR_INDEX.md#adr-022-langgraph-state--checkpointing) (state & checkpointing)
