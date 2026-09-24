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
