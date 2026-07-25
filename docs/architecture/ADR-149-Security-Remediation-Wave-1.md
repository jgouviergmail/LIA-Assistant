# ADR-149 : Remédiation sécurité 2026-07 — vague 1

**Status**: ✅ IMPLEMENTED (2026-07-25)
**Date**: 2026-07-25
**Deciders**: jgouvier + Claude
**Technical Story**: Audit sécurité externe du 2026-07-13 (`docs/audit/AUDIT_SECURITE_CODEBASE_LIA_2026-07-13.html`). Chaque constat a été re-vérifié dans le code avant d'être traité : plusieurs étaient des faux positifs, et l'audit avait manqué des défauts voisins que la vérification a exhumés (SEC-030, SEC-032, FN-3, FN-5).

Cet ADR ne réécrit pas le rapport d'audit. Il consigne les **décisions d'architecture** prises pour y répondre, avec ce qui a été mesuré.

## Décisions

### 1. Les scripts de skills s'exécutent dans un conteneur jetable (SEC-001)

Le chemin historique tombait à un uid non privilégié *avant* `exec`. Cette défense ne vaut **que si l'API tourne en root** : en production elle tourne en `appuser`, membre du groupe `docker`, et un processus fils **hérite du groupe** — donc de la socket Docker montée en lecture/écriture. Un script de skill valait root sur l'hôte.

Deux options ont été mesurées avant d'arbitrer :

- **`cap_add SETGID` pour purger les groupes sans être root** — testé, `PermissionError` avec et sans `no-new-privileges`. `cap_add` ne fournit pas de capacité *ambiante* à un processus non root : la voie est fermée, pas seulement inconfortable.
- **Conteneur éphémère par exécution** — retenu. Il ne dépend d'aucune capacité et supprime l'héritage par construction.

Le **source** du script est passé en argument (`python -c`) plutôt que monté. L'API étant elle-même un conteneur, un `-v /app/data/skills/...` se résoudrait contre le système de fichiers de **l'hôte** (les skills système sont un bind depuis `~/lia/data/skills/system`, les skills utilisateur un volume nommé) : le montage serait silencieusement vide. Passer le source règle ce problème *et* laisse stdin libre pour la charge JSON, contrat dont dépend chaque skill existante.

Le mode dégradé n'existe pas : sans démon Docker joignable, l'exécution est **refusée** (`Script sandbox unavailable`). Un bac à sable qui se désactive tout seul ne protège de rien — la désactivation est précisément ce qu'un attaquant cherche.

**Preuves runtime** (conteneur de dev, code réel) :

| Sonde | Résultat |
|---|---|
| `uid` / `os.getgroups()` | `65534` / `[65534]` — plus aucun groupe hérité |
| `/var/run/docker.sock` | absente du système de fichiers, `connect()` → `FileNotFoundError` |
| Réseau | `--network none` → `OSError` |
| Écriture rootfs / lecture `config/firebase-*.json` | `OSError` / `FileNotFoundError` |
| Variables d'environnement visibles | seulement `GPG_KEY` (celle de l'image Python) — aucun secret LIA |

**Non-régression prouvée par différentiel** : les 10 scripts de skills livrés exécutés dans les deux modes, mêmes paramètres — **sortie identique octet pour octet sur 9/10**. Le dixième (`dice-roller`) diffère par `secrets.randbelow`, non par le bac à sable.

**Défaut trouvé pendant l'implémentation, corrigé** : tuer le client `docker run` sur timeout **n'arrête pas le conteneur** (mesuré : `Up 6 seconds` après le timeout). Un script qui dort ne consomme aucun CPU, donc ni le rlimit CPU ni `--rm` ne le récupèrent — il survivrait indéfiniment. Chaque exécution reçoit donc un nom unique et le chemin timeout force `docker rm --force`, dans le **thread de travail** pour que le nettoyage survive à l'annulation de la coroutine appelante. Vérifié : `AFTER: []`.

### 2. Un plafond HTTP global réellement appliqué (SEC-016)

Un `slowapi.Limiter` était construit avec `default_limits` et posé sur `app.state.limiter` — **sans rien pour le consulter** : ni `SlowAPIMiddleware`, ni décorateur. L'API annonçait un plafond qu'elle n'appliquait pas, et ses compteurs par défaut étaient en mémoire, soit un budget par worker uvicorn (quatre en production).

Décision : supprimer l'objet et le remplacer par un **middleware ASGI pur** adossé au `RedisRateLimiter` déjà partagé. Le plafond est calibré sur la mesure (pic réel observé : **67 req/min** pour une session navigateur ; défaut à **300**), les sondes sont exemptées, et la politique reste **fail-open** — sur une instance unique, échouer fermé transformerait une panne Redis en panne totale. La fenêtre aveugle est comptée (`http_rate_limit_degraded_total`) et alertée (`GlobalRateLimitDegraded`), parce qu'un compromis n'est défendable que s'il est visible.

> **Amendement (2026-07-25) — deux défauts de cette section, corrigés.**
>
> **L'alerte n'existait pas.** `GlobalRateLimitDegraded` avait été ajoutée à `alerts.yml`, un fichier qui est **à la fois** un artefact régénéré par `prepare_config.sh` depuis `alerts.yml.template` — donc toute édition manuelle disparaît au déploiement suivant — **et** commenté hors de `rule_files` dans `prometheus.yml` (ADR-119 : ses seuils hérités sont corrompus). L'alerte ne pouvait donc jamais se déclencher, alors que cette ADR, le CHANGELOG et `SECURITY.md` affirmaient le contraire. Elle vit désormais dans `alerts-core.yml.template`, avec un seuil `ALERT_CORE_RATE_LIMIT_DEGRADED_RPS` par environnement, un runbook et deux cas promtool. Le noyau passe de 13 à 14 alertes.
>
> **L'exemption des sondes était un contournement.** `_is_subject_to_limit` comparait en `startswith`, si bien que tout chemin *commençant* par `/health`, `/ready` ou `/metrics` échappait au plafond — `/healthz`, `/metrics-flood`. Ces routes répondent 404, mais un 404 coûte une traversée complète du middleware et une passe de routage, servie au rythme que le client veut : le plafond avait une porte dérobée ouverte à quiconque savait écrire `/health`. La comparaison est passée en **égalité stricte** (les trois sondes n'exposent aucun sous-chemin), et le même motif a été corrigé dans `BodySizeLimitMiddleware` avant que sa liste d'exemptions ne soit un jour remplie.
>
> Une garde exécutable (`tests/unit/test_alerts_core_guard.py`) ferme la classe : le rendu committé doit être la sortie exacte de son template, chaque alerte doit lier un runbook qui existe et posséder un cas promtool, et les trois jeux de seuils doivent déclarer les mêmes clés.

Les helpers devenus morts (`build_default_limit`, `resolve_endpoint_limit`, `get_rate_limit_message`) ont été **supprimés**, pas conservés : seuls leurs propres tests les maintenaient en vie, ce qui gonflait la couverture sans couvrir quoi que ce soit.

### 3. Le corps d'une requête est borné avant d'être lu (SEC-031)

Les endpoints validaient leur charge **après** l'avoir matérialisée (`await request.body()` sur les webhooks Telegram et téléphonie, `await file.read()` sur les pièces jointes et les imports de skills) : le pic mémoire d'une requête était fixé par le client, pas par nous — et sur les webhooks, **avant authentification**.

`BodySizeLimitMiddleware` refuse en amont. Le plafond global (21 Mo) doit rester au-dessus du plus gros upload légitime, or les deux plafonds d'upload sont configurables jusqu'à 100 Mo : relever l'un sans l'autre produirait un 413 distant qu'aucun log d'endpoint n'explique. La cohérence est donc **assertée au démarrage** — le `Settings` composé refuse de se construire sur la contradiction, plutôt que de la livrer.

### 4. Toute tâche DevOps est confirmée avant de s'exécuter (FN-1)

`claude_server_task_tool` pilote Claude CLI sans surveillance sur le serveur de production, avec `Bash` dans les outils par défaut : une tâche formulée comme une inspection peut redémarrer un conteneur ou déclencher un déploiement. Rien ne l'arrêtait — le manifeste portait `hitl_required=False`, et ce drapeau n'est de toute façon lu que par ReAct, la porte d'approbation du pipeline étant un passe-plat.

Deux mécanismes ont été écartés, pour des raisons mesurées :

- **`hitl_required=True` seul** — ne couvre que ReAct. Le pipeline continuerait d'exécuter sans rien demander.
- **Changer `tool_category`** — pilote `tool_is_mutation()` et donc les branches du validateur sémantique : deux régressions identifiées, pour un gain nul côté confirmation utilisateur.

Décision : le tool **ne s'exécute plus**. Il produit un brouillon `DEVOPS_TASK` (serveur + texte intégral de la tâche) et la session SSH n'a lieu que dans `execute_devops_task_draft`, après approbation. C'est le seul mécanisme honoré par **les deux** modes d'exécution. La confirmation est inconditionnelle : elle ne dépend pas d'un LLM jugeant la tâche « destructrice », et elle s'applique aussi à la reprise de session (`resume_session`), qui pilote le même CLI.

Le streaming de progression est **préservé** : le contrat d'exécuteur ne transporte pas de config, la queue SSE passe donc par un `ContextVar` posé autour de l'appel. Sans cela, confirmer une action transformait un flux en attente muette de 30 s et plus — une régression qu'un contrôle de sécurité n'a pas le droit de causer.

Deux défauts de cette première implémentation, trouvés en contre-revue et corrigés :

- **La carte de confirmation masquait `context`.** Ce champ est produit par le modèle et atterrit dans le `--append-system-prompt` du CLI distant : c'est précisément par lui qu'un contenu venu d'une source non fiable (email, page web, résultat MCP) oriente la session distante. Confirmer sans le voir n'est pas confirmer. Il est désormais affiché en entier, comme la tâche.
- **Les droits n'étaient vérifiés qu'à la création du brouillon.** Un délai arbitraire sépare la création de la confirmation, et une décision HITL est rejouable : un superutilisateur révoqué aurait vu sa tâche s'exécuter. Le contrôle est refait à l'exécution — un privilège doit tenir au moment où le serveur est touché, pas au moment où la demande a été formulée.

L'ajout du type de brouillon a fait franchir à `draft_executor.py` son plafond de taille (613 > 600 SLOC). Le plafond **n'a pas été relevé** : le peuplement du registre — la seule partie qui doit importer toute la surface des tools — a été extrait dans `draft_executor_registry.py`, avec `draft_executor_types.py` en module feuille pour ne pas fermer de cycle d'import.

### 5. Les sorties réseau sont validées à chaque saut, pas à la première URL

Trois surfaces distinctes, même défaut de fond — la validation portait sur l'URL d'entrée et pas sur ce qui se passait ensuite :

- **MCP OAuth (SEC-008/SEC-030)** — 5 points d'appel sortants dont **deux que l'audit n'avait pas vus** (sondes heuristiques, sonde `WWW-Authenticate`). Une garde AST vérifie désormais que *chaque* appel sortant du module est protégé ; sa sensibilité a été prouvée par mutation.
- **Image de profil (SEC-026)** — redirections suivies **à la main**, chaque saut re-validé, lecture bornée.
- **Navigateur (SEC-032)** — l'intercepteur ne regardait que le schéma et laissait passer sur exception : une page publique pouvait rediriger vers une adresse de loopback ou le service de métadonnées. Il valide maintenant chaque requête et **échoue fermé**. Le déploiement se fait en `report-only` d'abord (`BROWSER_SSRF_ENFORCE=false`) : une vraie page tire aussi des CDN et des polices, le taux de blocage s'observe avant qu'on lui fasse confiance.

### 6. Les journaux ne portent plus les secrets ni la position (P1/P2)

Le filtre PII s'appliquait aux champs structurés, mais **les logs d'accès uvicorn ne passaient pas par structlog** (`uvicorn.access` a `propagate=False`) : la ligne `GET /auth/google/callback?code=…&state=…` partait en clair. Les loggers uvicorn sont désormais repris explicitement, et les paramètres GPS (`lat`, `lng`, `origin`, `dest`…) rejoignent la liste des paramètres sensibles. Vérifié en runtime : `code`, `state`, `lat`, `lng` ressortent `[REDACTED]` dans le log JSON.

## Ce qui n'a pas été fait, et pourquoi

- **`slowapi` reste épinglé** dans `requirements.txt` alors que plus rien ne l'importe. Le retirer impose `task deps:lock` (ADR-112) ; c'est un changement de dépendances à part entière, pas un effet de bord de celui-ci.
- **`BROWSER_SSRF_ENFORCE` reste à `false`.** Le basculer sans avoir lu les journaux `report-only` d'un usage réel reviendrait à livrer un blocage dont personne ne connaît le taux.
- **Le compte total de métriques dans `METRICS_REFERENCE.md`** n'a pas été réajusté : c'est un relevé daté, et je n'ai pas pu reproduire sa méthodologie de comptage à l'identique (410 contre 419 annoncés). Inventer un nouveau chiffre serait pire que laisser le relevé daté.

## Consequences

- Toute exécution de script de skill dépend désormais d'un démon Docker joignable. C'est un point de défaillance **assumé et explicite** : il échoue bruyamment, jamais en dégradant l'isolation.
- Le premier lancement d'un script paie le démarrage d'un conteneur (~300 ms mesurés en dev, davantage sur Raspberry Pi). Le budget de grâce du timeout en tient compte.
- Une tâche DevOps demande maintenant un aller-retour de confirmation. C'est le comportement voulu, y compris pour les tâches d'inspection.
- Trois modules de plus dans `agents/services` (moteur / registre / feuille) : c'est le prix de ne pas relever un plafond de taille.
