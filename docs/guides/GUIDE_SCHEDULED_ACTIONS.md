# Guide Pratique : Actions Planifiees (Scheduled Actions)

> Guide pratique pour les developpeurs souhaitant comprendre, configurer, etendre et debugger le systeme d'actions planifiees recurrentes de LIA.
> Version 1.0 - 2026-03-08

---

## Table des Matieres

- [1. Introduction](#1-introduction)
- [2. Architecture](#2-architecture)
- [3. Configuration](#3-configuration)
- [4. API Endpoints](#4-api-endpoints)
- [5. Types d'Actions](#5-types-dactions)
- [6. Timezone Handling](#6-timezone-handling)
- [7. Retry Logic](#7-retry-logic)
- [8. Notifications](#8-notifications)
- [9. Comparaison Reminders vs Scheduled Actions vs Heartbeat](#9-comparaison-reminders-vs-scheduled-actions-vs-heartbeat)
- [10. Testing](#10-testing)
- [11. Troubleshooting](#11-troubleshooting)

---

## 1. Introduction

### Qu'est-ce qu'une action planifiee ?

Les **Scheduled Actions** permettent aux utilisateurs de configurer des taches recurrentes executees automatiquement par l'assistant selon un calendrier defini. Chaque action consiste en :

- Un **titre** descriptif (ex: "Meteo du jour")
- Un **prompt d'instruction** envoye au pipeline d'agents (ex: "Recherche la meteo du jour")
- Un **calendrier** : jours de la semaine (ISO 1-7) + heure/minute en timezone locale
- Un **fuseau horaire** (herite du profil utilisateur)

Le resultat de chaque execution est automatiquement archive dans la conversation de l'utilisateur et notifie via FCM push et Redis SSE.

### Exemples concrets

| Titre | Jours | Heure | Prompt |
|-------|-------|-------|--------|
| Meteo du jour | Tous les jours | 08:00 | "Recherche la meteo du jour" |
| Veille IA | Lun, Mer, Ven | 19:30 | "Recherche les 5 dernieres actualites IA" |
| Synthese weekend | Sam, Dim | 09:00 | "Affiche mes taches, emails, rdv, rappels" |

### Difference avec les Reminders

Les **Reminders** sont des rappels ponctuels (one-shot) crees via le langage naturel ("Rappelle-moi d'appeler le medecin dans 2 heures"). Ils sont supprimes apres execution.

Les **Scheduled Actions** sont des taches recurrentes configurees via l'UI Settings. Elles persistent et se reprogramment automatiquement apres chaque execution.

---

## 2. Architecture

### Schema global

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
       |     c. FCM + SSE notification                         |
       |     d. compute_next_trigger_utc (CronTrigger)         |
       |     e. mark_execution_success / failure               |
```

### Fichiers du domaine

| Fichier | Role |
|---------|------|
| `domains/scheduled_actions/models.py` | Modele SQLAlchemy `ScheduledAction` + enum `ScheduledActionStatus` |
| `domains/scheduled_actions/schemas.py` | Pydantic v2 : `ScheduledActionCreate`, `Update`, `Response`, `ListResponse` |
| `domains/scheduled_actions/repository.py` | `BaseRepository` + requetes scheduler (`FOR UPDATE SKIP LOCKED`, recovery) |
| `domains/scheduled_actions/service.py` | CRUD + toggle + recalcul timezone cascade |
| `domains/scheduled_actions/router.py` | 6 endpoints FastAPI |
| `domains/scheduled_actions/schedule_helpers.py` | `compute_next_trigger_utc()` via APScheduler `CronTrigger` |
| `infrastructure/scheduler/scheduled_action_executor.py` | Job scheduler `process_scheduled_actions()` + `execute_single_action()` |

### Modele de donnees

```
scheduled_actions
+-- id (UUID, PK)
+-- user_id (UUID, FK users.id CASCADE)
+-- title (String 200)
+-- action_prompt (Text)
+-- days_of_week (ARRAY SmallInteger) -- ISO: 1=Lun..7=Dim
+-- trigger_hour (SmallInteger, 0-23)
+-- trigger_minute (SmallInteger, 0-59)
+-- user_timezone (String 50, default "Europe/Paris")
+-- next_trigger_at (DateTime TZ, UTC) -- Calcule automatiquement
+-- is_enabled (Boolean, default true)
+-- status (String 20: active|executing|error)
+-- last_executed_at (DateTime TZ, nullable)
+-- execution_count (Integer, default 0)
+-- consecutive_failures (Integer, default 0)
+-- last_error (Text, nullable)
+-- created_at, updated_at (DateTime TZ)
```

**Index partiel** (hot path du scheduler) : `ix_scheduled_actions_due` sur `next_trigger_at WHERE is_enabled=true AND status='active'`

### Statuts (`ScheduledActionStatus`)

| Statut | Description |
|--------|-------------|
| `active` | Prete pour execution au prochain declenchement |
| `executing` | En cours d'execution (verrouillee par le scheduler) |
| `error` | Auto-desactivee apres trop d'echecs consecutifs |

### Pipeline d'execution

L'executeur utilise `stream_chat_response()` avec `auto_approve_plan=True`, ce qui injecte `state["plan_approved"] = True` dans l'etat LangGraph. Le noeud `approval_gate_node` skip l'interrupt HITL quand ce flag est `True`.

Avant execution, un **guard HITL** verifie via `graph.aget_state()` qu'il n'y a pas d'interrupt HITL en attente sur la conversation de l'utilisateur. Si un interrupt est en attente, l'action est skippee sans erreur et reprogrammee au prochain cycle.

> **Note** : Les actions planifiees sont des sources automatisees — elles ne declenchent **ni l'extraction de memoire long terme**, **ni la detection de centres d'interet**. Seules les interactions directes de l'utilisateur alimentent ces systemes d'apprentissage. Le `response_node` detecte les sources automatisees via le prefixe `SCHEDULED_ACTIONS_SESSION_PREFIX` du `session_id`.

---

## 3. Configuration

### Feature flag

Le feature flag `SCHEDULED_ACTIONS_ENABLED` est documente dans le README et le guide de deploiement. En pratique, le job scheduler et le router sont toujours enregistres (pas de garde conditionnelle dans le code actuel).

```bash
# .env
SCHEDULED_ACTIONS_ENABLED=true
```

### Constantes

Toutes les constantes sont definies dans `apps/api/src/core/constants.py` :

| Constante | Valeur | Description |
|-----------|--------|-------------|
| `SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS` | `60` | Intervalle du scheduler job (secondes) |
| `SCHEDULED_ACTIONS_MAX_PER_USER` | `20` | Limite d'actions par utilisateur |
| `SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS` | `300` | Timeout execution (5 min) |
| `SCHEDULED_ACTIONS_MAX_RETRIES` | `1` | Retries sur erreur transitoire (2 tentatives max) |
| `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` | `30` | Delai entre retries (secondes) |
| `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` | `10` | Seuil recovery pour actions bloquees en `executing` |
| `SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES` | `5` | Seuil avant auto-disable |
| `SCHEDULED_ACTIONS_BATCH_SIZE` | `50` | Nombre max d'actions traitees par cycle |

### Enregistrement du job scheduler

Le job est enregistre dans `apps/api/src/main.py` au demarrage de l'application :

```python
scheduler.add_job(
    process_scheduled_actions,
    trigger="interval",
    seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
    id=SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
    name="Process scheduled actions",
    replace_existing=True,
    max_instances=1,
    misfire_grace_time=30,
)
```

`max_instances=1` empeche les executions concurrentes du job APScheduler. Le `SchedulerLock` (Redis SETNX) ajoute une securite supplementaire pour les deployments multi-worker.

---

## 4. API Endpoints

Le router est monte sur le prefixe `/scheduled-actions` dans `apps/api/src/api/v1/routes.py`.

### Endpoints

| Methode | Path | Status | Description |
|---------|------|--------|-------------|
| `GET` | `/scheduled-actions` | `200` | Liste toutes les actions de l'utilisateur connecte |
| `POST` | `/scheduled-actions` | `201` | Creer une nouvelle action (verifie la limite par user) |
| `PATCH` | `/scheduled-actions/{id}` | `200` | Modifier une action (recalcule `next_trigger_at` si le schedule change) |
| `DELETE` | `/scheduled-actions/{id}` | `204` | Supprimer une action (hard delete) |
| `PATCH` | `/scheduled-actions/{id}/toggle` | `200` | Toggle `is_enabled` (re-enable reset les compteurs d'erreur) |
| `POST` | `/scheduled-actions/{id}/execute` | `202` | Execution immediate (fire-and-forget en background task) |

### Exemples de requetes

**Creer une action** :

```json
POST /api/v1/scheduled-actions
{
    "title": "Meteo du jour",
    "action_prompt": "Recherche la meteo du jour pour ma ville",
    "days_of_week": [1, 2, 3, 4, 5, 6, 7],
    "trigger_hour": 8,
    "trigger_minute": 0
}
```

**Reponse** :

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "...",
    "title": "Meteo du jour",
    "action_prompt": "Recherche la meteo du jour pour ma ville",
    "days_of_week": [1, 2, 3, 4, 5, 6, 7],
    "trigger_hour": 8,
    "trigger_minute": 0,
    "user_timezone": "Europe/Paris",
    "next_trigger_at": "2026-03-09T07:00:00Z",
    "is_enabled": true,
    "status": "active",
    "last_executed_at": null,
    "execution_count": 0,
    "consecutive_failures": 0,
    "last_error": null,
    "schedule_display": "Tous les jours a 08:00",
    "created_at": "2026-03-08T10:00:00Z",
    "updated_at": "2026-03-08T10:00:00Z"
}
```

**Modifier partiellement** :

```json
PATCH /api/v1/scheduled-actions/550e8400-...
{
    "days_of_week": [1, 3, 5],
    "trigger_hour": 19,
    "trigger_minute": 30
}
```

**Toggle enable/disable** :

```
PATCH /api/v1/scheduled-actions/550e8400-.../toggle
```

**Execution immediate** (pour tester) :

```
POST /api/v1/scheduled-actions/550e8400-.../execute
```

Retourne `202 Accepted` avec `{"status": "executing"}`. L'execution s'effectue en background. Le resultat apparait dans la conversation et en notification.

### Validation des donnees

- `title` : 1 a 200 caracteres
- `action_prompt` : 1 a 2000 caracteres
- `days_of_week` : 1 a 7 valeurs, chacune entre 1 (Lundi) et 7 (Dimanche), sans doublons
- `trigger_hour` : 0 a 23
- `trigger_minute` : 0 a 59
- Limite : max `SCHEDULED_ACTIONS_MAX_PER_USER` (20) actions par utilisateur

### Ownership check

Tous les endpoints verifient que l'action appartient a l'utilisateur connecte via `get_with_ownership_check()`. Toute tentative d'acces a une action d'un autre utilisateur leve une `ResourceNotFoundError`.

---

## 5. Types d'Actions

Toute requete qui peut etre traitee par le pipeline d'agents peut etre planifiee. Le prompt `action_prompt` est envoye a `stream_chat_response()` exactement comme un message utilisateur.

### Exemples par domaine

| Domaine | Prompt exemple | Prerequis |
|---------|---------------|-----------|
| **Meteo** | "Recherche la meteo du jour" | Brave Search API key configuree |
| **Email** | "Affiche mes emails non lus" | Google OAuth connecte |
| **Calendrier** | "Affiche mes rendez-vous du jour" | Google OAuth connecte |
| **Taches** | "Liste mes taches en cours" | Google OAuth connecte |
| **Actualites** | "Recherche les 5 dernieres news IA" | Perplexity ou Brave API |
| **Web** | "Recherche le cours du Bitcoin" | web_search / web_fetch disponible |
| **Multi-domaine** | "Affiche mes emails, rdv et taches du jour" | Connexions requises configurees |
| **MCP** | Tout prompt utilisant des outils MCP | MCP servers configures |

### Limitations

- Les actions necessitant une **interaction HITL** (confirmation destructive, clarification) sont gereees via le guard HITL : si un interrupt est en attente, l'action est replanifiee sans erreur.
- `auto_approve_plan=True` bypass l'approbation du plan, mais pas les HITL de type "destructive confirm" ou "draft critique" qui sont generes par les agents eux-memes.
- Le timeout d'execution est de **5 minutes** (`SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS`). Les prompts tres complexes ou lents peuvent echouer par timeout.

---

## 6. Timezone Handling

### Principe general

Les heures de declenchement sont stockees en **UTC** dans `next_trigger_at`, mais definies par l'utilisateur en heure locale.

```
CONFIGURATION (heure locale utilisateur)
    |
compute_next_trigger_utc(days, hour, minute, user_timezone)
    |
STOCKAGE: next_trigger_at (UTC)
    |
SCHEDULER: next_trigger_at <= NOW(UTC) ?
    |
AFFICHAGE: converti en timezone utilisateur (via schedule_display)
```

### Calcul avec CronTrigger

Le calcul du prochain declenchement utilise `APScheduler.CronTrigger.get_next_fire_time()` (zero dependance supplementaire) :

```python
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

trigger = CronTrigger(
    day_of_week="mon,wed,fri",
    hour=19, minute=30,
    timezone=ZoneInfo("Europe/Paris"),
)
next_fire = trigger.get_next_fire_time(None, now_utc())
# IMPORTANT: CronTrigger retourne l'heure dans la timezone du trigger
# La conversion explicite vers UTC est indispensable
return next_fire.astimezone(UTC)
```

### Changement de timezone utilisateur

Quand un utilisateur modifie son fuseau horaire dans son profil, le service `ScheduledActionService.recalculate_all_for_user()` recalcule le `next_trigger_at` de toutes ses actions actives.

Le meme horaire local est preserve (ex: 19:30 reste 19:30) mais la valeur UTC change. Cet appel est declenche depuis `users/service.py` lors de la mise a jour du profil.

### Piege classique

`CronTrigger.get_next_fire_time()` retourne un datetime dans la timezone du trigger, **pas en UTC**. Oublier `.astimezone(UTC)` provoquera un decalage horaire.

---

## 7. Retry Logic

### Erreurs transitoires vs non-transitoires

| Type | Erreurs concernees | Comportement |
|------|-------------------|-------------|
| **Transitoire** | `TimeoutError`, `ConnectionError`, `OSError` | Retry automatique |
| **Non-transitoire** | `RuntimeError` (HITL interrupt), erreur logique | Arret immediat, pas de retry |

### Mecanisme de retry

1. Premiere tentative d'execution
2. En cas d'erreur transitoire : attente de `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` (30s)
3. Deuxieme tentative (avec un `session_id` different pour eviter la reprise d'un checkpoint LangGraph corrompu)
4. Si la deuxieme tentative echoue : l'erreur est comptabilisee

Chaque tentative utilise un `session_id` unique (`scheduled_action_{id}` puis `scheduled_action_{id}_retry_{n}`) pour s'assurer que LangGraph demarre un nouveau graphe plutot que de reprendre un checkpoint partiel.

### Auto-disable apres echecs consecutifs

Le compteur `consecutive_failures` est incremente a chaque echec et remis a zero a chaque succes.

Quand `consecutive_failures >= SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES` (5) :
- `is_enabled` passe a `False`
- `status` passe a `error`
- L'action ne sera plus executee tant qu'elle n'est pas reactivee

**Reactivation** : l'endpoint `PATCH .../toggle` remet `consecutive_failures` a 0, `status` a `active`, et recalcule `next_trigger_at`.

### Crash recovery

Si le processus crashe pendant l'execution (status `executing`), la methode `recover_stale_executing()` est appelee au debut de chaque cycle du scheduler. Toute action en `executing` depuis plus de `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` (10 min) est remise en `active`.

---

## 8. Notifications

### Canaux de notification

Apres execution reussie, le resultat est notifie via :

| Canal | Condition | Detail |
|-------|-----------|--------|
| **Archive conversation** | Toujours | Automatique via `stream_chat_response()` |
| **FCM Push** | `FCM_NOTIFICATIONS_ENABLED=true` + tokens actifs | Titre localise (6 langues) + body tronque a 150 chars |
| **Redis SSE** | Redis disponible | Publie sur `user_notifications:{user_id}` |

### Format FCM

```python
title = f"{localized_title}: {action.title}"
# Exemples: "Action planifiee: Meteo du jour" (fr)
#           "Scheduled Action: Daily Weather" (en)
body = response_content[:150]  # Tronque a 150 caracteres
data = {"type": "scheduled_action", "action_id": str(action_id)}
```

Les titres sont localises dans les 6 langues supportees (fr, en, es, de, it, zh) via la fonction `_get_localized_title()` dans l'executor.

### Format SSE

```json
{
    "type": "scheduled_action",
    "content": "...",
    "action_id": "550e8400-...",
    "title": "Meteo du jour"
}
```

Le contenu SSE est tronque a 500 caracteres.

### Gestion des erreurs de notification

Les erreurs FCM et SSE sont loguees mais ne bloquent pas l'execution. L'action est marquee comme reussie meme si la notification echoue. Le resultat reste accessible dans l'archive de conversation.

---

## 9. Comparaison Reminders vs Scheduled Actions vs Heartbeat

| Critere | Reminders | Scheduled Actions | Heartbeat |
|---------|-----------|-------------------|-----------|
| **Declencheur** | Date/heure fixe (one-shot) | Recurrence jour/heure (cron) | Decision LLM periodique |
| **Creation** | Langage naturel ("rappelle-moi...") | UI Settings (formulaire CRUD) | Automatique (scheduler) |
| **Persistence** | Supprime apres execution | Persiste, recalcule `next_trigger_at` | Pas de persistence action |
| **Contenu** | Message personnalise par LLM | Resultat du pipeline d'agents | Notification proactive contextuelle |
| **HITL** | N/A | Bypass plan approval, guard HITL | N/A |
| **Feature flag** | `FCM_NOTIFICATIONS_ENABLED` | `SCHEDULED_ACTIONS_ENABLED` | `HEARTBEAT_ENABLED` |
| **Retry** | 3 tentatives, DELETE apres echec | 2 tentatives, auto-disable apres 5 echecs | Pas de retry |
| **Timezone** | Conversion locale -> UTC au create | Calcul CronTrigger avec timezone | Plage horaire configurable |
| **Notification** | FCM + SSE + archive | FCM + SSE + archive | FCM + SSE + Telegram + archive |
| **Scheduler** | `reminder_notification` (60s) | `scheduled_action_executor` (60s) | `heartbeat_notification` (configurable) |
| **Donnees** | Table `reminders` | Table `scheduled_actions` | Table `heartbeat_notifications` |
| **Use case** | "Rappelle-moi dans 2h" | "Tous les matins a 8h, donne-moi la meteo" | "Il va pleuvoir cet apres-midi" |

---

## 10. Testing

### Fichiers de tests existants

| Fichier | Couverture |
|---------|-----------|
| `tests/unit/domains/scheduled_actions/test_schedule_helpers.py` | 27 tests : `compute_next_trigger_utc` (incl. validation UTC), `validate_days`, `format_display` |
| `tests/unit/domains/scheduled_actions/test_schemas.py` | 18 tests : validation `Create`/`Update` schemas |

### Lancer les tests

```bash
# Depuis la racine du projet
task test:backend:unit:fast

# Ou directement les tests du domaine
cd apps/api
.venv/Scripts/pytest tests/unit/domains/scheduled_actions/ -v
```

### Ecrire un test pour `compute_next_trigger_utc`

```python
from datetime import UTC, datetime
from src.domains.scheduled_actions.schedule_helpers import compute_next_trigger_utc

def test_next_trigger_weekday_in_user_timezone():
    """Verifie que le calcul respecte la timezone utilisateur."""
    # Lundi a 08:00 Europe/Paris
    result = compute_next_trigger_utc(
        days_of_week=[1],  # Lundi
        hour=8,
        minute=0,
        user_timezone="Europe/Paris",
    )
    # Le resultat doit etre en UTC
    assert result.tzinfo is not None
    # Paris est UTC+1 en hiver, UTC+2 en ete
    # 08:00 Paris = 07:00 UTC (hiver) ou 06:00 UTC (ete)
    assert result.hour in (6, 7)
```

### Ecrire un test pour les schemas

```python
import pytest
from src.domains.scheduled_actions.schemas import ScheduledActionCreate

def test_create_schema_rejects_invalid_day():
    """Les jours doivent etre entre 1 et 7."""
    with pytest.raises(ValueError, match="Invalid day"):
        ScheduledActionCreate(
            title="Test",
            action_prompt="test prompt",
            days_of_week=[0, 8],  # Invalide
            trigger_hour=8,
            trigger_minute=0,
        )

def test_create_schema_rejects_duplicate_days():
    """Les doublons dans days_of_week sont interdits."""
    with pytest.raises(ValueError, match="Duplicate"):
        ScheduledActionCreate(
            title="Test",
            action_prompt="test prompt",
            days_of_week=[1, 1, 3],
            trigger_hour=8,
            trigger_minute=0,
        )
```

### Tester l'execution manuellement

L'endpoint `POST /scheduled-actions/{id}/execute` permet de declencher une action immediatement sans attendre le scheduler. C'est la methode recommandee pour tester en developpement.

```bash
# Via curl (avec cookie de session)
curl -X POST http://localhost:8000/api/v1/scheduled-actions/{action_id}/execute \
  -H "Cookie: session=..." \
  -v
# Reponse: 202 Accepted {"status": "executing"}
```

Le resultat apparaitra dans la conversation SSE et/ou en notification push.

---

## 11. Troubleshooting

### Les actions ne se declenchent pas

1. **Verifier que le scheduler tourne** :
   ```bash
   docker logs api 2>&1 | grep "scheduled_action_executor_job_scheduled"
   ```

2. **Verifier les actions dues en base** :
   ```sql
   SELECT id, title, status, is_enabled, next_trigger_at, consecutive_failures
   FROM scheduled_actions
   WHERE is_enabled = true AND status = 'active'
   ORDER BY next_trigger_at;
   ```

3. **Verifier les logs du job** :
   ```bash
   docker logs api 2>&1 | grep "scheduled_action"
   ```

4. **Verifier le lock Redis** : si un autre worker detient le lock, le job sera skip.
   ```bash
   task shell:redis
   > KEYS scheduler_lock:*
   ```

### L'action est en statut `executing` depuis longtemps

C'est un signe de crash pendant l'execution. Le mecanisme `recover_stale_executing` remettra l'action en `active` apres 10 minutes. Pour forcer la recovery :

```sql
UPDATE scheduled_actions
SET status = 'active'
WHERE status = 'executing'
  AND updated_at < NOW() - INTERVAL '10 minutes';
```

### L'action est auto-desactivee (`status = 'error'`)

Verifier la cause :

```sql
SELECT id, title, consecutive_failures, last_error
FROM scheduled_actions
WHERE status = 'error';
```

Pour reactiver, utiliser l'endpoint toggle ou directement en SQL :

```sql
UPDATE scheduled_actions
SET is_enabled = true,
    status = 'active',
    consecutive_failures = 0,
    last_error = NULL,
    next_trigger_at = NOW()  -- Sera recalcule proprement via l'API
WHERE id = '<action_id>';
```

La methode recommandee est d'utiliser l'endpoint `PATCH /scheduled-actions/{id}/toggle` qui recalcule correctement `next_trigger_at`.

### L'action est skip a cause du HITL

Le log `scheduled_action_skipped_hitl_pending` indique qu'un interrupt HITL est en attente sur la conversation de l'utilisateur. L'action sera replanifiee au prochain cycle.

Pour debloquer : repondre a l'interrupt HITL dans le chat, ou resumer le graphe LangGraph.

### Pas de notification FCM

1. Verifier `FCM_NOTIFICATIONS_ENABLED=true` dans `.env`
2. Verifier que l'utilisateur a des tokens FCM actifs :
   ```sql
   SELECT * FROM user_fcm_tokens WHERE user_id = '...' AND is_active = true;
   ```
3. Verifier les logs FCM :
   ```bash
   docker logs api 2>&1 | grep "scheduled_action_fcm_failed"
   ```

### Decalage horaire dans le declenchement

Verifier la timezone de l'utilisateur et le calcul :

```sql
SELECT id, title, trigger_hour, trigger_minute, user_timezone, next_trigger_at
FROM scheduled_actions
WHERE user_id = '...';
```

Si `user_timezone` est incorrecte apres un changement de timezone, relancer le recalcul via la mise a jour du profil utilisateur.

### Metriques Prometheus

Pour monitorer la sante du job en production :

- `background_job_duration_seconds{job_name="scheduled_action_executor"}` : duree du job
- `background_job_errors_total{job_name="scheduled_action_executor"}` : compteur d'erreurs

---

## Documentation associee

- [SCHEDULED_ACTIONS.md](../technical/SCHEDULED_ACTIONS.md) - Documentation technique de reference
- [README_REMINDERS.md](../readme/README_REMINDERS.md) - Systeme de rappels (Reminders)
- [HEARTBEAT_AUTONOME.md](../technical/HEARTBEAT_AUTONOME.md) - Heartbeat autonome
- [GUIDE_DEBUGGING.md](GUIDE_DEBUGGING.md) - Guide de debugging general
- [GUIDE_TESTING.md](GUIDE_TESTING.md) - Guide de testing general
