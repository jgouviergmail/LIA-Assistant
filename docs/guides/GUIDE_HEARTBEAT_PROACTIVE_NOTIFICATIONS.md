# Guide Pratique : Heartbeat et Notifications Proactives

**Version** : 1.0
**Date** : 2026-03-08
**Audience** : Developpeurs backend LIA

---

## Table des matieres

1. [Introduction](#1-introduction)
2. [Architecture](#2-architecture)
3. [Configuration](#3-configuration)
4. [Creer un nouveau type de notification proactive](#4-creer-un-nouveau-type-de-notification-proactive)
5. [ContextAggregator](#5-contextaggregator)
6. [Weather Change Detection](#6-weather-change-detection)
7. [NotificationDispatcher](#7-notificationdispatcher)
8. [EligibilityChecker](#8-eligibilitychecker)
9. [Token Tracking](#9-token-tracking)
10. [Testing](#10-testing)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Introduction

### Qu'est-ce que le Heartbeat Autonome ?

Le Heartbeat Autonome (Feature F5 du roadmap evolution) permet au LLM de contacter proactivement les utilisateurs avec des informations pertinentes, **sans attendre de requete utilisateur**. C'est un systeme LLM-driven qui :

1. **Agregue du contexte** depuis 8+ sources (calendrier, meteo, taches, centres d'interet, memories, activite, historique notifications)
2. **Laisse le LLM decider** s'il y a quelque chose d'utile a communiquer (structured output)
3. **Genere un message personnalise** avec la personnalite et la langue de l'utilisateur

Le nom cote utilisateur est **"Notifications proactives"** dans l'UI et les push notifications.

### Positionnement dans l'infrastructure

Le Heartbeat reutilise l'infrastructure generique de notifications proactives (`infrastructure/proactive/`) qui sert aussi aux notifications de centres d'interet. Cette infrastructure fournit :

- `ProactiveTask` Protocol : contrat que chaque type de notification implemente
- `ProactiveTaskRunner` : orchestrateur generique (batch processing, eligibility, dispatch, token tracking)
- `EligibilityChecker` : verification d'eligibilite (time window, quota, cooldown, cross-type dedup)
- `NotificationDispatcher` : envoi multi-canal (archive DB + SSE + FCM + Telegram)
- `track_proactive_tokens()` : suivi des tokens et couts

---

## 2. Architecture

### Vue d'ensemble : 2 phases LLM

```
APScheduler (30 min, configurable)
      |
      v (pour chaque utilisateur opt-in)
+----------------------------+
| EligibilityChecker         |  <-- Infrastructure generique (reutilisee)
| (heartbeat_enabled,        |
|  plage horaire dediee,     |
|  quota, cooldown, activite)|
+------------+---------------+
             v (si eligible)
+----------------------------+
| HeartbeatProactiveTask     |  <-- Implemente ProactiveTask Protocol
|  select_target() ->        |
|    1. ContextAggregator    |  <-- Fetch parallele (asyncio.gather)
|       [Calendar, Weather,  |
|        Tasks, Interests,   |
|        Memories, Activity, |
|        Time]               |
|    2. LLM Decision         |  <-- Structured output (gpt-4.1-mini)
|       -> skip | notify     |
|  generate_content() ->     |
|    LLM Message             |  <-- Personality + message_draft
+------------+---------------+
             v (si action="notify")
+----------------------------+
| NotificationDispatcher     |  <-- Infrastructure generique
| Archive + SSE (toujours)   |
| FCM + Telegram             |  <-- Seulement si heartbeat_push_enabled
+----------------------------+
```

### Phase 1 : Decision (structured output)

- **Modele** : `gpt-4.1-mini` (pas cher, rapide)
- **Temperature** : 0.3 (deterministe)
- **Output** : `HeartbeatDecision` (Pydantic BaseModel)
- Inclut les heartbeats recents + notifications d'interets pour eviter la redondance

```python
class HeartbeatDecision(BaseModel):
    action: Literal["skip", "notify"]
    reason: str
    message_draft: str | None  # Requis quand action="notify"
    priority: Literal["low", "medium", "high"]
    sources_used: list[str]
```

### Phase 2 : Generation du message (si `action="notify"`)

- **Modele** : `gpt-4.1-mini`
- **Temperature** : 0.7 (creatif)
- Reecrit le `message_draft` avec la personnalite et la langue de l'utilisateur
- Output : 2-4 phrases, ton naturel

### ProactiveTask Protocol

Tout type de notification proactive implemente ce Protocol (`infrastructure/proactive/base.py`) :

```python
class ProactiveTask(Protocol):
    task_type: str

    async def check_eligibility(
        self, user_id: UUID, user_settings: dict[str, Any], now: datetime
    ) -> bool: ...

    async def select_target(self, user_id: UUID) -> Any | None: ...

    async def generate_content(
        self, user_id: UUID, target: Any, user_language: str
    ) -> ProactiveTaskResult: ...

    async def on_feedback(
        self, user_id: UUID, target: Any, feedback: str
    ) -> None: ...

    async def on_notification_sent(
        self, user_id: UUID, target: Any, result: ProactiveTaskResult
    ) -> None: ...
```

**Point cle de design** : la decision LLM est dans `select_target()` (pas `generate_content()`), de sorte qu'un "skip" mappe correctement vers `no_target` dans le runner et non `content_failed`.

### Flux de donnees dans le runner

Le `ProactiveTaskRunner._process_user()` orchestre le pipeline complet pour chaque utilisateur :

1. **Eligibility checks communs** via `EligibilityChecker.check()`
2. **Check probabiliste** via `should_send_notification()` (garantie de min_per_day)
3. **Eligibilite task-specifique** via `task.check_eligibility()`
4. **Selection de target** via `task.select_target()` (inclut decision LLM pour heartbeat)
5. **Generation de contenu** via `task.generate_content()`
6. **Pre-generation de run_id** et calcul de cout pour injection dans metadata
7. **Dispatch notification** via `NotificationDispatcher.dispatch()`
8. **Token tracking** via `track_proactive_tokens()`
9. **Hook post-notification** via `task.on_notification_sent()`

---

## 3. Configuration

### Feature Flags

| Flag | Scope | Default |
|------|-------|---------|
| `HEARTBEAT_ENABLED` | Global : scheduler job + router | `false` |
| Per-user : `heartbeat_enabled` | Opt-in par utilisateur | `false` |

Le scheduler job ne s'enregistre que si `HEARTBEAT_ENABLED=true`. Le router API ne s'enregistre que si `HEARTBEAT_ENABLED=true`.

### Variables d'environnement (.env)

| Setting | Default | Description |
|---------|---------|-------------|
| `HEARTBEAT_ENABLED` | `false` | Feature flag global |
| `HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES` | `30` | Intervalle du scheduler (10-120) |
| `HEARTBEAT_NOTIFICATION_BATCH_SIZE` | `50` | Utilisateurs par batch |
| `HEARTBEAT_GLOBAL_COOLDOWN_HOURS` | `2` | Min heures entre notifications |
| `HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES` | `15` | Skip si utilisateur actif recemment |
| `HEARTBEAT_DECISION_LLM_PROVIDER` | `openai` | Provider LLM pour la decision |
| `HEARTBEAT_DECISION_LLM_MODEL` | `gpt-4.1-mini` | Modele LLM pour la decision |
| `HEARTBEAT_MESSAGE_LLM_PROVIDER` | `openai` | Provider LLM pour le message |
| `HEARTBEAT_MESSAGE_LLM_MODEL` | `gpt-4.1-mini` | Modele LLM pour le message |
| `HEARTBEAT_CONTEXT_CALENDAR_HOURS` | `6` | Heures devant pour calendrier |
| `HEARTBEAT_CONTEXT_MEMORY_LIMIT` | `5` | Max memories a fetcher |
| `HEARTBEAT_CONTEXT_TASKS_DAYS` | `2` | Jours devant pour taches (1-7) |
| `HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH` | `0.6` | pop au-dessus = pluie probable |
| `HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW` | `0.3` | pop en-dessous = eclaircie |
| `HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD` | `5.0` | Changement en degres C a signaler |
| `HEARTBEAT_WEATHER_WIND_THRESHOLD` | `14.0` | m/s pour alerte vent |
| `HEARTBEAT_INACTIVE_SKIP_DAYS` | `7` | Skip si utilisateur inactif > N jours |
| `PROACTIVE_CROSS_TYPE_COOLDOWN_MINUTES` | `30` | Min minutes entre types differents |

### Reglages utilisateur (colonnes User)

| Champ | Type | Default | Description |
|-------|------|---------|-------------|
| `heartbeat_enabled` | bool | `false` | Activer les notifications proactives |
| `heartbeat_max_per_day` | int | `3` | Max notifications par jour (1-8) |
| `heartbeat_push_enabled` | bool | `true` | Activer push FCM/Telegram (sinon archive silencieuse) |
| `heartbeat_notify_start_hour` | int | `9` | Heure de debut de la fenetre (0-23) |
| `heartbeat_notify_end_hour` | int | `22` | Heure de fin de la fenetre (0-23) |

### Plages horaires

Le heartbeat utilise une **plage horaire dediee et independante** des notifications d'interets. Les champs `heartbeat_notify_start_hour` / `heartbeat_notify_end_hour` sont distincts de `interests_notify_start_hour` / `interests_notify_end_hour`.

L'`EligibilityChecker` gere les fenetres de nuit (ex: 22h-9h) avec la logique :

```python
if start_hour <= end_hour:
    in_window = start_hour <= current_hour < end_hour
else:
    # Fenetre overnight : ex 22-9
    in_window = current_hour >= start_hour or current_hour < end_hour
```

---

## 4. Creer un nouveau type de notification proactive

Pour ajouter un nouveau type (ex: `birthday`, `event_reminder`), suivre ces 3 etapes :

### Etape 1 : Implementer le ProactiveTask Protocol

Creer le fichier `domains/<votre_domaine>/proactive_task.py` :

```python
from src.infrastructure.proactive.base import ContentSource, ProactiveTaskResult

class MonNouveauProactiveTask:
    """Implemente le ProactiveTask Protocol."""

    task_type: str = "mon_type"  # Identifiant unique

    async def check_eligibility(
        self, user_id: UUID, user_settings: dict[str, Any], now: datetime
    ) -> bool:
        """Verification specifique au type de task.
        Les checks communs (time window, quota, cooldown) sont geres
        par EligibilityChecker AVANT cet appel.
        """
        return bool(user_settings.get("mon_type_enabled", False))

    async def select_target(self, user_id: UUID) -> MonTarget | None:
        """Selectionner la cible de notification.
        Retourner None si pas de cible => le runner enregistre "no_target".
        """
        # Logique metier...
        return target_or_none

    async def generate_content(
        self, user_id: UUID, target: MonTarget, user_language: str
    ) -> ProactiveTaskResult:
        """Generer le contenu de la notification."""
        # Appel LLM, etc.
        return ProactiveTaskResult(
            success=True,
            content="Votre message...",
            source=ContentSource.CUSTOM,
            target_id=str(target.id),
            tokens_in=tok_in,
            tokens_out=tok_out,
            model_name="gpt-4.1-mini",
        )

    async def on_feedback(self, user_id: UUID, target: Any, feedback: str) -> None:
        """Gerer le feedback utilisateur (optionnel)."""
        pass

    async def on_notification_sent(
        self, user_id: UUID, target: Any, result: ProactiveTaskResult
    ) -> None:
        """Hook post-envoi : audit trail, mise a jour stats, etc."""
        # Ex: creer un enregistrement dans la table d'audit
        pass
```

### Etape 2 : Creer la configuration EligibilityChecker

Dans `infrastructure/scheduler/mon_type_notification.py` :

```python
from src.infrastructure.proactive.eligibility import EligibilityChecker
from src.infrastructure.proactive.runner import execute_proactive_task

def _create_mon_type_eligibility_checker() -> EligibilityChecker:
    return EligibilityChecker(
        task_type="mon_type",
        enabled_field="mon_type_enabled",            # Champ User model
        start_hour_field="mon_type_notify_start_hour",
        end_hour_field="mon_type_notify_end_hour",
        min_per_day_field="mon_type_min_per_day",
        max_per_day_field="mon_type_max_per_day",
        notification_model=MonTypeNotification,       # Modele SQLAlchemy
        global_cooldown_hours=2,
        activity_cooldown_minutes=15,
        interval_minutes=30,
        # Cross-type dedup : eviter rafale avec heartbeat et interets
        cross_type_models=[HeartbeatNotification, InterestNotification],
        cross_type_cooldown_minutes=30,
    )

async def process_mon_type_notifications() -> dict[str, Any]:
    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_MON_TYPE) as lock:
        if not lock.acquired:
            return {"status": "skipped", "reason": "lock_busy"}

        task = MonNouveauProactiveTask()
        checker = _create_mon_type_eligibility_checker()
        stats = await execute_proactive_task(task=task, eligibility_checker=checker)
        return stats.to_dict()
```

### Etape 3 : Enregistrer le job scheduler

Dans `main.py`, ajouter le job dans le lifespan (conditionne par un feature flag) :

```python
if getattr(settings, "mon_type_enabled", False):
    scheduler.add_job(
        process_mon_type_notifications,
        trigger="interval",
        minutes=settings.mon_type_interval_minutes,
        id=SCHEDULER_JOB_MON_TYPE,
        max_instances=1,
        replace_existing=True,
    )
```

### Checklist complementaire

- [ ] Ajouter les colonnes utilisateur (migration Alembic)
- [ ] Ajouter le modele de notification (table d'audit)
- [ ] Ajouter la constante `SCHEDULER_JOB_*` dans `core/constants.py`
- [ ] Ajouter les settings dans `core/config/agents.py`
- [ ] Ajouter les champs dans `ProactiveTaskRunner._extract_user_settings()`
- [ ] Ajouter le `ContentSource` dans `infrastructure/proactive/base.py`
- [ ] Ajouter les titres localises dans `NotificationDispatcher._get_localized_title()`
- [ ] Ajouter le cross-type dans les checkers existants (symetrique)
- [ ] Conditionner le router API par un feature flag dans `api/v1/routes.py`
- [ ] Ecrire les tests unitaires

---

## 5. ContextAggregator

Le `ContextAggregator` (`domains/heartbeat/context_aggregator.py`) fetche 8 sources de contexte en parallele via `asyncio.gather(return_exceptions=True)`.

### Fonctionnement

```python
results = await asyncio.gather(
    self._fetch_calendar(user_id, user, settings),
    self._fetch_tasks(user_id, user, settings),
    self._fetch_weather_with_changes(user_id, user, settings),
    self._fetch_interests(user_id),
    self._fetch_memories(user_id, settings),
    self._fetch_activity(user_id),
    self._fetch_recent_heartbeats(user_id),
    self._fetch_recent_interest_notifications(user_id),
    return_exceptions=True,
)
```

**Points cles** :

- **`return_exceptions=True`** : une source en echec ne bloque pas les autres. Les exceptions sont retournees comme valeurs dans le tableau de resultats.
- **Ordering stable** : les resultats sont mappes par index avec un tableau `source_names` et `zip(..., strict=True)`.
- **Chaque source est independamment failable** : si le calendrier n'est pas connecte, la meteo est quand meme fetchee.
- **Le contexte temporel** (`_compute_time_context`) est calcule de maniere synchrone avant le gather (pas d'I/O, ne peut pas echouer).

### Sources de contexte

| Source | Methode | Dependance | Fallback |
|--------|---------|------------|----------|
| Calendar | Google/Apple/Microsoft Calendar API | Connector actif | `None` |
| Weather + Changes | OpenWeatherMap API | Connector + home_location | `None` |
| Tasks | Google Tasks / Microsoft To Do API | Connector actif | `None` |
| Interests | `InterestRepository` | Centres d'interet actifs | `None` |
| Memories | LangGraph Store | `memory_enabled` | `None` |
| Activity | Query dernier message | Toujours disponible | `None` |
| Recent heartbeats | Table `heartbeat_notifications` | Toujours disponible | `[]` |
| Recent interest notifs | `InterestNotification` JOIN | Toujours disponible | `[]` |
| Time | Calcul depuis timezone | Toujours disponible | Toujours OK |

### HeartbeatContext

Le dataclass `HeartbeatContext` agregue toutes les sources avec un helper `has_meaningful_context()` qui verifie qu'au moins une source a retourne des donnees utiles :

```python
def has_meaningful_context(self) -> bool:
    return any((
        self.calendar_events,
        self.pending_tasks,
        self.weather_current,
        self.weather_changes,
        self.trending_interests,
        self.user_memories,
    ))
```

Si aucun contexte significatif n'est disponible, le heartbeat est skip avant meme l'appel LLM (economie de tokens).

### Serialisation pour le prompt LLM

`context.to_prompt_context()` genere un bloc texte structure pour le LLM, n'incluant que les sections avec des donnees. Les heures de calendrier et de taches sont converties dans le fuseau horaire de l'utilisateur avant serialisation (voir `_format_event_time()` et `_extract_due_date()` dans `context_aggregator.py`) :

```
TIME: Monday, 14:30 (afternoon)

UPCOMING CALENDAR EVENTS (times in user's local timezone):
  - Team standup (15:00 → 15:30)

CURRENT WEATHER: light rain, 12°C, wind 5 m/s

WEATHER CHANGES DETECTED:
  - [INFO] Rain clearing around 17:00

PENDING TASKS:
  - Buy groceries (due: 2026-03-08)

LAST INTERACTION: 3.5 hours ago
```

---

## 6. Weather Change Detection

Le systeme detecte 4 types de changements meteorologiques dans `ContextAggregator._detect_weather_changes()` :

### Types de changements

| Type | Condition | Severity |
|------|-----------|----------|
| `rain_start` | Pas de pluie actuellement + `pop > rain_threshold_high` dans le forecast | `warning` |
| `rain_end` | Pluie actuellement + `pop < rain_threshold_low` dans le forecast | `info` |
| `temp_drop` | Temperature baisse > `temp_change_threshold` degres C | `info` ou `warning` (si > 1.6x seuil) |
| `wind_alert` | Vitesse du vent > `wind_threshold` m/s dans le forecast | `warning` |

### Algorithme

1. L'API meteo actuelle (`/data/2.5/weather`) ne retourne **pas** de `pop`. On utilise `weather[0].main` (ex: "Rain", "Clear") pour l'etat actuel.
2. L'API forecast retourne des entrees a 3 heures d'intervalle avec `pop` (probability of precipitation).
3. Chaque type de changement est detecte **au plus une fois** grace a un `set` de dedup (`detected_types`).

```python
# Extrait de _detect_weather_changes()
detected_types: set[str] = set()

for entry in hourly:
    entry_pop = entry.get("pop", 0)

    # Rain start: pas de pluie + pop eleve dans le forecast
    if (
        not is_currently_raining
        and entry_pop > rain_high
        and "rain_start" not in detected_types
    ):
        changes.append(WeatherChange(
            change_type="rain_start",
            expected_at=entry_time,
            description=f"Rain expected around {time_str}",
            severity="warning",
        ))
        detected_types.add("rain_start")
        is_currently_raining = True  # Mise a jour de l'etat
```

### Seuils configurables

- `HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH` (default: 0.6) : pop au-dessus duquel on considere qu'il va pleuvoir
- `HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW` (default: 0.3) : pop en-dessous duquel on considere que la pluie s'arrete
- `HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD` (default: 5.0) : changement de temperature minimum en degres C
- `HEARTBEAT_WEATHER_WIND_THRESHOLD` (default: 14.0) : vitesse du vent en m/s pour une alerte

---

## 7. NotificationDispatcher

Le `NotificationDispatcher` (`infrastructure/proactive/notification.py`) gere l'envoi multi-canal avec un **ordre critique** pour eviter les race conditions.

### Canaux de livraison

| Canal | Condition | Quand `push_enabled=False` |
|-------|-----------|---------------------------|
| **Archive DB** | Toujours | Toujours envoye |
| **SSE** (Redis Pub/Sub) | Toujours | Toujours envoye |
| **FCM Push** | Si tokens enregistres | **Skip** |
| **Telegram** | Si binding actif + `CHANNELS_ENABLED` | **Skip** |

### Ordre d'operations (race condition prevention)

```
1. Archive message en conversation (DB)
2. COMMIT la transaction  <-- CRITIQUE : message visible en DB AVANT notification push
3. FCM Push (si push_enabled)
4. SSE via Redis Pub/Sub
5. Channels externes : Telegram (si push_enabled)
```

**Pourquoi le commit avant le push ?** Si l'utilisateur recoit la notification FCM et ouvre l'app avant que le message soit commite, il ne verrait pas le message dans l'historique.

### Parametre `push_enabled`

Le runner resout `push_enabled` par convention depuis le modele utilisateur :

```python
# Dans ProactiveTaskRunner._process_user()
push_enabled = getattr(user, f"{self.task.task_type}_push_enabled", True)
```

Pour le heartbeat, cela lit `user.heartbeat_push_enabled`. Quand `False`, seuls archive + SSE sont utilises (mode "silencieux").

### Titres localises

Le dispatcher genere des titres localises en 6 langues pour chaque type de task :

```python
"heartbeat": {
    "fr": "Notification proactive",
    "en": "Proactive notification",
    "es": "Notificacion proactiva",
    "de": "Proaktive Benachrichtigung",
    "it": "Notifica proattiva",
    "zh": "主动通知",
}
```

Pour un nouveau type, ajouter l'entree dans `NotificationDispatcher._get_localized_title()`.

---

## 8. EligibilityChecker

L'`EligibilityChecker` (`infrastructure/proactive/eligibility.py`) effectue des verifications generiques dans un ordre precis. Il est configure avec des noms de champs du modele User (strategy pattern via `getattr()`).

### Ordre des verifications

1. **Feature enabled** : `getattr(user, enabled_field, False)`
2. **Time window** : heure courante dans la fenetre de notification (timezone utilisateur)
3. **Quota journalier** : `COUNT(notifications WHERE created_at >= today_start)`
4. **Global cooldown** : temps depuis la derniere notification du **meme type**
5. **Cross-type cooldown** : temps depuis la derniere notification d'un **type different** (heartbeat <-> interests)
6. **Activity cooldown** : ne pas interrompre un utilisateur actif

### Cross-type dedup (heartbeat <-> interets)

Pour eviter les rafales de notifications, chaque checker declare les modeles des **autres types** :

```python
# Dans heartbeat_notification.py
EligibilityChecker(
    ...
    cross_type_models=[InterestNotification],  # Verifie les notifs d'interets
    cross_type_cooldown_minutes=settings.proactive_cross_type_cooldown_minutes,
)

# Dans interest_notification.py (symetrique)
EligibilityChecker(
    ...
    cross_type_models=[HeartbeatNotification],  # Verifie les heartbeats
    cross_type_cooldown_minutes=settings.proactive_cross_type_cooldown_minutes,
)
```

La verification est symetrique : si un heartbeat a ete envoye il y a 10 minutes et que le cooldown cross-type est de 30 minutes, la notification d'interet sera rejetee avec la raison `CROSS_TYPE_COOLDOWN`.

### Algorithme probabiliste (`should_send_notification`)

L'`EligibilityChecker.should_send_notification()` utilise un algorithme time-aware pour distribuer les notifications dans la fenetre :

1. **Quota atteint** : si `today_count >= max_per_day` -> `False`
2. **Guarantee zone** : dans les derniers 20% de la fenetre, si en-dessous de `min_per_day` -> `True` (force l'envoi)
3. **Probabilite adaptive** : basee sur le temps restant et les notifications restantes a envoyer
4. **Deficit boost** : si en retard par rapport au nombre attendu -> boost jusqu'a 2x

```python
# Probabilite de base
probability = remaining_target / remaining_checks

# Boost si en retard
expected_by_now = target_per_day * time_fraction
if today_count < expected_by_now:
    deficit_ratio = (expected_by_now - today_count) / expected_by_now
    probability *= 1.0 + deficit_ratio
```

### EligibilityReason enum

```python
class EligibilityReason(str, Enum):
    ELIGIBLE = "eligible"
    FEATURE_DISABLED = "feature_disabled"
    OUTSIDE_TIME_WINDOW = "outside_time_window"
    QUOTA_EXCEEDED = "quota_exceeded"
    GLOBAL_COOLDOWN = "global_cooldown"
    CROSS_TYPE_COOLDOWN = "cross_type_cooldown"
    ACTIVITY_COOLDOWN = "activity_cooldown"
    TASK_SPECIFIC = "task_specific"
    NO_TARGET = "no_target"
```

---

## 9. Token Tracking

Le suivi des tokens est critique pour la visibilite des couts et les statistiques utilisateur.

### `_TokenCaptureHandler` : capturer les tokens du structured output

Le `get_structured_output()` retourne uniquement le modele Pydantic, pas le `AIMessage` avec `usage_metadata`. Un callback LangChain capture les tokens :

```python
class _TokenCaptureHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        super().__init__()
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.tokens_cache: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generation_list in response.generations:
            for gen in generation_list:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                meta = getattr(msg, "usage_metadata", None)
                if meta:
                    self.tokens_in += meta.get("input_tokens", 0)
                    self.tokens_out += meta.get("output_tokens", 0)
                    self.tokens_cache += meta.get("cache_read_input_tokens", 0)
```

Utilisation dans la phase de decision :

```python
token_capture = _TokenCaptureHandler()
runnable_config = RunnableConfig(callbacks=[token_capture])

decision = await get_structured_output(
    llm=llm, messages=messages, schema=HeartbeatDecision,
    provider=provider, node_name="heartbeat_decision", config=runnable_config,
)

tokens_in = token_capture.tokens_in
tokens_out = token_capture.tokens_out
```

### Tracking des decisions "skip"

Quand le LLM decide de ne pas notifier (`action="skip"`), les tokens sont quand meme trackes via `_track_skip_tokens()`. Sans cela, les couts des decisions "skip" seraient silencieusement perdus.

```python
# Dans HeartbeatProactiveTask.select_target()
if decision.action == "skip":
    await self._track_skip_tokens(user_id, tok_in, tok_out, tok_cache)
    return None  # Pas de notification
```

`_track_skip_tokens()` appelle directement `track_proactive_tokens()` avec un target_id prefixe `heartbeat_skip_`.

### Aggregation multi-phase

Les tokens des 2 phases (decision + message) sont agreges dans `generate_content()` :

```python
# Dans HeartbeatProactiveTask.generate_content()
total_in = target.decision_tokens_in + msg_tok_in
total_out = target.decision_tokens_out + msg_tok_out
total_cache = target.decision_tokens_cache + msg_tok_cache
```

### Pre-generation du run_id

Le runner pre-genere le `run_id` et l'injecte dans les metadata **avant** le dispatch, pour que le message archive contienne deja le `run_id`. Cela permet le LEFT JOIN dans `get_messages_with_token_summaries()` au chargement de l'historique :

```python
# Dans ProactiveTaskRunner._process_user()
run_id = generate_proactive_run_id(self.task.task_type, target_id_for_tracking)

result.metadata.update({
    "run_id": run_id,
    "tokens_in": result.tokens_in,
    "tokens_out": result.tokens_out,
    "tokens_cache": result.tokens_cache,
    "cost_eur": cost_eur,
    "model_name": result.model_name,
})
```

### `TokenAccumulator` pour les multi-call LLM

Si votre task fait plusieurs appels LLM, utiliser `TokenAccumulator` :

```python
from src.infrastructure.proactive.tracking import TokenAccumulator

accumulator = TokenAccumulator(model_name="gpt-4.1-mini")

result1 = await llm.invoke(prompt1)
accumulator.add_from_usage_metadata(result1.usage_metadata)

result2 = await llm.invoke(prompt2)
accumulator.add_from_usage_metadata(result2.usage_metadata)

total_in, total_out, total_cache = accumulator.get_totals()
```

---

## 10. Testing

### Tests existants

| Fichier | Nb tests | Couverture |
|---------|----------|------------|
| `tests/unit/domains/heartbeat/test_schemas.py` | 38 | Schemas, validation, serialisation |
| `tests/unit/domains/heartbeat/test_context_aggregator.py` | 52 | Sources, weather detection, timezone conversion, parallel fetch |
| `tests/unit/domains/heartbeat/test_proactive_task.py` | 17 | Protocol compliance, token capture |
| `tests/unit/infrastructure/proactive/test_eligibility.py` | 7 | Time window, quota, cooldowns |

### Comment executer les tests

```bash
# Tous les tests heartbeat
cd apps/api
.venv/Scripts/pytest tests/unit/domains/heartbeat/ -v

# Tests specifiques
.venv/Scripts/pytest tests/unit/domains/heartbeat/test_proactive_task.py -v

# Tests infrastructure proactive
.venv/Scripts/pytest tests/unit/infrastructure/proactive/ -v
```

### Patterns de test pour un ProactiveTask

**Tester la conformite au Protocol** :

```python
@pytest.mark.unit
class TestProtocolCompliance:
    def test_task_type(self):
        task = HeartbeatProactiveTask()
        assert task.task_type == "heartbeat"

    def test_has_required_methods(self):
        task = HeartbeatProactiveTask()
        assert callable(task.check_eligibility)
        assert callable(task.select_target)
        assert callable(task.generate_content)
        assert callable(task.on_feedback)
        assert callable(task.on_notification_sent)
```

**Tester check_eligibility** :

```python
@pytest.mark.asyncio
async def test_eligible_when_enabled(self):
    task = HeartbeatProactiveTask()
    result = await task.check_eligibility(
        user_id=uuid4(),
        user_settings={"heartbeat_enabled": True},
        now=datetime.now(UTC),
    )
    assert result is True
```

**Tester le weather change detection** (pas d'I/O, testable directement) :

```python
@pytest.mark.unit
class TestWeatherChangeDetection:
    def test_rain_start_detected(self):
        aggregator = ContextAggregator(MagicMock())
        settings = _make_settings()

        current = {"weather": [{"main": "Clear"}], "main": {"temp": 20}}
        hourly = [{"pop": 0.8, "dt": 1709910000, "main": {"temp": 18}, "wind": {"speed": 5}}]
        user_tz = ZoneInfo("UTC")

        changes = aggregator._detect_weather_changes(current, hourly, user_tz, settings)

        assert len(changes) == 1
        assert changes[0].change_type == "rain_start"
```

**Tester le `_TokenCaptureHandler`** :

```python
def test_token_capture():
    handler = _TokenCaptureHandler()
    msg = MagicMock()
    msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 20}
    gen = ChatGeneration(message=msg, text="")
    result = LLMResult(generations=[[gen]])

    handler.on_llm_end(result)

    assert handler.tokens_in == 100
    assert handler.tokens_out == 50
    assert handler.tokens_cache == 20
```

### Mocker les dependances externes

Pour les tests unitaires, mocker les clients externes :

```python
@pytest.fixture
def mock_db():
    return MagicMock(spec=AsyncSession)

@pytest.fixture
def mock_settings(monkeypatch):
    """Patcher get_settings() pour retourner un objet controle."""
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(
        heartbeat_context_calendar_hours=6,
        heartbeat_weather_rain_threshold_high=0.6,
        # ...
    )
    monkeypatch.setattr("src.core.config.get_settings", lambda: fake_settings)
    return fake_settings
```

---

## 11. Troubleshooting

### Probleme : les notifications ne sont pas envoyees

**Verifications** :
1. `HEARTBEAT_ENABLED=true` dans `.env` ?
2. L'utilisateur a `heartbeat_enabled=true` dans la DB ?
3. L'heure courante est dans la fenetre `[heartbeat_notify_start_hour, heartbeat_notify_end_hour]` (timezone de l'utilisateur) ?
4. Le quota journalier n'est pas atteint ? (`heartbeat_max_per_day`)
5. Le cooldown global n'est pas actif ? (`heartbeat_global_cooldown_hours`)
6. L'utilisateur n'est pas actif ? (`heartbeat_activity_cooldown_minutes`)
7. Le cross-type cooldown n'est pas actif ? (verifier les notifications d'interets recentes)

**Logs a chercher** :
- `heartbeat_notification_job_started` : le job scheduler a demarre
- `eligibility_*` : raison du skip (feature_disabled, outside_time_window, quota_exceeded, etc.)
- `heartbeat_skip_no_context` : aucune source de contexte n'a retourne de donnees
- `heartbeat_llm_skip` : le LLM a decide de ne pas notifier
- `proactive_probabilistic_decision` : le check probabiliste a decide de ne pas envoyer

### Probleme : les tokens ne sont pas comptes

**Verifications** :
1. Le `_TokenCaptureHandler` est bien passe dans le `RunnableConfig` ?
2. Pour les skips : `_track_skip_tokens()` est bien appele ?
3. Le `run_id` est pre-genere et injecte dans les metadata **avant** le dispatch ?

**Logs a chercher** :
- `proactive_tokens_tracked` : tokens enregistres avec succes
- `proactive_tokens_skip` : pas de tokens a tracker (0/0)
- `heartbeat_skip_token_tracking_failed` : erreur lors du tracking des tokens de skip

### Probleme : les push notifications ne sont pas recues

**Verifications** :
1. `heartbeat_push_enabled=true` sur l'utilisateur ?
2. Des tokens FCM sont enregistres pour l'utilisateur ?
3. Pour Telegram : `CHANNELS_ENABLED=true` et un binding actif existe ?

**Logs a chercher** :
- `proactive_notification_dispatched` : resume de tous les canaux (fcm_success, sse_sent, channel_sent)
- `proactive_fcm_failed` : erreur FCM
- `proactive_channels_failed` : erreur Telegram

### Probleme : trop de notifications

**Solutions** :
- Reduire `heartbeat_max_per_day` (cote utilisateur)
- Augmenter `HEARTBEAT_GLOBAL_COOLDOWN_HOURS`
- Augmenter `HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES`
- Augmenter `PROACTIVE_CROSS_TYPE_COOLDOWN_MINUTES`

### Probleme : contexte toujours vide

**Verifications** :
1. L'utilisateur a un connecteur Google Calendar actif ?
2. L'utilisateur a un connecteur OpenWeatherMap avec une `home_location` configuree ?
3. L'utilisateur a des centres d'interet actifs ?
4. Les memories sont activees (`memory_enabled`) ?

**Log** : `heartbeat_source_failed` avec le nom de la source et l'erreur.

### Base de donnees : tables et index

- Table `heartbeat_notifications` : audit trail immutable (sauf `user_feedback`)
- Index `ix_heartbeat_notifications_user_created` sur `(user_id, created_at)` pour les requetes de quota et historique

### Fichiers cles

| Fichier | Role |
|---------|------|
| `domains/heartbeat/proactive_task.py` | Implementation du ProactiveTask Protocol |
| `domains/heartbeat/context_aggregator.py` | Aggregation multi-source parallele |
| `domains/heartbeat/schemas.py` | HeartbeatDecision, HeartbeatContext, HeartbeatTarget |
| `domains/heartbeat/prompts.py` | Prompts LLM et `_TokenCaptureHandler` |
| `domains/heartbeat/models.py` | Modele SQLAlchemy HeartbeatNotification |
| `domains/heartbeat/repository.py` | CRUD et queries DB |
| `domains/heartbeat/router.py` | Endpoints API |
| `infrastructure/proactive/base.py` | ProactiveTask Protocol, ProactiveTaskResult |
| `infrastructure/proactive/eligibility.py` | EligibilityChecker generique |
| `infrastructure/proactive/runner.py` | ProactiveTaskRunner orchestrateur |
| `infrastructure/proactive/notification.py` | NotificationDispatcher multi-canal |
| `infrastructure/proactive/tracking.py` | Token tracking + TokenAccumulator |
| `infrastructure/scheduler/heartbeat_notification.py` | Job scheduler APScheduler |
| `core/config/agents.py` | Settings heartbeat dans AgentsSettings |
