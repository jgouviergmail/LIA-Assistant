# Habitudes : l'usage appris devient des propositions — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** remplacer le verrou « même demande à heure fixe » (ADR-214) par un apprentissage de l'usage réel qui ouvre des propositions concrètes, exécutables en un clic, visibles dans le chat et dans la boîte « Propositions », sans aucun appel de modèle.

**Architecture :** chaque nuit, le recalcul des habitudes lit ce que LIA enregistre déjà (ledger des demandes par domaine, routines et leurs exécutions, présence, notifications proactives et leurs réactions, connecteurs), en tire des **besoins récurrents** (lignes `user_habits` de type `recurring_request`, charge utile v2 sans heure verrouillée) et des **propositions** (nouvelle table `habit_proposals`, cycle de vie ouvert / plus tard / jamais / acceptée / retirée). Les règles sont des fonctions pures ; les faits possédés par `agents` et `heartbeat` arrivent par deux ports que ces domaines installent (aucune nouvelle arête d'import). L'acceptation exécute l'action par une table de gestionnaires par type, déclarée complète au démarrage. Le chat montre une proposition sous la réponse par le même canal que les puces de relance (métadonnées archivées + événement `done`), décidée par le code dans le nœud de réponse, commun aux deux modes.

**Tech Stack :** FastAPI, SQLAlchemy 2 + Alembic, Pydantic 2, Redis, Next.js 16 / React 19, react-i18next (6 langues), pytest, vitest, Playwright.

**Spec :** conception arrêtée le 2026-11-06 et validée par le propriétaire le 2026-11-08 (« implémente tous les lots »), mémoire `project_habits_no_output_analysis_2026_11_06` : règles prototypées, rejouées sur les 5 comptes actifs de la production (lecture seule) et simulées sur 13 profils. La section « Décisions » ci-dessous en est la forme exécutable.

## Décisions (spec)

1. **L'heure n'est plus une condition.** Le verrou horaire (`recurrence_locks.evaluate_locks`, R ≥ 0,8, moitiés, empan, densité) est supprimé avec ses 8 réglages. L'heure habituelle (médiane) et le moment de la journée deviennent des **descripteurs** : ils pré-remplissent l'horaire d'une routine proposée, ils ne décident jamais.
2. **Besoin récurrent** = un domaine demandé sur ≥ `RECURRENCE_MIN_DISTINCT_DAYS` (4) jours distincts, sur ≥ 2 semaines ISO, dont un dans les 14 derniers jours, dans la fenêtre `RECURRENCE_WINDOW_DAYS` (35). Il devient une ligne `recurring_request` (v2). Cadence descriptive : `weekly` si un même jour de semaine porte ≥ `RECURRENCE_WEEKLY_DOW_FRACTION` (0,75) d'au moins `RECURRENCE_WEEKLY_MIN_SAME_DOW` jours ; `weekdays` si ≤ `RECURRENCE_WEEKEND_TOLERANCE` jour de week-end parmi ≥ 5 jours ; `daily` sinon. Il est « au seuil d'automatisation » quand ses jours représentent ≥ 0,40 des jours actifs de la personne (rollup `user_activity_days`) ET ≥ 12 jours (calibré pour 35 jours ; le harnais du lot 4 le vérifie).
3. **Types de proposition** (une ligne par `(user, kind, key)`) :
   - `automate_need` (clé = domaine) : besoin au seuil, domaine automatisable (agenda, e-mails, tâches, météo, rappels, SMS, santé), aucune routine active ne lit déjà ce domaine. Accepter crée une routine `time` (titre et consigne dans la langue de la personne, cadence et heure pré-remplies, fuseau du compte).
   - `add_routine_pass` (clé = `routine:<id>:<domaine>`) : besoin au seuil, une routine active lit déjà ce domaine, mais l'heure habituelle de la demande est à ≥ 2 h de chacun de ses horaires. Accepter ajoute cet horaire à la routine.
   - `shift_routine` (clé = id de routine) : ≥ 3 lancements manuels sur ≥ 3 jours distincts à ≥ 2 h de l'horaire planifié. Accepter remplace l'horaire planifié le plus proche par l'heure manuelle médiane.
   - `fix_routine` (clé = id de routine) : routine `error` ou ≥ 3 échecs consécutifs. Accepter ouvre la routine.
   - `extend_notification_window` (clé = `heartbeat`) : notifications proactives actives, présence hors plage ≥ 5 jours, ≥ 8 cellules-heure et ≥ 25 % des cellules ; extension par heures CONTIGUËS fréquentes (≥ 5 jours), au plus 3 h de chaque côté. Accepter applique la plage.
   - `review_notifications` (clé = `heartbeat`) : ≥ 20 notifications proactives sur la fenêtre, aucune réaction. Accepter les désactive ; « Jamais » vaut « garder ».
   - `connect_source` (clé = catégorie) : un domaine lié à une catégorie de connecteur (agenda, e-mails, tâches, contacts) demandé ≥ 3 jours sans connecteur actif de cette catégorie. Accepter ouvre les connecteurs.
4. **Cycle de vie** : ouverte → `accepted` (réouverture possible après 90 jours si la règle tient encore), `dismissed` « Plus tard » (réouverture après 14 jours), `refused` « Jamais » (pierre tombale définitive), retirée (ligne supprimée) quand la règle ne tient plus pour une proposition ouverte. Trois refus du même type taisent ce type pour la personne. « Tout oublier » efface les propositions ; l'interrupteur « Apprendre mes habitudes » ferme toutes les portes (ni calcul, ni service).
5. **Surfaces** : la section « Propositions » du centre d'alertes liste les propositions ouvertes (phrase rendue côté client depuis des faits structurés, jamais un texte pré-traduit) avec « Accepter » (libellé par type), « Plus tard », « Jamais » ; le compteur de la section les compte ; le panneau « Habitudes » montre les besoins v2 (domaine, jours sur jours actifs, moment, cadence) ; le chat montre au plus une proposition sous une réponse, décidée par le code : celle du domaine de la demande si elle existe, sinon une proposition jamais montrée, au plus une par jour, chaque proposition au plus une fois par 7 jours. **Aucun texte n'est gardé** : les consignes de routine sont des modèles par domaine, dans la langue du compte.
6. **Retraits** : l'offre de routine manquée du heartbeat (contexte, section du prompt de décision, règle 24, `habit_offered`, comptabilité `offer_dates`, mise en sourdine, métrique `heartbeat_habit_offers_total`), la boîte `/heartbeat/offers`, la suggestion textuelle injectée dans le prompt de réponse (`evaluate_suggestion`, promotion depuis le chat, textes `RECURRENCE_SCHEDULE_SUGGESTION_TEXT`), la colonne `user_habits.muted_until_reproof`. La colonne `heartbeat_notifications.habit_offer_id` reste (enregistrement), plus personne ne l'écrit. Le rythme d'activité (fenêtres, report des tics) ne change pas.
7. **Écartés en v1** (dits dans l'ADR) : la proposition « raccourci » (aucune fonction raccourci n'existe), les enchaînements (absorbés par une routine qui lit plusieurs domaines), la proposition d'activer les centres d'intérêt, les formulations de la personne.

## Global Constraints

- CLAUDE.md s'applique en entier : jamais d'action git, `structlog` seul, exceptions centralisées, i18n 6 langues en parité stricte, prompts versionnés, `AGENTS.md` régénéré, cartes vivantes à chaque ADR.
- Aucun appel de modèle ajouté ; aucune dépense nouvelle. Les preuves sur dev n'appellent aucun modèle payant (modèle factice dans le seul processus de preuve) ; aucune mesure payante sans budget validé.
- `habits` n'importe ni `agents` ni `heartbeat` (ratchet des cycles) : les faits de ces domaines arrivent par `habits/usage_ports.py`, installé par eux au démarrage, avec assertion de complétude.
- Fichiers gelés : `agents/api/service.py` 981/982 lignes logiques (tout ajout compensé), `agents/nodes/response_node.py` 2114/2153, `scheduler/scheduled_action_executor.py` 595/600.
- Une valeur réglable = constante `*_DEFAULT` + champ Settings + les 6 gabarits `.env` + les 4 `.env` du démonstrateur ; un réglage retiré disparaît des mêmes fichiers.
- Aucune donnée d'usage réel dans le dépôt (fixtures génériques, mesures agrégées dans l'ADR).

## Review Focus

1. Une routine créée la veille (aucune exécution liée) ou des exécutions antérieures à la colonne `run_id` : « sert-elle ce domaine ? » est inconnu → aucune `automate_need` ouverte cette nuit-là, jamais une proposition de doublon (lot 1, `test_unknown_routine_reads_hold_automation`).
2. Deux clics « Accepter » simultanés (chat et boîte) sur la même proposition → une seule routine créée ; le second reçoit un conflit propre (lot 2, `test_accept_is_claimed_once`).
3. Plafond de routines atteint, routine supprimée ou modifiée depuis la proposition → l'acceptation échoue avec un message traduit, la proposition reste ouverte (lot 2).
4. Plage de notification qui passe minuit (22 h → 2 h) et présence de nuit isolée → aucune extension par saut, extension contiguë seulement (lot 1, `test_window_extension_wraps_midnight_contiguously`).
5. Une ligne `recurring_request` v1 (en pause ou bloquée) lue par le panneau, les discussions, le portrait → convertie par la migration ; aucun lecteur ne lève (lot 1, test de migration + `test_discussion_projection_reads_v2_only`).

---

## Lot 0 — Observations exactes

### Task 0.1 : ledger dédoublonné par heure

**Files :** Modify `apps/api/src/domains/agents/services/recurrence_ledger.py` (`record_occurrence`), `apps/api/src/core/constants.py` (`RECURRENCE_DAY_HOURS_CAP_DEFAULT` 5 → 24), gabarits `.env` ; Test `apps/api/tests/unit/domains/agents/services/test_recurrence_ledger.py`.

- [ ] Test `test_record_occurrence_keeps_one_hour_per_hour_bin` : six demandes à 10,1 / 10,5 / 11,2 / 14,0 / 14,3 / 18,0 → jour stocké `[10.1, 11.2, 14.0, 18.0]`.
- [ ] Test `test_record_occurrence_respects_the_cap` avec un cap lu dans `settings`.
- [ ] Implémenter : n'ajouter l'heure que si `int(h)` n'est pas déjà présent ce jour-là ; cap inchangé dans le code, défaut relevé à 24 (une case par heure).

### Task 0.2 : `scheduled_action_runs.run_id`

**Files :** Create migration `apps/api/alembic/versions/2026_11_08_*_scheduled_run_id.py` ; Modify `domains/scheduled_actions/models.py` (`run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment=…)`), `runs.py::record_run(..., run_id: str | None = None)`, `run_repository.py`, `scheduler/scheduled_action_executor.py` (passe `run_id`) ; Test intégration `tests/integration/domains/scheduled_actions/test_runs_pg.py`.

- [ ] Test intégration `test_record_run_stores_the_run_id` (et `None` pour une occurrence jamais lancée).
- [ ] `task db:migrate:replay-check` vert ; une seule tête Alembic.

---

## Lot 1 — Moteur pur, stockage, synchronisation nocturne

### Task 1.1 : besoins (`habits/needs.py`)

**Interfaces — Produces :** `Need(domain, cadence, weekday, usual_hour, part_of_day, distinct_days, active_days, occurrences, at_automation_bar)` ; `detect_needs(days_by_domain: Mapping[str, Mapping[date, Sequence[float]]], *, active_days: int, today: date, settings: NeedSettings) -> list[Need]` ; `part_of_day(hour: float) -> PartOfDay` ; `NEED_PAYLOAD_VERSION = 2` ; `need_payload(need, usual_intent) -> dict`.

- [ ] Tests (fixtures génériques) : `test_existence_needs_four_days_two_weeks_and_recent`, `test_cadence_weekly_weekdays_daily`, `test_automation_bar_needs_share_and_days`, `test_usual_hour_is_a_descriptor_not_a_condition` (heures dispersées sur 10 h → besoin détecté), `test_part_of_day_any_below_share`.

### Task 1.2 : domaines automatisables (`habits/need_domains.py`)

**Produces :** `AUTOMATABLE_DOMAINS: Mapping[str, AutomatableDomain(read_tools: frozenset[str], connector_category: str | None)]` ; textes de routine dans `core/i18n_habits.py` (`routine_title(domain, lang)`, `routine_prompt(domain, lang)`, 6 langues).

- [ ] Garde `test_automatable_domains_are_registered_and_their_tools_exist` (domaine dans `DOMAIN_REGISTRY`, chaque outil dans le registre d'outils avec ce domaine) ; `test_routine_texts_cover_six_languages`.

### Task 1.3 : règles de proposition (`habits/proposal_rules.py`)

**Produces :** `ProposalKind` (StrEnum, 7 membres) ; `ProposalCandidate(kind, key, payload)` ; `UsageObservations` (besoins, routines avec horaires/exécutions/domaines lus ou `None` si inconnu, présence par jour, plage et état heartbeat, notifications et réactions, catégories de connecteurs actives, refus par type) ; `evaluate_proposals(obs, settings, today) -> list[ProposalCandidate]`.

- [ ] Un test par règle et par bord : `test_automate_need_only_when_unserved_at_bar`, `test_unknown_routine_reads_hold_automation`, `test_add_routine_pass_needs_two_hours_from_every_time`, `test_shift_routine_three_manual_runs_three_days`, `test_fix_routine_on_error_or_streak`, `test_window_extension_wraps_midnight_contiguously`, `test_window_isolated_night_presence_no_jump`, `test_review_notifications_twenty_silent`, `test_connect_source_category_missing`, `test_kind_muted_after_three_refusals`.

### Task 1.4 : table et dépôt des propositions

**Files :** Create `habits/proposal_models.py` (`HabitProposal`), migration `2026_11_08_*_habit_proposals.py`, `habits/proposal_repository.py` ; Modify `infrastructure/database/registry.py`.

Colonnes : `id`, `user_id` (FK CASCADE), `kind` String(40), `key` String(200), `payload` JSONB, `status` String(20) (`open|accepted|dismissed|refused`), `resurface_after` timestamptz NULL, `decided_at` NULL, `chat_shown_at` NULL, `created_at/updated_at` ; unique `(user_id, kind, key)` ; index `(user_id, status)`.

- [ ] Intégration PostgreSQL : `test_open_refresh_withdraw_cycle`, `test_dismissed_reopens_after_resurface`, `test_refused_is_a_tombstone`, `test_accept_is_claimed_once` (UPDATE conditionné `status='open'`, deux sessions), `test_list_open_page_and_exact_total`.

### Task 1.5 : synchronisation (`habits/proposal_sync.py`) et besoins v2 (`habits/recurrence_sync.py`)

- [ ] `recurrence_sync` réécrit sur `detect_needs` (charge utile v2, plafond par type, pierres tombales gardées, ledger illisible = rien ne change) ; `recurrence_locks.py` supprimé ; lecteurs adaptés : `discussion_projection`, `portrait_source`, `management_explanation`, `service.build_explanation` (seuils v2 publiés), `candidates`.
- [ ] `sync_proposals` : ouvre, rafraîchit, rouvre après délai, retire ; compte `habit_proposals_total{kind,transition}`.
- [ ] Migration de données : lignes v1 ACTIVES supprimées (recalculées la nuit suivante), lignes v1 en pause ou bloquées converties en v2 minimale ; colonne `muted_until_reproof` supprimée.

### Task 1.6 : observations et ports

**Files :** Create `habits/usage_ports.py` (`install_routine_reads(reader)`, `install_proactive_feedback(reader)`, `assert_usage_ports_installed()`), `habits/usage_observations.py` (`gather_usage_observations(db, user, needs, settings, today) -> UsageObservations`) ; installation dans `agents` (domaines lus par `run_id`, via `treatment_domain`) et `heartbeat` (envois et réactions sur la fenêtre), appel au démarrage (`startup/registries.py`).

- [ ] Tests : port absent → domaines lus « inconnus » (jamais « aucun ») ; `recompute_user_profile` appelle besoins puis propositions ; réglages, constantes, gabarits `.env` (6 + 4) ; réglages retirés supprimés partout.

---

## Lot 2 — API et surfaces

- [ ] **2.1 API** (`habits/proposals_router.py`, monté sous `/habits/proposals`, garde capacité + interrupteur) : `GET` paginé (total exact), `POST /{id}/accept|dismiss|refuse` ; `habits/proposal_actions.py` : registre type → gestionnaire, assertion de complétude au démarrage ; gestionnaires routine dans `habits` (via `ScheduledActionService`), gestionnaires heartbeat installés par `heartbeat` (via `update_heartbeat_preferences`), navigation pour `fix_routine` et `connect_source`. Compteur `offers` du centre d'alertes = propositions ouvertes. Retrait de `/heartbeat/offers` et `get_open_offers`.
- [ ] **2.2 Interface** : `components/habits/ProposalRow.tsx` (phrase + actions, focus et états désactivés), section « Propositions » du centre d'alertes branchée sur `/habits/proposals`, `OpenOffersList.tsx` supprimé ; panneau `HabitsSettings.tsx` en v2 ; clés i18n 6 langues ; FAQ 6 langues ; `docs/knowledge`.
- [ ] Tests : routeur (accept crée la routine, conflit, plafond, propriété cachée), vitest (rendu de chaque type, libellés, erreurs, focus), e2e hermétique « accepter une proposition ».

## Lot 3 — Chat et heartbeat

- [ ] **3.1** `agents/nodes/turn_proposal.py` : `resolve_turn_proposal(state, run_id)` appelé par le nœud de réponse, propose au plus une, horodate `chat_shown_at`, passe par le canal des puces (`followup_metadata` regroupé en un seul `pop` pour tenir le budget de `service.py`) ; archivage et événement `done` ; retrait de la suggestion textuelle et de la promotion depuis le chat.
- [ ] **3.2** `components/chat/ChatProposalCard.tsx` sous la dernière réponse, mêmes actions que la boîte.
- [ ] **3.3** Heartbeat : retrait de l'offre de routine manquée (code, prompt de décision, schéma, métrique, tableau de bord, alerte) ; le rythme reste.

## Lot 4 — Mesure, preuves, documentation, portes

- [ ] `apps/api/scripts/habits/measure_proposals.py` + `task habits:proposals:measure` (13 profils, code réel) + test court ; retrait du verrou du banc `measure_calibration.py`.
- [ ] Rejeu lecture seule sur la production avec le code réel (hors dépôt) ; preuve dev de bout en bout sur le compte de preuve (semis inerte, aucun modèle payant).
- [ ] ADR-375 + amendement ADR-214, `ADR_INDEX`, cartes (6 langues), `HEARTBEAT_AUTONOME.md`, runbook `RecurrenceLedgerSilent`, CLAUDE.md (2-4 lignes) puis `task docs:sync-agents`.
- [ ] Portes : `task lint`, `task test:backend:unit:fast`, intégration ciblée (habits, scheduled_actions, heartbeat, notifications), `task test:frontend:coverage`, e2e de la section, `task ci:fast`, redémarrage de `lia-api-dev` jusqu'à `application_ready`.
