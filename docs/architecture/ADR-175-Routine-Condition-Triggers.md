# ADR-175 : Studio de routines — déclencheurs conditionnels au tick cron

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (programme UX Actions 2026-07-28, lot F / N-07)

## Contexte

Les actions planifiées (ADR-140) ne se déclenchaient que sur l'horloge :
jours ISO + heure/minute, `next_trigger_at` recalculé après chaque exécution
par APScheduler. N-07 veut des routines réactives : « fais X quand une tâche
est en retard », « quand la météo change », « quand un mail correspond »,
avec une option « propose d'abord ».

Deux contraintes de conception :

1. Le vrai event-driven (Gmail watch/Pub-Sub, webhooks calendrier) demande une
   infrastructure de souscription par utilisateur et par fournisseur —
   disproportionné pour un v1.
2. Aucun flag `SCHEDULED_ACTIONS_ENABLED` n'existe (piège documenté) ; le
   routeur est inclus inconditionnellement. Ne rien garder qui en dépende.

## Décision

**Phase 1 = « horaire OU condition », l'horloge reste le cron pour les deux.**
Une routine CONDITION évalue sa condition à chaque tick et ne s'exécute que si
elle est remplie ET que le fait est nouveau (déduplication par empreinte).

- Modèle : `trigger_kind` (`time`/`condition`, défaut `time`),
  `condition_config` (JSONB), `condition_state` (ledger de dédup),
  `requires_approval`. Migration f6a7b8c9d0e1 ; les lignes existantes
  rétro-remplissent `time`/false — **zéro changement de comportement**
  (test de non-régression dédié).
- Évaluateurs dans `infrastructure/scheduler/condition_evaluators.py` — pas
  dans le domaine : l'évaluation lit à travers les **fetchers du briefing**
  (leurs caches Redis bornent le coût API fournisseur), et `briefing.fetchers`
  importe déjà le domaine scheduled_actions (carte For-you) ; un import
  domaine→domaine fermerait un cycle. Le domaine possède le VOCABULAIRE
  (`CONDITION_TYPES`) et le contrat API (`ConditionConfig`) ; l'infra possède
  l'évaluation. **Assert de complétude au boot** (ADR-085) : un type sans
  évaluateur refuse de démarrer.
- Déduplication : chaque évaluateur renvoie une empreinte du FAIT qui rend la
  condition vraie ; le ledger (`condition_state`, règle new-dict JSONB) n'est
  écrit qu'à une exécution RÉELLE — un échec réessaie le même fait. Pattern
  ledger du heartbeat.
- « Proposer d'abord » (`requires_approval`) : le tick notifie au lieu
  d'exécuter ; le lien markdown porte le prompt de la routine en
  `?intent=` (ADR-173), donc le run appartient au chat et passe par le
  pipeline normal + HITL au clic. Le tick ne compte jamais comme exécution
  (`repo.reschedule`, pas `mark_execution_success`).
- Chat (ADR-140) inchangé : il crée des routines `time`. Les champs N-07 sont
  additifs à défaut `time`, donc une routine créée en chat et une créée au
  studio sont le MÊME objet — le studio est simplement la surface des
  conditions et du mode proposer-d'abord.

Les évaluateurs NE LÈVENT JAMAIS : une panne fournisseur lit « non remplie »
et le tick suivant réessaie. Un type stocké inconnu (config d'une autre
release) lit « non remplie », loggé, jamais un crash ni un tir silencieux.

## Alternatives écartées

- **Event-driven réel en phase 1** : Gmail watch/PubSub + webhooks calendrier
  = souscriptions par utilisateur/fournisseur, renouvellement, réconciliation.
  Le cron-tick + cache borné livre la valeur perçue à une fraction du coût.
- **Évaluateurs dans le domaine** : fermerait le cycle
  `scheduled_actions ↔ briefing` que l'infra évite déjà.
- **Un flag `SCHEDULED_ACTIONS_ENABLED`** : n'existe pas ; en inventer un pour
  ce lot serait hors périmètre et contraire au piège documenté.
- **Exécuter puis demander pardon** (pas de mode proposer-d'abord) : une
  routine réactive à conséquence externe qui agit sans accord est précisément
  ce que l'option d'approbation évite.
