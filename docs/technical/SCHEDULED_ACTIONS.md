# Scheduled Actions (Actions Planifiees)

> Routines persistantes exécutées selon une récurrence ou une condition définie par l'utilisateur.

**Version**: 1.0
**Date**: 2026-02-27
**Mise à jour**: 2026-11-13 — troisième horloge, l'appel signé d'un autre système ([ADR-386](../architecture/ADR-386-A-Signed-Call-Starts-A-Routine.md)) ; 2026-10-12 — récurrence partagée et réservations manuelles sous autorité actuelle ([ADR-322](../architecture/ADR-322-One-Clock-Per-Routine.md))

---

## Vue d'Ensemble

Les Scheduled Actions permettent aux utilisateurs de configurer des taches recurrentes que l'assistant execute automatiquement. Chaque action consiste en :

- Un **titre** descriptif
- Un **prompt d'instruction** pour l'assistant
- Une **horloge** : récurrence calendaire ou condition vérifiée par le système
- Un **fuseau horaire** (herite du profil utilisateur)

Les resultats sont archives dans la conversation de l'utilisateur et notifies via FCM push et Redis SSE.

> **Pas de canaux externes.** Contrairement aux rappels et aux notifications proactives, l'executeur d'actions planifiees n'appelle pas `send_notification_to_channels()` : un resultat d'action planifiee n'est jamais pousse vers Telegram, meme avec `CHANNELS_ENABLED=true`.

**Une routine qui ne s'exécute pas le dit** (ADR-265, amendement 2026-11-12). Trois avis partent de `infrastructure/scheduler/scheduled_action_notices.py`, par `NotificationDispatcher` comme la proposition d'une routine « proposer d'abord » — archive dans la conversation, push, SSE, et canaux externes quand ils sont actifs :

- au **premier échec d'une série** ; les échecs suivants de la même série se taisent, la personne le sait déjà ;
- à la **mise en pause** après les échecs consécutifs ;
- quand la **limite d'utilisation** écarte une routine : cet avis est celui du COMPTE, réclamé une fois par fenêtre (`SCHEDULED_ACTIONS_QUOTA_NOTICE_COOLDOWN_HOURS`), quelle que soit la routine qui a rencontré la limite la première.

Une exécution lancée à la main est attendue : elle dit toujours comment elle s'est terminée. Chaque avis part APRÈS le commit du résultat du tick, et n'écrit aucune ligne de registre : c'est un compte rendu d'état, pas un acte de l'initiative de LIA.

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
       |  1. Leader scheduler        |                        |
       |  2. recover_stale_executing  |                        |
       |  3. get_and_lock_due_actions (FOR UPDATE SKIP LOCKED) |
       |  4. COMMIT (release locks)                            |
       |  5. Pour chaque action :                              |
       |     a0. Routine condition : verifier la condition,    |
       |         continuer sur un fait NEUF seulement          |
       |     a. Guard: HITL pending check                      |
       |     b. stream_chat_response(auto_approve_plan=True)   |
       |     c. FCM + SSE notification                         |
       |     d. TriggerPlan.after_tick (recurrence ou systeme) |
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
| `core/recurrence/schedule.py` | Réarmement et instants servis depuis RecurrenceSpec |
| `infrastructure/scheduler/scheduled_action_executor.py` | Job scheduler + execute_single_action |

### Modele de donnees

```
scheduled_actions
├── id (UUID, PK)
├── user_id (UUID, FK users.id CASCADE)
├── title (String 200)
├── action_prompt (Text)
├── recurrence (JSONB, nullable) -- RecurrenceSpec d'une routine time ; NULL pour une routine condition
├── trigger_kind (String 20: time|condition|webhook) -- l'horloge de la routine (ADR-322, ADR-386)
├── condition_config (JSONB, nullable) -- routine condition : {type, parametres, until}
├── condition_state (JSONB, nullable) -- registre des faits : {seen, last_checked_at, last_check_error, last_fired_at}
├── webhook_key (String 64, unique, nullable) -- routine webhook : la clé de son adresse (ADR-386)
├── webhook_secret (Text, nullable) -- routine webhook : son secret HMAC, chiffré, montré une seule fois
├── user_timezone (String 50, default "Europe/Paris")
├── next_trigger_at (DateTime TZ, UTC, nullable) -- Calcule ; NULL = plus rien
├── is_enabled (Boolean, default true)
├── status (String 20: active|executing|error)
├── execution_token (UUID, nullable) -- identité de réservation
├── last_executed_at (DateTime TZ, nullable)
├── execution_count (Integer, default 0)
├── consecutive_failures (Integer, default 0)
├── last_error (Text, nullable)
├── created_at, updated_at (DateTime TZ)
```

**Index partiel** : `ix_scheduled_actions_due` sur `next_trigger_at WHERE is_enabled=true AND status='active' AND next_trigger_at IS NOT NULL`

**Une horloge par routine** (ADR-322, ADR-386) : le CHECK `ck_scheduled_actions_one_clock` exige une `recurrence` et aucune condition pour `time`, une condition et aucune `recurrence` pour `condition`, ni l'une ni l'autre pour `webhook` ; `ck_scheduled_actions_webhook_address` donne une adresse et un secret à une routine `webhook`, et à elle seule. Les appels qu'elle a acceptés vivent dans `routine_webhook_deliveries` (corps chiffré, effacé une fois servi). Les trois colonnes JSONB sont `none_as_null` : un `None` Python y devient un NULL SQL, jamais le `null` JSON que `IS NULL` ne voit pas.

**La planification tient dans une colonne.** `recurrence` porte un
`RecurrenceSpec` (`src/core/recurrence/spec.py`) : les jours calendaires
servis (`freq`, `interval`, `anchor_date`, `byweekday`, `bymonthday`,
`nth_weekday`, `bymonth`), les moments a l'interieur (`times`), et la fin de
serie (`end`). Il remplace trois colonnes cron qui ne savaient pas decrire une
routine declenchee deux fois par jour.

`next_trigger_at` est **nullable** depuis cette refonte : NULL signifie qu'il
n'y a plus rien apres — serie epuisee, occurrence unique consommee. En SQL
`NULL <= now()` vaut UNKNOWN, donc le scrutin exclut la ligne par
construction, et non par un filtre qu'il faudrait penser a ecrire.

### API Endpoints

| Methode | Path | Status | Description |
|---------|------|--------|-------------|
| GET | `/scheduled-actions` | 200 | Liste actions de l'utilisateur |
| POST | `/scheduled-actions` | 201 | Creer (verifie limite par user) |
| PATCH | `/scheduled-actions/{id}` | 200 | Modifier |
| DELETE | `/scheduled-actions/{id}` | 204 | Supprimer |
| PATCH | `/scheduled-actions/{id}/toggle` | 200 | Toggle is_enabled |
| POST | `/scheduled-actions/{id}/execute` | 202 | Tester maintenant (fire-and-forget) |
| GET | `/scheduled-actions/week` | 200 | La semaine en cours de chaque routine : instants du moteur de récurrence + issue du run qui a servi chaque creneau (ADR-265). Declaree AVANT `/{id}`. |
| POST | `/scheduled-actions/{id}/webhook-secret` | 200 | Routine webhook : tire un nouveau secret, rendu dans CETTE réponse seule ; l'ancien cesse aussitôt (ADR-386) |
| POST | `/hooks/routines/{key}` | 202 | Adresse publique d'une routine webhook : sans session, authentifiée par sa signature HMAC-SHA256 (ADR-386, voir [ROUTINE_WEBHOOKS.md](ROUTINE_WEBHOOKS.md)) |

### Calcul du prochain declenchement

Les routines utilisent le moteur partagé `core/recurrence`, comme les rappels.
`rearm_after()` combine la `RecurrenceSpec`, le fuseau local et l'instant servi,
puis rend un instant UTC ou `None` si la série n'a plus d'occurrence. APScheduler
cadence le scrutin ; il ne représente pas la récurrence de chaque routine.

```python
from src.core.recurrence import RecurrenceSpec, rearm_after

# Exemple de calendrier, pas des valeurs par défaut.
spec = RecurrenceSpec.model_validate({
    "freq": "weekly", "interval": 1, "anchor_date": "2026-10-12",
    "byweekday": [1, 3, 5],
    "times": {"mode": "at", "at": [{"hour": 19, "minute": 30}]},
})
next_fire = rearm_after(spec, "Europe/Paris", due_at=None)
```

Une routine `condition` ne possède pas cette planification :
`TriggerPlan.after_tick()` calcule son prochain contrôle système.

### Execution par le scheduler

Le job `process_scheduled_actions` tourne toutes les 60 secondes :

1. **Recovery** : reset actions `executing` au-delà du pire cas d'un run, jamais moins de 10 min (crash recovery)
2. **Lock** : `FOR UPDATE SKIP LOCKED`, transition `status='executing'` et nouveau `execution_token`
3. **Commit** : libere les verrous FOR UPDATE (status='executing' sert de verrou logique)
4. **Execute** : `execute_single_action()` dans sa propre session DB
5. **Notification** : FCM push + Redis SSE (voir [Corps des notifications](#corps-des-notifications))

> **Collecte sérialisée** : l'élection du leader, `max_instances=1` et le verrou SQL coordonnent le scrutin. Aucun `SchedulerLock` Redis supplémentaire n'est pris. La concurrence du batch est bornée par `scheduled_actions_max_concurrency`, avec une session distincte par exécution.

Chaque règlement vérifie le `execution_token` sous verrou SQL avant de modifier
la routine : résultat du pipeline, vérification sans fait neuf, proposition et
question en attente. Une vérification ou une notification tardive peut conserver
la trace de ce qui a eu lieu, mais ne reprogramme pas une réservation annulée ou
remplacée pendant son attente.

### Réservation d'une exécution manuelle

L'UI et les commandes applicatives passent par
`ScheduledActionService.reserve_manual_execution()` : la ligne appartenant au
compte est verrouillée et un lancement déjà `executing` est refusé. La
réservation porte un `execution_token` opaque. La récupération d'un état
ancien et le règlement d'un run libèrent ce token.

Une commande conversationnelle peut attendre la fin du tour actif. Sa reprise
conserve la configuration confirmée et son échéance, puis
`application/routine_execution_policy.py::authorize_reserved_routine()` relit
l'autorité, le token, le statut, le snapshot et l'expiration après les lectures
et avant l'inférence. Une réservation obsolète est annulée seulement si son
token correspond encore ; elle ne libère ni ne consomme une réservation plus
récente. Ce contrôle ne promet pas une transaction exactement une fois chez un
fournisseur externe. Voir [les commandes applicatives](APPLICATION_COMMANDS.md).

### Deux horloges : une planification, ou les vérifications du système (ADR-322)

Une routine a UNE horloge. Une routine `time` suit sa `recurrence` ; une routine `condition` n'en a pas : le système vérifie sa condition lui-même, jour et nuit, et ne l'exécute que sur un fait NOUVEAU. La règle est écrite une fois (`schemas.trigger_mode_refusal`, lue par le schéma de création et par la mise à jour du service, qui voit la moitié stockée de la paire) et tenue par la table.

- **Météo** — toujours Google Weather, la source que l'instance garantit à chaque compte, jamais le fournisseur choisi par la personne (`weather_provider.open_platform_weather_client`) ; la prévision HORAIRE sur l'horizon publié, l'heure en cours comprise ; un changement d'un type surveillé dont la probabilité de précipitations dépasse strictement le seuil publié ; la note donnée à l'exécution nomme le type, l'heure, le jour, le fuseau, la probabilité et la source (ADR-322, amendement 2026-09-29).
- **Page web** (ADR-387) — `page_change` lit une page publique (`url`, refusée dès la saisie si son écriture exclut une page publique ou si elle porte des identifiants), sans modèle, par le lecteur public de LIA (`radio.newsroom.fetch.fetch_public` : chaque saut validé et épinglé, le corps borné, la lecture bornée dans le temps, le lecteur nommé `PAGE_WATCH_USER_AGENT`) ; la page devient les lignes qu'une personne lit (`infrastructure/scheduler/page_reading.py`), éventuellement filtrées par `contains` ; chaque ligne est un fait. La note de l'exécution montre les lignes nouvelles, enveloppées comme contenu externe ; un seuil de prix appartient à l'instruction, jugé par l'exécution. Une adresse qui ne mène à aucune page publique est `not_configured`, une page qui n'a pas répondu `unavailable`.
- **Cadence** — `domains/scheduled_actions/trigger.py::CONDITION_CHECKS` : `SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES` pour le courrier, les tâches, l'agenda et les documents, `SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES` pour la météo, `SCHEDULED_ACTIONS_PAGE_CHECK_MINUTES` pour une page web ; jamais plus rapide que le cache que sa source lit (la recherche Gmail, `EMAILS_CACHE_SEARCH_TTL_SECONDS`) ; une phase par routine tirée de son identifiant, sur une grille ancrée sur l'époque, donc sans dérive. `TriggerPlan` arme à la création, à l'édition, à la réactivation, au changement de fuseau et après chaque passage ; une vérification manquée n'est jamais rejouée.
- **Fin** — `condition_config.until`, dernier jour local inclus : la routine s'arrête au minuit local suivant et `close_finished` la clôt, comme une série épuisée.
- **Registre des faits** — `condition_state`, écrit par `condition_ledger.py` seul : un fait est neuf quand sa clé (identité hachée : message, tâche et son échéance, événement et son début, fichier, type et jour de la météo, ligne d'une page par ce qu'elle dit) n'a jamais été vue ; un fait non servi (plafond, question en attente, échec) reste neuf ; un fait encore présent n'est jamais évincé. Le registre d'une page est un INSTANTANÉ (`SNAPSHOT_CONDITION_TYPES`, ADR-387) : il garde les lignes présentes à la dernière lecture servie et oublie celles qui sont parties, si bien qu'une ligne qui revient (« en stock ») est à nouveau neuve ; une lecture en échec n'oublie rien. Tant qu'aucune lecture n'a été servie (`last_fired_at` vide), l'exécution apprend que rien de la page n'a encore été rapporté : ce qu'elle montre maintenant, sans comparaison.
- **Plafond** — au plus `SCHEDULED_ACTIONS_CONDITION_MAX_FIRES_PER_DAY` exécutions par jour local, comptées dans `scheduled_action_runs` (`count_fires_since`, `FIRED_OUTCOMES`).
- **Une vérification sans suite** ré-arme et n'écrit que le registre (`last_checked_at`, `last_check_error` : `not_configured` ou `unavailable` quand la source n'a pas pu être lue, `quota_blocked` quand la limite d'utilisation a écarté la vérification) — aucune ligne d'historique.
- **Au dossier** — chaque vérification tourne sous le `TrackingContext` de la routine (`out_of_turn_spend`) et dépose une consultation `routine_condition` : `failed` sur un refus, rien quand il n'y avait rien à ouvrir. `evaluate_condition` ne lève jamais.
- **« Vérifier maintenant »** remplace « Tester » sur la carte d'une routine sur condition : `POST /execute` lance une vraie vérification, qui n'exécute la routine que sur un fait neuf.

### La troisième horloge : l'appel signé d'un autre système (ADR-386)

Une routine `webhook` n'a ni planification ni condition : un autre système (box domotique, forge de code, service de formulaires) appelle son adresse propre, `POST /api/v1/hooks/routines/{key}`, avec le corps signé en HMAC-SHA256 sous son secret (`X-LIA-Signature-256`, `X-Hub-Signature-256` lu de même). Le mécanisme complet, le côté de l'expéditeur et les bornes : [ROUTINE_WEBHOOKS.md](ROUTINE_WEBHOOKS.md).

- **Adresse et secret** tirés par le serveur quand la routine passe sur cette horloge (`webhook_address.py`) ; le secret, chiffré, ne sort qu'une fois, dans la réponse qui l'a tiré, jamais dans un journal ni dans l'export ; quitter l'horloge les efface, avec les appels en attente.
- **Un appel** est lu, signé, borné puis gardé sous le verrou de la routine (`webhook_service.py`), avant la réponse 202 ; il arme la routine pour le prochain passage, dans la minute.
- **Un passage** (`routine_webhook_gate.py`) lit les plus anciens appels en attente après l'instruction de la routine, comme contenu externe ; un run qui a répondu les marque servis dans son règlement ; un échec recule de `ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS` ; sans appel en attente, la routine dort (`next_trigger_at` NULL) — jamais « finie » : `close_finished` l'épargne, et seuls les lecteurs d'une PLANIFICATION annoncent une prochaine exécution.
- **Ni « Tester », ni proposition** : une routine webhook n'a rien à exécuter sans appel, et une proposition confierait le run au chat, qui ne lirait jamais les appels.
- **Un interrupteur** : `PlatformCapability.ROUTINE_WEBHOOKS` ferme l'adresse, le tirage d'un secret et l'acte ; les routines et les appels déjà acceptés restent (ADR-280).

### Corps des notifications

Le contenu de la reponse est **riche** : HTML enveloppe dans `<div class="lia-response">` quand le mode d'affichage de l'utilisateur est `html`, cartes de donnees rendues cote serveur en mode `cards`, Markdown sinon. Or le service worker passe `body` tel quel a `showNotification()` et le toast frontend rend sa description en texte echappe : sans aplatissement, l'utilisateur lit `<div class="lia-response"><h2>` sur son ecran de verrouillage.

Deux regles, dans cet ordre :

1. **Contenu canonique** — l'executeur consomme le chunk `content_replacement`, qui **remplace** les tokens diffuses (il porte le texte final apres post-traitement : cartes HTML, injection de photos, nettoyage des balises `psyche_eval`). N'accumuler que les `token` construisait la notification sur une version perimee, en desaccord avec le message archive que l'utilisateur ouvre ensuite dans le chat.
2. **Aplatissement puis troncature** — `plain_text_for_notification()` (`infrastructure/proactive/notification.py`) retire le HTML, aplatit les liens Markdown en `libelle (url)` et replie le tout sur une ligne. La troncature vient **apres** : tronquer du HTML brut coupe au milieu d'une balise et gaspille le budget (`<div class="lia-response">` consomme a lui seul 26 des 150 caracteres par defaut).

Le budget du push suit `PROACTIVE_NOTIFICATION_MAX_LENGTH` ; l'apercu SSE est plafonne par `SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH`. Cote frontend, `toPlainPreview()` (`apps/web/src/lib/notification-preview.ts`) applique la meme protection aux descriptions de toast, pour les trois familles de notifications.

C'est precisement parce que ces surfaces **tronquent** que les blocs `<head>`/`<style>`/`<script>` y sont retires **sans exiger de balise fermante** : un `<style>` coupe au milieu d'une regle ne conserve pas son `</style>`, et le retrait de balises laissait alors le CSS ressortir en texte. Voir [NOTIFICATIONS_FLOW.md](NOTIFICATIONS_FLOW.md) pour le detail des deux motifs (`_BLOCK_ELEMENT_RE` backend / `BLOCK_RE` frontend) et des garde-fous qui evitent qu'un `<script src="x"/>` auto-fermant avale le document.

### Pas de contournement HITL (constat ADR-323)

L'exécuteur passe `auto_approve_plan=True` à `stream_chat_response()`, qui écrit `state["plan_approved"] = True` dans l'état d'entrée — mais le routeur remet ce drapeau à `None` au début de chaque tour, avant tout lecteur : il est inerte depuis la v1.0.0. Seule une routine en mode pipeline rencontre le validateur sémantique — le mode d'une routine est ReAct par défaut (`OUT_OF_TURN_EXECUTION_MODE_DEFAULT`). Si son plan appelle une clarification, elle s'arrête sur une question, comme un tour tapé : l'exécution est comptée en échec (et pour la désactivation automatique), et la question attend dans la conversation de la personne, où la garde ci-dessous reporte les routines suivantes tant que l'enregistrement de la question vit (`HITL_PENDING_DATA_TTL_SECONDS`), pas forcément jusqu'à sa réponse. Depuis le 2026-09-05 (ADR-263) et jusqu'à ce changement (ADR-323), le routage ignorait le verdict du validateur pour tout le monde : aucune question n'était posée. Une politique propre aux exécutions sans personne reste à décider (proposition d'ADR-323).

**Garde HITL** : avant d'exécuter, l'exécuteur lit l'enregistrement de question en attente dans Redis — celui sur lequel le chat route la réponse de la personne (`conversation_has_pending_hitl`, `infrastructure/scheduler/out_of_turn_run.py`), jamais le checkpoint du graphe, qui dit « interrompu » jusqu'à l'entrée suivante. S'il en existe un, l'action est ignorée sans erreur et reprogrammée au prochain cycle ; une sonde qui échoue laisse passer.

### Pas d'apprentissage depuis les actions planifiées

L'exécuteur positionne également `is_automated_source=True` dans `stream_chat_response()`. Ce drapeau est propagé via `configurable` — et non via la metadata, qui est reconstruite par l'instrumentation Langfuse — puis lu une seule fois par `response_node`, où il désactive les **quatre** extractions post-réponse : mémoire long terme, centres d'intérêt, journal et psyché. Seules les entrées directes de l'utilisateur (chat web, Telegram, voix) alimentent ces sous-systèmes ; le prompt d'une action planifiée, injecté comme `HumanMessage`, ne crée donc plus de souvenirs ni de centres d'intérêt indésirables. Les notifications proactives (heartbeat, intérêts) ne passent pas par `response_node` et n'ont jamais été concernées.

### Retry sur erreurs transitoires

En cas d'erreur transitoire (`TimeoutError`, `ConnectionError`, `OSError`), l'executeur retente automatiquement jusqu'a `SCHEDULED_ACTIONS_MAX_RETRIES` fois (defaut: 1 retry, soit 2 tentatives max) avec un delai de `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` (defaut: 30s) entre les tentatives. Les erreurs non-transitoires (HITL interrupt, erreur logique) ne sont pas retentees.

### Auto-disable apres echecs

Apres **5 echecs consecutifs** (`SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES`), l'action est automatiquement desactivee (`is_enabled=False`, `status='error'`). Le re-enable via toggle reset les compteurs et recalcule le prochain declenchement. La personne est prévenue au premier échec de la série, puis à la mise en pause (`scheduled_action_notices.failure_notice`, qui lit la ligne que `mark_execution_failure` rend : le seuil garde un seul propriétaire).

### Limite d'utilisation atteinte (ADR-272)

Un compte au-delà de sa limite d'utilisation, ou une instance au-delà de son budget du jour, n'exécute pas ses routines, et **ce n'est pas un échec** : rien ne compte vers la mise en pause. Le tick est écarté AVANT toute lecture de source (une vérification météo est facturée), la routine est réarmée sur sa propre horloge, et le motif est écrit là où chaque sorte de routine tient son histoire :

- routine `time` : une ligne `skipped_quota` sur le créneau, lue par la semaine ;
- routine `condition` : aucune ligne (une par vérification écartée, la règle d'ADR-322), mais `last_check_error = quota_blocked` sur son registre, que sa carte affiche.

Un refus de la limite rencontré PENDANT le tour (`RunOutcome.QUOTA_BLOCKED`) prend la même sortie. Jusqu'au 2026-11-12 il était compté comme un échec, et une série de refus mettait en pause une routine qui n'avait rien ; le pré-contrôle, lui, rendait la main sans réarmer, et la routine restait `executing` jusqu'à la récupération des réservations périmées.

### Fenêtre de rattrapage (ADR-265, amendement 2026-11-12 b)

Une occurrence d'une routine `time` n'est exécutée en retard que dans sa fenêtre de rattrapage : la MOITIÉ de l'écart avec l'occurrence qui la suit, plafonnée par `SCHEDULED_ACTIONS_CATCH_UP_MAX_MINUTES`. Le rythme de la routine dit donc quand son occurrence est périmée — quelques minutes pour une routine au quart d'heure, le plafond pour une routine quotidienne. Une occurrence que rien ne suit (la dernière d'une série, une occurrence unique) n'est jamais abandonnée.

- **Occurrence atteinte trop tard** (panne, planificateur à l'arrêt) : elle n'est pas exécutée, son créneau porte `skipped_late`, rien ne compte comme un échec et personne n'est notifié (une panne qui a sauté cinq routines répondrait par cinq avis). La routine est réarmée sur l'occurrence la plus RÉCENTE si celle-ci peut encore démarrer — une panne qui se termine vingt minutes après le créneau du jour sert le jour même, au passage suivant du planificateur — sinon sur la prochaine (`TriggerPlan.after_missed`). Jamais sur une occurrence intermédiaire : une occurrence dont la suivante est déjà venue est toujours hors fenêtre, par construction.
- **Compte occupé** (`RunOutcome.BUSY`) : l'occurrence reste armée sur le MÊME instant, sans ligne d'historique, et le passage suivant la retrouve due — jusqu'à la fin de sa fenêtre, après quoi le créneau porte `skipped_busy` et la routine passe à l'occurrence suivante. Jusqu'au 2026-11-12 la routine était réarmée tout de suite sur l'occurrence SUIVANTE : une routine quotidienne était perdue pour la journée parce que son propriétaire écrivait à 8 h, ou parce que deux routines du même compte tombaient à la même minute. Une question en attente dans le chat (`skipped_hitl`) n'est pas attendue : elle dure le temps que la personne met à répondre.
- Une routine `condition` n'a pas d'occurrence : rien de tout cela ne la concerne, une vérification manquée est manquée.
- **Une exécution lancée par la personne n'est jamais classée « manquée »** : « Exécuter maintenant » et une exécution demandée dans le chat le DÉCLARENT à l'appel (`execute_single_action(started_by_person=True)`). Qui a lancé une exécution ne se déduit pas du créneau en attente — un créneau peut être dépassé parce que le planificateur était à l'arrêt, précisément le moment où l'on clique. L'attente d'un compte occupé, elle, reste celle du créneau.

### Ne prévenir que s'il y a du nouveau (ADR-265, amendement 2026-11-12 c)

`scheduled_actions.notify_only_when_new` est l'option d'une routine : l'exécution a toujours lieu, sa réponse reste archivée dans la conversation, et c'est la NOTIFICATION (push et message à l'écran) qui est retenue quand l'exécution n'a rien trouvé de nouveau. Seul le modèle qui écrit la réponse sait si elle dit du nouveau : il le déclare par une balise machine après sa réponse, `<lia_nothing_new/>`, sur le mécanisme du registre de ton (ADR-253) — retirée du flux (`streaming/machine_tags.py`) et de la réponse enregistrée, remise au fragment `done` (`nothing_new: true`), lue par le moteur (`RunResult.nothing_new`) puis par l'exécuteur.

- L'instruction n'est donnée qu'à un tel tour : l'exécuteur passe `StreamRequest.quiet_when_nothing_new`, le moteur le publie pour la durée du flux (`nothing_new.quiet_run_scope`), et le prompt de réponse reçoit `routine_nothing_new_instruction.txt` avant son rappel final. Un tour de chat ordinaire n'apprend jamais la balise, et une balise écrite hors d'un tel tour est retirée sans rien déclarer.
- Le doute notifie : pas de balise, balise tronquée, tour sans fragment `done`, exécution en échec — la personne est prévenue, comme avant. Le silence est la seule issue qui exige une déclaration complète, et un échec est toujours dit (ses avis ne lisent pas l'option).
- **Une exécution qui a quelque chose à avouer n'est jamais « rien de nouveau »**, quoi que déclare son modèle : une étape en échec, une recherche interrompue, une étape non exécutée. Le prompt le dit, le code s'en assure (ADR-303) : la couture qui assemble ce que la réponse doit avouer de sa propre exécution (`build_run_honesty_block`) annule la déclaration (`nothing_new.note_run_admission`) avant même que le modèle soit interrogé. Une dégradation de la plateforme, signalée par le conseiller de diagnostic, est dite au modèle à côté des échecs et n'annule rien : le nombre d'échecs du tour est UNE fonction (`failure_context.count_turn_failures`), lue par le total de la directive et par la garde (trouvé sur dev le 12/11 : un seul incident ouvert sur le disque de l'instance annulait le silence de toutes les routines).
- L'option et « demander mon accord avant d'exécuter » s'excluent (`schemas.delivery_refusal`, appliquée à la création et, sur la ligne RÉSULTANTE, à la mise à jour) : une proposition EST une notification, l'option serait stockée et jamais lue.
- Les opérations de l'assistant sur les routines (création, mise à jour, lecture) portent l'option par héritage des schémas du Studio ; `routine_operations._CONFIGURATION_FIELDS` la couvre, donc une option changée après l'affichage d'une carte périme la commande.
- Dans le formulaire (`RoutineDeliveryFields`), chaque option est décrite par son indice (`aria-describedby`), et l'option écartée par « demander mon accord » reste atteignable au clavier (`aria-disabled`, jamais `disabled`) : son indice dit pourquoi, et c'est le gestionnaire qui refuse le changement.
- **Mesure** : `task routines:quiet:measure` (`scripts/routines/measure_quiet_delivery.py`, payante, à la demande) demande à de vrais modèles, avec le prompt de réponse de production d'un tel tour et des données posées par cinq scénarios, dans les deux modes d'exécution (les données du pipeline, et la réponse de la boucle ReAct qu'une routine utilise par défaut), s'ils déclarent « rien de nouveau » quand il le faut — et jamais quand il y a quelque chose à dire. `--dry-run` n'appelle aucun modèle ; la mesure s'arrête au-delà de `--budget-eur` ; `--instruction FICHIER` mesure une autre instruction à la place du fichier versionné ; la plateforme est posée elle aussi (rien de dégradé). Mesuré le 13/11/2026 sur trois familles × deux modes × cinq scénarios × cinq répétitions (0,60 €) : l'instruction actuelle, qui juge la course sur ce que demande l'instruction de la routine, ne manque aucune notification et en envoie 20 inutiles sur 60 (deux familles se taisent exactement quand il le faut, la troisième n'écrit jamais la balise : elle notifie comme avant) ; la première formulation en envoyait 34 ; un rappel dans le dernier message faisait taire la troisième famille aussi sur une tâche en retard (5 notifications manquées) et a été écarté. Détail dans l'ADR-265, amendement (c).

### Cloture d'une routine finie (ADR-281)

Une serie se termine de **trois** facons : la date de son `SeriesEnd` est
atteinte, son `after_count` est epuise, ou son occurrence unique est consommee.
Les trois aboutissent au **meme** etat — `next_trigger_at` NULL, ce que le
modele definit deja comme « rien ne suit » — et la requete des routines dues
l'exclut par construction, `NULL <= now()` valant UNKNOWN en SQL.

Ce que rien ne faisait, c'etait **fermer** la ligne : elle restait `is_enabled`
et `status='active'` pour toujours, indiscernable d'une routine mise en pause.
L'etape 0b du tick de l'executeur (`_close_finished_routines`, sa propre
session, jamais fatale) la passe a `is_enabled=False` et
`status='completed'` — **desactivee, jamais supprimee** : la personne doit
pouvoir voir ce qu'elle avait pose.

`completed` est distinct de `error` a dessein : « c'est fini » et « ca a
echoue » ne se disent pas pareil, et tous deux sont distincts d'une pause, qui
est une decision.

La fin d'une routine a **une seule autorite**, le `SeriesEnd` de sa recurrence.
Une colonne `expires_at` a ete ecrite puis retiree avant livraison : elle
aurait double une fin deja stockee, validee, editable dans le studio et
racontee en six langues.

### Veilles courriel servies par le reveil (ADR-281)

Une « veille » est une routine `trigger_kind=condition` de type `mail_match` :
« previens-moi quand Marie repond ». Sa condition n'etait evaluee qu'au tick de
sa propre recurrence, plafonnee a douze par jour par defaut (ADR-268) — donc jusqu'a deux
heures de retard — alors que le balayage des reveils (ADR-261) tient deja le
delta Gmail **a la minute**. Depuis ADR-322, une veille n'a plus de recurrence :
le systeme la verifie a sa propre cadence
(`SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES`), jour et nuit, et le reveil
rapproche encore cette verification.

`domains/scheduled_actions/mail_watches.py` evalue les veilles du compte contre
ce delta, **avant toute porte du battement** : ni le cooldown de reveil, ni
`heartbeat_enabled`, ni un refus de la source « emails » ne s'appliquent. Une
veille est une consigne que la personne a ecrite, pas une decision de LIA — le
meme raisonnement que pour l'indexation des sources courriel, qui tourne au meme
endroit et pour la meme raison.

La boite n'est ouverte que pour un compte qui detient une veille
(`has_mail_watches`, une recherche indexee), et elle est lue une seule fois : le
delta est passe a la decision du reveil plutot que relu.

Quatre regles :

- **le reveil ne fait pas tourner la routine** : il avance `next_trigger_at` et
  s'arrete la. L'executeur reste le seul a savoir executer une routine ;
- **aucune seconde deduplication** : le registre des faits `condition_state`
  decide deja si un courriel est neuf ;
- **on avance une echeance, on ne ressuscite pas une serie** : un
  `next_trigger_at` NULL veut dire que la veille est finie, et l'armement ne peut
  que **rapprocher** un passage ;
- **l'armement depasse le cache qu'il fait lire** : l'executeur reevalue via
  `fetch_mails`, dont la recherche Gmail est cachee pendant
  `EMAILS_CACHE_SEARCH_TTL_SECONDS` ; un cache rempli avant l'arrivee du
  courriel repondrait « non remplie », et ce verdict **consomme** l'armement.

La lecture SQL prend `SKIP LOCKED` : une ligne que l'executeur detient verra son
echeance reecrite a la fin de son passage, donc l'armer serait une ecriture que
personne ne lit — et attendre mettrait le reveil derriere la transaction de
quelqu'un d'autre.

**Deux lectures d'une meme question**, inevitables (le reveil tient une
ressource Gmail brute, l'executeur une projection d'affichage) et donc epinglees
par `tests/unit/domains/scheduled_actions/test_mail_match_agreement.py`.

### Puce « Surveiller » (ADR-281)

Sur les cartes de courriel du briefing. Elle **ecrit** la ou ses deux voisines
ouvrent le chat pre-rempli : le chat ne peut pas composer une veille,
`create_scheduled_action_tool` ne creant que des routines `time` par decision
ecrite. La forme vit dans `lib/mail-watch.ts` — l'**expediteur** comme requete
et jamais le sujet, la fin portee par le dernier jour de la condition (`until`,
ADR-322), sans aucune planification — et la puce **lit ce que le
compte detient avant d'ecrire** : deux veilles identiques annonceraient une
seule reponse attendue deux fois.

### Historique des executions et semaine en cours (ADR-265)

`scheduled_action_runs` : une ligne par tick, ecrite par l'executeur AU RESULTAT dans la transaction du marquage (`runs.py::record_run`, savepoint, jamais bloquante) — huit issues (`success`, `failure`, `skipped_condition`, `proposed`, `skipped_hitl`, `skipped_busy`, `skipped_quota`, `skipped_late`) et le creneau SERVI (`served_slot` : un run du sert son instant du, un « Tester » apres le creneau du jour le sert, avant ne sert rien). `GET /scheduled-actions/week` (`week.py::build_week`) calcule les sept instants de la semaine de chaque routine avec `week_slots()` depuis le lundi local de SON fuseau, et une cellule prend le DERNIER run dont `slot_at` est EGAL a l'instant : un changement d'horaire remet la grille a blanc par construction. Retention `SCHEDULED_ACTIONS_RUNS_RETENTION_DAYS` (90 j), purge a l'etape 0 du tick, dans sa propre session, jamais fatale. Chaque ligne dont le pipeline a tourne garde `run_id`, l'identifiant du tour execute (ADR-375) : ce que la routine a consulte se lit alors exactement dans les registres (`agent_treatments.run_id`), sans deviner par les instants ; `NULL` pour une occurrence jamais lancee et pour les lignes anterieures a la colonne.

Une routine sur condition n'a pas de creneau (ADR-322) : son run sert la VERIFICATION qui a declenche (`slot_at` = son debut), et ses cellules de la semaine sont ces verifications, chacune a son instant. `skipped_condition` n'a plus de producteur : une verification sans suite n'ecrit que le registre de la routine ; la valeur reste lisible jusqu'a ce que la retention purge les lignes ecrites avant. Une question en attente ecrit `skipped_hitl` pour une routine `time` — sans compter d'execution — et rien pour une routine `condition`, dont les faits restent neufs. Un compte occupé (`skipped_busy`) et une limite d'utilisation atteinte (`skipped_quota`) suivent la même règle.

### Recalcul timezone

Quand l'utilisateur modifie son fuseau horaire (dans `users/service.py`), toutes ses actions planifiees actives sont recalculees pour maintenir le meme horaire local avec le nouveau fuseau.

---

## Frontend

### Composants

| Fichier | Description |
|---------|-------------|
| `components/settings/ScheduledActionsSettings.tsx` | Section settings complète : tri chronologique, rangs, grille repliable, cartes |
| `components/settings/ScheduledActionsTimeline.tsx` | La grille heures × jours (`<table>`, puces `<button>`, focus itinerant, legende, jour courant) — ADR-265 |
| `components/settings/RoutineNumberChip.tsx` | La puce numerotee partagee par la carte et la grille (cinq tons en jetons du theme) |
| `components/settings/RoutineTemplatePicker.tsx` | La liste « Modèle » de la création : une routine prête à l'emploi remplit le formulaire en un choix |
| `lib/routine-templates.ts` | Les modèles (fonctions pures) : `applyRoutineTemplate`, `routineTemplateOf`, `clearRoutineTemplate`, `blankRoutineFields` (le vide du formulaire, une seule source) |
| `lib/scheduled-actions.ts` | Helpers purs : `numberByTriggerTime`, `buildTimelineGrid`, `chipState`, `rovingTarget`, `routineZones`, `weekDates` |
| `hooks/useScheduledActions.ts` | Hook CRUD avec optimistic updates, auto-refresh, `initialLoading` monotone et la lecture de `/week` refetchee apres chaque mutation |

### UI

- Cards avec titre, statut (badge), prompt tronque, schedule, dates execution
- Switch inline enable/disable
- Boutons : Tester (Play), Modifier (Pencil), Supprimer (Trash2)
- Dialog creation/edition : d'abord le MODE (« Quand s'exécute-t-elle ? » — sur une planification, ou quand quelque chose se produit), puis les seuls champs de ce mode ; le brouillon de l'autre mode est gardé tant que la boîte est ouverte et jamais envoyé (ADR-322)
- Routine sur condition : sa cadence et son plafond (publiés par `GET /scheduled-actions`, jamais recopiés), « Surveiller jusqu'au » facultatif, sa dernière vérification et la cause d'un échec, « Vérifier maintenant » à la place de « Tester »
- **Routines prêtes à l'emploi** (lot 13) : la création — jamais la modification ni la duplication — ouvre sur une liste « Modèle » : briefing du matin (chaque jour à 7 h 30), tri de la boîte de réception (jours de semaine à 8 h, « ne me prévenir que s'il y a du nouveau »), revue de la semaine (dimanche à 18 h), tâche en retard (condition `task_overdue`). Un choix remplit le titre et l'instruction dans la langue de la personne (`scheduled_actions.templates.*`), l'horloge à partir d'aujourd'hui et la livraison ; rien n'est planifié avant l'enregistrement. Le modèle choisi se LIT dans le formulaire (son instruction) : une instruction retouchée n'est plus un modèle, et revenir à « Aucun modèle » ne vide que ce qu'un modèle a rempli. Les instructions du briefing, de la revue et du tri demandent ce que répondent les skills système `briefing-quotidien`, `revue-hebdomadaire` et `tri-boite-reception` (plan fixe, sans planificateur) — détection mesurée par `task skills:detection:measure` (voir [SKILLS_INTEGRATION.md](SKILLS_INTEGRATION.md))
- Confirmation suppression via AlertDialog
- Etat vide avec icone et texte explicatif
- **Auto-refresh** : polling 30s (normal) / 10s (quand une action est en cours d'execution) — sans demonter les cartes : le spinner ne s'affiche qu'au PREMIER chargement, un sondage marque la region `aria-busy`
- **Ordre et rangs** : cartes triees par heure de declenchement (heure, minute, titre, id) et numerotees ; une routine en pause garde son rang
- **Vue de la semaine** : grille repliable (ouverte par defaut), heures en descendant et jours en travers, puce coloree par l'issue du creneau (blanc / vert / rouge / ambre / gris), anneau pour une routine conditionnelle, pulsation pendant une execution, colonne du jour courant, legende, mention du fuseau ; clic ou Entree sur une puce amene et focalise la carte ; la grille est UN arret de tabulation, les fleches la parcourent

### i18n

Cles `scheduled_actions.*` dans les 6 langues (fr, en, es, de, it, zh).

---

## Constants

| Constante | Valeur | Description |
|-----------|--------|-------------|
| `SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS` | 60 | Intervalle du scheduler job |
| `SCHEDULED_ACTIONS_MAX_PER_USER` | 20 | Limite par utilisateur |
| `SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS` | 300 | Budget d'une tentative (5 min), jamais sous les appels modèle d'un tour (ADR-221) |
| `SCHEDULED_ACTIONS_MAX_RETRIES` | 1 | Retries sur erreur transitoire (2 tentatives max) |
| `SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS` | 30 | Delai entre retries |
| `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` | 10 | Seuil recovery stale |
| `SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES` | 5 | Seuil auto-disable |
| `SCHEDULED_ACTIONS_BATCH_SIZE` | 50 | Limite batch par cycle |
| `SCHEDULED_ACTIONS_MIN_STEP_MINUTES` | `…_DEFAULT` (`core/constants.py`) | Pas minimal d'une routine « à intervalle régulier » ; chaque exécution est un tour complet de l'agent (ADR-268, amendement 2026-10-30) |
| `SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY` | `…_DEFAULT` (`core/constants.py`) | Exécutions au plus par jour d'une routine à heures fixes ou à intervalle ; toutes les 5 minutes toute la journée demande 5 et 288 (ADR-268, amendement 2026-10-30) |
| `SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES` | `…_DEFAULT` (`core/constants.py`) | Cadence des routines sur condition : courrier, tâches, agenda, documents (ADR-322) |
| `SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES` | `…_DEFAULT` (`core/constants.py`) | Cadence d'une routine météo (deux appels Google Weather facturés par vérification ; jamais plus longue que l'horizon, refusé au démarrage) |
| `SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS` | `…_DEFAULT` (`core/constants.py`) | Horizon d'une routine météo : un changement dû dans ce nombre d'heures, l'heure en cours comprise (ADR-322, amendement 2026-09-29) |
| `SCHEDULED_ACTIONS_WEATHER_MIN_PRECIPITATION_PERCENT` | `…_DEFAULT` (`core/constants.py`) | Probabilité de précipitations qu'une heure prévue doit dépasser STRICTEMENT pour déclencher une routine météo |
| `SCHEDULED_ACTIONS_CONDITION_MAX_FIRES_PER_DAY` | `…_DEFAULT` (`core/constants.py`) | Exécutions au plus par routine sur condition et par jour local |
| `SCHEDULED_ACTIONS_QUOTA_NOTICE_COOLDOWN_HOURS` | `…_DEFAULT` (`core/constants.py`) | Fenêtre pendant laquelle un compte n'est pas reprévenu que sa limite d'utilisation écarte ses routines (ADR-265, amendement 2026-11-12) |

---

## Metriques Prometheus

- `background_job_duration_seconds{job_name="scheduled_action_executor"}` - Duree du job
- `background_job_errors_total{job_name="scheduled_action_executor"}` - Compteur erreurs

---

## Tests

| Fichier | Tests |
|---------|-------|
| `tests/unit/domains/scheduled_actions/test_schedule_helpers.py` | compute_next_trigger_utc (incl. UTC timezone validation), validate_days, format_display, trou de minuit et differentiel contre le cron brut, week_slots / local_day_slot / served_slot |
| `tests/unit/domains/scheduled_actions/test_schemas.py` | validation Create/Update |
| `tests/unit/domains/scheduled_actions/test_runs.py`, `test_run_repository.py`, `test_week.py`, `test_router_week.py`, `test_service.py` | ADR-265 : record_run, repository des runs, pliage de la semaine, route /week et son ordre, recalcul de fuseau des routines en pause |
| `tests/integration/domains/scheduled_actions/test_runs_pg.py` | contre PostgreSQL : CHECK reel sur outcome, cascades, lecture par semaine, purge |
| `tests/unit/domains/scheduled_actions/test_trigger.py`, `test_condition_ledger.py`, `test_one_clock_migration.py` | ADR-322 : cadence, phase et fin d'une routine sur condition ; nouveauté des faits ; fin gardée par la migration |
| `tests/integration/domains/scheduled_actions/test_one_clock_migration_pg.py`, `test_one_clock_service_pg.py` | contre PostgreSQL : migration aller-retour (fins gardées, réparations, `null` JSON), CHECK réel, écritures du service dans les deux modes |
