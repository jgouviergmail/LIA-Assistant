# Lot 3 — Rappels durables et récurrents

**But :** donner aux rappels la planification générique du lot 1, et la surface de
gestion (lister, créer, modifier, supprimer) que le propriétaire demande — sans
régression sur le comportement post-it existant.

**Architecture :** le lot 3 est le premier consommateur *autre* de
`src/core/recurrence`. Il n'ajoute aucune capacité au moteur : il prouve
(ou réfute) que le moteur, ses aides et l'éditeur React se montent tels quels.

**Spec / amont :** `docs/superpowers/specs/2026-09-06-generic-recurrence-design.md`,
lots 1/2A/2B livrés.

## Contraintes globales

- `RECURRENCE_REMINDER_LIMITS` = 48 déclenchements/jour, pas mini 5 min, 1000
  occurrences (`src/core/constants.py`, déjà déclaré au lot 1, encore inutilisé).
- Aucun import domaine→domaine. Aucun ratchet relevé. 6 langues, parité stricte.
- `task lint`, `test:backend:unit:fast`, `test:frontend` verts à chaque lot ;
  intégration PG + build managé e2e avant de déclarer le lot terminé
  (leçon du lot 2 : trois défauts n'étaient visibles que là).

## Les deux décisions du propriétaire (2026-09-06)

1. **Fin de série → suppression.** Une seule règle : `rearm_after(...) is None`
   → `DELETE`. Vérifié : `once` consommée rend `None`, donc le comportement
   actuel devient un cas particulier et non une exception. Corollaire :
   `trigger_at` reste **NOT NULL**, il n'y a pas d'état « terminé », rien ne
   s'accumule.
2. **Tout suit l'heure murale.** Un changement de fuseau recalcule *tous* les
   rappels, unique compris. C'est un **changement de comportement** sur
   l'existant (aujourd'hui l'instant est figé), assumé pour n'avoir qu'une
   seule règle. Il doit être testé explicitement et écrit dans l'ADR.

## Ce que l'analyse a établi (tout mesuré)

| # | Constat | Preuve |
|---|---|---|
| S1 | `schedule_helpers.py` est générique mais vit dans le domaine des routines | ses imports : `core.recurrence` + `core.time_utils`, aucun domaine |
| S2 | Les types de récurrence frontend vivent dans `hooks/useScheduledActions.ts` ; `lib/recurrence.ts` en dépend | inversion : le générique dépend d'un consommateur |
| R1 | `retry_count` n'est **jamais** remis à zéro | aucune écriture dans tout `src/` |
| R2 | Le chemin d'échec supprime après 3 essais | `reminder_notification.py:681` |
| R3 | Le prompt ordonne de citer la date de la demande | `reminder_prompt.txt`, ligne INSTRUCTIONS |
| R4 | Le changement de fuseau ignore les rappels | `users/service.py:237` ne connaît que les routines |
| P1 | 3 branches fr/en en dur | `format_elapsed_time`, `format_creation_datetime`, repli de personnalité |
| P2 | Aucun ramasseur de bail ; **non atteignable** par crash | transaction unique + `commit` ligne 703 → rollback complet |
| P3 | `CANCELLED` n'est écrit nulle part, mais l'absence de lignes héritées est **indémontrable** | git écrasé, base de dev vide → **on garde** |
| I1 | Un seul chemin de création | `reminder_tools.py:295` |
| I2 | Le manifeste de catalogue doit suivre la signature de l'outil | ADR-184 |

Marges de taille (plafond 600 SLOC logiques) :
`reminder_notification.py` **481 (marge 119)** — la plus tendue, extraire plutôt
qu'ajouter ; `reminder_tools.py` 384 ; le reste > 470 de marge.

---

## Lot 3A — Le socle générique (aucun changement de comportement)

**Fichiers**
- Déplacer `apps/api/src/domains/scheduled_actions/schedule_helpers.py`
  → `apps/api/src/core/recurrence/schedule.py`, exporté par `__init__.py`.
  Généraliser la prose : le docstring affirme « only a routine asks them »,
  ce lot le réfute.
- Mettre à jour les 4 appelants source + 2 fichiers de tests.
- Déplacer les 5 types de récurrence de `apps/web/src/hooks/useScheduledActions.ts`
  → `apps/web/src/types/recurrence.ts` ; ré-exporter depuis le hook pour ne pas
  casser les consommateurs existants ; faire pointer `lib/recurrence.ts` et les
  5 composants sur le module neutre.

**Tests**
- `tests/unit/core/recurrence/test_no_domain_import.py` couvre désormais les
  aides déplacées (il balaye le paquet) — vérifier qu'il les voit.
- Le ratchet de cycles (25) ne doit pas bouger : un déplacement domaine→core
  ne peut qu'en retirer.
- Suites complètes vertes = preuve du non-changement.

## Lot 3B — Le modèle et la migration

- `reminders.recurrence` JSONB **NOT NULL**, `trigger_at` reste NOT NULL.
- Backfill en SQL pur depuis `trigger_at` + `user_timezone` :
  `freq='once'`, `anchor_date` = date locale, `times.at = [{heure, minute}]`.
  **Ne jamais recalculer `trigger_at` depuis le spec** : les secondes s'y
  perdraient. `trigger_at` reste l'autorité pour l'occurrence en cours.
- `downgrade()` refuse toute récurrence non exprimable en instant unique
  (même doctrine qu'au lot 2A).
- `recurrence_spec` en propriété, comme sur `ScheduledAction`.
- **Ne pas toucher** `ReminderStatus.CANCELLED` (P3).

**Tests** : équivalence du backfill sur un échantillon de fuseaux ×
heures ; round-trip `to_dict`/`model_validate` ; garde de nullité.

## Lot 3C — Le job de notification

- `delete` terminal → `rearm_after(spec, tz, due_at=reminder.trigger_at)` :
  `None` → `DELETE` ; sinon `trigger_at = suivant`, `status = PENDING`,
  **`retry_count = 0`** (R1) et `notification_error = None`.
- Chemin d'échec (R2) : au-delà de `MAX_RETRIES`, **passer à l'occurrence
  suivante** si elle existe, supprimer seulement s'il n'y a plus rien.
- Prompt (R3) : le bloc d'origine devient un `{origin_context}` construit par
  le code — un rappel unique cite la demande, une occurrence récurrente cite
  la planification et **interdit** de mentionner la date de mise en place.
- i18n (P1) : les trois branches fr/en passent par `core.i18n_*`, 6 langues.
  Extraire dans un module dédié pour tenir la marge de 119 SLOC.

**Tests** : étendre `test_reminder_processing_lease.py` (harnais existant) —
`test_a_sent_reminder_is_deleted` devient un couple unique/récurrent ; un
échec répété sur un récurrent saute au créneau suivant sans détruire la série ;
`retry_count` remis à zéro après un succès ; les 6 langues du temps écoulé.

## Lot 3D — L'API

- `POST /reminders` et `PATCH /reminders/{id}` ; `recurrence` remplacé en
  entier, jamais par morceaux (même règle qu'au lot 2A, `null` explicite refusé).
- La réponse publie `recurrence`, `schedule_display` (`describe()`),
  `next_occurrences`, `times_of_day`, `runs_per_day`.
- Plafonds **injectés** : `RECURRENCE_REMINDER_LIMITS` — première preuve que le
  moteur sert deux appelants aux limites différentes.
- Corriger les docstrings qui affirment que le domaine refuse une surface de
  gestion (règle du dépôt : une docstring qui contredit le code est un bug).

**Tests** : contrat, plafonds refusés au bon seuil, `null` explicite refusé,
propriété du rappel (`check_resource_ownership`).

## Lot 3E — Le fuseau

- Le point de bascule unique de `users/service.py` apprend les rappels, dans le
  même bloc que les routines — jamais un bloc parallèle.
- **Tous** les rappels sont recalculés (décision 2).

**Tests** : un rappel unique et un récurrent déplacés ensemble ; échec du
recalcul non fatal ; test explicite du **changement de comportement** assumé.

## Lot 3F — Le frontend

- `useReminders.ts` (`useApiQuery`/`useApiMutation`).
- `RemindersSettings.tsx` montant **`RecurrenceEditor` sans modification** —
  c'est le test de généricité. Toute retouche de l'éditeur est un échec du lot 1
  à documenter, pas à contourner en silence.
- Câblage : `settings-sections.ts`, le registre, `settings-search.ts`,
  `capability-sections.ts` si les rappels sont un nœud de capacité.
- i18n × 6, parité stricte.
- La carte du briefing : l'annulation supprime désormais une **série** —
  la confirmation doit le dire.

**Tests** : montage de l'éditeur, création/modification/suppression, états
vide/chargement/erreur, noms accessibles, clavier, dialogue contraint en
hauteur (`max-h-[Ndvh] overflow-y-auto` — défaut trouvé au lot 2B).

## Lot 3G — L'outil de chat

- Paramètre de récurrence optionnel ; sans lui, comportement inchangé.
- **Manifeste de catalogue mis à jour dans le même changement** (ADR-184 : ce
  qu'un validateur refuse, son producteur doit pouvoir le lire).
- `mutation_policy` déjà `draft` ; inchangé.

**Tests** : l'outil produit un spec canonique ; un jour répété est replié ;
le manifeste et la signature restent en phase (garde).

## Lot 3H — Revue adversariale et portes

Portes obligatoires avant de déclarer le lot fini — les trois dernières ont
attrapé des défauts que 22 456 tests unitaires verts avaient laissés passer :

```
task lint                      # + ratchets, i18n, docs (preview si non stagé)
task test:backend:unit:fast
task test:frontend
task test:backend:integration -- reminders   # PostgreSQL réel
task db:migrate:replay-check                 # migration
build managé e2e                             # directive 'use client', compilation
```

## Plan de test (enrichi pendant l'implémentation)

| Axe | Ce qui doit être prouvé |
|---|---|
| Non-régression | un rappel unique se comporte **exactement** comme avant : notifié puis supprimé |
| Fin de série | bornée épuisée → supprimée ; quotidienne → réamorcée |
| Échec | 3 échecs sur un récurrent ne détruisent pas la série ; `retry_count` remis à zéro au succès |
| Fuseau | unique **et** récurrent suivent l'heure murale (changement assumé) |
| Prompt | une occurrence récurrente ne cite pas la date de mise en place |
| i18n | temps écoulé, date de création et repli de personnalité dans les 6 langues |
| Plafonds | 48/jour accepté, 49 refusé ; pas de 5 min accepté, 4 refusé |
| Généricité | `RecurrenceEditor` monté **sans diff** |
| Intégration PG | contraintes réelles, cascade de suppression du compte |
| UX | dialogue contraint en hauteur, actions identiques sur mobile |
