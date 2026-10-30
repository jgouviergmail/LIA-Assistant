# ADR-304 : aucune transaction ouverte pendant un appel réseau

**Statut** : accepté — 2026-09-22
**Amende** : ADR-261 (réveil poussé et synchronisation Drive incrémentale), ADR-301 (une session ne vit pas plus longtemps que ses requêtes), ADR-263 (réclamations et registres), ADR-119 (noyau d'alertes), ADR-283 (anatomie mémoire)

## Contexte — quatre défauts vus en production le 2026-09-22

1. **Le balayage des réveils poussés (ADR-261) était bloqué depuis 14 minutes**, 0 réveil servi depuis le démarrage contre ~206 par 24 h. Une session PostgreSQL restait `idle in transaction` 863 s sur une lecture de `webhook_channels`. Mesuré ensuite, cinq mécanismes s'additionnaient : le flux de changements Drive était lu par pages de **25** (le défaut de Google, 40 fois les allers-retours nécessaires) ; le drainage n'avait **aucune borne** ; le réveil mis en file portait le **jeton lu à la notification**, pendant le drainage précédent, si bien que chaque drainage rejouait le précédent (935 puis 1 328 s, les mêmes 26 522 changements lus deux fois) ; la session était **tenue pendant les appels Google** ; et `max_instances=1` sautait chaque tick suivant pendant qu'un lot de dix réveils attendait derrière celui qui ne rendait pas la main.
2. **La classe entière, pas seulement Drive.** Un recensement de production a trouvé des sessions `idle in transaction` de 11 à 330 s dans le briefing, le heartbeat, les moments, le contexte téléphonique et la vue relations — chacun sur la même forme : un client connecteur construit sur la session de l'appelant, qui devait donc rester ouverte pendant que le fournisseur répondait. Le tour de chat tenait une transaction pour toute sa durée, et **le tampon `last_used_at` d'une clé API y posait un verrou de ligne** qu'une autre requête attendait. Un client pouvait même **fermer la session de son appelant** (`async with self.connector_service.db`), expurgeant les objets chargés : l'écriture suivante ne committait rien, en silence (prouvé sur PostgreSQL).
3. **`telegram_bot_initialization_failed: Conflict: terminated by other setWebhook`** à chaque déploiement : les N workers posaient le même webhook ensemble.
4. **`ConnectionClosedError (keepalive ping timeout)`** journalisé en ERROR à la fermeture normale d'une session Live : le ping keepalive de l'implémentation WebSocket héritée d'uvicorn attend un futur blindé dont personne ne consomme l'exception.

Un cinquième signal, `lia-web-prod` à 95,32 % de sa limite mémoire, n'était pas une fuite : Node **dérive la limite de son tas V8 du cgroup** (259 Mo dans un conteneur de 256 Mo), le tas seul pouvait donc remplir le conteneur.

## Décision

### (1) Une session ne vit pas plus longtemps que les requêtes qu'elle sert — jamais autour d'une attente

C'est la règle d'ADR-301, étendue à toute la base. Trois formes la tiennent :

- **Un client connecteur écrit à travers une unité de travail, jamais dans la session de son appelant** (`connectors/session_scope.py`). `DetachedConnectorService` ouvre, committe et rend une session par unité (un jeton rafraîchi, un connecteur invalidé) ; un client construit sur `ConnectorService(db)` obligeait `db` — et sa transaction — à rester ouverts pendant tout l'usage du client. **Garde exacte** (`test_connector_client_on_session_guard.py`) : aucun client n'est construit sur un `ConnectorService` lié à une session ; elle nomme l'argument du constructeur, pas un bloc de code, donc un job qui tient une session mais committe avant chaque appel réseau (la synchronisation Drive) n'est pas signalé, et aucune liste d'exceptions n'existe.
- **Une porte pour ouvrir le client actif d'une catégorie** (`connectors/active_client.py`) : fournisseur, credentials et nom du conteneur par défaut lus dans UNE session courte, fermée avant que le client ne serve ; le client est fermé sur tous les chemins (plusieurs sites ne le fermaient jamais). Les huit lignes recopiées dans le briefing, le heartbeat, les moments, le contexte téléphonique, la vue relations, les outils « pairs », le préchauffage des contacts et la recherche de contacts téléphonique passent par elle ; `open_active_calendar` y ajoute la résolution de l'agenda par défaut, séparée en moitié base (`read_owner_container_name`) et moitié réseau (`resolve_owner_container_id`).
- **Là où un job garde sa session, il termine sa transaction avant chaque attente** : lectures committées avant le parcours Drive et avant les embeddings, avant la synthèse d'une réunion et le choix de son modèle, avant l'extraction des boucles ouvertes et des intérêts, avant le regroupement des sujets, avant la synthèse de retour d'appel, avant les appels vendeur d'un appel téléphonique (sonde du zombie, synchro de l'agent, attache des outils, agenda), avant l'ouverture d'un canal push chez Google, avant la synchronisation des libellés Gmail. Chaque commit ajouté est dans une session que la fonction possède ; les objets restent attachés (`expire_on_commit=False`).

### (2) Le tour de chat

- **Chaque opération du service de connecteurs du tour termine sa transaction** (`ConcurrencySafeConnectorService`) : commit en sortie, rollback sur erreur, y compris les coroutines atteintes par `__getattr__`, qui passaient jusque-là hors du verrou. Les écritures propres d'un client (rafraîchissement, invalidation) ne tournent plus sous le verrou dans la session du tour : elles ont leur session courte. Un rafraîchissement relit les credentials dans cette session avant d'appeler le fournisseur, donc une carte d'identité périmée dans la session du tour ne provoque jamais de second rafraîchissement (pas de jeton de rafraîchissement Microsoft réutilisé après rotation).
- **La session du tour committe ses lectures de préparation avant le graphe.** Les serveurs MCP de la personne sont lus dans une session courte, les embeddings d'outils rafraîchis écrits dans une autre ; les noms de conteneur par défaut, la préférence de connecteur et les réglages de l'utilisateur de Perplexity sont lus dans des sessions courtes au lieu de la session partagée, hors verrou.
- **Le tampon `last_used_at` d'une clé API est écrit à part** (`connectors/api_key_use.py`) : UNE instruction atomique qui fusionne la clé dans le JSONB STOCKÉ, dans une transaction courte, sous un `lock_timeout` borné (`CONNECTOR_USE_STAMP_LOCK_TIMEOUT_MS`). Une LECTURE ne laisse plus de verrou dans la transaction de son appelant, et une clé écrite entre-temps par un autre (l'empreinte de l'agent téléphonique) n'est plus écrasée par un dict recalculé en Python. Prouvé sur PostgreSQL : `NOWAIT` réussit pendant la lecture, la clé concurrente survit, une ligne occupée est sautée dans son délai.

### (3) Le flux Drive poussé (ADR-261)

`rag_spaces/drive_push.py` : le **jeton du canal est la seule autorité** (le réveil n'en porte plus) et il avance par **comparer-et-échanger** (`advance_page_token`) ; pages de 1 000 ; drainage **borné en pages et en temps** (`RAG_DRIVE_PUSH_MAX_PAGES`, `RAG_DRIVE_PUSH_DRAIN_DEADLINE_SECONDS`) qui garde sa place et se remet en file ; après `RAG_DRIVE_PUSH_MAX_CONSECUTIVE_TRUNCATIONS` coupes d'affilée, le flux est **rebasé** et les arbres re-synchronisés en entier ; le jeton ne bouge que si **chaque arbre** a pris sa fenêtre ; l'application tourne sous le bail de la source, jamais dans le balayage. Le balayage sert **un réveil à la fois** sous un plafond (`PUSH_WAKE_SERVE_TIMEOUT_SECONDS`) : un réveil qui ne rend pas la main est coupé et compté `timeout`, il ne retient plus les neuf autres.

### (4) Les rappels : réclamés un par un, notifiés sans transaction

`get_and_lock_pending_reminders` verrouillait jusqu'à 100 lignes et gardait **une transaction ouverte pendant toutes les générations LLM et tous les envois du lot** — son commentaire « transition to PROCESSING to release lock » était faux, il ne faisait qu'un `flush`. Le motif canonique de `scheduled_actions` s'applique désormais, un rappel à la fois : `claim_next_due` (SKIP LOCKED, PROCESSING, **committé** aussitôt), notification sans transaction, règlement dans sa propre transaction **conditionné par la réclamation** (`get_processing_for_update` : un rappel supprimé entre-temps par sa propriétaire est laissé tel quel), et libération des réclamations abandonnées par un crash sur `updated_at` (`REMINDER_PROCESSING_STALE_TIMEOUT_MINUTES`). Prouvé sur PostgreSQL à deux acteurs. La fonction passe de CC 27 à moins de 8.

### (5) Telegram : le webhook est global au bot

Chaque worker construit le bot (il envoie, et la route webhook reçoit) ; **seul le leader du scheduler pose le webhook**, par une tâche ponctuelle (`SCHEDULER_JOB_TELEGRAM_WEBHOOK`, sans fenêtre de ratage : un leader élu tard la joue quand même). **L'arrêt d'un worker ne supprime plus le webhook** : un worker parmi N, ou l'ancien conteneur d'un déploiement, le supprimait pour tous les autres.

### (6) WebSockets : l'implémentation sans E/S

`--ws websockets-sansio` sur les trois lancements (image de production, image de dev, commande Compose de dev), l'option ajoutée au lanceur `src.serve` à la parité du CLI. Garde : `test_serve_launcher.py`.

### (7) Le conteneur web

Tas V8 borné sous la limite dans l'image (`NODE_OPTIONS=--max-old-space-size=320`), limite portée à 512M, démonstrateur aligné (même image, même plafond au lieu de 1g). La description de `ContainerMemoryNearLimit` ne prétend plus que le working set EST la grandeur de l'OOM (il compte les pages de fichiers actives, encore récupérables).

**Rejeté : `Cache-Control: immutable` sur `/models/`.** Les modèles de réveil vocal sont servis à des URL **non versionnées** : `immutable` épinglerait dans les navigateurs un modèle périmé après une mise à jour, sans aucun moyen de le rafraîchir. Il n'y a pas de gain mémoire côté serveur à attendre d'un en-tête de cache client.

### (8) Observabilité

- `push_wakes_enqueued_total{provider}` : ce que le webhook a MIS EN FILE, à côté de `push_wakes_total` (SERVI) ; tableau 13.
- **`PushWakeSweepStalled`** (noyau, ADR-119) : des réveils en file et aucun servi sur `ALERT_CORE_PUSH_WAKE_STALL_WINDOW` (30 min). Le côté servi lit `or vector(0)` : un compteur qui n'a jamais tiré n'expose aucune série, et « rien servi depuis le démarrage » était exactement l'incident. Trois cas promtool, runbook.
- `rag_drive_push_drains_total{end}` dit comment finit chaque drainage borné.

## Limites énoncées

- **Les routes HTTP** qui lisent puis appellent un fournisseur dans la session de requête gardent une transaction de lecture bornée par la requête et le délai du fournisseur ; leurs clients sont désormais construits sur une unité détachée (la garde le tient), mais leur session de requête n'est pas découpée.
- **L'envoi FCM** lit les jetons puis envoie dans une transaction courte (sous-seconde par appareil) ; les écritures de statut sont faites APRÈS tous les envois, pour qu'aucun verrou de jeton ne soit tenu pendant un envoi.
- **Un rappel notifié juste avant un crash** peut être renvoyé après la récupération de sa réclamation : livraison au moins une fois, comme avant.
- **La carte d'identité de la session du tour** peut garder un `Connector` périmé après un rafraîchissement écrit ailleurs ; le rafraîchissement relit dans sa propre session, ce qui couvre le seul cas qui compte (le jeton).

## Conséquences

Les copies de construction de client passent par la porte ou par une unité détachée, et les clients qu'aucun chemin ne fermait (mails et tâches du briefing, outils « pairs », préchauffage et recherche de contacts, réunions, disponibilités téléphoniques, découverte Hue, balayage des canaux push) le sont sur tous les chemins. Deux gardes AST (une session empruntée n'est jamais entrée ; un client n'est jamais construit sur une session). Preuves sur PostgreSQL réel — propriété de session d'un client, avance du jeton Drive par comparer-et-échanger, tampon de clé API, opérations du tour, réclamations de rappels à deux acteurs — et sur Redis réel pour la file de réveils. Le ratchet de complexité descend de 319 à 317 fonctions au-dessus du seuil.

## Amendement 2026-10-23 — Le serveur borne aussi : verrou et transaction inactive (audit AC-028)

**Amende** la décision : jusqu'ici, rien côté serveur ne disait qu'une session vit moins
longtemps que les requêtes qu'elle sert. Une attente de verrou durait autant que son
détenteur ; une transaction laissée ouverte pendant un appel réseau restait ouverte le temps
de l'appel.

**Décision.** Chaque connexion du moteur de l'application démarre avec deux bornes
PostgreSQL, envoyées à la connexion (`apps/api/src/infrastructure/database/server_bounds.py`,
`server_settings` d'asyncpg) : `lock_timeout` = `DATABASE_LOCK_TIMEOUT_MS` et
`idle_in_transaction_session_timeout` = `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` (0 laisse le
réglage du serveur). Ce sont des valeurs par défaut de connexion : une transaction se resserre
elle-même par `SET LOCAL` (la porte de rafraîchissement OAuth le fait), jamais l'inverse. Le
moteur des migrations n'en porte aucune — une migration peut tenir un verrou plus longtemps
qu'une requête ne doit l'attendre —, ni les pools psycopg de LangGraph. Aucun
`statement_timeout` global.

**Compter.** `handle_error` voit chaque échec du moteur, pas seulement ceux des dépôts, et
compte `db_bound_reached_total{bound}` : `55P03` et `57014` par leur SQLSTATE, jamais par le
message. La fin d'une transaction inactive fait exception, MESURÉE sur PostgreSQL 16 : asyncpg
la remonte comme une déconnexion nue, sans SQLSTATE (le 25P03 du serveur n'atteint pas le
client). Le moteur garde donc, par connexion, l'instant où sa transaction est devenue inactive,
et une déconnexion qui suit une inactivité au-delà de la borne est cette borne. Une connexion
invalidée n'est jamais relue : lire son `info` la revaliderait, et le rollback qui suit une
déconnexion levait alors `PendingRollbackError` (trouvé par le test PostgreSQL). Alerte
`DatabaseBoundReached` (seuil zéro), panneau du tableau 03, fiche
[DatabaseBoundReached](../runbooks/alerts/DatabaseBoundReached.md) ; les seaux de
`db_transaction_duration_seconds` vont désormais jusqu'à 600 s.

**Calibration.** La prod ne garde que quatre séries de l'exporteur PostgreSQL — aucune durée de
transaction ni attente de verrou — et la base n'a pas été lue directement (décision du
propriétaire). Sur sept jours de `db_transaction_duration_seconds`, 852 sessions sur 540 263
dépassaient 10 s, alors le dernier seau : leur durée était inconnue. Le pire cas de dev sur
quinze jours (53,5 s inactive en transaction, le 2026-10-07) n'est plus explicable, ses séries
ayant expiré. Les bornes retenues le 2026-10-23 sont donc prudentes — 30 s et 300 s, plus de
cinq fois ce pire cas — et la queue devient mesurable : elles se réévaluent sur le P99,9 après
déploiement.

**Preuves.** Sur PostgreSQL réel : une attente de verrou refusée dans sa borne et comptée, une
transaction inactive terminée par le serveur, comptée, puis le pool qui sert de nouveau, un
`SET LOCAL` prioritaire, et le moteur des sessions qui démarre borné — la suite d'intégration
tourne désormais sous les bornes de production. Tests unitaires et quatre mutants tués.

## Amendment 2026-10-28 — the turn commits before the MCP preparation; the progressive routes hold no session

Measured at runtime (spec 2026-10-21 §0ter H6): one backend stayed `idle in transaction` for the
whole personal-MCP preparation of a chat turn, its age following the wait. The turn's own writes
(state, archived request) are committed before the preparation starts
(`agents/api/turn_preparation.py`), and the preparation runs with no session open. The four
progressive dashboard routes authenticate through `get_current_active_session_for_stream` (a
session of its own, closed before the route): measured on Docker dev, a section read waiting 4 s on
a slow source held no `idle in transaction`, where the old `/briefing/cards` held one for the whole
wait.

## Amendment 2026-10-29 — the changes feed reads under the bulk-read budget, and the worst drain fits its wake

Measured on 2026-10-26 in production (read-only): 3 wakes of 1 292 in seven days failed on
`GET /changes`, each page waiting for its headers past the generic 5 s read budget three attempts in
a row, in the middle of a long feed — the pages already read were thrown away and the token did not
move. The network of the host was sound at those instants; Google was slow while the feed was long.
A page of 1 000 changes is a bulk read: `list_changes` now reads under `HTTP_TIMEOUT_CONNECTOR_LONG`
and connects under `HTTP_TIMEOUT_EXTERNAL_API` (`changes_feed_timeout`, a per-call budget of
`_make_request`); every other request keeps the client's.

A longer budget is only safe if the drain still ends before its wake is cut. The worst drain is its
deadline plus one page started just before it, every attempt and every backoff
(`drive_changes.worst_drain_seconds`, read from `retry_policy.worst_request_seconds`): 45 + 3 × (5 +
30) + 3 = 153 s with the defaults, under `PUSH_WAKE_SERVE_TIMEOUT_SECONDS` (180). The boot refuses a
configuration where it is not (`assert_drain_fits_a_wake`, in `run_failfast_validations`) — on a
deployment that drains a Drive feed only (`PUSH_CHANNELS_ENABLED`: the bulk-read budget also serves
attachments, and an instance without Drive push must not be refused for it), naming what the bound
does not count: a `Retry-After` beyond the backoff, the rate limiter's wait, a token refresh. No
request loop waits after its last attempt any more: after a final 429 or 5xx both loops slept their
backoff (4 s) before failing, which delayed every connector failure and ran the worst drain past the
bound (fresh review 2026-10-29).

**A page Google cannot serve no longer throws away the pages read before it** (lot 2 of the
2026-10-26 analysis). When a page fails for want of the provider (`ExternalServiceError`: every
attempt timed out, refused or failed in transport) after at least one page was read, the drain ends
like a cut one: the window read is offered, the token moves past it, the wake is re-queued, the end is
`interrupted`, and the cut counts toward the rebase streak exactly as a truncation does. When the
FIRST page fails, nothing was read and the wake fails as before — logged as a warning
(`rag_drive_push_feed_unavailable`, the transport cause only), never as an exception trace, because a
provider that did not answer is an expected event; any other failure keeps its trace. Both counters
(`rag_drive_push_reindex_total{outcome}`, `rag_drive_push_drains_total{end}`) are exported at zero for
every value at import (lot 3): Prometheus had counted 1 failed wake where Loki logged 3. Still open:
the channel renewal re-anchors the token (`push_channels/service.py`, `_open`) and would drop a window
still waiting — latent, never observed.
