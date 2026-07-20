# Scheduled Actions (Actions Planifiees)

> Systeme d'actions recurrentes executees automatiquement par l'assistant selon un calendrier defini par l'utilisateur.

**Version**: 1.0
**Date**: 2026-02-27

---

## Vue d'Ensemble

Les Scheduled Actions permettent aux utilisateurs de configurer des taches recurrentes que l'assistant execute automatiquement. Chaque action consiste en :

- Un **titre** descriptif
- Un **prompt d'instruction** pour l'assistant
- Un **calendrier** : jours de la semaine (ISO 1-7) + heure/minute en timezone locale
- Un **fuseau horaire** (herite du profil utilisateur)

Les resultats sont archives dans la conversation de l'utilisateur et notifies via FCM push et Redis SSE.

> **Pas de canaux externes.** Contrairement aux rappels et aux notifications proactives, l'executeur d'actions planifiees n'appelle pas `send_notification_to_channels()` : un resultat d'action planifiee n'est jamais pousse vers Telegram, meme avec `CHANNELS_ENABLED=true`.

### Exemples

| Titre | Jours | Heure | Prompt |
|-------|-------|-------|--------|
| Meteo du jour | Tous les jours | 08:00 | "Recherche la meteo du jour" |
| Veille IA | Lun, Mer, Ven | 19:30 | "Recherche les 5 dernieres actualites IA" |
| Synthese weekend | Sam, Dim | 09:00 | "Affiche mes taches, emails, rdv, rappels" |

---

## Architecture

```
[User Settings UI] --CRUD--> [Router/Service] --DB--> [scheduled_actions]
                    |                                          |
       [POST /execute] (test)                                 |
                    |                                          |
[APScheduler 60s] --poll--> [scheduled_action_executor.py]    |
       |                              |                        |
       |  1. SchedulerLock(Redis)     |                        |
       |  2. recover_stale_executing  |                        |
       |  3. get_and_lock_due_actions (FOR UPDATE SKIP LOCKED) |
       |  4. COMMIT (release locks)                            |
       |  5. Pour chaque action :                              |
       |     a. Guard: HITL pending check                      |
       |     b. stream_chat_response(auto_approve_plan=True)   |
       |     c. FCM + SSE + Channels notification               |
       |     d. compute_next_trigger_utc (CronTrigger)         |
       |     e. mark_execution_success / failure               |
```

---

## Backend

### Fichiers

| Fichier | Description |
|---------|-------------|
| `domains/scheduled_actions/models.py` | Modele SQLAlchemy + enum ScheduledActionStatus |
| `domains/scheduled_actions/schemas.py` | Pydantic v2 : Create, Update, Response, ListResponse |
| `domains/scheduled_actions/repository.py` | BaseRepository + lock queries scheduler |
| `domains/scheduled_actions/service.py` | CRUD + toggle + timezone recalculation |
| `domains/scheduled_actions/router.py` | 6 endpoints FastAPI |
| `domains/scheduled_actions/schedule_helpers.py` | APScheduler CronTrigger integration |
| `infrastructure/scheduler/scheduled_action_executor.py` | Job scheduler + execute_single_action |

### Modele de donnees

```
scheduled_actions
├── id (UUID, PK)
├── user_id (UUID, FK users.id CASCADE)
├── title (String 200)
├── action_prompt (Text)
├── days_of_week (ARRAY SmallInteger) -- ISO: 1=Lun..7=Dim
├── trigger_hour (SmallInteger, 0-23)
├── trigger_minute (SmallInteger, 0-59)
├── user_timezone (String 50, default "Europe/Paris")
├── next_trigger_at (DateTime TZ, UTC) -- Computed
├── is_enabled (Boolean, default true)
├── status (String 20: active|executing|error)
├── last_executed_at (DateTime TZ, nullable)
├── execution_count (Integer, default 0)
├── consecutive_failures (Integer, default 0)
├── last_error (Text, nullable)
├── created_at, updated_at (DateTime TZ)
```

**Index partiel** : `ix_scheduled_actions_due` sur `next_trigger_at WHERE is_enabled=true AND status='active'`

### API Endpoints

| Methode | Path | Status | Description |
|---------|------|--------|-------------|
| GET | `/scheduled-actions` | 200 | Liste actions de l'utilisateur |
| POST | `/scheduled-actions` | 201 | Creer (verifie limite par user) |
| PATCH | `/scheduled-actions/{id}` | 200 | Modifier |
| DELETE | `/scheduled-actions/{id}` | 204 | Supprimer |
| PATCH | `/scheduled-actions/{id}/toggle` | 200 | Toggle is_enabled |
| POST | `/scheduled-actions/{id}/execute` | 202 | Tester maintenant (fire-and-forget) |

### Calcul du prochain declenchement

Utilise `APScheduler.CronTrigger.get_next_fire_time()` (zero dependance ajoutee) :

```python
trigger = CronTrigger(
    day_of_week="mon,wed,fri",
    hour=19, minute=30,
    timezone=ZoneInfo("Europe/Paris"),
)
next_fire = trigger.get_next_fire_time(None, now_utc())
# CronTrigger retourne l'heure dans la timezone du trigger -> conversion UTC
return next_fire.astimezone(UTC)
```

**Important** : `CronTrigger.get_next_fire_time()` retourne un datetime dans la timezone du trigger (timezone utilisateur), pas en UTC. La conversion explicite `.astimezone(UTC)` est indispensable.

### Execution par le scheduler

Le job `process_scheduled_actions` tourne toutes les 60 secondes :

1. **Recovery** : reset actions `executing` > 10 min (crash recovery)
2. **Lock** : `FOR UPDATE SKIP LOCKED` + transition `status='executing'`
3. **Commit** : libere les verrous FOR UPDATE (status='executing' sert de verrou logique)
4. **Execute** : `execute_single_action()` dans sa propre session DB
5. **Notification** : FCM push + Redis SSE (voir [Corps des notifications](#corps-des-notifications))

> **Aucun SchedulerLock Redis** (F003). L'unicite d'execution est deja garantie par l'election de leader (`SchedulerLeaderElector`), le `max_instances=1` d'APScheduler et le `FOR UPDATE SKIP LOCKED` de l'etape 2. L'ancien lock, retenu pendant tout son TTL (300 s), bridait ce job de 60 s a une execution toutes les cinq minutes. Verrouille par `test_process_scheduled_actions_uses_no_redis_lock`.

### Corps des notifications

Le contenu de la reponse est **riche** : HTML enveloppe dans `<div class="lia-response">` quand le mode d'affichage de l'utilisateur est `html`, cartes de donnees rendues cote serveur en mode `cards`, Markdown sinon. Or le service worker passe `body` tel quel a `showNotification()` et le toast frontend rend sa description en texte echappe : sans aplatissement, l'utilisateur lit `<div class="lia-response"><h2>` sur son ecran de verrouillage.

Deux regles, dans cet ordre :

1. **Contenu canonique** — l'executeur consomme le chunk `content_replacement`, qui **remplace** les tokens diffuses (il porte le texte final apres post-traitement : cartes HTML, injection de photos, nettoyage des balises `psyche_eval`). N'accumuler que les `token` construisait la notification sur une version perimee, en desaccord avec le message archive que l'utilisateur ouvre ensuite dans le chat.
2. **Aplatissement puis troncature** — `plain_text_for_notification()` (`infrastructure/proactive/notification.py`) retire le HTML, aplatit les liens Markdown en `libelle (url)` et replie le tout sur une ligne. La troncature vient **apres** : tronquer du HTML brut coupe au milieu d'une balise et gaspille le budget (`<div class="lia-response">` consomme a lui seul 26 des 150 caracteres par defaut).

Le budget du push suit `PROACTIVE_NOTIFICATION_MAX_LENGTH` ; l'apercu SSE est plafonne par `SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH`. Cote frontend, `toPlainPreview()` (`apps/web/src/lib/notification-preview.ts`) applique la meme protection aux descriptions de toast, pour les trois familles de notifications.

### HITL bypass

L'executeur injecte `auto_approve_plan=True` dans `stream_chat_response()`, ce qui positionne `state["plan_approved"] = True` dans l'etat LangGraph. Le noeud `approval_gate_node` skip l'interrupt quand ce flag est `True`.

**Guard HITL** : avant d'executer, on verifie via `graph.aget_state()` qu'il n'y a pas d'interrupt HITL en attente sur la conversation de l'utilisateur. Sinon, l'action est skippee sans erreur et reprogrammee au prochain cycle.

### Pas d'apprentissage depuis les actions planifiées

L'exécuteur positionne également `is_automated_source=True` dans `stream_chat_response()`. Ce drapeau est propagé via `configurable` — et non via la metadata, qui est reconstruite par l'instrumentation Langfuse — puis lu une seule fois par `response_node`, où il désactive les **quatre** extractions post-réponse : mémoire long terme, centres d'intérêt, journal et psyché. Seules les entrées directes de l'utilisateur (chat web, Telegram, voix) alimentent ces sous-systèmes ; le prompt d'une action planifiée, injecté comme `HumanMessage`, ne crée donc plus de souvenirs ni de centres d'intérêt indésirables. Les notifications proactives (heartbeat, intérêts) ne passent pas par `response_node` et n'ont jamais été concernées.

### Retry sur erreurs transitoires

En cas d'erreur transitoire (`TimeoutError`, `ConnectionError`, `OSError`), l'executeur retente automatiquement jusqu'a `SCHEDULED_ACTIONS_MAX_RETRIES` fois (defaut: 1 retry, soit 2 tentatives max) avec un delai de `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` (defaut: 30s) entre les tentatives. Les erreurs non-transitoires (HITL interrupt, erreur logique) ne sont pas retentees.

### Auto-disable apres echecs

Apres **5 echecs consecutifs** (`SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES`), l'action est automatiquement desactivee (`is_enabled=False`, `status='error'`). Le re-enable via toggle reset les compteurs et recalcule le prochain declenchement.

### Recalcul timezone

Quand l'utilisateur modifie son fuseau horaire (dans `users/service.py`), toutes ses actions planifiees actives sont recalculees pour maintenir le meme horaire local avec le nouveau fuseau.

---

## Frontend

### Composants

| Fichier | Description |
|---------|-------------|
| `components/settings/ScheduledActionsSettings.tsx` | Section settings complète |
| `hooks/useScheduledActions.ts` | Hook CRUD avec optimistic updates + auto-refresh |

### UI

- Cards avec titre, statut (badge), prompt tronque, schedule, dates execution
- Switch inline enable/disable
- Boutons : Tester (Play), Modifier (Pencil), Supprimer (Trash2)
- Dialog creation/edition avec selection jours + heure
- Confirmation suppression via AlertDialog
- Etat vide avec icone et texte explicatif
- **Auto-refresh** : polling 30s (normal) / 10s (quand une action est en cours d'execution)

### i18n

Cles `scheduled_actions.*` dans les 6 langues (fr, en, es, de, it, zh).

---

## Constants

| Constante | Valeur | Description |
|-----------|--------|-------------|
| `SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS` | 60 | Intervalle du scheduler job |
| `SCHEDULED_ACTIONS_MAX_PER_USER` | 20 | Limite par utilisateur |
| `SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS` | 300 | Timeout execution (5 min) |
| `SCHEDULED_ACTIONS_MAX_RETRIES` | 1 | Retries sur erreur transitoire (2 tentatives max) |
| `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` | 30 | Delai entre retries |
| `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` | 10 | Seuil recovery stale |
| `SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES` | 5 | Seuil auto-disable |
| `SCHEDULED_ACTIONS_BATCH_SIZE` | 50 | Limite batch par cycle |

---

## Metriques Prometheus

- `background_job_duration_seconds{job_name="scheduled_action_executor"}` - Duree du job
- `background_job_errors_total{job_name="scheduled_action_executor"}` - Compteur erreurs

---

## Tests

| Fichier | Tests |
|---------|-------|
| `tests/unit/domains/scheduled_actions/test_schedule_helpers.py` | 27 tests : compute_next_trigger_utc (incl. UTC timezone validation), validate_days, format_display |
| `tests/unit/domains/scheduled_actions/test_schemas.py` | 18 tests : validation Create/Update |
