# ADR-222 : suppression de la couche stratégie HITL jamais câblée

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Date**: 2026-08-16
**Origine**: audit d'exploitation LangChain/LangGraph (montée d'écosystème 2026-08)

## Contexte

Le module `hitl/resumption_strategies.py` portait une classe
`ConversationalHitlResumption` (~1 200 lignes avec ses trois helpers privés
`_build_resume_value`, `_build_runnable_config`, `_build_tool_level_command`)
derrière un Protocol `HitlResumptionStrategy` (`hitl/base.py`). Cette couche
implémentait sa propre boucle `graph.astream` de reprise HITL — abonnée à
`["values", "messages"]` seulement — avec son propre flux tracker/archivage.

Trois faits, vérifiés à l'audit :

1. **Aucun appelant de production.** `resume_and_stream` n'était référencé que
   par le docstring du Protocol et par ses tests. Le chemin réel de reprise
   passe par `api/service.py` → `orchestration/service.py`
   (`_build_hitl_resume_command`, `Command(resume=…)`) →
   `streaming/service.py::stream_sse_chunks`, qui a été conçu pour ce rôle
   (drapeau `is_hitl_resumption`, gestion des interrupts imbriqués, quatre
   modes de stream). Les payloads de resume de production sont construits par
   `parse_approval_decision` / `build_structured_decision`
   (`approval_decision.py`) — pas par `_build_resume_value`.
2. **Comportement divergent dormant.** La boucle morte ne souscrivait ni
   `updates` ni `custom` : si elle avait un jour été câblée, les événements de
   compaction et les enrichissements d'outils auraient silencieusement disparu
   des reprises. C'est la classe de dérive « deux implémentations d'un même
   dispatch » qu'ADR-220 (Lot 4) a éliminée côté messages d'erreur.
3. **Couverture factice.** Trois fichiers de tests (~50 tests, « coverage
   target: 85%+ ») maintenaient ce code vert — le docstring de l'un affirmait
   la fonction « very much live », à tort. L'observation « chemin mort
   apparent » avait déjà été consignée dans l'ADR_INDEX (findings HITL cards) ;
   cet ADR la clôt.

## Décision

Application de la règle systémique « dead code is deleted, not kept » :

- Supprimés : `ConversationalHitlResumption`, ses trois helpers privés,
  `hitl/base.py` (Protocol sans autre implémentation), les exports associés
  du package, et les deux fichiers de tests dédiés à la classe.
- Conservés dans `resumption_strategies.py` (seuls consommés en production) :
  `_build_plan_modifications_from_classifier` (approval_decision),
  `build_edit_reformulated_intent` et `resolve_user_language`
  (orchestration/service). Le module passe de 1 542 à ~340 lignes.
- Les quatre tests du contrat d'entrée `ToolApprovalDecision` — qui
  n'exerçaient pas le code mort mais le validateur du schéma vivant — sont
  préservés dans `tests/unit/domains/agents/test_domain_schemas.py`.

## Conséquences

- Une seule implémentation de la reprise HITL : la dérive nominal/reprise
  devient structurellement impossible sur ce chemin.
- Si une stratégie de reprise alternative devient un besoin réel (boutons
  admin, voix), elle se branche sur `StreamingService` — pas sur une boucle
  de stream parallèle.
- Récupération : `git log` porte l'implémentation complète si besoin.
