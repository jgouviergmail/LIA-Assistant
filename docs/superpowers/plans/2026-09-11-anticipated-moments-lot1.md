# Lot 1 — Socle des moments anticipés et débrief post-réunion

**Spécification** : [2026-09-11-anticipated-moments-design.md](../specs/2026-09-11-anticipated-moments-design.md)
**Méthode** : TDD strict, rouge puis vert puis refactor, tâche par tâche.
**Inline, aucun sous-agent. Aucune action git.**

---

## Réordonnancement décidé à la rédaction du plan

Le découpage de la spécification (§14) séparait le socle (lot 1) de la source
heartbeat (lot 2). **Ce découpage est faux** : livré seul, le lot 1 produirait un
balayage qui sert une tâche incapable de lire un moment, c'est-à-dire du code
mort — précisément ce que la doctrine « wire it or remove it » interdit. La plus
petite unité qui fonctionne va de la table à la phrase.

Et le front passe **avant** les genres supplémentaires : sans réglage par genre,
le lot des genres livrerait trois nouvelles raisons d'interrompre sans le moyen
d'en refuser une (leçon ADR-214 : le contrôle précède l'exploitation).

| Lot | Contenu |
|---|---|
| **1 (ici)** | Caractérisation de l'existant, table, registre des genres, score, détecteur, balayage, source heartbeat, prompt, capacité, registres, métriques |
| 2 | Front : réglages par genre, libellé d'historique, puces de réponse |
| 3 | Garde « en réunion » |
| 4 | Genres `deadline_eve`, `counterparty_silence`, `return_from_absence` |
| 5 | Veilles : `expires_at`, évaluation au réveil, puce « Surveiller » |
| 6 | Docs, ADR, surfaces de release |
| 7 | Appel vocal vers la personne (spécification séparée) |

---

## T1.0 — Épingler la boucle de réponse existante

**Pourquoi d'abord** : tout le programme repose sur `_inject_proactive_messages`
(spécification §2.1) et **rien ne le teste** (vérifié : aucune occurrence dans
`tests/`). Un mécanisme porteur que rien ne tient peut disparaître sans bruit.

`tests/unit/domains/agents/orchestration/test_proactive_injection_characterization.py`

| Cas | Attendu |
|---|---|
| Notification archivée après le point de reprise | Présente en `AIMessage`, `additional_kwargs.proactive_notification is True` |
| Ordre | L'injection précède le `HumanMessage` du tour |
| Ligne cachée (`hidden=True`) | Jamais remontée (le `visible_only` du dépôt) |
| Plafond | Au plus `proactive_inject_max_messages` lignes |
| Sans point de reprise | La fenêtre vaut `proactive_inject_lookback_hours`, lue dans les réglages et jamais codée en dur |
| Erreur de base | Retourne 0, ne lève pas, laisse l'état utilisable |

Aucune correction de production attendue. Si un cas échoue, c'est une découverte
et elle est traitée avant d'aller plus loin.

---

## T1.1 — Constantes, réglages, `.env`

- `core/constants.py` : `SCHEDULER_JOB_MOMENT_SWEEP`, `MOMENTS_SWEEP_INTERVAL_MINUTES_DEFAULT` (5), `MOMENTS_EVENT_FOLLOWUP_DELAY_MINUTES_DEFAULT` (15), `MOMENTS_EVENT_FOLLOWUP_WINDOW_MINUTES_DEFAULT` (180), `MOMENTS_EVENT_MIN_DURATION_MINUTES_DEFAULT` (30), `MOMENTS_EVENT_CHAIN_GAP_MINUTES_DEFAULT` (15), `MOMENTS_EVENT_FOLLOWUP_MIN_SCORE_DEFAULT` (2), `MOMENTS_DETECT_LOOKBACK_MINUTES_DEFAULT` (240), `MOMENTS_RETENTION_DAYS_DEFAULT` (30), `MOMENTS_SWEEP_BATCH_SIZE_DEFAULT` (50), `REDIS_KEY_MOMENTS_AGENDA_PREFIX`.
- `core/config/notifications.py` : `moments_enabled` (défaut **False**) et les bornes ci-dessus, chacune avec `ge`/`le` et une description.
- `.env.example` **et** `.env.prod.example` : bloc inséré **avant** la section `[99]` (numérotation partagée, jamais en fin de fichier).

**Test** : bornes lues depuis `settings`, jamais réécrites dans un test.

---

## T1.2 — Modèle et migration

`domains/moments/models.py` : `MomentKind`, `MomentState`, `ProactiveMoment(BaseModel)`
conforme au §6 de la spécification (unicité `(user_id, kind, source_ref)`, index
partiel sur `due_at WHERE state='pending'`, `ON DELETE CASCADE`).

Migration alembic, `down_revision = "39c7e93d85b1"`, `upgrade`/`downgrade`
symétriques. Enregistrement du modèle aux **trois** endroits :
`infrastructure/database/registry.py`, `alembic/env.py` (si l'import n'y est pas
dérivé du registre), `infrastructure/startup/registries.py`.

**Tests** : colonnes et contraintes ; `alembic heads` unique.

---

## T1.3 — Dépôt, transitions atomiques

`domains/moments/repository.py` :

| Méthode | Forme imposée |
|---|---|
| `insert_candidates` | `pg_insert(...).on_conflict_do_nothing(index_elements=[user_id, kind, source_ref])`, une instruction |
| `claim_due` | `select(...).with_for_update(skip_locked=True).limit(1)` puis UPDATE conditionnel **dans la même transaction**, jeton propriétaire dans `claim_owner` |
| `settle` | UPDATE conditionné sur `claim_owner` (un règlement tardif d'un worker mort n'écrit rien) |
| `expire_stale` | UPDATE borné `state='pending' AND not_after < now` |
| `purge_closed` | DELETE borné sur la rétention |

**Tests intégration PostgreSQL** (`tests/integration/domains/moments/`) : unicité,
réclamation à deux acteurs concurrents (un seul gagne), règlement par un jeton
étranger sans effet, expiration, purge.

---

## T1.4 — Le score, pur

`domains/moments/importance.py` : `score_event(...) -> EventScore(worthy, score, reasons)`.
Nécessaires et points exactement comme la spécification §5.1, seuils lus dans les
réglages.

**Tests, table de cas** : sans participant ; un seul participant ; deux ; durée
sous le seuil ; journée entière ; décliné ; annulé ; organisatrice ; lieu ; visio ;
favori ; ticket lié ; combinaisons au seuil et juste sous.

---

## T1.5 — Le registre des genres

`domains/moments/kinds.py` : `MomentKindSpec(kind, detector, due_rule, label_key,
requires)` et `MOMENT_KIND_SPECS`, plus
`assert_moment_kind_registry_complete()` appelé à l'import (le boot le porte) et
depuis un test.

**Tests** : complétude **dans les deux sens** (un membre sans spec échoue, une spec
sans membre échoue) ; chaque `label_key` existe dans les six locales.

---

## T1.6 — Le détecteur `event_followup`

`domains/moments/detectors/event_followup.py` : résolution du connecteur actif,
lecture bornée `[now - MOMENTS_DETECT_LOOKBACK_MINUTES, now]` avec
`fields=["id","summary","start","end","location","attendees","organizer","status"]`,
fermeture déterministe du transport, exclusion des réunions LIA, règle de fusion
des blocs, score, échéances.

La résolution « connecteur actif vers client » est aujourd'hui écrite dans
`ContextAggregator._fetch_calendar` et dans `briefing/fetchers.fetch_agenda`. Elle
est **extraite** en un helper partagé plutôt que copiée une troisième fois — et
l'extraction fait **rétrécir** `context_aggregator.py`, qui est gelé à 690.

**Tests** : aucun connecteur ; aucun événement ; événement non digne ; digne ;
enchaîné ; réunion LIA ; instance de récurrence ; fournisseur en erreur (aucun
moment, aucune exception).

---

## T1.7 — Le balayage

`infrastructure/scheduler/moment_sweep.py`, six étapes de la spécification §7,
leader-élu, jitté, `max_instances=1`, enregistré dans `startup/schedulers.py`.

**Tests** : ordre des étapes ; un compte hors fenêtre n'est ni détecté ni servi ;
capacité éteinte à chaud ; un moment à la fois ; chaque sortie règle la ligne dans
exactement un état ; un refus de quota journalise « skipped » et jamais « failed ».

---

## T1.8 — La source `moment` du heartbeat

- `HeartbeatContext.moment` et son rendu en section FRESH ;
- `HeartbeatProactiveTask(moment=...)` ; `_trigger()` renvoie `"moment"` ;
- `check_eligibility` : quand un moment est servi, seul le drapeau du compte
  décide (spécification §4.2), **test dans les deux sens** ;
- `has_meaningful_context()` compte le moment ;
- `ANTICIPATED_MOMENT` dans `HeartbeatSourceLabel` ;
- `heartbeat_notifications.trigger` accepte `moment` (colonne `String`, aucune
  migration).

**Tests** : rendu du prompt ; contournement des reports ; label accepté par le
schéma ; `trigger` persisté.

---

## T1.9 — Le prompt

Règle 23 dans `heartbeat_decision_prompt.txt` : le moment est HAUTE VALEUR dans sa
fenêtre ; **une** question ouverte ; une ou deux informations de contexte ; une
proposition de suite formulée en question ; **jamais** de jugement sur la personne
ni sur sa journée ; jamais de relance si le même moment figure dans les
notifications récentes.

Nouveau fichier `moment_fresh_prompt.txt` (le pendant de
`heartbeat_wake_fresh_prompt.txt`), ajouté au Literal `PromptName`. Aucun nombre
en prose : les bornes viennent des réglages (ADR-184).

**Tests** : le fichier existe et se charge ; le Literal le connaît ; aucun nombre
codé en dur.

---

## T1.10 — Capacité, registres, métriques

- `PlatformCapability.MOMENTS`, `CapabilitySpec(family="knowledge",
  env_flag="moments_enabled", setting_key=..., service_enforced=True)`,
  `SystemSettingKey.CAPABILITY_MOMENTS_ENABLED`, entrée dans
  `EXPECTED_CAPABILITIES`, libellé front dans les six locales ;
- `key_families.py` : `moments:agenda` en `USER_CACHE` ;
- `consultation_surfaces.py` : surface `moment`, `source="proactive"`,
  `domains={"calendar": "event"}` ; `CONSULTATION_RECORDERS["moment"]` ;
- `direct_client_callers.py` : le détecteur, déclaré recorder ;
- métriques `proactive_moments_total{kind,outcome}` et
  `proactive_moment_latency_seconds`, **câblées au tableau de bord 13** (sinon le
  cliquet des métriques rougit), avec `or vector(0)` et `noValue: "0"`.

**Tests** : les gardes existants passent — familles de clés, surfaces, appelants
directs, dépense, jitter, fuseau, taille de fichier, couverture des métriques,
partition des capacités dans les deux sens.

---

## T1.11 — Preuve runtime

Conteneur en marche, capacité allumée, un événement de test terminant dans deux
minutes : moment détecté, servi, notification reçue, réponse tapée, mémoire
extraite. Journal d'exploitation lu, pas déduit.

---

## T1.12 — Portes de qualité

`task lint`, `task test:backend:unit:fast`, les suites d'intégration touchées,
puis `task ci:fast`. Cliquets relevés **après** mesure, jamais avant, et jamais
un plafond desserré.

---

## Pièges connus, à ne pas redécouvrir

1. `fetch_agenda` est un projeté d'affichage : ni identifiant ni date exploitable.
2. Un `IntervalTrigger` sans jitter s'aligne avec les autres pour la vie du
   processus (ADR-254).
3. Un JSONB ne se mute jamais en place.
4. Un enum nu dans un `case()` SQL part en `NullType`.
5. Une session `AsyncSession` ne se partage pas entre tâches concurrentes.
6. La date et l'heure sont toujours en UTC conscient ; le fuseau d'affichage vient
   des préférences.
7. Le heredoc casse sur ce dépôt (apostrophes et accents) : écrire les fichiers
   avec l'outil d'écriture.
8. `task ... | tail` renvoie le code de sortie de `tail`.
