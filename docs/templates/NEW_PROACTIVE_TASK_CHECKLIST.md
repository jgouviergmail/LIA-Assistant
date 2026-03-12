# Checklist: Creer une Nouvelle Notification Proactive

**Nom du Type de Notification**: _________________________
**Developpeur**: _________________________
**Date**: _________________________
**Temps estime**: 3-5h

---

## Concepts Cles

Le framework proactif de LIA repose sur le pattern `ProactiveTask` :

```
ProactiveTask.select_target() → EligibilityChecker → generate_content() → NotificationDispatcher → on_notification_sent()
```

Deux implementations existantes servent de reference :
- **Heartbeat** : `domains/heartbeat/proactive_task.py` — notifications autonomes LLM-driven
- **Interests** : `domains/interests/proactive_task.py` — notifications centres d'interet

---

## Phase 1: Definition du ProactiveTask (1-2h)

### 1.1 Creer le module

- [ ] **Creer le dossier du domaine** (si nouveau domaine) :
  ```
  apps/api/src/domains/{votre_domaine}/
  ├── __init__.py
  ├── proactive_task.py     # Implementation ProactiveTask
  ├── schemas.py             # Schemas Pydantic (decision, contenu)
  ├── models.py              # Modeles SQLAlchemy (audit trail)
  └── router.py              # Endpoints API (optionnel)
  ```

### 1.2 Implementer le Protocol ProactiveTask

- [ ] **Creer `proactive_task.py`** avec les 3 methodes obligatoires :

```python
from infrastructure.proactive.protocols import ProactiveTask

class VotreProactiveTask:
    """Implementation ProactiveTask pour {votre_type}."""

    async def select_target(self, db: AsyncSession) -> list[User]:
        """Selectionne les utilisateurs eligibles pour cette notification."""
        # Retourner les utilisateurs qui pourraient recevoir une notification
        # Filtrer par: feature active, preferences utilisateur, etc.
        ...

    async def generate_content(
        self, user: User, db: AsyncSession
    ) -> ProactiveContent | None:
        """Genere le contenu de la notification pour un utilisateur."""
        # Phase 1: Decision (devrait-on notifier ?)
        # Phase 2: Generation du message
        # Retourner None si pas de notification pertinente
        ...

    async def on_notification_sent(
        self, user: User, content: ProactiveContent, db: AsyncSession
    ) -> None:
        """Callback apres envoi reussi (audit trail, metriques)."""
        # Sauvegarder en DB pour historique
        # Incrementer metriques Prometheus
        ...
```

### 1.3 Definir les Schemas

- [ ] **Creer `schemas.py`** :

```python
from pydantic import BaseModel

class VotreDecision(BaseModel):
    """Decision LLM structuree (Phase 1)."""
    should_notify: bool
    reason: str
    priority: Literal["low", "medium", "high"]
    # ... champs specifiques

class VotreNotificationContent(BaseModel):
    """Contenu de la notification (Phase 2)."""
    title: str
    message: str
    # ... champs specifiques
```

---

## Phase 2: EligibilityChecker (30 min)

### 2.1 Configurer les regles d'eligibilite

- [ ] **Definir la configuration EligibilityChecker** :

```python
from infrastructure.proactive.eligibility import EligibilityCheckerConfig

votre_eligibility_config = EligibilityCheckerConfig(
    # Plage horaire
    start_hour_field="votre_notify_start_hour",  # Nom du champ User
    end_hour_field="votre_notify_end_hour",       # Nom du champ User

    # Quotas
    max_per_day=3,                                 # Max notifications/jour
    quota_redis_prefix="proactive:votre_type",     # Prefix Redis

    # Cooldowns
    cooldown_minutes=60,                           # Minimum entre 2 notifications
    cooldown_redis_key="proactive:votre_type:last",

    # Cross-type dedup (optionnel)
    cross_type_cooldown_minutes=30,                # Cooldown croise avec autres types
    cross_type_redis_keys=["proactive:heartbeat:last"],  # Autres types a verifier
)
```

### 2.2 Champs utilisateur

- [ ] **Ajouter les champs utilisateur** (si necessaire) :
  - Migration Alembic pour ajouter les colonnes au modele User :
    - `votre_push_enabled: bool = False`
    - `votre_notify_start_hour: int = 8`
    - `votre_notify_end_hour: int = 22`
    - `votre_max_per_day: int = 3`

---

## Phase 3: Job Scheduler (30 min)

### 3.1 Creer le job APScheduler

- [ ] **Ajouter le job dans `infrastructure/scheduler/`** :

```python
# infrastructure/scheduler/votre_notification.py
from infrastructure.proactive.task_runner import ProactiveTaskRunner
from domains.votre_domaine.proactive_task import VotreProactiveTask

async def run_votre_proactive_task():
    """Job APScheduler pour les notifications {votre_type}."""
    runner = ProactiveTaskRunner(
        task=VotreProactiveTask(),
        eligibility_config=votre_eligibility_config,
    )
    await runner.run()
```

### 3.2 Enregistrer le job

- [ ] **Ajouter dans `main.py` (lifespan)** :
  ```python
  scheduler.add_job(
      run_votre_proactive_task,
      trigger=IntervalTrigger(minutes=60),
      id="votre_proactive_task",
      name="Votre Proactive Task",
      replace_existing=True,
  )
  ```

### 3.3 Feature flag

- [ ] **Ajouter le feature flag** dans `.env` :
  ```bash
  VOTRE_TYPE_ENABLED=false
  ```

- [ ] **Conditionner l'enregistrement du job** :
  ```python
  if getattr(settings, "votre_type_enabled", False):
      scheduler.add_job(...)
  ```

---

## Phase 4: NotificationDispatcher (15 min)

- [ ] **Verifier l'integration avec NotificationDispatcher** :
  Le framework proactif utilise automatiquement `NotificationDispatcher` pour la livraison multi-canal :
  - Archive en DB (toujours)
  - SSE real-time (toujours)
  - FCM push (si `FCM_NOTIFICATIONS_ENABLED` et push active pour l'utilisateur)
  - Telegram (si `CHANNELS_ENABLED` et utilisateur lie)

- [ ] **Personnaliser le type de notification** (si necessaire) :
  ```python
  class VotreNotificationType(str, Enum):
      VOTRE_TYPE = "votre_type"
  ```

---

## Phase 5: Tests (1h)

### 5.1 Tests unitaires

- [ ] **Test ProactiveTask** :
  ```python
  async def test_select_target():
      task = VotreProactiveTask()
      users = await task.select_target(db)
      assert len(users) >= 0

  async def test_generate_content_should_notify():
      task = VotreProactiveTask()
      content = await task.generate_content(user, db)
      assert content is not None
      assert content.title

  async def test_generate_content_should_skip():
      # Tester le cas ou la decision est "skip"
      ...
  ```

- [ ] **Test EligibilityChecker** :
  ```python
  async def test_eligibility_within_hours():
      # Verifier que l'utilisateur est eligible dans la plage horaire
      ...

  async def test_eligibility_quota_exceeded():
      # Verifier le rejet quand le quota est atteint
      ...

  async def test_cross_type_cooldown():
      # Verifier le cooldown croise avec d'autres types
      ...
  ```

### 5.2 Tests integration

- [ ] **Test du job scheduler** :
  ```python
  async def test_proactive_task_runner():
      runner = ProactiveTaskRunner(
          task=VotreProactiveTask(),
          eligibility_config=votre_eligibility_config,
      )
      await runner.run()
      # Verifier que les notifications ont ete envoyees
  ```

---

## Phase 6: Observabilite (15 min)

- [ ] **Ajouter les metriques Prometheus** :
  ```python
  votre_notification_total = Counter(
      "votre_proactive_notification_total",
      "Total notifications proactives envoyees",
      ["status"],  # "sent", "skipped", "error"
  )

  votre_notification_duration = Histogram(
      "votre_proactive_notification_duration_seconds",
      "Duree de generation de notification",
  )
  ```

- [ ] **Dashboard Grafana** : ajouter un panel au dashboard Proactive Notifications

---

## Phase 7: Documentation (15 min)

- [ ] **Documenter** dans `docs/technical/` ou mettre a jour le doc existant
- [ ] **Mettre a jour `CLAUDE.md`** si pertinent (feature flag, types, locations)
- [ ] **Mettre a jour `docs/INDEX.md`** si nouveau document cree

---

## Validation Finale

- [ ] ProactiveTask implemente avec les 3 methodes
- [ ] EligibilityChecker configure (plages horaires, quotas, cooldowns)
- [ ] Job scheduler enregistre et conditionne par feature flag
- [ ] Tests unitaires et integration passent
- [ ] Metriques Prometheus ajoutees
- [ ] Documentation a jour

**Date de completion**: _________________________
**Notes**: _________________________

---

## References

- `infrastructure/proactive/` — Framework proactif generique
- `domains/heartbeat/proactive_task.py` — Implementation de reference (Heartbeat)
- `docs/technical/HEARTBEAT_AUTONOME.md` — Documentation technique Heartbeat
- `docs/guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md` — Guide pratique
