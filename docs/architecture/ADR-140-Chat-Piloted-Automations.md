# ADR-140 : Automatisations pilotées depuis le chat + suggestion de récurrence

**Statut** : Accepté — implémenté (backend), preuve runtime dev.
**Date** : 2026-07-22
**Contexte produit** : P11 + P12 du programme « Interdomain Intelligence »
(spec `docs/superpowers/specs/2026-07-22-lot3-chat-automation-design.md`) ;
suit [ADR-139](ADR-139-Open-Loops-Commitments-Ledger.md) (Lot 2 du même
programme). P13 (suggestion contextuelle de skills) détaché du lot à la spec.

## Contexte

Les scheduled actions s'exécutaient déjà via le pipeline agent complet, mais
ne se pilotaient que depuis l'UI : « fais-moi ça tous les matins à 8 h » ne
pouvait pas aboutir en chat. Et rien n'observait qu'un utilisateur demande la
même chose chaque matin — l'opportunité d'automatisation restait invisible.

## Décision

- **P11 — Nouveau domaine routable `automation`** (`automation_agent`,
  interne, sans OAuth) + 3 outils : `create_scheduled_action_tool` (retourne
  un **draft `SCHEDULED_ACTION`** confirmable — arbitrage D4 : rien n'est
  persisté avant confirmation HITL ; l'exécuteur enregistré crée via
  `ScheduledActionService.create` qui calcule `next_trigger_at` et applique
  le cap par utilisateur), `list_scheduled_actions_tool` (lecture, expose les
  ids réels), `toggle_scheduled_action_tool` (bascule directe — réversible en
  un message, pas de draft). **Suppression = UI uniquement en v1** (toggle-off
  couvre le besoin réversiblement). Plomberie draft complète : enum,
  `DRAFT_DISPLAY_REGISTRY` (assert de boot), renderer de prévisualisation +
  goldens de caractérisation, noms/verbes/labels i18n ×6 (`i18n_drafts`,
  clés backend-canoniques `zh-CN`).
- **P12 — Détecteur de récurrence déterministe** (pas de table, pas de LLM) :
  ledger Redis par `(user, signature)` où la signature =
  `domaine_primaire+secondaires triés@bucket_4h` (heure LOCALE utilisateur).
  Écriture fire-and-forget en 7e bloc post-réponse (mêmes gardes sources
  automatisées/messages triviaux). Suggestion **one-shot par cooldown** quand
  la forme a des occurrences sur ≥ N jours DISTINCTS dans la fenêtre
  (répétitions le même jour ≠ récurrence) ; texte localisé ×6
  (`core/i18n_automation.py`) injecté via le slot existant
  `STATE_KEY_INITIATIVE_SUGGESTION` (directive déjà rendue par le response
  node) — le nœud initiative devient un wrapper fin (`_initiative_core`
  inchangé) qui fusionne la suggestion seulement quand le cœur n'en a pas
  produit. Flags indépendants : la suggestion fonctionne même si
  `INITIATIVE_ENABLED` est off.
- **Flags défaut OFF** (`RECURRENCE_SUGGESTION_ENABLED`) pour P12 ; P11 suit
  le catalogue standard (pas de flag — les scheduled actions sont toujours
  câblées, cf. CLAUDE.md : ne pas inventer `SCHEDULED_ACTIONS_ENABLED`).

## Alternatives rejetées

- **Réutiliser `PlanPatternLearner` pour la récurrence** : ses stats sont
  globales (par séquence d'outils), sans timestamps par occurrence ni
  dimension utilisateur — vérifié, inutilisable.
- **Suggestion via le prompt du response node** : `response_node.py` est au
  plafond du ratchet de taille ; le slot initiative existant rend la même
  surface sans le toucher.
- **Draft pour le toggle** : friction inutile sur une action réversible.

## Conséquences

- La boucle d'auto-composition est fermée : détection de récurrence →
  suggestion → création confirmée → exécution pipeline → résultat visible
  dans la fenêtre anti-redondance du heartbeat (P10, Lot 1).
- Mesure J+14 après activation du flag : taux d'acceptation des suggestions,
  faux positifs (suggestions refusées).
- Vérification : TDD intégral (~40 tests nouveaux), suites complètes vertes,
  preuve runtime dev.
