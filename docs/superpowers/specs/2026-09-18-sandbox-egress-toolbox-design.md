# Le bac à sable comme boîte à outils — sortie réseau contrôlée, identifiants injectés au proxy, question à trois réponses

**Date** : 2026-09-18 · **Statut** : APPROUVÉE par le propriétaire le 2026-09-18 (six décisions, §2), zéro code · **ADR cible** : ADR-298 (amendant ADR-249, ADR-263, ADR-280, ADR-284, ADR-149/SEC-001, ADR-288) · **Source externe analysée** : Hermes Agent (`nousresearch/hermes-agent`, `77ecc72`, 2026-09-17) et iron-proxy (`ironsh/iron-proxy` v0.49.0)

## 0. Origine et verdict

Le tool `run_python_tool` (ADR-249) exécute du code écrit par le modèle dans un
conteneur jetable **sans réseau** (`--network none`, mesuré 2026-09-18 : une
seule interface `lo`, DNS / TCP / HTTP refusés). C'est ce qui rend l'injection
de prompt inoffensive : un script hostile ne peut qu'imprimer du texte.

Le propriétaire veut en faire **la boîte à outils de repli et de sur-mesure**
de la boucle ReAct : diagnostiquer un service tiers en panne, combler un outil
manquant par un client temporaire corrigé sur sa propre trace, transformer des
données avec un vrai socle de bibliothèques — avec un accès internet, « toutes
les précautions d'usage possibles mais non contraignantes ».

**Verdict** : lever `--network none` sans rien couper d'autre ouvrirait un canal
d'exfiltration parfait (le run reçoit sur stdin les e-mails et contacts lus ce
tour). La forme qui rend le besoin sûr existe, mesurée chez Hermes puis sur le
binaire : **un proxy de sortie à injection d'identifiants, seule porte d'un
réseau interne** — le conteneur ne tient que des jetons opaques, ne peut joindre
que des hôtes déclarés et permis, et la personne décide de l'inconnu.

Ce que Hermes fait et que LIA reprend : jetons opaques échangés par hôte et par
en-tête, liste d'autorisation refus-par-défaut, CIDR privés refusés à la
connexion (le DNS rebinding est fermé), fail-closed, gardes de collision.
Ce que Hermes déclare ne pas couvrir et que LIA ferme par la topologie : « un
socket brut contourne le proxy » — leur sandbox a un vrai réseau et
l'interception repose sur `HTTPS_PROXY` ; ici le sandbox est sur un réseau
`internal` dont le proxy est l'unique membre routé, un socket brut n'a nulle
part où aller. Ce que LIA a déjà et que Hermes n'a pas : le stdout du sandbox
marqué `untrusted` (Hermes n'enveloppe que web/browser/mcp), le registre des
effets, le code visible de l'administrateur.

## 1. Faits mesurés avant de décider

| Fait | Preuve |
|---|---|
| Le sandbox dev était **inopérant** depuis le 2026-08-03 : `SKILLS_SCRIPT_SANDBOX_IMAGE=lia-api` visait le tag prod, absent d'un hôte dev | `execute_source` → « Script sandbox unavailable » ; corrigé le 2026-09-18 (`lia-api-dev:latest` + `test_dev_sandbox_runs_on_the_dev_api_image`) |
| iron-proxy dernière stable **v0.49.0** (2026-07-19), image `ironsh/iron-proxy:0.49.0@sha256:c4628019c24f4cc8d77564a26b7c9cedb00accee6f93d06270e85fb8f9c6a7da`, amd64 + arm64 ; les 0.50 sont des rc | `gh api repos/ironsh/iron-proxy/releases`, Docker Hub |
| Schéma 0.49 validé en direct : `source: {type: file}`, `management` à bearer (401 sans, `{"status":"ok"}` avec), allowlist → 403, audit JSON `host`/`path` **sans query string**, `upstream_deny_cidrs` actifs | sonde `docker run … iron-proxy -config` |
| iron-proxy **ne génère pas sa CA** et refuse un simple auto-signé (« CA certificate missing KeyUsageCertSign ») ; l'image est Alpine + `openssl` + shell, root par défaut | sonde, `docker history` |
| `sandboxed ∈ PASS_THROUGH_POLICIES` : un run du sandbox **n'écrit aucune ligne** au registre des effets | `effects/gate.py` |
| Le normaliseur web **écarte** tout identifiant d'action hors `SUPPORTED_ACTIONS` | `apps/web/src/lib/hitl-payload.ts` |
| `draft_critique.build_metadata_chunk` fige trois boutons pour tous les types ; `destructive_confirm` en surcharge avec `STANDARD_DESTRUCTIVE_ACTIONS` | `services/hitl/interactions/*.py`, `services/hitl/schemas.py` |
| Les clients à clé personnelle déclarent déjà `api_base_url`, `auth_method`, `auth_header_name`, `auth_query_param` (Brave `X-Subscription-Token`, Perplexity `Authorization: Bearer`, OpenWeatherMap `?appid=`) | `connectors/clients/base_api_key_client.py` et sous-classes ; familles USER dans `usage_limits/cost_bearers.py` |
| Production tourne à `WEB_CONCURRENCY=4` : un registre en mémoire par worker écraserait les jetons des autres | ADR-271, ADR-283 |
| `OAuthLock` relâche **sans jeton propriétaire** ; `shared_flight._try_claim/_release` a la forme exigée (compare-and-delete) | `infrastructure/locks/oauth_lock.py`, `infrastructure/utils/shared_flight.py` |
| L'image dev embarque déjà 30 bibliothèques utiles (numpy, pandas, openpyxl, httpx, requests, aiohttp, bs4, lxml, PyMuPDF, python-docx, python-pptx, PIL, jinja2, yaml, jsonschema, orjson, msgpack, icalendar, vobject, dateutil, pytz, regex, tabulate, cryptography, jwt, dnspython, email_validator, zstandard, markdownify, chardet) ; le manifeste en annonce cinq. L'image « prod » présente sur l'hôte est un build périmé (Python 3.12) et ne prouve rien | sonde d'import sur `lia-api-dev:latest` |

## 2. Décisions du propriétaire

- **D1 — Identifiants (« B »)** : les clés API **personnelles** du compte (familles USER de `cost_bearers`) sont utilisables depuis un script, **sans jamais entrer dans le conteneur** : jeton opaque par run, échangé par le proxy sur l'hôte du connecteur uniquement. Jamais de jeton OAuth, jamais de clé d'instance.
- **D2 — Destinations (« A »)** : liste d'autorisation composée des hôtes **dérivés** des connecteurs à clé actifs du compte, d'une liste opérateur (`.env`) et des hôtes **accordés par la personne** ; tout hôte inconnu déclenche une question HITL **avant** exécution ; l'accord est mémorisé par compte.
- **D3 — Données (« A » + trois réponses)** : un run réseau reçoit les données du tour sur stdin, et la question offre **trois réponses** : autoriser avec les données / autoriser sans / refuser. La portée « données » d'un run est le **minimum** sur ses hôtes.
- **D4 — Mécanisme (« 1 »)** : iron-proxy en conteneur frère, seule porte d'un réseau Docker `internal`.
- **D5 — Rôle du tool** : le manifeste et le bloc `<Computation>` sont **réécrits** autour de quatre rôles (calculer, diagnostiquer, combler, transformer) ; « ça coûte un conteneur » disparaît.
- **D6 — Bibliothèques** : déclarer ce qui existe ; ajouter cinq paquets purs Python (`xmltodict`, `feedparser`, `phonenumbers`, `pycountry`, `unidecode`).

Deux choix pris par l'analyse, renversables : le proxy tourne sous le **même uid** que l'API (pas de `chown` inter-uid) ; `HTTP_PROXY` n'est **pas** posé (aucun HTTP en clair, même via proxy).

## 3. Topologie et cycle d'un run

### 3.1 Réseaux, volumes, services

- Réseau `lia-sandbox` (`internal: true`) : chaque conteneur jetable **réseau** + le proxy. Le proxy est aussi membre de `lia-network` (routé en dev et en prod), où l'API le joint pour `POST /v1/reload`. **L'API n'est pas sur `lia-sandbox`** : elle y serait joignable par un script.
- Service `egress-init` (image iron-proxy, `restart: "no"`, root) : au premier démarrage, génère la CA avec `openssl` et des extensions x509 v3 (`basicConstraints=critical,CA:TRUE,pathlen:0`, `keyUsage=critical,keyCertSign,cRLSign`), le bearer de gestion (256 bits), puis `chown` vers `LIA_RUNTIME_UID`. Script : `infrastructure/sandbox-egress/ca-init.sh`.
- Service `egress` (`ironsh/iron-proxy:0.49.0@sha256:c4628019c24f4cc8d77564a26b7c9cedb00accee6f93d06270e85fb8f9c6a7da`, `user: ${LIA_RUNTIME_UID}`, `cap_drop: [ALL]`, `no-new-privileges`, `mem_limit: 256m`, `pids_limit: 128`, `depends_on: egress-init: service_completed_successfully`).
- Trois volumes nommés **avec `name:` explicite** (sinon Compose les préfixe du nom de projet et le `docker run -v` lancé depuis l'API ne les trouve pas) :
  - `lia-egress-ca` — `ca.crt` seul ; monté `:ro` dans le sandbox (`/etc/lia-egress/ca.crt`) et dans le proxy ;
  - `lia-egress-key` — `ca.key` + `management.token` ; proxy (et API pour le token) ; **jamais le sandbox** (test de contrat compose) ;
  - `lia-egress-config` — `proxy.yaml` + `secrets/<run_id>/<connector>.key` ; **tmpfs** (`driver_opts: type: tmpfs, o: uid=${LIA_RUNTIME_UID},mode=0700`) : rien ne touche le disque, tout disparaît à l'arrêt ; API rw, proxy ro.
- Où : `docker-compose.dev.yml` (en clair) et `docker-compose.skill-sandbox.yml` (prod : le sandbox n'existe qu'avec cet overlay — socket, `SKILLS_SCRIPTS_ENABLED`, et désormais le proxy et `PYTHON_SANDBOX_EGRESS_ENABLED=true`). L'installateur (`scripts/install/compose.py`) n'a rien à apprendre : l'overlay porte tout. Les compose du démonstrateur ne changent pas (pas de socket, capacité off).

### 3.2 Le run réseau

`_build_sandbox_command` reste **l'unique constructeur** (SEC-001) ; il reçoit un `EgressSpec | None` :

- `None` → l'argv d'aujourd'hui, `--network none` (golden inchangé) ;
- sinon : `--network lia-sandbox`, `-v lia-egress-ca:/etc/lia-egress:ro`, `--env HTTPS_PROXY=http://egress:3128`, `--env SSL_CERT_FILE=/etc/lia-egress/ca.crt`, `--env REQUESTS_CA_BUNDLE=…`, `--env CURL_CA_BUNDLE=…`, et un `--env LIA_KEY_<CONNECTOR>=<jeton>` par identifiant du run. Pas de `HTTP_PROXY`, pas de `NO_PROXY`.

Délai d'un run réseau : `PYTHON_SANDBOX_NETWORK_TIMEOUT_SECONDS` (défaut 60 ; un diagnostic attend un service lent), transmis par `execute_source(timeout_seconds=…)` qui existe déjà. Le proxy plafonne un corps de requête à `PYTHON_SANDBOX_EGRESS_MAX_BODY_BYTES` (1 Mio), publié.

### 3.3 Les règles, rendues par LIA, seule autrice

Module `domains/agents/python_sandbox/egress/` :

- `registry.py` — **les runs réseau vivants sont en Redis**, famille `sandbox_egress` (scope `GLOBAL`, déclarée dans `key_families.py`) : `sandbox_egress:run:<run_id>` → `{user_id, hosts, credentials: [{connector, token, secret_path, header|query}], expires}` avec TTL = délai du run + grâce de démarrage + 30 s, et un index `sandbox_egress:runs` (SET). Une entrée est écrite avant le `docker run` et retirée dans un `finally` ; une entrée orpheline expire.
- `ruleset.py` — rend `proxy.yaml` depuis **toutes** les entrées vivantes : `transforms: [allowlist{domains = ∪ hôtes de tous les runs vivants}, secrets{une règle par identifiant : source file, proxy_value = jeton, match_headers ou match_query selon auth_method, require: true, rules: [{host}]}]`, `proxy.upstream_deny_cidrs` (liste ADR : loopback v4/v6, link-local, RFC1918, ULA, `::ffff:0:0/96`, CGNAT, `198.18.0.0/15`), `tls`, `management{listen: 0.0.0.0:9093, api_key_env}`, `metrics{listen: 0.0.0.0:9094}`, `log{level: info}`. Rendu **golden** en test. Les fichiers secrets sont écrits `0600` sous `secrets/<run_id>/` et supprimés avec l'entrée.
- `proxy_client.py` — `reload()` (bearer lu dans `lia-egress-key/management.token`, délai `PYTHON_SANDBOX_EGRESS_RELOAD_TIMEOUT_SECONDS` = 5) et `healthy()`.
- Écriture sous un verrou Redis **à jeton propriétaire** (compare-and-delete), extrait de `shared_flight._try_claim/_release` en `infrastructure/locks/redis_claim.py` ; `OAuthLock` n'est pas réutilisé (release inconditionnelle).
- Boot (ADR-123, `startup/agents.py`) : si la capacité est active, rendre depuis Redis et `reload` — un worker qui redémarre ne vide pas les runs des trois autres ; le proxy, lui, recharge le YAML présent.

**Fail-closed** : proxy injoignable, `reload` refusé ou hors délai, CA absente, verrou non obtenu → le run réseau est **refusé** avec sa raison (`ToolErrorCode.CONFIGURATION_ERROR`, message technique anglais, ADR-256), compté `proxy_unavailable`, jamais dégradé vers un réseau routé. Un run sans réseau n'est pas concerné.

## 4. Le contrat du tool et la question à trois réponses

### 4.1 `hosts`

`run_python_tool(code, purpose, hosts: list[str] = [])`. Le manifeste publie (ADR-184) : noms d'hôte exacts, minuscules, IDNA (un hôte non-LDH ou un homographe est refusé), sans port ni schéma ni IP, dédupliqués, au plus `PYTHON_SANDBOX_MAX_HOSTS_PER_RUN` (5) ; vide = pas de réseau ; le proxy n'autorise que `hosts ∩ permis` et répond 403 à tout autre hôte, ce qui dit au modèle de le déclarer.

### 4.2 Quatre statuts, décidés avant tout `docker run` (`hosts.py`)

| Statut | Source | Identifiant | Données |
|---|---|---|---|
| `connector` | `api_base_url` d'un client à clé dont le connecteur est **actif** pour le compte (`ConnectorService.get_user_connectors`, statut actif) | jeton frappé | fournies |
| `operator` | `PYTHON_SANDBOX_EGRESS_HOSTS` | aucun | fournies |
| `grant` | `sandbox_egress_grants` du compte | aucun | selon l'accord |
| `unknown` | — | — | → question |

Un service à clé d'**instance** (Gmail, fournisseur LLM) n'est jamais dérivé : sonder son hôte passe par la question une fois, puis par l'accord, sans identifiant.

**Règle du minimum** : `share_turn_data` du run = ET logique sur ses hôtes ; un hôte accordé « sans » impose « sans » au run entier.

### 4.3 La question (`DraftType.SANDBOX_EGRESS`)

Un seul `unknown` → le tool rend un brouillon (`DraftService.create_draft`, comme `effects/confirmation.py::confirmation_draft`), `requires_confirmation=True`, que `_extract_draft_info` (ReAct) remet à `draft_critique` comme tout brouillon. Contenu : `hosts_unknown`, `hosts_known` (avec leur statut), `purpose`, `data_summary` (comptes par domaine depuis `current_turn_registry`, jamais le contenu), `tool_args` (l'appel intact, pour le rejeu). **Le code n'est pas sur la carte** (ADR-249 §8 : panneau de debug seul).

Boutons, déclarés par type dans `build_metadata_chunk` (le précédent est `STANDARD_DESTRUCTIVE_ACTIONS`) :

| `action` | `label` | style |
|---|---|---|
| `confirm` | `allow_with_data` | primary |
| `confirm_without_data` | `allow_without_data` | secondary |
| `cancel` | `refuse` | destructive |

Web : `SUPPORTED_ACTIONS` de `hitl-payload.ts` gagne `confirm_without_data` (sans quoi le bouton disparaît en silence) ; `DraftPreview` gagne une branche `draftType === 'sandbox_egress'` (hôtes, motif, comptes). Backend : `_STRUCTURED_ACTION_ALIASES["confirm_without_data"] = "confirm"` et la charge de reprise porte `share_turn_data: false` ; `draft_sequence.decision_entry` copie le drapeau dans l'entrée (ADR-288) ; l'exécuteur `execute_sandbox_egress_draft` (enregistré dans `draft_executor_registry`) **écrit l'accord puis** rejoue l'appel sous `approved_scope`, comme `execute_tool_call_draft`. Réponse en texte libre : le classifieur ne connaît que confirmer / modifier / annuler → confirmer = avec les données. Ticket workboard : `workboard/answers.classify_answer` → approuver = avec les données ; la nuance « sans » est un bouton du chat et un réglage.

Au plafond d'accords, l'autorisation vaut **pour ce run seul** (`one_shot`), la carte le dit en une ligne.

### 4.4 Ce que le run rend

`turn_data_shared: bool` dans `structured_data`, à côté de `stdout` marqué `untrusted` (inchangé) ; sur échec, la trace, comme aujourd'hui. Réseau = HTTPS via proxy, rien d'autre — pas d'ICMP, de DNS brut, de TCP : un « test de connexion » est un `GET`, ses codes et ses latences, et le manifeste le dit.

## 5. Accords et contrôles

### 5.1 La personne

Table `sandbox_egress_grants` (`UUIDMixin`, `TimestampMixin`) : `user_id` FK `ON DELETE CASCADE`, `host` (String 253), `share_turn_data` (bool), `last_used_at` ; unique `(user_id, host)`. Migration + `import_all_models` + `db:migrate:replay-check`. Ce sont des **décisions**, pas un apprentissage : la réinitialisation de conversation et « Tout oublier » n'y touchent pas (table Postgres, hors familles Redis) ; la suppression du compte les emporte.

Routes (`python_sandbox/egress/router.py`, sous `/sandbox/egress-grants`, `Depends(get_current_active_session)`, garde de capacité) : `GET` (page + total exact, ordre `created_at desc, id`), `PATCH /{id}` (portée), `DELETE /{id}`, `GET /reachable` (hôtes `connector` + `operator`, lecture seule). Plafond `PYTHON_SANDBOX_MAX_GRANTS_PER_USER` (50) publié dans la réponse.

Section de réglages `sandbox-egress` (`settings-sections.ts`, registry, icône, `useSettingsAvailability`, épinglable au dock ADR-277) : deux listes — « ce que LIA peut joindre sans demander » et « mes accords » (hôte, portée modifiable, dates, révoquer). Mobile-first (une colonne à 360 px, cibles ≥ 44 px), noms accessibles traduits, focus rendu à la liste après révocation, états vide / chargement / erreur.

### 5.2 L'opérateur (`.env` ; ADR-280 : une capacité, un interrupteur)

| Variable | Défaut | Rôle |
|---|---|---|
| `PYTHON_SANDBOX_EGRESS_ENABLED` | `false` en base prod, `true` dans l'overlay `skill-sandbox` et en dev, `false` démos | `PlatformCapability.PYTHON_SANDBOX_EGRESS` (famille `reach`, `service_enforced`, lue à l'acte, hors carte avec raison) |
| `PYTHON_SANDBOX_EGRESS_ASK_ENABLED` | `true` | à `false`, l'inconnu est refusé au lieu de demandé |
| `PYTHON_SANDBOX_EGRESS_HOSTS` | vide | liste opérateur |
| `PYTHON_SANDBOX_EGRESS_PROXY_URL` | `http://egress:3128` | ce que le sandbox reçoit |
| `PYTHON_SANDBOX_EGRESS_MANAGEMENT_URL` | `http://egress:9093` | `reload` |
| `PYTHON_SANDBOX_MAX_HOSTS_PER_RUN` | 5 | |
| `PYTHON_SANDBOX_MAX_GRANTS_PER_USER` | 50 | |
| `PYTHON_SANDBOX_NETWORK_TIMEOUT_SECONDS` | 60 | |
| `PYTHON_SANDBOX_EGRESS_MAX_BODY_BYTES` | 1048576 | |
| `PYTHON_SANDBOX_EGRESS_RELOAD_TIMEOUT_SECONDS` | 5 | |
| `PYTHON_SANDBOX_MAX_RUNS_PER_TURN` | 3 → **5** | un essai, trois corrections, une vérification |
| `LIA_RUNTIME_UID` (compose) | 1000 prod, 0 dev | uid commun API / proxy |

Huit fichiers d'environnement suivent (`.env`, `.env.example`, `.env.prod.example`, `.env.min.prod.example`, les quatre du démonstrateur à `false`).

## 6. Le contrat vivant

### 6.1 Manifeste (`python_sandbox/catalogue_manifests.py`)

Quatre rôles, dans l'ordre : **calculer** (existant), **diagnostiquer** (sur `EXTERNAL_API_ERROR` / `TIMEOUT` d'un outil, sonder le service en HTTPS et distinguer « le tiers est en panne » / « refus d'authentification » / « le problème est chez nous », avec code et latence mesurés), **combler** (écrire et exécuter un client temporaire, avec `LIA_KEY_*` s'il existe pour cet hôte, sinon une API publique, et **corriger son propre code** sur la trace), **transformer**. « Ne pas l'utiliser » recentré : pas pour ce qu'un outil existant fait, pas pour un calcul à deux nombres. `semantic_keywords` étendus (panne, service manquant, intégration, API, sonde). Paramètre `hosts` publié avec ses bornes. `initiative_eligible=False`, `execution_modes={react}`, `mutation_policy="sandboxed"` inchangés. Budget ≤ 350 tokens (mesuré par `react_bound_tool_tokens`).

### 6.2 `<Computation>` (`prompts/v1/react_computation_prompt.txt`, `react_prompt.py`)

Rendu ssi tool lié et capacité active (existant). Contenu : les quatre rôles en deux phrases, `{reachable_hosts}` (connecteurs actifs + opérateur, avec pour chacun l'identifiant disponible et son en-tête : « `LIA_KEY_BRAVE_SEARCH` → `X-Subscription-Token` sur `api.search.brave.com` »), la règle « tout autre hôte doit être déclaré dans `hosts` et sera demandé à la personne, qui peut retirer les données », HTTPS via proxy uniquement, `{libraries}`, et les bornes par placeholders (`{python_sandbox_max_runs_per_turn}`, `{network_timeout}`, `{max_hosts}`, `{max_body}`, mémoire, stdout). Sans hôte joignable et sans réseau (capacité EGRESS off), la section réseau n'est **pas** rendue (ADR-284 : ne promettre que ce que le tour peut faire). Les hôtes sont calculés dans `react_setup_node` (un `get_user_connectors` par tour) et passés à `build_system_prompt`. Mesure avant/après sur dev : le bloc passe de ~140 à ~300 tokens.

### 6.3 Bibliothèques

`python_sandbox/libraries.py::PYTHON_SANDBOX_LIBRARIES` — nom d'import, un mot d'usage, groupe (HTTP et parsing, données et tableurs, dates et calendriers, documents et images, formats et encodage, crypto et validation). Rendue dans le bloc ; **testée par import dans l'image de sandbox** (job CI sur l'image construite — l'image « prod » locale ne prouve rien). Ajouts : `xmltodict`, `feedparser`, `phonenumbers`, `pycountry`, `unidecode` (`requirements.txt` + `task deps:lock`, ADR-112) ; jamais importés par l'API (garde `LAZY_ONLY` sans objet, vérifié). Écartés : `matplotlib`/`scipy` (lourds, un run ne rend que du texte), `pypdf`/`pdfplumber` (`fitz` couvre), `markdown` (`jinja2` suffit), `rich`, `tldextract` (réseau à l'import), `validators`.

## 7. Registre, observabilité, pannes

- **Effet** : `sandboxed` reste pass-through pour un run sans réseau. Un run **réseau** est **réclamé avant** `docker run` et **clos** du résultat, via une couture en-tour `effects/direct_effects.py` extraite de `out_of_turn_effects._claim/_close` (`ClaimRequest` construit par `runtime._build_request` depuis `runtime_context_if_running()` ; idempotence `sandbox:<run_id>`) ; le libellé porte `hosts`, `turn_data_shared` et la source de chaque autorisation (`connector` / `operator` / `grant` / `one_shot`). La docstring de `PASS_THROUGH_POLICIES` (« no network ») est corrigée. Les consultations (`treatment_labels`, `python_sandbox`) sont inchangées.
- **Métriques** (ratchet : chaque série sur un panneau ou une alerte) : `python_sandbox_egress_runs_total{outcome=allowed|asked|refused|proxy_unavailable}`, `python_sandbox_egress_grants_total{decision=with_data|without_data|refused|one_shot}`, jauge `lia_python_sandbox_egress_enabled` ; scrape `lia-egress` (`egress:9094`) ; panneaux sur le tableau 07 (à côté de `agent_tool_invocations{run_python}`). Alerte `SandboxEgressProxyDown` : `lia_python_sandbox_egress_enabled == 1 and up{job="lia-egress"} == 0` pendant 5 min, runbook `docs/runbooks/alerts/SandboxEgressProxyDown.md`, `EvidenceRecipe` (`dependency_up`, événements `sandbox_egress_proxy_unavailable`, `sandbox_egress_reload_failed`).
- **Journal** : celui du proxy (host, path, action, status), ramassé par Promtail comme tout conteneur ; query et corps jamais journalisés ; rien n'est recopié en base.
- **Pannes** : cf. §3.3 (fail-closed compté) ; un run qui lève retire son entrée dans `finally` ; un worker tué laisse une entrée qui expire par TTL ; `docker rm --force` existant sur dépassement.

## 8. Cas limites, résidus consignés

Cas traités : hôte se résolvant en IP privée (403 CIDR → trace au modèle) ; DNS amont en échec (502 du proxy) ; connecteur désactivé entre l'accord et le run (redevient `unknown`, pas de jeton) ; accord révoqué pendant un run (règles déjà chargées, le run suivant demande) ; doublons et casse ; deux runs simultanés du même compte (deux jetons) ; redémarrage de l'API pendant un run (registre Redis) ; capacité coupée entre la question et le rejeu (refus à l'acte) ; séquence ADR-288 avec d'autres brouillons ; ticket workboard ; plafond d'accords.

Résidus consignés dans l'ADR, non cachés :
1. « Sans les données » borne la lecture en masse par le code, pas ce que le modèle retape depuis son contexte (source ≤ 256 Ko).
2. Exfiltration vers un hôte **autorisé** (corps d'une requête Brave) : journalisée, pas empêchée — le résidu d'un outil Brave ordinaire.
3. Un jeton de run survit ≤ TTL à un crash ; inutilisable hors du réseau sandbox et hors de son couple (hôte, en-tête).
4. Port de gestion (bearer 256 bits) et métriques (agrégats) visibles depuis le sandbox : une adresse d'écoute par démon.
5. Deux sandboxes partagent `lia-sandbox` ; aucun n'écoute.
6. Le proxy voit le clair (MITM) ; c'est notre conteneur ; `path` journalisé.
7. Le quota du service tiers appartient à la personne (sa clé, jamais comptée — directive 2026-09-16), borné par le délai du run.

## 9. Plan de test

**Unitaires** — `hosts.py` (validation IDN/port/IP/doublons/plafond, quatre statuts, minimum, connecteur inactif) ; `ruleset.py` (YAML golden à deux runs / trois identifiants / un opérateur / un accord, fichiers 0600, aucune query) ; `registry.py` (deux runs, TTL, `finally` après exception, rendu au boot depuis Redis) ; `proxy_client.py` (401 / ok / délai → refus compté) ; tool (sans `hosts` = argv golden inchangé ; `unknown` → brouillon et **aucun** `docker run` ; `share_turn_data=False` → stdin `{"items": {}}` et `turn_data_shared: false` ; plafond → `one_shot`) ; brouillon (contenu, aperçu ×6, résumé, exécuteur : accord écrit **avant** rejeu sous `approved_scope`, `decision_entry` porte le drapeau, aliases) ; effet (claim avant, close après, libellé ; pass-through sans hôtes) ; gardes existantes (partition capacités, off-map, couverture métriques, familles de clés, politiques de mutation, placeholders de prompt, `test_react_turn_reset_guard`, taille de fichiers) ; nouvelles gardes : `PYTHON_SANDBOX_LIBRARIES` = imports réels dans l'image, contrat compose (réseaux, volumes nommés, `lia-egress-key` jamais dans l'argv sandbox, `HTTP_PROXY` absent).

**Intégration (PostgreSQL / Redis)** — accords : unicité, plafond, page + total, cascade ; verrou : deux acteurs, expiration, reprise.

**Mesure Docker dev** (`task sandbox:egress:probe`, forme `mobile:probe`) — DNS / TCP bruts refusés ; hôte permis → 200 via proxy avec jeton **échangé** (statut 200 / 401 distingués contre le service réel du compte de test) ; hôte non déclaré → 403 ; IP privée → refus ; clé CA absente du conteneur ; reload concurrent ; le **vrai prompt** ReAct assemblé avec et sans identifiants (ADR-284).

**Frontend** — vitest : normaliseur (l'action survit), carte à trois boutons (clavier, noms accessibles), `DraftPreview` egress, section réglages (liste, révocation, portée, vide, erreur, chargement) ; e2e hermétique : parcours carte HITL egress sur SSE mocké (`e2e/fixtures/chat.ts`) + axe.

## 10. Lots

0. **Socle proxy** — image épinglée, `ca-init.sh`, compose dev + overlay, volumes/réseaux, scrape, `task sandbox:egress:probe` à blanc (proxy vivant, 403, reload).
1. **Registre & ruleset** — famille Redis, `redis_claim.py`, YAML golden, secrets, client reload, étape de boot.
2. **Run réseau** — `EgressSpec`, `hosts` + validation + classification, `LIA_KEY_*`, délai propre, effet ledgerisé, métriques, panneaux, alerte, recette, runbook. Sonde : 200 avec jeton échangé.
3. **Accords** — modèle, migration, repo, service, routes, plafond, capacité `PYTHON_SANDBOX_EGRESS` (+ `ASK`), `.env` ×8, off-map.
4. **Question à trois réponses** — `DraftType.SANDBOX_EGRESS` (display / preview / summary / i18n / exécuteur), actions par type, aliases + drapeau, `decision_entry`, web (`SUPPORTED_ACTIONS`, carte, locales ×6), e2e.
5. **Le contrat vivant** — manifeste, `<Computation>` v2, hôtes/identifiants par tour, `PYTHON_SANDBOX_LIBRARIES` + test d'import, cinq paquets + lock, `MAX_RUNS_PER_TURN` 5, mesure tokens.
6. **Réglages** — section web, hooks, locales, dock, tests.
7. **Documents et clôture** — ADR-298, `REACT_EXECUTION_MODE.md`, guides d'installation, `CLAUDE.md` + `task docs:sync-agents`, `docs/INDEX.md`, `ADR_INDEX.md`, ratchets relevés, `ci:fast`.

Dépendances : 0 → 1 → 2 ; 3 et 5 après 2 (parallélisables) ; 4 et 6 après 3 ; 7 en dernier. Chaque lot rouge → vert avant le suivant ; chaque changement de comportement mesuré sur Docker dev, jamais en local.

## 11. Hors périmètre

Jetons OAuth dans le sandbox ; clés d'instance ; réseau par run ; HTTP en clair ; extension au mode pipeline (ADR-249 §2 tient) ; un scanner advisory de la sortie (Hermes) — peut-être plus tard, à part.

## 12. Écarts mesurés à la livraison (2026-09-18)

Consignés ici parce que la spécification est ce qui a été approuvé, et l'ADR ce qui a été construit ; l'écart entre les deux est une mesure, pas une négligence.

- **§3.1 conteneur d'init → point d'entrée.** Docker rend le tmpfs à la sortie du conteneur d'init : le proxy démarrait vide. L'état (CA x509 v3 avec `keyCertSign`, jeton de gestion, YAML d'amorçage) est frappé par le point d'entrée du proxy lui-même, dans trois volumes tmpfs possédés par `LIA_RUNTIME_UID` ; ni root, ni `chown`.
- **§7 métriques du proxy → sonde blackbox.** iron-proxy 0.49.0 n'expose aucune série Prometheus (404 mesuré) : `SandboxEgressProxyDown` lit `probe_success{job="blackbox-egress"}` sur `/healthz`, et la jauge `python_sandbox_egress_enabled` dit si l'absence compte.
- **§6.2 coût du bloc.** Estimé ~140 → ~300 ; mesuré (o200k) 439 sans réseau, 692 avec quatre hôtes. Chaque phrase énonce un rôle ou une règle imposée ; rien n'a été ajouté « au cas où ».
- **§6.2 la ligne d'identifiant épelle la lecture.** Au premier vrai tour sur dev, « `LIA_KEY_BRAVE_SEARCH` dans l'en-tête » a fait envoyer le NOM de la variable comme valeur (422 `SUBSCRIPTION_TOKEN_INVALID`, deux fois, sans autocorrection possible). La ligne rendue est désormais « `os.environ["LIA_KEY_…"]` in the header … » ; le tour suivant a atteint Brave avec la clé échangée (200, un seul run).
- **§6.3 bibliothèques : 22, pas 30.** Le manifeste promet ce qu'un script utilise (HTTP et parsing, données et tables, dates et calendriers, documents, texte et formats) ; six des présentes étaient TRANSITIVES et sont désormais épinglées directement (`requests`, `beautifulsoup4`, `lxml`, `tabulate`, `icalendar`, `chardet`) ; les cinq ajouts sont là. Écartées en plus de la liste de la spec : `dnspython` (le sandbox n'a pas de DNS propre), `Pillow`, `python-pptx`, `xlsxwriter`, `orjson`, `jsonschema`, `cryptography`, `pydantic`, `jinja2` (un run ne rend que du texte ; la bibliothèque standard couvre).
- **§4.3 le rejeu voyageait sur le fil.** `hitl_interrupt_metadata.action_requests[0].draft_content.replay` portait le script ET les items jusqu'au navigateur ; l'exécuteur lit l'état, la carte lit hôtes/motif/décompte : le rejeu est retiré de la projection filaire.
- **Trouvé en chemin : `react_scripts` s'accumulait toute la vie du fil** (le fil est la conversation). Rejoint `react_turn_reset()`, la déclaration unique.
- **§10 lot 5 : une dérivation partagée.** Les hôtes joignables (connecteurs actifs + opérateur) sont dérivés UNE fois (`egress/offer.py::merge_reachable`) pour le prompt et pour la page de réglages ; le prompt est best-effort (une lecture de connecteurs en échec garde les hôtes opérateur et journalise), la page est exacte.
- **`.env.min.prod.example`** ne porte rien : la capacité est OFF par défaut et n'exige aucune variable.
- **§4.3 le brouillon n'est PAS exécuté par le dispatch : la question se règle DANS la boucle.** Mesuré par le propriétaire (2026-09-18) : « regarde mes 5 derniers mails … ; vérifie aussi que httpbin.org répond » → carte, autorisation, puis SEUL httpbin exécuté — le dispatch exécute un brouillon et répond de son résultat, il ne reprend jamais la boucle. Désormais `nodes/react_egress_question.py` lève l'interruption depuis le nœud (même charge utile, même carte, mêmes trois boutons), enregistre l'accord à la reprise et ré-invoque LE MÊME appel sous l'accord (`tool_path.approved_for_call`, portée d'effet dérivée « approuvée par la carte ») ; l'exécuteur `execute_sandbox_egress_draft`, le rejeu dans le brouillon et le champ de décision porté dans le contenu sont supprimés. Deux corollaires mesurés : une question ne coûte aucun run du tour ; `interrupt()` remonte de l'intérieur de l'appel et le filet « toute erreur d'outil devient un message » l'avalait — re-levé avant le filet. Vérifié sur dev : question, réponse « avec les données », ré-invocation, autocorrection d'un 415, les deux volets répondus en quatre itérations.
- **§7 panneaux** : `rate()` de quelques décisions humaines par jour lisait vide — les deux compteurs sont dessinés en COMPTES (runs par intervalle, réponses sur la plage).
- **Revue à froid finale (2026-09-18)** : liste de refus complétée (`0.0.0.0/8` — Linux le route vers loopback —, `::/128`, `64:ff9b::/96` NAT64) et tenue par un test sur chaque famille d'adresses ; sondé depuis le réseau sandbox : l'API de gestion répond 401 sans bearer sur chaque point, `CONNECT 0.0.0.0` refusé ; §8 gagne un résidu explicite : l'allowlist du proxy est l'UNION des runs vivants (une par démon en 0.49), deux runs simultanés voient les hôtes l'un de l'autre, jamais leurs jetons ; la trace d'un script en échec est marquée `untrusted` comme sa sortie ; le marquage des accords utilisés a UNE implémentation (`grants.mark_relied_grants`).
