# Suivi — vague de remédiation de l'audit V14 et de sa révision

> Document de suivi vivant du chantier, tenu par la session Claude « lia-a7 ».
> Il fait foi pour reprendre le travail après une compaction ou dans une autre
> session : relire les §0 à §3 avant toute action, puis le dernier état du §5.
> Plan daté : rédigé en français (exemption des plans datés, décision AC-039a).

## 0. Protocole de reprise

**Espace de travail.**

| Élément | Valeur |
|---|---|
| Worktree | `C:\Users\jgouv\LIA-worktrees\audit-v14` (hors de `D:\Developpement`, que Google Drive synchronise) |
| Branche | `audit/v14-wave`, créée depuis `main` à `ccd4688c0` (2026-10-23, release v3.5.0 commitée, v3.4.0 taguée) |
| Jonctions vers `D:\` | `apps/api/.venv`, `node_modules`, `apps/web/node_modules`, `apps/web/e2e/node_modules` |
| Fichiers ignorés copiés | `.env`, `apps/api/tests/.infra_denylist`, `apps/web/.env.local` |
| Vérifié | pytest lancé depuis le worktree importe `C:\Users\jgouv\LIA-worktrees\audit-v14\apps\api\src` |

- **Jamais `pip install` ni `pnpm install` dans le worktree** : les jonctions écriraient dans `D:\`.
- **Jamais `EnterWorktree`** : il déplace l'historique de la session hors de la liste VS Code de `D:\`
  (mémoire `reference_worktree_session_leaves_vscode_list`). Toujours des chemins absolus.
- Supprimer le worktree : délier chaque jonction (`cmd /c rmdir`) AVANT `git worktree remove`.
- Docker dev exécute UNIQUEMENT `D:\Developpement\LIA`. Une preuve d'exécution du code du worktree
  demande une méthode dédiée, décidée au lot concerné.

**Parallélisme.**
- `D:\` main : le propriétaire y travaille sur d'autres sujets.
- Codex : un autre worktree, sur d'autres sujets ; se coordonner si un fichier est commun.
- `lia-d9` : la session d'audit (messages inter-sessions) ; elle tient le plan d'actions
  `docs/superpowers/plans/2026-10-22-audit-v14-revision-action-plan.md`.

**Règles du chantier.**
- Exécution INLINE uniquement (aucun sous-agent).
- Aucun commit, push ni déploiement : le propriétaire gère git.
- TDD : test rouge, puis correction minimale, puis vert.
- Ratchets et planchers décroissants seulement ; ni `Any`, ni `cast`, ni `noqa`, ni `type: ignore` pour passer une porte.
- Code, commentaires, docstrings et documents vivants en anglais.

**Cycle de chaque lot.**
1. Analyse sur le code courant (revérifier les faits du §4).
2. Test rouge, correction minimale, test vert.
3. Portes ciblées, puis portes canoniques.
4. « Suis-je sincèrement et pleinement satisfait ? »
5. Revue adversariale à froid **exhaustive** : chaque fichier, chaque ligne, avec un plan de vérification fonctionnel.
6. Mise à jour du registre des constats (dès L1) et du §3 et du §5 de ce document.

**Tests et preuves.**
- **Backend unitaire** : `C:\Users\jgouv\LIA-worktrees\audit-v14\apps\api\.venv\Scripts\pytest` depuis le worktree.
- **Intégration** : PostgreSQL et Redis jetables (testcontainers, sur l'hôte, `--no-cov`), **jamais**
  dans `lia-api-dev` (mémoire : la base de dev serait recréée).
- **Frontend** : vitest sur l'hôte depuis le worktree, via les `node_modules` en jonction.
  Le conteneur `lia-web-dev` ne voit que `D:\`. Fidélité à valider au premier lot frontend.
- **Coûts** : aucun fournisseur payant réel. La preuve OAuth sur Docker dev se fait sur un **compte de preuve**
  (accord du propriétaire du 22/10), jamais sur son compte.

## 1. Sources

| Source | Rôle |
|---|---|
| `docs/audit/AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html` | rapport V14 (8,0/10), constats AC-0xx |
| `docs/audit/AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html` | révision (7,8/10, 26 ouverts, 12 nouveaux AC-028→039) ; suivie depuis v3.5.0 |
| `docs/superpowers/plans/2026-10-22-audit-v14-remediation.md` | plan initial A01–A19 (actions de cette vague) |
| `docs/superpowers/plans/2026-10-22-audit-v14-revision-action-plan.md` | plan de `lia-d9` : 34 actions, lots L1–L9, prompts |
| Mémoire `project_audit_v14_remediation_wave_2026_10_22.md` | condensé des décisions |

Horizons de la révision : **H0** au plus 1 semaine, **H1** 2 à 4 semaines, **H2** le trimestre.

## 2. Décisions du propriétaire (journal, ne jamais réécrire)

| Date | Sujet | Décision |
|---|---|---|
| 22/10 | Périmètre | Lots A01–A07, A10–A16 du plan initial ; le lot 4 (AC-002, AC-005) et A17/A18 restent HORS vague |
| 22/10 | Q1 | Attendre la fin de v3.4.0. Taguée le 23/10 ; v3.5.0 commitée |
| 22/10 | Q2 | A06b : inclure `peer_message_delivery`, `diagnostics/notifications` et un garde AST |
| 22/10 | Q3 | Alertmanager : la gravité fixe l'urgence, le composant fixe le public (`continue: true`), avec dédoublonnage (§4 L7) |
| 22/10 | Q4 | Refus de compilation : attente exponentielle par signature (§4 L8) |
| 22/10 | Q5 | Un SSE seul **n'est pas** une livraison durable |
| 22/10 | Q6 | P1 échu : avertissement en CI, **échec de `release:check`** sauf report daté et motivé |
| 22/10 | Q7 | « je ne sais pas » ; décidé par moi : calibrer AC-028 sur les séries postgres-exporter (prod lue en lecture seule via Prometheus), aucun accès direct à la base de production |
| 22/10 | Ajout | AC-028, AC-029 et AC-031 entrent dans la vague |
| 22/10 | Q8 | Porte unique de rafraîchissement OAuth (§4 L4) |
| 22/10 | Q9 | Ajouts : AC-033a, AC-033b, AC-030a, AC-032, AC-006, AC-034a, AC-037, AC-030b |
| 22/10 | AC-035 | Inclus : aucun arbitrage métier |
| 22/10 | AC-036 | Règle du propriétaire : **base de données > .env > constantes**. Gabarits : 8 fonctions à `true`, ligne `BACKGROUND_RUNS_ENABLED` retirée de `.env.min.prod.example`, analytique à `false` |
| 22/10 | AC-039a | Amendement pragmatique de la règle de langue (texte au §4 L1) |
| 22/10 | Hue Remote | Inclus dans la porte OAuth |
| 22/10 | Preuve OAuth | Sur Docker dev, avec un compte de preuve |
| 23/10 | Mise en œuvre | « GO » : worktree (le propriétaire avance en parallèle sur `D:\` main), tous les lots enchaînés en TDD, arrêt seulement sur arbitrage bloquant |
| 23/10 | AC-036 (ajout, pendant L8) | « Aligner `.env.example` avec les valeurs de `.env.prod`, qui sont les valeurs éprouvées et utilisées en production aujourd'hui. » Mise en œuvre (§4 L9) : valeurs réglables seulement — jamais un secret, un identifiant, une adresse, un hôte ou un fait de l'hôte (pièges du 03/10 et du 08/10), jamais une clé d'identité d'environnement (`ENVIRONMENT`, `DEBUG`…) ; lecture de `.env.prod` sans afficher les valeurs sensibles |
| 23/10 | AC-036 (2 arbitrages) | (1) Conflit « analytique à false dans les gabarits » ↔ production à `true` : **false** dans les gabarits (`PRODUCT_ANALYTICS_ENABLED`, `NEXT_PUBLIC_PRODUCT_TELEMETRY`), annoté « diffère de la production ». (2) **`.env.prod.example` aussi** aligné sur `.env.prod`, mêmes exclusions |
| 23/10 | AC-030b | Mesure du 23/10 : unitaire seul 78,98 % (il manque 2 202 lignes pour 80 %) ; union unitaire + intégration de 4 domaines (460 tests) ≥ 80,53 % — sms 53,6 → 93,6 %, discussions 70,7 → 93,8 % : ces domaines sont testés sur PostgreSQL, la mesure unitaire ne le voit pas. Question posée, réponse : **« Mesurer les deux »** — la CI additionne la couverture des tests unitaires et d'intégration et applique le plancher inchangé (78 %) à ce total ; la porte des lignes modifiées lit ce total ; les 78 % ne s'appliquent plus aux seuls unitaires ; des tests unitaires seulement là où aucune des deux suites ne couvre |
| 23/10 | Intégration | Question posée en fin de L11 (main réel `4ef630984`, 7 conflits planifiés) ; réponse : **« Je l'applique sur D:\ »** — le diff du worktree appliqué sur l'arbre de travail de `D:\`, SANS commit, les 7 conflits résolus selon le §4 L11, puis release:check/sync-counts, docs:maps, lint, suite rapide, les 3 tests SMS d'intégration, les portes de couverture, les 2 clés des `.env` vivants du démonstrateur, le rejeu E2E A10 et les preuves Docker (OAuth sur un compte de preuve) ; le propriétaire relit et commite |
| en attente | Processus orphelins | pytest PID 15320 et 15888 (20/10 14:12), scripts PID 45460 et 58392 (19/10) : redemander avant de les arrêter (pas les miens) |

**Interprétation retenue le 23/10.** La consigne propre à cette demande dit « worktree, afin que je
puisse avancer en parallèle sur D main » ; le gabarit générique dit « directement sur D main ». La
consigne motivée l'emporte. C'est réversible : le diff s'appliquera sur `D:\` à la demande.

## 3. Lots : ordre et statut

| Lot | Contenu | Statut |
|---|---|---|
| L1 | Registre et doctrine : AC-031 (registre + gardes), AC-032 (doctrine de couverture écrite une fois), AC-039a (règle de langue + cliquet) | fait (AC-031, AC-032 `remediated` ; AC-039 ouvert, AC-039a fait) — suite rapide finale en cours |
| L2 | Banc et CI : A11 (suites canoniques instrumentées, dépendances courantes), AC-033a (`faulthandler_timeout`, `timeout-minutes`), AC-033b (2 tests jamais exécutés), AC-030a (porte de couverture du diff) | fait (AC-033 et AC-030 : remédiations partielles inscrites) |
| L3 | Livraison durable : A06 (3 sites téléphonie) + A06b (pairs, diagnostics) + garde AST | fait (AC-003 `remediated` ; résidu écrit : l'archive du dispatcher partage la session de l'appelant ; portes : suite rapide, `lint:backend`, marqueurs, docs en preview) |
| L4 | Porte unique de rafraîchissement OAuth (AC-029 : 4 portes héritées, grants, Hue Remote) + amendement ADR-302 + métriques et tableau 10 | fait (AC-029 `remediated` ; preuve Docker dev d'un échange réel sur compte de preuve → L11) |
| L5 | Bornes PostgreSQL (AC-028) + métrique, panneau, alerte + amendement ADR-304 + 5 gabarits | fait (AC-028 `remediated` ; recette de preuves `DatabaseBoundReached` ajoutée en L6 ; preuve Docker `SHOW lock_timeout` → L11) |
| L6 | Petits correctifs : A05 (jointure du shutdown), A04 (fermeture Hue), A03 (`.dockerignore`), A14a (6 codes MyPy morts + 12 ignores inutiles), AC-035 (ASYNC2) | fait (AC-035 `remediated` ; reste : 37 % de la suite d'intégration de L5, en tâche de fond pendant L7) |
| L7 | Alertmanager : A07a (composition), A07b (routage (a) + dédoublonnage), matrice hermétique ; AC-006 (panneaux sans producteur) | fait (AC-004 et AC-006 `remediated` ; re-décision des 3 alertes produit de comportement au plus tard le 2026-12-15) |
| L8 | A16 (refus sémantique, attente exponentielle) + AC-034a (jauges des tables de discussions) + A12 (oracle CPU) | fait (AC-023, AC-034, AC-033 `remediated`) |
| L9 | Frontend et dette : A13 (5 primitives dans la couverture), AC-037 (cliquet `as unknown as`), A15 (AssistantAvatar), A14b (`conversations.service`), AC-036 (parité des gabarits) | fait (AC-036, AC-037, AC-040 `remediated` ; A15 fait ; A14b : remédiation partielle d'AC-012 inscrite, constat ouvert) |
| L10 | AC-030b : marge de couverture backend ≥ 2 points (cibles sms, proactive_discussions, conversations) | fait (AC-030 `remediated` ; décision « mesurer les deux » : union 87,47 %) |
| L11 | Qualification : rejeu E2E contrôlé A10 (0 retry, médias natifs), `ci:fast` complet, registre à jour, revue finale, plan d'intégration dans `D:\` | fait : worktree qualifié (`ci:fast` par composants, registre, revue, plan), intégré dans `D:\` le 23/10 (rejeu A10 690/0, preuves Docker L4/L5, `.env` vivants du démonstrateur), revue à froid et correctifs, portes finales du 24/10 (journal), registre consolidé (18 remédiés), publié en v3.6.0 |

Déjà clos, à inscrire au registre : A01 (AC-025) et A02 (AC-024), clos par la révision (preuve R11)
et livrés dans v3.4.0.

## 4. Conceptions retenues, par lot

Les faits datent de l'analyse du 22/10 sur `3c6795d4b`, recoupée le 23/10. Le diff `3c6795d4b..ccd4688c0`
ne touche, dans ce périmètre, que les gabarits `.env`, `pyproject.toml` (version) et `docs/audit`.
Revérifier chaque fait au début de son lot.

### L1 — Registre (AC-031), doctrine de couverture (AC-032), langue (AC-039a)

**Registre** — `docs/audit/findings_register.json`, en JSON (bibliothèque standard ; un test YAML
imposerait PyYAML en dépendance directe).
- Champs : `id`, `title`, `level` (major/moderate/minor), `priority`, `effort`, `horizon`, `status`
  (open/closed/partially_closed/presumed_closed/reopened/unpublished), `opened_on`, `due_on` (calculé :
  H0 +7 j, H1 +28 j, H2 +90 j depuis la dernière vérification), `appearances` (rapport, statut, niveau),
  `closure` {`on`, `proof`}, `deferral` {`until`, `reason`, `decided_on`}, `aliases`.
- AC-014 garde son sujet de V13 (clos) ; le sujet de V14 (exclusions de couverture) devient **AC-040**,
  alias « V14:AC-014 ». AC-022 et AC-026 : `unpublished`, réservés, jamais réutilisables.
- Graine : table de continuité V13 → V14 → révision. Format des rapports V11 à V13 à vérifier EN PREMIER.

**Gardes.**
- Test unitaire, indépendant de la date : identifiants et alias uniques ; tout constat clos porte une
  preuve ; tout `AC-\d{3}` d'un rapport de l'ère AC existe dans le registre.
- Outil `lint:docs` : P1 échu → avertissement. Mode `--strict` appelé par `release:check` : échec,
  sauf report valide et non expiré.
- Règle de publication (§4.2 du protocole) : les preuves sont des chemins, des ADR, des commits ou des
  identifiants d'exécution ; jamais de numéros de ligne ni de détail exploitable. La sécurité reste hors registre.
- Référencer le registre depuis `AUDIT_PROTOCOL.md` (§1.6 et §4.3) et `docs/audit/README.md`.

**AC-032** : planchers et doctrine de couverture écrits une seule fois (CLAUDE.md, GUIDE_TESTING,
Taskfile, pyproject) ; les autres documents pointent vers la source.

**AC-039a**. Texte à ajouter à CLAUDE.md, puis `task docs:sync-agents` :
> Documentation language: every NEW document is written in English. An existing French document may be
> edited in French; the list of French living documents is frozen by a shrink-only ratchet (a new French
> document fails, a translated one leaves the list). Exempt by decision: living maps, dated plans
> (`docs/superpowers/plans/`), audit reports (`docs/audit/`).

Détecteur déterministe (proportion de mots-outils FR/EN hors blocs de code), calibré sur un échantillon
étiqueté. Les 4 points d'entrée français (`docs/INDEX.md`, `docs/ARCHITECTURE.md`, `GUIDE_TESTING.md`,
`GUIDE_DEVELOPPEMENT.md`) seront traduits dans un lot séparé, AC-039b, hors vague.

### L2 — Banc et CI (A11, AC-033a, AC-033b, AC-030a)

**Faits.**
- La dernière couverture canonique complète (`coverage.xml`, 22/10 09:25, 78,67 %) précède les
  dépendances tardives : `langgraph-checkpoint` 4.3.0 et `certifi` 2026.10.19, installées à 09:35.
- Les blocages T15a/b de V14 viennent du harnais d'audit (`.tmp-codex`, `--cov` avec `-n 8`).
- Mécanisme connu : `socket.accept` dans `_fallback_socketpair` sous xdist Windows (Taskfile, commentaire de `test:backend:unit:fast`).
- `faulthandler_timeout` affiche bien la pile d'un worker xdist bloqué (vérifié le 22/10).
- Aucun `timeout-minutes` dans `ci.yml` ; aucun `faulthandler_timeout` dans pyproject.

**AC-033b** : `tests/unit/domains/telephony/test_wiring.py` (ignoré si la téléphonie est désactivée) et
`tests/unit/domains/agents/orchestration/test_parallel_executor_compute_step_timeout.py` (chemin
« kept-as-is » ignoré quand plancher = plafond). Les faire tourner avec des surcharges locales.

**AC-030a** : porte de couverture des lignes modifiées, avec un script du dépôt (pas de nouvelle
dépendance), lancée depuis Taskfile et appelée par la CI (ADR-151).

**Gate canonique** : `task test:backend:unit:fast` puis `task test:backend:unit:coverage`, l'un après
l'autre. Watchdog : `PYTEST_ADDOPTS="-o faulthandler_timeout=600"`.

### L3 — Livraison durable (A06 + A06b, AC-003 élargi à 5 sites)

**Faits.**
- `NotificationDispatcher.dispatch` absorbe chaque échec de canal et calcule
  `success = archived or sse_sent or fcm_success > 0 or channel_sent > 0` ; il renvoie `failure` sans lever.
- Cinq consommateurs écrivent un état durable sans lire le résultat :
  - `domains/telephony/reapers.py` (`mark_notification_delivered`) ;
  - `domains/telephony/return_synthesis.py` (idem) ;
  - `infrastructure/scheduler/phone_relay_runner.py` (`_settle_relay` → idem) ;
  - `infrastructure/scheduler/peer_message_delivery.py` (`mark_message_delivered` + avis « livré » à l'expéditeur) ;
  - `domains/diagnostics/notifications.py` (`sent += 1` puis `mark_notified`).
- Le bon modèle existe : `infrastructure/proactive/notification_sink.py`.
- Les doubles de test renvoient `None` (`test_reapers.py`, `test_return_synthesis.py`).
- Les diagnostics ne notifient qu'à l'ouverture d'un incident : aucun renvoi n'existe (résidu documenté).
- `peers.last_error` est un `String(50)`.

**Conception.**
- `NotificationResult.durably_delivered` : `archived or fcm_success > 0 or channel_sent > 0`. Un SSE
  seul ne suffit pas (Q5).
- `NotificationDispatcher.dispatch_durable(...)` lève `NotificationNotDelivered` (typée) quand la
  notification n'est pas livrée durablement. Les 5 sites remplacent un appel ; leur chemin d'échec actuel
  fait le reste :
  - reaper → `record_notification_failure` ;
  - synthèse et relais → la notification reste `PENDING` ;
  - pairs → `_record_retryable_failure` avec `dispatch_error` ;
  - diagnostics → l'envoi raté n'est pas compté, donc pas de `notified_at`.
- Garde AST : dans un module qui écrit un état de livraison durable, un `dispatch(` dont le résultat est
  jeté est refusé. Les avis best-effort figurent en liste blanche avec un motif écrit : `meetings/processing`,
  `peers/notifications`, `scheduled_action_executor`, `voice_session_closing`, l'appel push seul de `phone_relay_runner`.
- Les doubles de test renvoient un vrai `NotificationResult`.
- Tests : succès, échec renvoyé, SSE seul, succès partiel, exception, annulation, `user=None` inchangé ;
  intégration PostgreSQL du reaper jusqu'au plafond de tentatives.

**Réalisé (écarts à la conception, 23/10).**
- Un mot-clé `dispatch(..., require_durable=True)` plutôt qu'une méthode `dispatch_durable` : une
  seule porte, et le garde AST lit le mot-clé.
- `NotificationResult.success` et `error` supprimés (et `failure()`, sans appelant) :
  `durably_delivered` est l'unique verdict. Trois lecteurs déduisaient « livré » de `success`, que
  le SSE seul rendait vrai : le règlement du registre d'actions dans le runner proactif et dans le
  sink, et le `delivered` renvoyé à l'expéditeur d'une image. Le crochet `on_notification_sent`
  (audit heartbeat, déduplication des intérêts) ne tourne plus sur un SSE seul.
- `archived` est retenu après le commit de l'archive, plus avant (un commit raté se disait archivé).
- Mesuré sur PostgreSQL : une archive dont l'instruction échoue avorte la transaction de
  l'appelant (25P02 ensuite) et un COMMIT sur transaction avortée annule en silence. D'où :
  comptage de l'échec sur une session propre (reaper, pairs) ; un administrateur par session ;
  le webhook committe l'incident avant de notifier (comme le self-check).
- Résidu écrit (amendement ADR-263) : l'archive du dispatcher reste sur la session de
  l'appelant, pour les 14 sites. Le corriger change le contrat transactionnel du dispatcher
  (`voice_session_closing` veut l'archive dans sa transaction) : arbitrage du propriétaire.

### L4 — Porte unique de rafraîchissement OAuth (AC-029 élargi)

**Faits.**
- `_refresh_oauth_token` a 4 appelants ; seul `base_oauth_client.py` passe sous `OAuthLock`. Les trois
  autres n'ont aucun verrou :
  - `ConnectorService.get_connector_credentials`, porte de chaque outil OAuth (`agents/tools/base.py`) et
    du balayage heartbeat ;
  - `refresh_connector_credentials` (route `/refresh`) ;
  - `scheduler/token_refresh.py` (rafraîchissement anticipé).
- L'écriture des identifiants est inconditionnelle.
- Un `invalid_grant` passe le connecteur en `ERROR`.
- `OAuthGrantRuntime` tient un `FOR UPDATE` PENDANT l'appel au point de jeton (`_refresh` → `_post_refresh`).
  ADR-302 point 3 l'écrit (« sous verrou de ligne ») ; ADR-304, postérieure, l'interdit.
- Ce runtime propage la rotation aux connecteurs liés, met en `ERROR` les services dont les scopes ne sont
  plus couverts, et fait `commit()` sur la session de l'appelant. Le chemin hérité fait de même.
- Hue Remote (`philips_hue_client._ensure_valid_remote_token`) : POST direct, sans verrou, écriture
  inconditionnelle de `HueBridgeCredentials`.
- `OAuthLock` : valeur fixe `"locked"`, `DELETE` inconditionnel ; un seul réglage sert d'attente et de durée
  de vie. `force_release` et `is_locked` n'ont aucun appelant.

**Conception.**
- Une porte `ensure_fresh_credentials(owner)` pour les jetons hérités, les grants et Hue Remote.
  - Le format propre de chaque magasin est conservé.
  - Un adaptateur par fournisseur pour l'appel au point de jeton.
- Partage dans le worker : `run_single_flight`, clé = identité du propriétaire du jeton. Un
  rafraîchissement manuel ou forcé REJOINT un rafraîchissement en cours.
- Partage entre workers : `run_shared_flight`.
  - `claim_ttl_s` et le budget d'attente sont calculés à partir des constantes de relance, extraites des
    littéraux `stop_after_attempt` et `wait_exponential`. Défaut `CLAIM_TTL_SECONDS` = 30 s, inférieur au
    pire cas (≈ 36 s avec 10 s de délai).
  - `read_shared` lit un **marqueur de version dans Redis** (les attendants sondent toutes les 20 ms), puis
    lit la base une seule fois, sur une session courte.
  - En cas de panne Redis : repli, avec la condition d'écriture.
- La fabrique ouvre **sa propre session courte** : elle tourne dans le contexte du premier appelant.
- L'appel au fournisseur se fait hors de toute transaction (ADR-304).
- **Écriture finale** : transaction courte. Verrouillage du grant puis de ses connecteurs, dans l'ordre
  d'ADR-302 (amendement du 15/10). Vérification du **chiffré lu ET d'un état toujours actif**. Puis
  écriture, propagation aux connecteurs liés et `ERROR` des scopes non couverts.
  - Si la condition échoue : relire et renvoyer les identifiants du gagnant.
  - `write_through_cancellation` sur la persistance.
- `invalid_grant` : `ERROR` seulement si le chiffré stocké est inchangé, sur tous les chemins.
- Plus d'engagement caché de la session de l'appelant. C'est un changement de comportement : le
  caractériser d'abord.
- `OAuthLock` est supprimé (et ses deux fonctions mortes). Les 5 séries du tableau 10
  (`10-oauth-connectors-mcp.json`, lignes 500, 541, 546, 1817, 1822) sont remplacées par des issues de
  rafraîchissement : claim pris, rafraîchissement rejoint, attente, repli, écriture perdue, `invalid_grant` revérifié.
- Garde AST : seule la porte appelle un point de jeton.
- Amendement d'ADR-302, point 3.
- Tests :
  - 2 workers simulés → 1 seul appel au fournisseur ;
  - 5 appels parallèles dans un worker → 1 seul appel ;
  - condition perdue → identifiants du gagnant ;
  - `invalid_grant` après une rotation faite par un autre → pas d'`ERROR` ;
  - vrai `invalid_grant` → `ERROR` ;
  - annulation juste après la réponse du fournisseur ;
  - Redis coupé ;
  - révocation concurrente ;
  - rafraîchissement manuel qui rejoint ;
  - Hue Remote ;
  - `UPDATE` conditionnels sur un vrai PostgreSQL.
- Charge ≈ 3,5 j + 0,5 j pour Hue. AVANT L5.

**Plan d'exécution (23/10, faits revérifiés sur `ccd4688c0`).**
- Revérifié : 4 appelants de `_refresh_oauth_token` (`service.py` ×2, `token_refresh.py`,
  `base_oauth_client.py` sous `OAuthLock`) ; la « double vérification » du client de base appelle
  `get_connector_credentials`, qui rafraîchit lui-même SANS verrou : le vrai rafraîchissement
  n'est presque jamais celui du client. Hue : aucune marge (`expires_at > now`), écriture
  inconditionnelle, `error=str(e)`. `OAuthGrantRuntime` : `FOR UPDATE` tenu pendant `_post_refresh`.
- Modules : `connectors/oauth_refresh.py` (la porte : `ensure_fresh_credentials(target, *, current,
  force, refresh_before)`, mono-vol + vol partagé + issues + revérification `invalid_grant` +
  `write_through_cancellation`) ; `connectors/oauth_refresh_exchange.py` (SEUL module où figure
  `grant_type=refresh_token` : un POST relancé, configurations Google, Microsoft et Hue, constantes
  de relance extraites) ; `connectors/oauth_refresh_targets.py` (contrat `RefreshTarget` + cibles
  connecteur hérité et grant) ; cible Hue à côté du client Hue.
- Contrat d'une cible : `flight_key`, `user_id`, `read(db)` → (chiffré, identifiants, actif),
  `needs_refresh`, `exchange` (nouveaux identifiants + scopes, ou refus typé : révoqué, transitoire,
  illisible), `write_if_unchanged(db, chiffré_attendu, …)`, `revoke_if_unchanged(db, chiffré_attendu)`.
- Chemin rapide : l'appelant passe ce qu'il a déjà lu (`current`) ; frais → aucune lecture.
- Vol partagé : clé `shared_flight:oauth_refresh:<flight_key>` ; TTL du claim et budget d'attente
  calculés (tentatives × délai HTTP + attentes + marge) ; marqueur de version Redis
  (empreinte du chiffré écrit) sondé toutes les 20 ms, puis UNE lecture base.
- Sessions : la porte n'utilise JAMAIS la session de l'appelant ; ses sessions courtes viennent de
  `get_db_context`. Les tests d'intégration du runtime passent sur données committées (le
  `async_session` du test n'est pas visible d'une autre connexion).
- Métrique `oauth_refresh_outcomes_total{kind, outcome}` ; tableau 10 : les 5 séries
  `oauth_lock_*` remplacées. `OAuthLock`, ses 5 métriques, `OAUTH_LOCK_TIMEOUT_SECONDS` (2 gabarits)
  et ses constantes supprimés.
- Ordre : (1) porte + échange + cibles, tests unitaires (cibles factices) ; (2) cibles sur
  PostgreSQL réel (écritures conditionnelles, revérification) + 2 workers sur Redis réel (base 15) ;
  (3) branchement des 4 appelants + Hue, caractérisation d'abord ; (4) suppression d'`OAuthLock`,
  métriques, tableau, gabarits ; (5) garde AST, amendement ADR-302 (point 3), docs, registre.

### L5 — Bornes PostgreSQL (AC-028)

**Faits.**
- Le moteur SQLAlchemy de l'application n'a ni `connect_args` ni `server_settings`.
- Dev (PostgreSQL 16.15) : `lock_timeout`, `idle_in_transaction_session_timeout` et `statement_timeout`
  sont à 0 ; `deadlock_timeout` = 1 s.
- Trois pools : SQLAlchemy, plus psycopg pour le checkpointer et le Store LangGraph (autocommit, DDL au
  démarrage). Alembic a son propre moteur.
- Verrous consultatifs qui ATTENDENT (55P03 sous une borne) : `owner_lock`, `bookmarks`,
  `connectors/repository`, `map_load_metering`, `jev_admin`. Le verrou de migration du checkpointer
  interroge sans bloquer.
- Aucun `NOWAIT` SQL.
- `db_query_errors_total` n'est alimenté que par `BaseRepository`. 25P03 n'est pas classé.
- Les tests d'intégration construisent leurs propres moteurs.
- Séries dev sur 15 jours : transaction inactive au plus 53,5 s (07/10 17:21–17:51, chemin NON identifié :
  au-delà du pire cas OAuth à 10 s, donc PAS attribuée aux grants) ; aucune attente de verrou à la
  résolution du scrape ; une transaction active de 2 h 21.

**Conception.**
- Bornes sur le seul moteur SQLAlchemy, via `server_settings`, calculées par une fonction partagée avec le test.
- Réglages `DATABASE_LOCK_TIMEOUT_MS` et `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` (0 = désactivé).
  Hypothèse : 30 s et 300 s, à confirmer par les séries de prod lues en lecture seule ; expliquer les 53,5 s
  avant de fixer la borne.
- Pas de `statement_timeout` global.
- Compteur au niveau du moteur (`handle_error`), plus un panneau (tableau 03) et une alerte (gabarit `alerts-core`).
- Amendement d'ADR-304.
- Gabarits : `.env.example`, `.env.prod.example`, `.env.min.prod.example`, `.env.demo-instance.example`,
  `.env.demo-instance.prod.example`.
- Tests d'intégration :
  - cycle entre deux connexions → 55P03 dans la borne (rouge aujourd'hui) ;
  - transaction inactive coupée, puis le pool se rétablit ;
  - `SET LOCAL` prioritaire ;
  - Alembic sans borne.

### L6 — Petits correctifs

**A05.** `wait_all_background_tasks` (`infrastructure/async_utils.py`) fait `cancel()` puis rend la main
sans attendre la fin des tâches (reproduit le 22/10).
- Ajouter une jointure bornée après annulation. Sa durée est une constante de module (modèle
  `LOOP_STOP_TIMEOUT_S`), ajoutée à la somme de `test_graceful_shutdown_budget_guard.py` (105 → 110 s ≤ 120 s).
- `CancelledError` est propagée ; une tâche récalcitrante est nommée en avertissement.
- Ce registre recueille aussi les écritures abandonnées de `write_through_cancellation`.
- `cancel_all_background_tasks` n'a aucun appelant : à supprimer.

**A04.** `PhilipsHueClient` n'est jamais fermé dans `connectors/service.py` (`activate_hue_local`) ni dans
`connectors/router.py` (route `/philips-hue/test`). Corriger par `try/finally: await client.close()`
(modèle `hue_discovery.py`). Tests : succès, échec (503 conservé), annulation. Marges SLOC : `service.py`
27 lignes, `router.py` 14.

**A03.** Ajouter `**/.next-*` au `.dockerignore`, aligné sur `.gitignore` et sur le motif accepté par
`capture_public_screenshots.ps1`. Garde texte, plus une sonde BuildKit ponctuelle.

**A14a.** Retirer les 6 codes neutralisés morts, sans toucher au code :
- `no-untyped-def` (`agents.nodes.*`) ;
- `operator` (`agents.tools.*`) ;
- `union-attr` (`graphs.base_agent_builder`) ;
- `arg-type`, `var-annotated` et `call-overload` (`services.hitl.*`).

Retirer aussi les 12 `type: ignore` inutiles. Puis `measure_mypy_debt.py --update`.

**AC-035.** 15 sites ASYNC2 : 12 ASYNC240 et 3 ASYNC230, les envois STT `elevenlabs`, `openai` et
`fishaudio` lisant des fichiers audio dans la boucle. Les corriger, puis activer ASYNC2 dans la sélection
Ruff, sans baseline ni `noqa`. Le site ASYNC110 de `provider_capacity.py` est un faux positif (sondage
inter-processus) : ne pas activer ASYNC110 ni ASYNC109.

### L7 — Alertmanager (A07a/b) et panneaux sans producteur (AC-006)

**Faits.**
- L'entrypoint choisit le gabarit complet dès qu'un canal optionnel est renseigné. Son en-tête annonce la
  suppression des blocs non configurés : c'est faux.
- Routes de gravité sans `continue`, placées en premier dans les deux gabarits. Les 32 alertes chargées
  (`alerts-core.yml`, 13 critical et 19 warning) n'atteignent donc jamais les récepteurs d'équipe. Dans le
  gabarit e-mail seul, `budget-email` et `security-email` sont inatteignables par construction.
- Aucune alerte chargée ne correspond au filtre finance `Budget|Cost`.
- `alerts-product.yml` n'est pas chargé (`ProductNorthStarDrop`, `severity: high`).

**Conception A07a.** Blocs Slack et PagerDuty balisés, supprimés quand leur variable est vide (shell
busybox). Corriger l'en-tête mensonger. Gate Task hermétique : image épinglée, `--network none`,
`amtool check-config` puis `amtool config routes test`, appelé par `ci.yml`.

**Conception A07b (décision (a)).** Les routes de gravité passent en `continue: true`. Dédoublonnage :
- route d'équipe générée seulement si l'adresse de l'équipe est renseignée et distincte de l'adresse backend ;
- Slack d'équipe seulement sur un webhook distinct ;
- PagerDuty seulement depuis la route critique.

Oracle : DatabaseDown, RedisDown, SSELatencyP95High, RedisConnectionPoolExhaustion, LLMCallsWithoutUsage,
EmbeddingOperationsFailing. Valeurs spéciales (`&`, `|`, `\`, `'`) à tester.

**AC-006.** Garde inverse panneau → producteur ; 4 panneaux vides ; garde de couverture limité aux règles
chargées ; décision sur `alerts-product.yml`.

### L8 — Refus sémantique (A16), jauges (AC-034a), oracle CPU (A12)

**A16. Faits.**
- `restricted_sources` lève `ValueError` avant `save_rule_cache` (`infrastructure/proactive/discussion_runner.py`,
  `apply_read_controls`).
- Le run se règle `failed` sans `retry_after`.
- La prise suivante n'est bloquée que par un `retry_after` (même révision, même époque).
- Passage toutes les 15 min (`DISCUSSION_INTERVAL_MINUTES`).
- Cache dans `ContextStateRecord.rule_cache` (JSONB, `extra="forbid"`).
- La raison est affichée à la personne (`discussions.activity.reason.<raison>`, garde `test_run_reason_sentences.py`).
- Le runner compte 558 SLOC sur 600.

**A16. Conception.**
- Erreur typée, sous-classe de `ValueError`.
- Cache négatif : `RuleCache` gagne `refused` (et un compteur de refus), avec des valeurs par défaut pour
  pouvoir relire les anciens blobs.
- Première attente = 2 × `DISCUSSION_INTERVAL_MINUTES`, puis doublement, plafonné à `DISCUSSION_RULE_CACHE_HOURS`.
- Invalidation au changement de signature.
- Raison `rules_refused` en 6 langues, ajoutée à `NOTHING_INTERPRETED`. Elle passe par le chemin de
  `ContextResult` non prêt.
- Logique pure dans `rule_controls.py`.

**AC-034a.** Jauges de croissance des tables de discussions, avant toute décision de rétention.

**A12. Faits.**
- `test_compaction_provenance.py::test_a_long_url_tail_is_trimmed_with_linear_cpu_growth` mesure un seul
  appel par taille, avec un plancher de 5 ms.
- Windows avance `thread_time` par pas de 15,625 ms (mesuré ; `get_clock_info` annonce 1e-07).
- Le garde des aplatisseurs groupe 16 appels, n'évalue rien sous 20 ms et possède un contrôle négatif.

**A12. Conception.** Extraire la mesure dans `tests/helpers/`, avec une calibration empirique bornée.
Ajouter un contrôle négatif volontairement quadratique. Comportement identique pour les aplatisseurs.

### L9 — Frontend et dette locale

**A13.** Réintégrer `dialog`, `alert-dialog`, `input`, `textarea` et `skeleton` (ARIA conditionnel et
lignes calculées) dans la couverture. `toaster` (libellé traduit) : à classer. Le seuil de glob
`src/components/ui/**/*.tsx` (88/84/84/89) s'appliquera. Tests d'abord, mesure avant et après, garde sur
les exclusions.

**AC-037.** Cliquet décroissant sur `as unknown as` : 107 sous `__tests__` + 1 dans
`apps/web/src/app/api/rag-upload/[spaceId]/route.test.ts` = 108.

**A15.** `AssistantAvatar.tsx` : 2 `set-state-in-effect` (motif « valeur précédente ») et une complexité
de 28. Le motif « garder la valeur du rendu précédent dans l'état » passe les 5 règles du compilateur
(`eslint-plugin-react-hooks` 7.0.1, vérifié). Extraire des décisions pures. Puis `--update` des deux baselines.

**A14b.** Retirer l'override de `src.domains.conversations.service`, qui donne 10 diagnostics réels
(sonde du 22/10). Le fichier est figé (804 SLOC, en compte 790) et couvert à 44,1 % : caractériser d'abord.

**AC-036.**
- Règle : base de données > .env > constantes. Un gabarit reprend la constante, omet la clé ou annote
  `# differs from default: <motif>` ; un garde de parité le vérifie.
- `.env.example` et `.env.prod.example` : passer à `true` `HABITS`, `OPEN_LOOPS`, `BACKGROUND_RUNS`,
  `ACCOUNT_EXPORT`, `INITIATIVE_REACT`, `RECURRENCE_SUGGESTION`, `HEARTBEAT_DEPARTURE`, `HABITS_TICK_SCORING`
  (`_ENABLED`) ; `PRODUCT_ANALYTICS_ENABLED` passe à `false`.
- `.env.min.prod.example` : supprimer la ligne `BACKGROUND_RUNS_ENABLED`.
- Gabarits du démonstrateur : déjà conformes.
- Environ 41 autres écarts : alignés par défaut ; ceux qui sont gardés passent en une seule revue du propriétaire.
- Les `.env` réels ne sont pas touchés.
- `HABITS` et `OPEN_LOOPS` sont des plafonds `env_flag` (`feature_switches/registry.py`) : `false` empêche
  même le panneau de réactiver la fonction.
- **Complément du 23/10 (décision du propriétaire)** : `.env.example` ET `.env.prod.example` reprennent les
  valeurs réglables de `.env.prod` (éprouvées en production). Recensement (`scratchpad/l9/prod_vs_example*.py`,
  valeurs sensibles jamais affichées) : ~99 valeurs réglables diffèrent de `.env.example` (81 + 9 + 8 masquées
  par leur nom + `ACCOUNT_EXPORT_ENABLED`). Exclus : secrets, identifiants, adresses, hôtes, faits de l'hôte,
  clés d'identité d'environnement (`NODE_ENV`, `DEBUG`, `ENVIRONMENT`, `LOG_LEVEL`, `WEB_CONCURRENCY`,
  `LANGFUSE_DEBUG`, `SESSION_COOKIE_SECURE`, `APP_VERSION`…). Analytique : `false` dans les gabarits, annotée
  « differs from production ». La garde de parité compare au DÉFAUT DU CODE : une valeur éprouvée qui en
  diffère porte `# differs from default: proven in production` — la liste de ces écarts dit au propriétaire où
  les défauts du code retardent sur la production (décision sur les défauts : hors vague, à lui).
- Les tests qui lisent les gabarits (`test_mfa_settings`, `test_installer_wizard_backend_alignment`,
  `test_avatar_style_rollout_contract`, `test_radio_settings`, `test_meetings_settings`, `test_mcp_settings`…)
  seront relancés après l'alignement : un échec y est soit une garde légitime (on la respecte, motif écrit),
  soit une copie de valeur à mettre à jour.

### L10 — AC-030b

Marge de couverture backend : 0,66 point au 22/10, pour 2 exigés. Cibler `sms` (53,6 %),
`proactive_discussions` (70,2 %), `infrastructure/proactive` (67,9 %), `conversations` (44,1 %). Relever
le plancher une fois la marge ≥ 2 points mesurée.

### L11 — Qualification

**Intégration de `main` — message de la session lia-ae (23/10).** Le propriétaire commitera sur `main` le
retrait du mode « privé » des SMS (ADR-357 amendé, note ADR-358 ; migration `213b9ac595c5` qui révise
`6b7fe9493921` ; `proactive_discussions/privacy.py` supprimé, `sms_context` retiré d'`OpeningDraft`), puis
sortira v3.5.1. À n'intégrer qu'APRÈS ce commit. Fusion simulée par lia-ae sur notre état : 21 fichiers
communs, 18 propres, 3 conflits et 1 piège :
1. `apps/api/src/infrastructure/proactive/notification.py`, signature de `dispatch` : garder notre
   `require_durable: bool = False`, SUPPRIMER `privacy: NotificationPrivacy = NotificationPrivacy.NORMAL`.
   PIÈGE : la ligne de docstring « privacy: Whether the push previews the content or a neutral line. »
   fusionne SANS conflit — la supprimer aussi (mypy ne la voit pas).
2. `apps/api/tests/integration/test_sms_cross_surface_flow.py` : résoudre en
   `assert sent.durably_delivered and "10h30" in dispatch._send_fcm.await_args.kwargs["body"]` puis
   `dispatch._send_channels.assert_awaited_once()` (le test passe désormais par
   `ProactiveTaskRunner(task, dispatcher=dispatch)._dispatch_notification(user, result, target, db)` ;
   vérifier que `durably_delivered` est vrai sur ce chemin).
3. `docs/architecture/ADR_INDEX.md`, statut de l'ADR-358 : garder les deux — « …amended 2026-10-21 (cold
   review, production measurement), 2026-10-22 (operator tick capacity) and 2026-10-23 (execution tables
   measured); its SMS privacy rule withdrawn on 2026-10-23 (ADR-357 amendment). »
Puis : `task test:backend:unit:fast` et
`pytest tests/integration/test_sms_cross_surface_flow.py tests/integration/test_sms_heartbeat.py --no-cov -m integration`.
Vérifier aussi `discussion_runner.py` (notre L8 l'a touché ; la fusion retire l'import `sms_in_context` et
`sms_context=`).

**Simulation recalculée le 23/10 ~18:55** (instantané de l'arbre du worktree sur un index temporaire,
`git merge-tree --write-tree` contre `7777d13c4` = v3.5.1 commitée ; aucune référence, aucun index réel
touchés) : **7 fichiers** en conflit, les 3 ci-dessus plus :
4. `README.md`, ligne des chiffres publics : 287 versions (v3.5.1) ; le nombre de métriques NE se choisit
   pas, il se recalcule (`task release:sync-counts` sur l'état fusionné).
5-7. `docs/maps/{adr-history,functional-map,technical-map}.html` : générés, `task docs:maps` après la
   fusion (`apps/web/src/data/maps/facts.json` fusionne mais se régénère aussi).
Fusionnent proprement : `apps/api/pyproject.toml` (version + réglages de couverture de L10),
`discussion_runner.py`, `runner.py`, les 6 locales, les guides `how.*`, `GETTING_STARTED.md`,
`docs/INDEX.md`, ADR-358, `PROACTIVE_DISCUSSIONS.md`.
**Main réel le 23/10 au soir : `4ef630984`** (v3.5.1 publiée et déployée, puis le test d'aller-retour de la
migration SMS corrigé, `tests/integration/test_sms_migration.py` : fusionne sans conflit). Re-simulation
contre lui : les mêmes 7 conflits ; lia-ae, de son côté, trouve les mêmes. README : 287 versions et 631
métriques (main est resté à 630 depuis la base ; seule la vague a changé ce compte), puis
`task release:check` sur l'état fusionné. Après la fusion : `task lint`, `task test:backend:unit:fast`,
`pytest tests/integration/test_sms_cross_surface_flow.py tests/integration/test_sms_heartbeat.py
tests/integration/test_sms_migration.py --no-cov -m integration`, puis les portes de couverture des deux
suites. Les deux `.env` vivants du démonstrateur (dans `D:\`, ignorés par git) reçoivent les deux clés que
la vague a ajoutées à leurs modèles (`DATABASE_LOCK_TIMEOUT_MS`, `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS`,
AC-028), sans afficher leurs autres valeurs.
Le rejeu A10 et les preuves Docker de L4/L5 qualifient le code de `D:\` (la procédure construit et sert
l'application DANS `lia-web-dev`, qui monte `D:\`) : ils suivent l'intégration, décision du propriétaire.

Rejeu E2E contrôlé A10 : build de production frais, port 3100, 0 retry, `run-native-media.sh` ;
typecheck e2e sur l'hôte. Puis `ci:fast`, le registre mis à jour, la revue finale et la proposition
d'intégration dans `D:\` (décision du propriétaire).

## 5. Journal d'exécution (ajouts uniquement, ordre chronologique)

- **2026-10-23** — Worktree `audit/v14-wave` créé sur `ccd4688c0`. Jonctions ×4, fichiers ignorés ×3.
  Sonde : pytest importe la copie du worktree (1 passé). Fichier de suivi créé.
- **2026-10-23** — Ligne de base du worktree : `task test:backend:unit:fast` (rootdir du worktree,
  8 workers) → 45 935 passés, 19 ignorés, 431 s, code 0, aucun vidage `faulthandler`.
- **2026-10-23** — L1 / AC-031. Constat en construisant la graine : V11, V12 et V13 renumérotent
  chacun leurs constats depuis AC-001. Les « identifiants stables depuis V11 » du protocole n'ont donc
  jamais existé : ils ne le sont que depuis V13. V11 et V12 sont déclarés `legacy_reports`, avec un motif.
  - `docs/audit/findings_register.json` : 40 constats ; AC-040 = sujet V14 d'AC-014, avec les alias
    `V14:AC-014` et `V14R:AC-014`.
  - `scripts/audit/findings_register.py` : bibliothèque standard seulement, lit les `<article id>` de
    chaque rapport ; `--strict` = échec sur un P1 échu sans report valide.
  - Câblage : `lint:docs` (avertissement), `release:check` (`--strict`).
  - Protocole §1.6, §4.3 et §5, et README d'audit : pointent vers le registre.
  - Tests : `test_findings_register_guard.py` (27 passés) ; `test_audit_scripts_cwd.py` étendu (passé).
  - Instruments (`lint:docs:preview`) : doc_audit, doc_facts, agents_mirror, doc_maps et
    findings_register à 0 ; « 40 findings, 26 open (9 P1), 0 P1 past their horizon ».
- **2026-10-23** — L1, revue à froid d'AC-031. Défaut trouvé : une entrée mal formée levait une
  exception au lieu d'une phrase, et le script utilisait `Any`.
  - Script retypé (dataclasses) : la forme est vérifiée clé par clé (clé inconnue ou absente,
    types, dates `YYYY-MM-DD` strictes), puis les règles sémantiques.
  - Règle des preuves (protocole §4.2), désormais vérifiée : chemin existant, ancre présente,
    ADR existant, commit, ou exécution d'un rapport enregistré ; jamais de numéro de ligne.
  - Mutations : 17 mutants, 16 tués ; le survivant est équivalent. Un test ajouté (format ISO
    de base `20260802`, accepté par `fromisoformat`). 40 tests.
  - MyPy strict, Black, Ruff : propres.
- **2026-10-23** — L1 / AC-032. Mesure CI Linux du 22/10 (`3c6795d4b`, job Test Backend,
  lecture seule via `gh`) : 78,67 % ; Windows local du même jour : 78,66 à 78,67 %. L'écart de
  plateforme se compte en centièmes : la « marge d'environ 4 points » est réfutée.
  - `doc_facts` tient le plancher frontend : 4 faits par axe, lus au premier niveau de
    `coverage.thresholds` par profondeur d'accolades (jamais un glob). Forme écrite :
    « statements N / branches N / functions N / lines N », entiers ; une mesure garde ses décimales.
  - Rouge observé : la citation périmée 64/58/58/65 du guide détectée.
  - GUIDE_TESTING : doctrine écrite une seule fois (backend et frontend), planchers en vigueur
    tenus par `doc_facts`, écart mesuré, historique complet (paliers 68 → 78 depuis `git log -G`),
    date d'en-tête supprimée.
  - pyproject, Taskfile et vitest renvoient au guide ; l'affirmation fausse du Taskfile
    (« ≥ 2 points » sur 80,36 %) est supprimée.
  - Mutations : 7 sur 7 tués.
- **2026-10-23** — L1 / AC-039a. `scripts/audit/doc_language.py` (part des mots-outils FR/EN,
  hors code et cibles de liens) et sa base décroissante `doc_language_baseline.json`.
  - Corpus : Markdown suivis, hors exemptions décidées et contenu produit localisé (`*.fr.md`…).
  - Calibration : 792 documents, 727 classés, bimodal ; 4 mots ambigus retirés (`plus`, `par`,
    `son`, `sans`).
  - Graine : 282 documents français figés.
  - `--update` retire sans jamais ajouter ; `--rename OLD NEW` pour un déplacement. Le message
    d'erreur nomme le renommage, pour éviter l'impasse « update puis traduire ».
  - Mutations : 15 sur 15 tués (après un test ajouté sur le code de sortie). 28 tests.
  - Câblage : `lint:docs`, `lint:docs:preview`, `docs:language:update`. CLAUDE.md : règle
    amendée et tableau des instruments (six) ; AGENTS.md régénéré. SCRIPTS.md : 3 lignes
    (dont `doc_maps.py`, qui manquait).
- **2026-10-23** — L1, registre mis à jour : AC-031 et AC-032 `remediated` (preuves) ; AC-039
  reste `open`, avec la remédiation AC-039a, et AC-039b hors vague. Résumé de l'outil :
  « 24 open (8 P1), 2 remediated pending re-audit ».
  - Portes : `lint:backend` (MyPy sur 3 623 fichiers), `lint:ci-parity`, `lint:hygiene` et
    `lint:docs:preview` à 0.
  - **Limite** : `lint:docs` strict signale 4 liens ou chemins vers mes fichiers non suivis. C'est
    attendu (l'index git fait foi) ; ils disparaissent au `git add`, que je ne fais pas.
- **À signaler au propriétaire.**
  - Échéances H0 : AC-003, AC-007, AC-028 et AC-029 arrivent à échéance le 29/10 (AC-031 est
    remédié).
  - AC-002 et AC-005 (hors vague) arrivent à échéance le 19/11 : `release:check` les refusera dès
    le 20/11, sauf report daté et motivé dans le registre.
  - La skill `lia-release` (`.claude/`, sur `D:\`, non suivie) devra mentionner que
    `release:check` refuse un P1 échu (à faire lors de l'intégration, L11).
  - 52 documents vivants portent une date d'en-tête « Dernière mise à jour » ou « Last updated »
    qui vieillit par construction (seule celle de GUIDE_TESTING a été retirée, au titre d'AC-032).
- **2026-10-23** — Clôture de L1 : `task test:backend:unit:fast` → 46 032 passés, 2 échecs, 19
  ignorés, 561 s, aucun vidage du chien de garde.
  - Les 2 échecs (`test_doc_audit_adr_link_guard`, liens et chemins vers mes fichiers non suivis)
    sont attendus : l'index git fait foi, et `lint:docs:preview` (index + `git add -A` simulé)
    est vert. Ils disparaissent au `git add`.
- **2026-10-23** — L2, mesures en lecture seule.
  - CI de `ccd4688c0` (v3.5.0, dépendances courantes) : backend 78,78 % (45 950 passés, 32 min) ;
    frontend 87,8 / 81,77 / 85,41 / 89,35 pour des planchers 85/80/83/87.
    **Marge `branches` frontend : 1,77 point < 2** ; marge backend : 0,78 point.
  - Durées maximales des jobs sur 9 runs `main` réussis : Test Backend 68 min, Integration 44,
    Docker 44, E2E 40, Frontend 17, autres ≤ 7 ; release (build web 68,5), a11y-matrix 75,
    installer-smoke 10, security ≤ 6.
- **2026-10-23** — L2 / AC-033b.
  - `test_telephony_routes_mounted` : le drapeau est posé le temps d'un rechargement de
    `routes` (précédent : `test_router_mounted_whatever_the_ceiling.py`), plus un contrôle
    inverse (drapeau coupé = non monté), sans `noqa`.
  - `kept-as-is` : plafond surchargé à 2 × le plancher configuré (relatif, non codé en dur).
  - Avant : 2 ignorés ; après : 51 passés. Mutations : 3 sur 3 tués.
- **2026-10-23** — L2 / AC-033a.
  - `faulthandler_timeout = 600` et `faulthandler_exit_on_timeout = true` (pytest 9.0.3, sans
    nouvelle dépendance).
  - Garde `test_hung_test_watchdog_guard.py` : un test bloqué volontairement, rejoué sous la
    configuration réelle. En séquentiel et sous xdist : « Timeout », pile du thread, worker
    remplacé, test en échec. Rouge observé avant la configuration (130 s, TimeoutExpired).
  - `timeout-minutes` sur les 25 jobs qui n'en avaient pas (ci ×12, release ×7, security ×4,
    a11y-matrix, installer-smoke), environ 2 × le maximum mesuré, ≥ 10 min.
  - Garde `test_ci_job_timeouts_guard.py`. `lint:ci-parity` vert, 134 tests sur les workflows verts.
- **2026-10-23** — L2 / AC-030a. `scripts/audit/diff_coverage.py`.
  - Lignes ajoutées ou modifiées sous `apps/api/src` depuis la base, non commitées et non suivies
    comprises, renommages suivis ; contre le plancher de pyproject (`doc_facts.floor_values`).
  - Rapport périmé refusé.
  - Base : `--base`, sinon `DIFF_COVERAGE_BASE`, sinon le point de départ depuis
    `origin/main`. Variable vide ou SHA nul : la porte le dit et passe. Base absente du clone
    superficiel : récupérée seule (`--depth=1`), prouvé sur un clone superficiel réel.
  - `check_ci_parity` lit chaque mot après `task` comme une tâche : d'où la base passée par
    variable d'environnement.
  - 19 tests ; mutations : 15 sur 16 tués (survivant équivalent : `/dev/null`), dont un test
    ajouté pour un `diff.renames=false` de l'utilisateur.
  - Câblage : `test:backend:diff-coverage`, `ci:fast`, étape CI juste après la couverture.
  - Docs : GUIDE_TESTING (règle 5 de la doctrine, tableau des jobs), CI_CD (porte, limites de
    temps, compte « 15 appels » remplacé par la règle, puisque ci.yml en compte 20), SCRIPTS,
    CLAUDE.md (une ligne). AGENTS.md régénéré.
  - **À signaler** : la CI tourne à chaque push sur `main`. La porte mesure tout ce qu'apporte
    un push (`github.event.before`) : un push massif peu couvert rougira.
- **2026-10-23** — Suite canonique séquentielle (A11) lancée à 04:53, avec `--durations=40`.
  Pendant son exécution, aucun fichier de `apps/api` n'est touché : des gardes AST relisent `src/`.
  - `tests/_git_sandbox.py` existe : les variables git locales au dépôt, héritées d'un hook,
    redirigent les commandes d'un test vers le vrai dépôt (incident du 02/10).
  - À corriger dès la fin de la suite : `test_diff_coverage_guard` (passer par `run_git`, et une
    fixture qui retire ces variables pour le script testé) et `test_doc_language_guard`
    (même fixture, puisque `tracked_paths` lance git).
- **2026-10-23** — L9 / A15 (AssistantAvatar), sans conflit avec la suite backend.
  - 6 tests de caractérisation d'abord, verts sur l'ancien code : une humeur nulle intercalée
    est sautée, une émotion nulle est retenue, fin d'animation (ping, salve), intensité seule
    sans effet.
  - Piège : sans `AnimationEvent` dans `window`, React écoute `webkitAnimationEnd`.
  - Refactor : décisions pures dans `avatar-transitions.ts` (et leurs tests directs), hook
    `useSnapshotTransitions` (motif « valeur du rendu précédent », vérifié aux 5 règles du
    compilateur), sous-composants de l'info-bulle et de la salve.
  - Mesures : complexité 28 → < 15, `set-state-in-effect` 2 → 0. Bases : react-hooks 30 → 28,
    complexité 39 → 38 (retraits seulement). 106 tests psyche verts, `tsc` non incrémental à 0.
  - Prettier n'est installé nulle part : `pnpm format` ne peut pas tourner, et aucune porte ne
    contrôle la mise en forme du frontend (à signaler au propriétaire).
- **2026-10-23** — L9 / AC-037.
  - Mesure par AST (`as unknown as` / `as any as`) : 119 doubles assertions dans 74 fichiers
    (tests 107, E2E 4, production 8 ; 0 `as any as`). La révision annonçait 108 en tests, par
    motif textuel.
  - `scripts/double-cast.mjs` (compteur pur, `compare`, `shrink`) + `check-double-cast-ratchet.mjs`
    + `.double-cast-baseline.json` (graine unique). `--update` abaisse sans jamais ajouter.
  - Câblage : `pnpm double-cast:ratchet` dans `lint:frontend`, donc en CI. Une sonde réelle (un
    fichier temporaire) fait échouer le cliquet.
  - Volet backend : 9 modules de test sous MyPy strict sans exemption (`TYPED_TESTS` de
    `lint:backend`).
  - Docs : CLAUDE.md, apps/web/CLAUDE.md, GUIDE_DEVELOPPEMENT, CI_CD (les « trois ratchets »
    sont nommés, plus comptés).
- **2026-10-23** — L9 / A13 (AC-040), en cours.
  - Recensement par AST des 14 exclusions : 10 portent un point de décision ou un hook
    (`dialog` 5 + 2 hooks, `dropdown-menu` 5, `separator` 3, `skeleton` 2, `slider` 1,
    `tooltip` 1 défaut, `alert-dialog` 1 + hook, `input`/`textarea` 1 + hook, `toaster` 1 + 2
    hooks). Restent exclus `accordion`, `label`, `switch`, `tabs`.
  - `coverage-exclusions.mjs` (liste + motifs) et `scripts/decision-points.mjs`. Le garde
    `coverage-exclusions.guard.test.ts` (5 tests) refuse un exclu qui gagne de la logique.
  - Mesure AVANT lancée (suite complète, `json-summary`). Le changement de `vitest.config.mts`
    attend sa fin.
- **2026-10-23** — A11, suite canonique séquentielle (`task test:backend:unit:coverage`,
  Windows, dépendances courantes, 57 min 24 s) :
  - 46 061 passés, 2 échecs (les liens vers des fichiers non suivis, preview vert), 17 ignorés
    au lieu de 19 : les 2 tests d'AC-033b tournent.
  - **78,78 %**, exactement la valeur de la CI Linux sur `ccd4688c0` : écart de plateforme nul.
  - 0 vidage du chien de garde. Test le plus lent : 89,7 s (séquentiel, sous couverture) : la
    borne de 600 s vaut 6,7 fois le pire cas. pytest suspend la borne dans son propre pdb.
  - `task test:backend:diff-coverage` sur ce rapport : « no measured line changed since
    ccd4688c015d » (exact : aucune modification de `src/`).
- **2026-10-23** — Revue à froid de L2.
  - `release.yml`, `build-candidates` : la borne de 90 min avait été fixée quand le build web
    prenait 34 à 39 min. Mesuré : jusqu'à 68,5 min (6 runs), soit seulement 1,3 fois. Portée à
    140 min par la règle même de son commentaire, avec la nouvelle mesure écrite.
  - Isolation git des tests : `isolate_from_the_running_repository` ajoutée à `_git_sandbox`
    (et prouvée par son garde), appliquée aux gardes de `diff_coverage` et de `doc_language`.
    `_git` passe par `run_git`.
- **2026-10-23** — A13, mesures (suite frontend complète, sans charge concurrente).
  - Avant : global 87,81 / 81,8 / 85,43 / 89,36 ; glob `ui` 97,70 / 93,14 / 96,48 / 98,19
    (32 fichiers).
  - Après : global 87,83 / 81,81 / 85,45 / 89,37 ; glob `ui` 96,88 / 92,16 / 94,44 / 97,20
    (42 fichiers), pour un seuil de 88/84/84/89.
  - `separator` (0 %) et `dropdown-menu` (62,5 % des branches) reçoivent des tests de
    comportement : séparateur décoratif ou sémantique ; menu non modal par défaut (pas de
    `data-scroll-locked`), modal sur demande, variante `inset`. Mutations : 4 sur 4 tués,
    témoin à 0.
  - Un passage sous charge (la suite backend en parallèle) a fait dépasser son délai de 15 s à
    `ChangelogHistory` ; seul, ce test passe en 2,7 s.
- **2026-10-23** — Registre : AC-031, AC-032, AC-037 et AC-040 `remediated` ; remédiations
  partielles inscrites pour AC-033, AC-030 et AC-013 (pilote). Outil : « 22 open (8 P1),
  4 remediated pending re-audit ».
- **2026-10-23** — L3 (AC-003), TDD sur les cinq sites, chacun rouge d'abord.
  - Doublure `tests/helpers/notifications.py` : le VRAI `dispatch` sur des canaux scriptés
    (`ScriptedChannels`, `sse_only()`), aux types du contrat de production. Les doubles
    qui renvoyaient `None`, `MagicMock(success=True)` ou `SimpleNamespace(success=True)` sont
    remplacés.
  - Sites : reaper, synthèse de retour, relais d'appel (`settle_owner_call`, jamais exercé
    jusqu'ici : 4 tests), pairs (`dispatch_error` relançable), diagnostics (`notified_at` suit
    le compte durable).
  - Garde AST `test_durable_delivery_guard.py` : 14 appels `dispatch` recensés, 11 jetés
    (5 durables, 6 best-effort motivés), 3 lus (passés à `durably_delivered`).
  - Mesures PostgreSQL (testcontainers, hôte, `--no-cov`) : SSE seul relancé jusqu'au plafond
    puis FAILED ; archive en échec SQL → 25P02 sur le chemin d'échec AVANT correctif, compté
    APRÈS ; COMMIT sur transaction avortée : aucune exception, tout annulé (sonde jetable).
    Diagnostics : un administrateur dont l'archive échoue en SQL n'affame plus les autres.
  - Trouvé en route : `test_real_template_formats_with_every_ingredient_slot` lisait la base
    de développement par quatre ingrédients best-effort (déjà sur HEAD). Rendu hermétique, avec
    des marques connues : le test vérifie maintenant chaque ingrédient.
  - **À signaler au propriétaire** : le garde réseau de la suite unitaire laisse passer le
    loopback, donc un test unitaire peut lire la base de dev sur `localhost:5432` sans échec.
  - Typage : 5 nouveaux fichiers de test sous MyPy strict (`TYPED_TESTS`).
  - Suite rapide complète (`task test:backend:unit:fast`, 6 min 14 s) : 46 097 passés,
    17 ignorés, 2 échecs attendus (`test_doc_audit_adr_link_guard` : liens vers les fichiers
    non suivis de L1, L2 et L9 ; `lint:docs:preview` vert). `task test:markers` vert.
  - Après la suite, même famille que le webhook : `_cancel_and_notify` (pairs) laissait
    l'annulation en attente pendant l'avis best-effort ; une archive en échec SQL l'annulait en
    silence et le message était re-réclamé 10 min plus tard. Annulation committée d'abord
    (test rouge d'abord).
  - Garde durci (rouge d'abord) : un dispatcher se reconnaît à ce qui l'a construit
    (`notifier = NotificationDispatcher()`), plus seulement au mot « dispatcher » ; 5 cas
    synthétiques épinglent le balayage.
  - Docs : TELEPHONY (durabilité du retour), DIAGNOSTICS_DOMAIN, GUIDE_HEARTBEAT (journal),
    amendement ADR-263 du 23/10, CLAUDE.md (2 lignes), AGENTS.md régénéré. Registre : AC-003
    `remediated` (« 21 open (7 P1), 5 remediated pending re-audit »).
- **2026-10-23** — L3 clos. Pour L11 : le CLAUDE.md de `D:\` (main) a avancé depuis la base du
  worktree (il cite ADR-362 et 630 métriques ; travail du propriétaire ou de Codex, peut-être
  non commité). L'intégration se fera contre l'état COURANT de `D:\`, fichier par fichier,
  jamais par copie brute du worktree (CLAUDE.md, AGENTS.md, Taskfile.yml, registre).
- **2026-10-23** — L4, étape 1 faite (porte + échange, non branchés).
  - `oauth_refresh_exchange.py` : un POST relancé (constantes extraites : 3 tentatives, attentes
    2-10 s), refus typés `REVOKED` / `TRANSIENT` / `UNREADABLE`, borne dérivée
    `worst_case_refresh_seconds()` = 34 s par défaut ; 21 tests (rouges d'abord).
  - `oauth_refresh.py` : `ensure_fresh_credentials(target, *, current, force, refresh_before)`,
    contrat `RefreshTarget`, verdicts typés `_Granted` / `_Refused`, marqueur Redis
    `<tentative>:<verdict>` (famille `oauth_refresh`), TTL du claim 39 s.
    `invalidate_oauth_connector_cache` y est déplacée (sinon cycle avec le runtime des grants).
    Métriques `oauth_refresh_outcomes_total{kind,outcome}` et `oauth_refresh_flights_total{kind,how}`
    (pas encore sur un panneau : à câbler à l'étape 4, sinon le cliquet de couverture rougit).
  - Porte écrite AVANT ses 19 tests : passe de MUTATION (7 mutants, script dans le scratchpad
    `l4/mutate_door.py`) — 2 survivants au premier passage (double lecture, chemin rapide) →
    2 tests ajoutés ; un test d'annulation qui pendait sous mutant réécrit avec `asyncio.wait`
    (aucune annulation pour observer). Résultat : 7/7 tués.
  - PIÈGE du harnais : `subprocess.run(capture_output=True)` attend des tuyaux qu'un petit-fils
    de pytest garde ouverts → sortie vers un fichier.
  - Double `tests/helpers/redis_double.py` (SET NX EX, libération par jeton propriétaire).
- **2026-10-23** — L4, étapes 2 et 3 (code) faites ; portage des tests EN COURS.
  - `oauth_refresh_targets.py` : `ConnectorTokenTarget[C]` (codec + échange ; instances
    `legacy_connector_target`, `hue_remote_target`), `GrantTokenTarget` (verrous grant puis liens
    triés par id, propagation, `ERROR` des scopes non couverts, lecture exigeant le lien à CE grant,
    `current(db)` = une lecture sur la session de l'appelant pour le chemin rapide), `expires_before`.
    Hue LOCAL : l'échange lève `ValueError` (pas de jeton, rien de révoqué).
  - PostgreSQL + Redis réels : 9 tests (`tests/integration/domains/connectors/test_oauth_refresh_pg.py`),
    mutation des magasins 4/4 tués (script `l4/mutate_targets.py`).
  - Branchés : `get_connector_credentials` (grant et hérité), `refresh_connector_credentials`
    (forcé ; Hue désormais routé, avant : ValueError → 500), `token_refresh.py` (session courte
    fermée AVANT les appels réseau, ADR-304), `base_oauth_client._refresh_access_token` (plus
    d'`OAuthLock`), Hue `_ensure_valid_remote_token` (marge ajoutée, connecteur disparu →
    `ConnectorRevokedError`). `_refresh_oauth_token` et `_get_oauth_refresh_config` SUPPRIMÉS de
    `service.py`. Journaux `error=str(e)` → `error_type` dans les fichiers touchés.
  - Résidu consigné : le service « sûr en concurrence » garde la transaction de LECTURE du tour
    pendant un rafraîchissement (rare, sans verrou de ligne désormais) ; la terminer serait finir la
    transaction d'un appelant (`owns_session`).
  - RESTE : porter les tests qui figent les anciennes coutures — unitaires :
    `connectors/test_base_google_client.py`, `test_google_gmail_client.py`,
    `test_connector_client_error_contract.py`, `test_connector_service.py`,
    `domains/connectors/test_legacy_oauth_binding.py`, `test_oauth_grant_runtime.py` (à supprimer
    avec le module) ; intégration : `domains/connectors/test_client_session_ownership.py`,
    `test_base_google_client_integration.py`, `test_connectors_service.py`,
    `test_connector_removal_owner.py` (`OAuthGrantRuntime._linked`), `test_oauth_grant_runtime.py`
    (13 tests, données committées). Puis supprimer `oauth_grant_runtime.py`, `OAuthLock` (+ famille
    `oauth_lock`, `REDIS_KEY_OAUTH_LOCK_PREFIX`, 5 métriques, réglage et 2 gabarits,
    `connector_token_refresh_total`), tableau 10, garde AST, ADR-302, docs, registre.
- **2026-10-23** — L4, deux défauts de la porte trouvés en portant `test_client_session_ownership.py`.
  - (a) Transaction tenue pendant l'échange : `get_connector_credentials` lit la ligne sur la
    session de l'appelant PUIS entre dans la porte ; une unité qui POSSÈDE sa session (client
    détaché, emballage « sûr en concurrence » du tour, `open_active_client`) la garde donc en
    transaction pendant l'appel au fournisseur — et l'emballage garde aussi son VERROU (34 s au pire
    pour les outils parallèles du tour). Constat sur `ccd4688c0` : l'ancien chemin faisait déjà ainsi
    en production (la « double vérification » du client rafraîchissait dans `get_connector_credentials`) ;
    la branche « commit avant l'appel » que prouvait le test n'était atteinte que sous mocks.
    Décision : lecture en deux temps — `ConnectorService.read_connector_credentials` (lecture,
    statuts, déchiffrement, compte de composition ; AUCUN appel réseau) renvoie un
    `StoredCredentials` dont `fresh()` passe par la porte ; `get_connector_credentials` = les deux
    à la suite (inchangé pour un appelant qui prête sa session). Les trois portes d'ADR-304 lisent
    dans leur unité et rafraîchissent APRÈS : client (`_refresh_access_token`), emballage du tour
    (verrou relâché avant la porte), `open_active_client`. Hue le faisait déjà.
  - (b) Interblocage possible : la porte écrit sur SA session ; un appelant dont la transaction
    ouverte tient la ligne du connecteur (ou le grant, ses liens) et demande un rafraîchissement
    attendrait la porte, qui attendrait son verrou — sans fin, invisible pour PostgreSQL (même
    classe que le gel Workboard de prod). Décision : chaque écriture de la porte sous
    `SET LOCAL lock_timeout` borné (précédent `api_key_use.py`), refus classé par SQLSTATE
    (`classify_database_error` = `timeout`), jamais par message. Issue `write_contended` : le
    demandeur reçoit les identifiants échangés (non persistés), les attendants reçoivent FAILED
    (jamais le jeton périmé resté stocké, qui déclencherait l'invalidation sur 401) ; issue
    `revocation_contended` : refus « révoqué » sans transition persistée. Preuve PostgreSQL à deux
    sessions (une tient `FOR UPDATE`, la porte rend la main dans la borne).
  - FAIT (b) : `_transition` (session courte, `SET LOCAL lock_timeout` = réglage
    `OAUTH_REFRESH_WRITE_LOCK_TIMEOUT_MS`, défaut 2000, bornes 100-10000 ; constante, `LocksSettings`,
    `.env.example`, `.env.prod.example`, `validate_config.py`), issues `write_contended` (demandeur servi
    sans écriture, attendants FAILED) et `revocation_contended` (FAILED pour tous — jamais une fausse
    déconnexion : correction de la décision ci-dessus). TTL du claim = échange au pire + UNE transition
    bornée + marge. 7 tests unitaires rouges d'abord ; 3 tests PostgreSQL (ligne tenue, lien de grant
    tenu, révocation invérifiable) écrits pour ÉCHOUER sans pendre ; 2 mutants tués (borne retirée,
    contention lue comme écriture perdue). 3 `# noqa: BLE001` que j'avais écrits retirés.
  - FAIT (a) : `ConnectorService.read_connector_credentials` → `StoredCredentials` (dans
    `oauth_refresh_targets.py`), `fresh()` = la porte + contrôle du compte de composition ;
    `get_connector_credentials` = les deux. Branchés : emballage du tour (verrou et transaction relâchés
    avant la porte), client (`fresh()` APRÈS l'unité), `open_active_client` (après la fermeture de sa
    session ; un `Any` retiré). Tests rouges d'abord + 3 mutants tués (unitaire) ; PostgreSQL :
    `test_client_session_ownership.py` porté sur données COMMITTÉES (la porte lit sur ses sessions),
    mutant « fresh() dans l'unité » tué (`[[True]]`). Double partagé `ServedCredentials`
    (`tests/helpers/oauth_refresh_io.py`). Oracle vide corrigé au passage : un test Gmail vérifiait
    qu'une méthode INEXISTANTE (`refresh_oauth_token`) n'était pas appelée.
  - Résidu (inchangé, consigné) : les ~95 autres constructions de `ConnectorService(db)` qui lisent
    par `get_connector_credentials` sur une session qu'elles tiennent gardent leur transaction de
    lecture pendant un rafraîchissement (rare, borné, sans verrou de ligne désormais).
  - L11 : les `.env` VIVANTS du démonstrateur (`.env.demo-instance`, `.env.demo-instance.prod`, non
    suivis, absents du worktree) ne listent pas les délais OAuth — rien à y ajouter ; vérifier à
    l'intégration qu'ils ne portent pas `OAUTH_LOCK_TIMEOUT_SECONDS` (supprimé à l'étape suivante).
- **2026-10-23** — L4, portage et suppression faits.
  - Intégration portée sur données COMMITTÉES (la porte lit sur ses sessions) : helpers partagés
    `commit_owner` (`tests/helpers/committed_users.py`) et `commit_expired_connector` /
    `expired_ciphertext` (`tests/helpers/oauth_refresh_io.py`). `test_connectors_service.py`
    (rafraîchissement expiré, manuel, `invalid_grant` qui déconnecte ; la classe
    `TestRefreshOAuthToken` de la méthode supprimée disparaît, ses cas sont prouvés par
    `test_oauth_refresh_exchange.py`), `test_base_google_client_integration.py` (4 patchs morts
    `get_redis_session` déballés), `test_connector_removal_owner.py`
    (`GrantTokenTarget._locked_links`), `test_oauth_grant_runtime.py` → RENOMMÉ
    `test_oauth_shared_grants.py` (12 tests, les 12 d'origine ; les 6 qui rafraîchissent passent
    par le vrai échange HTTP simulé et le vrai Redis — l'invalidation du cache prouvée sur la clé).
  - SUPPRIMÉS : `oauth_grant_runtime.py`, `infrastructure/locks/oauth_lock.py` (+ export),
    5 métriques `oauth_lock_*`, `connector_token_refresh_total`, `OAUTH_LOCK_TIMEOUT_SECONDS`
    (+ `OAUTH_LOCK_RETRY_INTERVAL_MS`, `OAUTH_LOCK_MAX_BACKOFF_EXPONENT`,
    `REDIS_KEY_OAUTH_LOCK_PREFIX`), famille `oauth_lock`, réglage `oauth_lock_timeout_seconds`,
    lignes des deux gabarits `.env`, borne de `validate_config.py`.
  - Tableau 10 : panneaux 11, 12, 18, 42 remplacés sur place (issues, partage, refus, écritures
    perdues/contestées — `or vector(0)` + `noValue` pour les deux rares) ; gardes d'observabilité
    et cliquet de couverture verts.
  - Garde `test_refresh_grant_single_sender_guard.py` (3 formes : dict, mot-clé, corps encodé ;
    exception `mcp/auth.py` motivée, exception périmée refusée) ; rouge prouvé sur l'ANCIEN
    `service.py` (ligne 1330).
  - Docs : amendement ADR-302 (fr) ; notes ADR-021 (fr), ADR-029 et ADR-047 (EN — ce sont des
    documents anglais : une note en français les faisait basculer « nouveau document français »
    au cliquet de langue) ; ADR_INDEX (historique + amendement 302) ; OAUTH, GOOGLE_CONTACTS
    (dépannage : `error=str(e)` → `error_type`), CONNECTORS_PATTERNS, TOOLS (l'extrait décrivait
    une méthode qui n'a jamais existé), MICROSOFT_365, MCP_INTEGRATION, GUIDE_BACKGROUND_JOBS,
    TIMEOUT_REGISTRY (ligne pointant la source au lieu de recopier la valeur). CLAUDE.md : une
    règle de 5 lignes ; AGENTS.md régénéré. Registre : AC-029 `remediated`.
  - PIÈGES de la journée : `Path.write_text` → CRLF sous Windows (un test et
    `doc_language_baseline.json` touchés, normalisés en octets ; `doc_language.py` écrit désormais
    `newline="\n"`, test rouge d'abord) ; `$'\r'` inerte dans l'outil Bash (compter les CRLF par
    `git ls-files --eol` ou en octets) ; une ligne de commande après un heredoc en échec s'exécute
    quand même (séparer par `&&`).
  - RESTE L4 : suite unitaire rapide complète, revue adversariale à froid, preuve OAuth sur dev
    (compte de preuve), fiche mémoire.
- **2026-10-23** — L4, revue adversariale à froid.
  - DÉFAUT trouvé et corrigé : dans un grant partagé, le refus « inactif » décrit le LIEN du
    service qui a lancé la tentative, mais il était remis tel quel à ceux qui la rejoignaient
    (même worker) ou lisaient son verdict (autre worker) — un service encore lié recevait un
    « reconnectez » nommant le mauvais connecteur quand un autre service était détaché pendant
    le rafraîchissement. Correction : `_Refused.holder` (le porteur dont un refus « inactif »
    énonce l'état), `_flown` (un vol du worker), `_refuses_another_holder` ; l'appelant
    redemande UNE fois pour lui-même, deux refus visant d'autres porteurs → `failed_error`
    (jamais « reconnectez », jamais de boucle). 4 tests rouges d'abord + 1 de non-régression ;
    3 mutants tués. Point 5 ajouté à l'amendement d'ADR-302.
  - Accepté et consigné (pas de correction) : un appelant qui REJOINT un vol pendant qu'on
    détache son propre lien reçoit le jeton du grant — sa lecture précédait le détachement,
    c'est la course ordinaire « lire puis utiliser », bornée par la durée du vol. Le job
    anticipé compte « refreshed » quand un appel à la demande a trouvé le jeton frais à 5 min
    près sous son seuil de 30 min : le passage suivant réessaie.
  - Petits correctifs : clés Redis de test avec TTL (`_CACHED_TTL_SECONDS`, Redis
    d'intégration partagé) ; `ServedCredentials.asked` devient un oracle (le client demande
    le jeton frais exactement une fois).
  - Résidu inchangé : des `error=str(e)` antérieurs subsistent dans des fichiers touchés
    (`service.py` ×5, client Hue ×2, `dependencies.py` ×1), hors des lignes changées et
    acceptés par le garde ADR-317 ; les convertir ôterait un diagnostic aux opérateurs.
  - Vérifs : mypy `src` (3 624 fichiers) et strict `TYPED_TESTS` (23) verts ; import de
    l'application depuis le worktree (`.env` de D:\ chargé EN MÉMOIRE, aucune copie de secret ;
    lifespan non lancé — il démarrerait les planificateurs contre la base de dev) : OK.
  - Preuve Docker dev + OAuth réel sur un compte de preuve : REPORTÉE à L11. Docker dev exécute
    le dossier D:\ (projet compose « lia » partagé) ; lancer la pile depuis le worktree
    remplacerait les conteneurs du propriétaire, qui travaille en parallèle sur D:\.
- **2026-10-23** — L5, calibration (avant code).
  - Prod en lecture seule (SSH, `curl` depuis `lia-api-prod` vers Prometheus, connexion jamais
    affichée) : la prod ne GARDE que 4 séries PostgreSQL (`pg_up`, `pg_settings_max_connections`,
    `pg_stat_database_numbackends`, `pg_stat_database_tup_fetched` — listes de rétention
    d'ADR-333) : aucune durée de transaction ni attente de verrou côté serveur. Calibration prévue
    sur l'exporteur IMPOSSIBLE telle quelle ; accès direct à la base exclu (Q7).
  - Ce que la prod garde : `db_transaction_duration_seconds` (durée de vie d'une session côté
    application). 7 jours : 467 983 sessions de fond dont 746 > 10 s, 72 280 de requête dont
    106 > 10 s ; le dernier seau est 10 s → queue inconnue au-delà.
  - Les 53,5 s de dev (07/10) : séries et journaux EXPIRÉS (Prometheus dev 15 j, Loki dev vide sur
    la fenêtre) → inexplicables ; sous la borne retenue.
  - DÉCISION (sans menu) : bornes prudentes `DATABASE_LOCK_TIMEOUT_MS` = 30 s et
    `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` = 300 s (> 5 × le pire cas mesuré ; ne coupe que
    l'épinglage pathologique, cf. les 863 s d'ADR-304), et rendre la queue OBSERVABLE : seaux
    au-delà de 10 s sur `db_transaction_duration_seconds` + compteur des coupures au niveau du
    moteur, panneau et alerte. Réévaluer les bornes sur ces mesures après déploiement.
- **2026-10-23** — L4 CLOS (hors preuve Docker, reportée à L11).
  - Suite unitaire rapide (options du hook, `-n 8 --dist loadscope`) : 46 156 passés, 17 sautés,
    6 échecs analysés — 2 artefacts d'index attendus (`test_doc_audit_adr_link_guard` : liens et
    chemins vers des fichiers NEUFS non suivis ; aperçu `lint:docs:preview` vert), 3 doubles de
    test du heartbeat restés sur l'ancienne lecture (`test_context_aggregator.py`, portés : 88
    verts), 1 dérive de compte publiée (métriques 630 → 626 : 6 retirées, 2 ajoutées) réparée
    par `bump_surfaces.py --counts-only` (49 citations, garde vert) puis AGENTS.md régénéré.
  - F006 (`check_test_marker_coverage.py`) : OK, 52 637 tests, aucun orphelin. Frontend :
    `vitest run src/components/landing` 37 fichiers, 610 tests verts.
  - L11 : RELANCER `task release:sync-counts` sur l'état FUSIONNÉ (D:\ peut avoir ajouté ou retiré
    des métriques de son côté), puis indexer avant `lint:docs` strict.
- **2026-10-23** — L5 (AC-028) fait, suite d'intégration complète EN COURS.
  - MESURÉ avant code (essais jetables, base de dev, `SELECT 1`) : après la fin d'une transaction
    inactive par le serveur, asyncpg lève `InterfaceError` SANS SQLSTATE (le 25P03 se perd) ;
    `handle_error` voit `is_disconnect=True`, `is_pre_ping=False` ; le moteur se rétablit
    (`pool_pre_ping`). Conséquence : compter cette borne par la durée d'inactivité que le moteur
    garde, pas par le SQLSTATE.
  - Code : `infrastructure/database/server_bounds.py` (`engine_server_settings`,
    `install_bound_counter`, `bound_reached`) ; `session.py` envoie les bornes
    (`connect_args.server_settings`) et installe le compteur ; réglages
    `DATABASE_LOCK_TIMEOUT_MS` (30 000) et `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` (300 000), 0 =
    réglage du serveur ; métrique `db_bound_reached_total{bound}` ; seaux de
    `db_transaction_duration_seconds` jusqu'à 600 s ; Alembic sans borne (garde AST).
  - DÉFAUT TROUVÉ PAR LE TEST PostgreSQL et corrigé : mon écouteur `rollback` lisait `conn.info`
    sur une connexion INVALIDÉE → revalidation → `PendingRollbackError` au rollback qui suit une
    déconnexion (il cassait la reprise de TOUTE session dont la connexion meurt). Règle : une
    connexion invalidée n'est jamais relue (2 tests unitaires + le test PG).
  - Le conftest d'intégration (redirection du moteur global) porte désormais les bornes et le
    compteur : la suite d'intégration tourne sous les bornes de production.
  - Tests : 17 unitaires, 4 PostgreSQL (verrou dans sa borne et compté, transaction inactive
    terminée/comptée/pool rétabli, `SET LOCAL` prioritaire, sessions bornées) ; 4 mutants tués ;
    promtool vert (2 tests ajoutés).
  - Observabilité : panneau « Bounds reached (by bound) » + série P99.9 sur « Tx Duration » (tableau
    03) ; alerte `DatabaseBoundReached` (`core_api`, seuil zéro, gabarit + rendu production —
    le moteur de rendu écrit CRLF sous Windows : normalisé) ; fiche
    `docs/runbooks/alerts/DatabaseBoundReached.md` indexée.
  - Gabarits (règle AC-036, valeur = défaut des constantes) : `.env.example`, `.env.prod.example`,
    `.env.min.prod.example`, `.env.demo-instance.example`, `.env.demo-instance.prod.example` ;
    `validate_config.py` ; TIMEOUT_REGISTRY (lignes pointant la source) ; amendement ADR-304 (fr) ;
    CLAUDE.md (4 lignes) + AGENTS.md ; AC-028 `remediated` ; métriques 626 → 627
    (`bump_surfaces.py --counts-only`). Hygiène, 5 instruments de doc (aperçu), mypy strict du
    nouveau test : verts.
  - L11 : les 2 `.env` VIVANTS du démonstrateur (sur D:\) reçoivent les deux lignes ; preuve
    Docker dev (`SHOW lock_timeout` depuis `lia-api-dev`) après intégration.
- **2026-10-23** — L6, mesures (avant code ; suite d'intégration L5 en cours).
  - A03 FAIT côté fichier : `.dockerignore` racine `**/.next-e2e*` → `**/.next-*` (D:\ porte
    `apps/web/.next-public-screenshots`, qui entrait dans le contexte de l'image web — contexte = la
    racine pour les deux Dockerfile web). Reste : garde texte + sonde BuildKit.
  - A14a MESURÉ : sonde mypy (config du scratchpad : les 6 codes retirés + `unused-ignore` réactivé
    dans `services.hitl.*` et `infrastructure.llm.*`) → AUCUNE autre erreur, 11 `type: ignore`
    inutiles (pas 12 : un a disparu avec les lots précédents) — IDENTIQUE sous Windows et sous Linux
    (conteneur jetable de l'image `lia-api-dev`, `--network none`, `src` monté en lecture seule).
    Les 3 `import-not-found` visent des paquets épinglés dans le lock (anthropic, langchain-deepseek,
    langfuse). Plan : retirer les 11, les 6 codes, et `unused-ignore` des deux surcharges (8 paires),
    puis `measure_mypy_debt.py --update`.
  - AC-035 : 15 sites confirmés (12 ASYNC240, 3 ASYNC230) ; ASYNC1 (27, dont ASYNC109) reste hors
    sélection, comme décidé.
- **2026-10-23** — L6 terminé (AC-035 `remediated`).
  - A05 : `wait_all_background_tasks` annule PUIS joint ce qu'il annule
    (`BACKGROUND_TASKS_CANCEL_JOIN_TIMEOUT_S` = 5 s, compté dans le budget d'arrêt), nomme une tâche
    qui ne s'arrête pas (`background_tasks_not_joined` ; noms vérifiés : libellé + identifiant) ;
    `cancel_all_background_tasks` (aucun appelant) supprimé. 3 tests.
  - A04 : client Hue fermé sur tous les chemins (activation locale : AVANT les écritures ; route de
    test : succès, échec, annulation). 6 tests.
  - A14a : 8 paires MyPy retirées (6 codes morts + `unused-ignore` ×2), 11 `type: ignore` inutiles ;
    base 81 paires. `measure_mypy_debt.py` et `doc_language.py` écrivent en LF (tests).
  - A03 : `.dockerignore` `**/.next-*` ; garde `test_dockerignore_next_dists_guard.py` (ROUGE sur le
    `.dockerignore` de HEAD : `.next-*` manquant) ; sonde BuildKit (contexte synthétique,
    `FROM scratch` + export local, rien de tiré ni d'exécuté) : HEAD laissait entrer
    `.next-public-screenshots` et `.next-hitl-validation`, l'actuel la source seule. Mesuré sur D:\ :
    `.next-public-screenshots` = 13 051 fichiers, 6,6 Go, entraient dans chaque construction web.
  - AC-035 : ASYNC2 actif sur `src`, exempté pour `tests/` par chemin (raison écrite dans
    `pyproject.toml` : la règle protège la boucle SERVIE ; 58 sites dans les tests) ; 15 → 0.
    - STT : sonde AVANT correctif, 3 moteurs : 4 lectures sur 4 dans la boucle, témoin 0 fois pendant
      une lecture. `infrastructure/multipart_upload.py` : corps identique OCTET POUR OCTET à httpx
      (oracle httpx ; mutant « sans échappement » tué), longueur déclarée, fichier modifié en cours
      d'envoi = `OSError` ; `voice/stt/audio_file.py` : ouverture commune (`provider_http_error` ×3).
      Parité : une lecture qui échoue en cours d'envoi reste `OSError` pour les 3 (ElevenLabs perd
      son `except OSError` large). 12 tests (témoin ; fermeture sur réponse, refus, annulation APRÈS
      la lecture en vol), 5 passages stables, voix sous xdist : 883 verts.
    - Export : `publish_archive` renomme DANS son nettoyage (renommer avant le `try` aurait laissé une
      archive orpheline à l'annulation) ; `build_export_archive` prépare, mesure et nettoie hors
      boucle. Défaut trouvé À FROID : deux appels de nettoyage successifs laissaient l'archive publiée
      sous annulation répétée (test rouge, puis UN appel `_discard_build`, vert).
    - Chemins RAG : les 3 copies de la validation → `owned_document_path` (`document_access.py`),
      14 tests (liens compte/espace/fichier, jonctions simulées, lien voisin que seul `is_symlink`
      refuse) ; `bookmark_delete_scope` cherche sous l'acteur (MyPy l'exigeait ; égalité prouvée par
      `require_owned_projection`) ; `upload_storage.prepare_space_directory` (racine passée par le
      service).
    - PIÈGE rencontré (mémoire : « lecture de settings déplacée ») : 2 passages ont écrit sous
      `C:\app\data\rag_uploads` (fichiers de test, créés 11:53:56) — supprimés ; `C:\app` vide reste
      (suppression bloquée par l'outil) → au propriétaire.
    - `peer_image` (2 helpers en thread) ; `skills/executor` (`read_text` ; fichier à 599/600 SLOC :
      nombre de lignes constant, journal `str(exc)` laissé, hors périmètre).
    - CLAUDE.md (2 phrases) + AGENTS.md ; guides HOW ×6 (ASYNC2 dans la ligne Ruff) ; registre.
  - Trouvé par les suites ou à froid, hors AC-035 : (1) L5 — `DatabaseBoundReached` n'avait pas de
    recette de preuves (ADR-266) : requête `db_bounds_reached` + recette ; (2) L3 —
    `test_sms_cross_surface_flow.py` lisait `NotificationResult.success` (retiré par AC-003) →
    `durably_delivered` ; balayage AST : seul lecteur périmé ; (3) cartes : `multipart_upload`
    rattaché à `t.voiceinfra`, `docs:maps` régénéré (55 modules).
  - Résidu mesuré (recensement AST, `scratchpad/l6/async_fs_census.py`) : 82 appels de fichiers
    synchrones plausibles hors de portée de Ruff dans des corps async, presque tous des métadonnées ;
    2 déplacent du contenu (capture d'écran `agents/api/service.py:1121`, `rmtree`
    `skills/router.py:209`) → proposés au propriétaire comme suite.
  - Preuves : intégration des chemins touchés : 48 fichiers, 454 passés + 1 échec (le lecteur
    périmé de L3), corrigé et repassé seul ; ruff + black `src tests` verts ; mypy complet `src` :
    1 erreur (marque-page) → corrigée ; mypy des 78 modules touchés vert ; doc_facts, doc_language,
    agents_mirror verts ; doc_audit et doc_maps verts en preview (`--include-unstaged`). Suite
    unitaire rapide complète (2e passage) : 46 235 passés, 17 ignorés, 3 échecs = les 3 gardes de
    documentation en vue INDEX (fichiers neufs non indexés) — comportement voulu : indexer, ne pas
    « corriger ».
  - Lancé : les 281 fichiers d'intégration restants de L5 (1 930 tests), en tâche de fond.
- **2026-10-23** — Suite d'intégration COMPLÈTE : les 281 fichiers restants = 1 927 passés, 2 ignorés
  (psycopg sous Windows, préexistant), 1 échec → `test_connectors.py::TestConnectorRefresh`, PÉRIMÉ
  depuis L4 : connecteur créé dans la transaction du test, invisible à la porte (sessions propres) → 403
  « revoked » ; il acceptait aussi 200/400/500 et aurait envoyé un vrai POST à Google. Réécrit au niveau
  du service, lignes COMMITTÉES (`commit_owner`, `commit_expired_connector`), échange scripté : un seul
  échange sur `refresh-1`, jeton émis stocké (13 tests du module verts). Bilan intégration de la vague :
  63 % (L5) + 48 fichiers touchés (L6) + 281 restants, 0 échec ouvert.
- **2026-10-23** — L7, A07a/b FAIT (AC-004 `remediated`).
  - RED mesuré par la porte AVANT tout changement (entrypoint actuel muni du seul `--render-only`) :
    12 cas sur 14 en échec — équipes jamais atteintes ; Alertmanager REFUSE la config avec Slack critique
    seul (« missing service or routing key in PagerDuty config ») ou PagerDuty seul (« unsupported scheme
    "" for URL ») → il ne démarrerait pas ; un `|` dans le mot de passe casse `sed` ; saut de ligne
    accepté.
  - UN gabarit (`alertmanager-email-only.yml.template` supprimé, montages dev + prod retirés) ; blocs
    `# @begin`/`# @end` retirés au rendu (table dans l'entrypoint) ; routes de gravité `continue: true` ;
    routes d'équipe seulement pour une adresse propre (casse ignorée), Slack sécurité seulement distinct du
    critique, PagerDuty depuis la seule route critique ; routes `postgresql`/`redis` supprimées (même
    public) avec leurs 2 modèles d'e-mail ; substitution LITTÉRALE `awk`/`ENVIRON` (apostrophes
    doublées), saut de ligne refusé (exit 65) ; bandeau sans adresse (garde ADR-317 reprise : elle a
    attrapé 6 lignes de mon premier bandeau).
  - Porte `task test:alertmanager` (+ `task ci`, + étape CI « Observability Config ») :
    `scripts/observability/alertmanager_matrix.py`, 14 cas de
    `alertmanager/tests/routing_matrix.yml` (image, montages et variables LUS dans
    `docker-compose.prod.yml`), `--network none`, `amtool check-config`, rendu de chaque modèle d'e-mail
    nommé (`amtool template render` — check-config ne les exécute pas), `config routes test`, valeurs
    relues. Vert 14/14 ; 4/4 mutants tués + un modèle qui n'échoue qu'au rendu attrapé.
  - Garde statique sans Docker `test_alertmanager_template_guard.py` (7 tests) remplace
    `test_alertmanager_webhook_matrix.py` (réimplémentation Python du rendu, supprimée) ;
    `alertmanager/validate_config.py` (non câblé, syntaxique) supprimé.
  - Changement VISIBLE en production : les e-mails « e-mail seul » prennent les corps HTML de
    `templates/email.tmpl` (rendus par la porte) — écrit dans l'amendement ADR-119.
  - Docs : ADR-119 amendement (+ index), ALERTING.md, GUIDE_OBSERVABILITY.md (arbre de routage et
    modèles), CI_CD.md, commentaires des adresses d'équipe dans `.env.example`/`.env.prod.example`.
  - Reste L7 : AC-006.
- **2026-10-23** — L7, AC-006 FAIT (AC-006 `remediated`) → L7 fait.
  - RED mesuré AVANT correction par la garde inverse `test_metric_producer_guard.py` : rouge sur
    exactement les 4 panneaux orphelins (5 séries). Extracteur `series_read` : commentaires, chaînes,
    variables Grafana, sélecteurs, plages et clauses `by`/`on` retirés ; une cible Loki, Tempo ou SQL
    n'est jamais lue comme PromQL (source de données du panneau ou de la cible, rangées comprises) ;
    `EXTERNAL_PRODUCERS` (9 familles) vérifiés eux-mêmes contre les jobs de `prometheus.yml` ou le
    remote write de `tempo.yml`.
  - Câblée AUSSI dans `task lint:observability` (`measure_metric_coverage.py --producers`, étape 3 du
    plan d'action), 3 tests ajoutés, RED vus (mode absent, tâche non câblée) ; CI_CD.md et
    l'amendement ADR-178 le disent.
  - Tableau 26 : `product_outcome_cost_eur_mean{window}` et `product_outcome_latency_p50_seconds{window}`,
    calculées par le rollup horaire dans PostgreSQL sur l'ensemble utile de la North Star
    (`validated_outcome_value` : moyenne du coût, médiane de la latence ; 2 tests PostgreSQL réels
    verts). Histogramme d'observation écarté : un résultat rejeté après validation ne s'en décompte pas,
    E2 → E1 compterait deux fois, le coût n'est connu qu'au rattrapage.
  - Tableau 14 : les 2 panneaux `memory_hybrid_search_*` retirés (producteur disparu en v1.25.30,
    ADR-168) ; METRICS_REFERENCE.md ne catalogue plus ces 2 métriques (section « BM25 Index Cache » :
    les 3 vivantes, lues par le tableau 14) ; HYBRID_SEARCH.md et ARCHITECTURE.md se disaient déjà
    historiques.
  - `alerts-product.yml` : décision datée en tête — `ProductAggregatesStale` rejoint le cœur (warning,
    seuil `ALERT_CORE_PRODUCT_AGGREGATES_STALE_SECONDS` dans les 3 fichiers de seuils, fiche
    `ProductAggregatesStale.md` indexée, 3 cas promtool, recette de preuves) ; les 3 alertes de
    comportement restent non chargées, re-décidées au plus tard le 2026-12-15 sur une mesure en lecture
    seule de la production (amendement ADR-178, français, 3 points + index).
  - Garde de couverture : ne lit plus que les règles chargées (`coverage_rule_files()` = le
    `_live_rule_files()` du validateur) ; mesuré : aucune métrique câblée par une règle dormante seule
    (base 39 inchangée, 590/629 couvertes).
  - Décomptes : 629 métriques (HEAD 630 ; la vague en retire 6 en L4, en ajoute 3 en L4-L5 et 2 ici ;
    CLAUDE.md portait 627 depuis L5, les autres surfaces encore 630) réalignées par
    `bump_surfaces.py --counts-only` sur toutes les surfaces (guides HOW ×6, `translation.json` ×6 —
    seul le nombre change, vérifié paire de lignes par paire, zh compris —, GETTING_STARTED,
    GUIDE_OBSERVABILITY, README, CLAUDE.md) puis AGENTS.md régénéré. À refaire sur l'état fusionné (L11).
  - Preuves : producteur + couverture + validateur 31 passés ; `task lint:observability` vert (2
    commandes) ; `task test:alerts` SUCCESS (35 règles du cœur) ; `task test:alertmanager` 14/14 ;
    `task release:check` vert ; registre : 40 constats, 16 ouverts (4 P1), 10 remédiés ; doc_audit,
    doc_facts, doc_maps, doc_language en preview et agents_mirror verts.
- **2026-10-23** — L7, revue adversariale à froid (tous les fichiers du lot relus) : 6 trouvailles,
  corrigées en TDD.
  1. **Route finance morte** (étape 3 du plan A07 non faite : « retirée ou dotée d'un producteur,
     décision écrite ») : aucune alerte chargée NI dormante ne l'atteint (les alertes budget du
     catalogue dormant portent `component: cost`). RETIRÉE : route, récepteur, `email.budget.html`,
     `ALERTMANAGER_FINANCE_TEAM_EMAIL` (gabarit, entrypoint, compose prod, `.env.example`,
     `.env.prod.example`, `apps/api/.env.alerting.example` — commentaires d'équipe corrigés aussi),
     matrice, ALERTING.md, GUIDE_OBSERVABILITY.md, point 6 de l'amendement ADR-119 + index. Nouvelle
     garde `test_every_audience_route_is_reached_by_a_loaded_alert_or_declared_dormant` (RED vu sur
     `finance-team`) : une route de public qu'aucune alerte chargée n'atteint échoue, sauf déclarée
     dormante avec sa raison ; une déclarée qui devient atteinte doit sortir. **Route sécurité : même
     défaut** (aucune alerte chargée `component: oauth` ; les alertes OAuth dormantes portent
     `component: auth`) mais sécurité hors périmètre → laissée telle quelle, déclarée dormante,
     **à signaler au propriétaire**. Hors arbre : `.env` (dev) et `.env.prod` du propriétaire gardent
     une variable désormais inutilisée (prod : les 3 adresses d'équipe = celle du backend, aucune
     route d'équipe n'y était rendue) ; `scripts/mask_env_secrets.py` et `.sops.yaml` la citent
     encore (inoffensif, outillage de secrets non touché).
  2. **Garde inverse non câblée dans `task lint:observability`** (étape 3 du plan AC-006) → mode
     `--producers` + 2 commandes + 3 tests (RED vus).
  3. **Angle mort de la garde inverse** : une cible sans source de données (qui lit la source par
     défaut, Prometheus — `datasources.yml`, `isDefault`) ou nommée par son seul uid était ignorée →
     `_datasource_kind` (type, sinon uid, sinon défaut) ; RED vu sur 2 des 3 cas paramétrés (le 3e
     témoin). Aujourd'hui 0 cible concernée : 941 cibles PromQL + 121 expressions de règles lues.
  4. **Tableau 14** : la rangée « Hybrid Search » gardait un trou (x 0-11) et nommait une recherche
     disparue → « BM25 Index Cache (RAG Spaces) », 2 panneaux en pleine largeur.
  5. **METRICS_REFERENCE.md** cataloguait encore les 2 métriques `memory_hybrid_search_*` comme
     vivantes → section « BM25 Index Cache » (3 vivantes, tableau 14).
  6. **AC-037** : 14 modules de test de la vague ajoutés à `TYPED_TESTS` (38 au total, strict vert) ;
     2 ne passaient pas : `test_server_bounds.py` (doubles `SimpleNamespace`) réécrit sur un
     `ExceptionContext` sous-classé et une VRAIE connexion SQLite — son oracle reproduit désormais
     le vrai piège (`PendingRollbackError` à la lecture de `info` d'une connexion invalidée dans sa
     transaction ; 2/2 mutants tués) ; `test_hue_client_closed.py` → vrai `User` transitoire.
  - Black avait 4 fichiers à reformater (dont `test_export_disk_off_loop.py` de L6, retouché à froid
    sans repasser black) → reformatés ; `task lint:backend` vert (ruff, black, mypy `src` 3 627
    fichiers, strict `TYPED_TESTS` 38) ; `lint:ci-parity`, `lint:hygiene`, `lint:observability`,
    `test:alertmanager` 14/14 et instruments documentaires (preview) verts.
  - Suite rapide après la revue : 46 255 passés, 4 échecs = les 3 gardes documentaires en vue INDEX
    (attendu) + `test_redis_claim::…re_armed…` (fragile sous charge, vert 8/8 seul) → traité en L8.
- **2026-10-23** — L8 FAIT (AC-023, AC-034, AC-033 `remediated`).
  - **A16 / AC-023** : `restricted_sources` lève `RuleCompilationRefused` (sous-classe de `ValueError`) ;
    `RuleCache` gagne `refused`/`refusals` (défauts : un blob ancien se relit) et `stored()` (une compilation
    garde sa forme d'AVANT : les valeurs interdisent un champ inconnu, et un retour arrière aurait refusé le
    cache de TOUS les comptes — trouvé à froid, RED vu) ; `cache_compilation` décide ce que laisse une
    compilation fraîche, `refusal_wait` double l'attente (première = `DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS`
    intervalles, plafond `DISCUSSION_RULE_CACHE_HOURS`, aucun débordement à 10 000 refus) ; autres entrées ou
    dernière compilation réussie → repart de 1. Exécuteur : `apply_read_controls` rend un booléen, un refus
    s'abstient (aucune source), `build` rend `rules_refused` (issue de `NOTHING_INTERPRETED`, phrase en 6
    langues), le passage se règle `skipped` (avant : `failed` sans report → compilation payée à chaque tick).
    Runner 558 → 568 SLOC (la logique est dans `rule_controls.py`). 23 + 3 tests, RED vus ; intégration
    discussions 177 passés, unitaires discussions 534. ADR-359 amendement + index, PROACTIVE_DISCUSSIONS.md.
  - **AC-034a / AC-034** : le lecteur des registres devient `infrastructure/database/table_volume.py`
    (générique) ; `effects/volume.py` ne garde que sa déclaration ; `proactive_discussions/volume.py` déclare
    les 5 tables d'exécution (vérifiées contre les modèles déclarés) ; jauges
    `proactive_discussion_table_{rows,bytes}{table}` dans la boucle périodique (échec journalisé par son type,
    pas `str(exc)`) ; tableau 13 : rangée + 2 panneaux ; pas d'alerte de croissance (décision écrite :
    ADR-358 amendement + index ; `TransparencyRegisterGrowth` lit `lia_ledger_bytes`, que ces tables ne
    rejoignent pas). Décompte 629 → 631 réaligné (`bump_surfaces --counts-only`, locales : seul le nombre).
    GRAFANA_DASHBOARDS.md : 851 panneaux MESURÉS (l'en-tête disait 847, déjà faux à HEAD = 850), 13 = 41,
    14 = 24 (l'en-tête de section de 14 disait encore 26 après L7). METRICS_REFERENCE.md : famille ajoutée.
  - **A12 / AC-033** : 3 copies du même critère → `tests/support/cpu_growth.py` (horloge du thread précise
    au cycle, paires alternées, médiane, planchers ; lots pour les appels courts) lu par les aplatisseurs
    (comportement identique, lots de 16), le filtre de balises et le rognage d'URL de la compaction (qui
    mesurait UN appel par taille sur `time.thread_time` : pas de 15,6 ms sous Windows). 7 tests du module
    (horloge scriptée + contrôle quadratique réel). TROUVÉ en mesurant : sous le petit plancher, une
    fonction quadratique PASSE (1,5 ms → 26,5 ms lu ×5,3) — écrit dans l'aide, GUIDE_TESTING et ADR-326
    (amendement + index), contrôle dimensionné au-dessus. Durée série des gardes : 107 s (121 s avant).
  - **Test fragile** `test_redis_claim::…re_armed…` : attendait 5 périodes de `sleep` (pas de 15,6 ms) →
    attend le rafraîchisseur lui-même (borne 5 s) ; mutant « le rafraîchisseur ne rafraîchit jamais » tué.
  - AC-037 : +6 modules dans `TYPED_TESTS` (44, strict vert). Cliquet de complexité verrouillé 263 → 262
    (`measure_cc.py --update-ratchet`, fichier repassé en LF).
  - Preuves : `task lint:backend` vert (mypy `src` + strict 44) ; suite rapide 46 286 passés, 3 échecs = les
    3 gardes documentaires en vue INDEX (attendu ; preview vert) ; `lint:cycles` (22/22), `lint:cc`,
    `lint:mypy-debt`, `lint:hygiene`, `lint:i18n`, `lint:ci-parity`, `lint:observability` verts ;
    `release:check` vert ; registre : 13 ouverts (4 P1), 13 remédiés.
  - Message de lia-ae (fusion du retrait du mode privé SMS) consigné au §4 L11 ; re-simulation avec L8 :
    mêmes 3 conflits, `discussion_runner.py` fusionne proprement.
  - Frontend : `task lint:frontend` vert (eslint, ratchets, tsc) ; `task test:frontend` 1 123 fichiers,
    13 983 tests verts.
- **2026-10-23** — L9, AC-036 FAIT (`remediated`).
  - Garde `test_env_template_parity_guard.py` (10 tests, strict MyPy vert) : (1) une valeur ≠ défaut du
    code sans motif échoue (RED 62/61/7) ; (2) un « (default: X) » faux échoue (RED 29/29 une fois listes,
    formats et « 604800 = 7 days » lus correctement) ; (3) chaque gabarit, secrets remplis, passe les
    validateurs des réglages (RED vu : les variables de la session de test masquaient celles du gabarit —
    son `DEBUG=true` contre l'`ENVIRONMENT=production` du gabarit — elles sont retirées ; le refus du secret
    Telegram factice est voulu, un vrai secret le remplace).
  - Alignement sur `.env.prod` (décision du propriétaire) : 96 valeurs dans `.env.example`, 90 dans
    `.env.prod.example` ; valeurs sensibles jamais affichées ni copiées ; exclus : secrets, identifiants,
    adresses, hôtes, identité d'environnement (`NODE_ENV`, `LANGFUSE_DEBUG`, `DEBUG`…).
  - Gardés au défaut du code, motif « differs from production » : l'analytique (arbitrage du 23/10) et les
    opt-in écrits par le propriétaire dans `specs/2026-08-06-config-defaults-vs-production.md` — MFA, pairs
    ×2, téléphonie payante, garde-fou `PSYCHE_AD_RELAXATION` — **à signaler** (même principe que
    l'analytique, appliqué sans redemander).
  - À la main : `CURRENCY_API_URL` (les gabarits perdaient `/v1`, la prod tourne au défaut), `APP_VERSION`
    (3.3.0 périmé → défaut, injecté au build), `TELEPHONY_DEFAULT_COUNTRY_CODE` (vide gardé dans un gabarit
    public, motif sur la ligne au-dessus), min.prod : ligne `BACKGROUND_RUNS_ENABLED` retirée (la section dit
    comment revenir au chemin hérité), `RADIO_ENABLED=false` motivé (l'installeur demande).
  - 134 annotations (112 « proven in production », 8 identité d'environnement, 18 valeurs de déploiement) ;
    29 affirmations « (default: X) » fausses retirées par gabarit complet (les « hard limit » vrais gardés).
  - Docs : CLAUDE.md (1 paragraphe) + AGENTS.md ; GUIDE_CONFIG_ARCHITECTURE.md (section en ANGLAIS :
    `doc_language` a refusé la version française — le guide n'est pas dans la liste française figée) ;
    registre (40 constats, 12 ouverts, 14 remédiés).
  - Preuves : 171 tests qui lisent les gabarits verts, `lint:hygiene` vert, doc_audit/doc_facts/doc_maps/
    doc_language en preview et miroir verts.
- **2026-10-23** — L9, A14b FAIT (AC-012 : remédiation partielle inscrite, constat ouvert).
  - Caractérisation d'abord : `test_messages_with_tokens.py` (5 tests, verts sur l'ancien code) fige ce que
    reçoit l'historique — une bulle d'assistant sans texte visible tombe, les jetons d'une exécution restent
    sur sa réponse la plus récente seulement, le message de la personne garde ce que la jointure lui donne.
  - Des 10 diagnostics que masquait l'exemption, 4 étaient dans `get_messages_with_tokens` (v1), que plus rien
    n'appelait depuis le retrait de son drapeau (`_auto` lance toujours v2) : supprimé, avec sa classe de tests
    d'intégration ; le seul cas qu'elle avait en propre (un message sans exécution) passe sous v2. Les 6 autres :
    le post-traitement de v2 devient `message_tokens.shown_with_tokens_once` (typé), les entrées sont
    `dict[str, object]`, `COUNT(*)` se lit par `scalar_one()`.
  - Exemption retirée de `pyproject.toml` ; dette MyPy 81 → 76 paires (baseline abaissée) ; plafonds de taille
    abaissés (conversations 688, connectors 1362) ; complexité 262 → 260 fonctions à CC ≥ 15 (verrouillé).
  - Revue à froid : les docstrings de v2 et `_auto` décrivaient encore le drapeau retiré, une « batch query for
    logs » qu'aucun des deux chargeurs n'a jamais faite, un paramètre `Default: False` inexistant et des
    tableaux de bord qui liraient le libellé `version` (le seul panneau agrège `sum by (le)`) → réécrites sur
    ce que fait le code. Mutants : 5/5 tués sur `message_tokens.py`.
  - AC-037 : `test_discussion_read_controls.py` (L8, nouveau) n'était pas sous MyPy strict — 13 erreurs, des
    `SimpleNamespace` posés sur des attributs typés. Réécrit sur un vrai `DiscussionRunSetup`, un vrai
    `DiscussionAct` et des sous-classes typées de `NativeContextStore`, `DiscussionLLM` et
    `DiscussionAuthority` ; la forme stockée se lit sur un vrai `ContextStateRecord`. Mutants : 4/4 tués.
    `TYPED_TESTS` : 44 → 47 (plus aucun module de test nouveau de la vague hors de la liste).
  - Preuves : `task lint:backend` vert (ruff, black, mypy `src` 3 630 fichiers sans l'exemption,
    strict `TYPED_TESTS` 47) ; `lint:mypy-debt` (76), `lint:cc` (260, verrouillé), `lint:cycles` (22)
    verts ; suite rapide 46 304 passés, 17 ignorés, 3 échecs = les 3 gardes documentaires en vue INDEX
    (attendu ; preview vert) ; intégration conversations 37 passés (avant la réécriture des docstrings,
    qui ne change aucun comportement).
- **2026-10-23** — L10, AC-030b : le plancher porte sur les deux suites (AC-030 `remediated`).
  - Mesure avant tout (xdist, sous couverture) : unitaire seul **78,98 %** (il manque 2 202 lignes pour
    80 %) ; union avec les 460 tests d'intégration des 4 domaines visés **80,53 %** — sms 53,6 → 93,6 %,
    discussions 70,7 → 93,8 %, `infrastructure/proactive` 70,5 → 84,9 %, conversations 49,1 → 80,4 %. Le
    code de sms est de la sémantique PostgreSQL (tables de transit, MVCC, clôtures de propriétaire) : le
    monter au plancher en unitaire exigeait de simuler PostgreSQL, interdit. Le plan disait « si l'analyse
    infirme le constat, arrête-toi et rapporte » → question posée, réponse « Mesurer les deux » (§2).
  - Mise en œuvre (TDD, gardes rouges d'abord) : chaque suite mesure dans SON fichier (`.coverage-unit`,
    `.coverage-integration`, la collection F006 en `--cov-append`), sentinelle `--cov-fail-under=0` contre
    le plancher d'`addopts` ; `test:backend:coverage` combine STRICTEMENT (`--keep`, un fichier absent =
    erreur), écrit `coverage.xml`, puis tient le plancher par `coverage report --fail-under` (précision 0,
    la comparaison de pytest-cov). CI : job `test-backend-coverage` (`needs` les deux suites, artefacts
    `backend-coverage-unit/-integration`, `include-hidden-files`), porte du diff déplacée dedans ;
    `task ci` tient les deux portes après l'intégration, `task ci:fast` (sans services) aucune.
  - TROUVÉ en sondant coverage 7.16 avant d'écrire : (1) toute commande de rapport recombine d'elle-même
    les fichiers `<fichier>.*` voisins, en mode NON strict, puis les EFFACE — un fichier d'exécuteur xdist
    périmé serait compté, une suite absente passerait inaperçue → noms hors motif, garde ; (2) sans
    `[tool.coverage.run] source`, la CLI écrit des chemins absolus sous une racine vide, que la porte du
    diff refuse (« does not measure apps/api/src ») → `source = ["src"]`, garde. Limite ÉCRITE (ADR-113
    amendement, Taskfile, CI_CD, GUIDE_TESTING) : le rapport de l'union est daté de sa combinaison ; en local,
    relancer les deux suites après une modification (un contrôle par dates de fichiers casserait en CI, où
    les données sont des artefacts téléchargés).
  - Gardes : `test_coverage_union_guard.py` (13 tests ; 10 mutants de câblage tués), parité (sous-ensemble
    partiel jamais au plancher, plancher sous ses deux graphies), garde du diff (la porte suit la
    combinaison, `ci:fast` ne tient rien qu'il ne peut mesurer), `doc_facts` (lit `--fail-under`).
  - Tests là où aucune suite ne couvre (option choisie) : la route d'avis des conversations par HTTP sur
    PostgreSQL (`test_response_feedback_route.py` : 404 qui masque, seul le PREMIER verdict nourrit les
    journaux, seul un 👎 commenté devient une correction, le crochet d'efficacité dans un point de sauvegarde
    — un crochet en échec reprend ses écritures et le verdict reste) — le test du module recopiait la route à
    la main ; `reply_receipts.py` (ADR-359 : seul un stockage complet lève la restriction, un accusé en
    échec ne lève jamais). Évités : les fichiers que v3.5.1 modifie (conflits à l'intégration).
  - Docs : ADR-113 amendement + index, CI_CD (job Backend Coverage, schéma, « chaque job » au lieu d'un
    compte), GUIDE_TESTING (doctrine 3-5, CI, jobs, exécution locale), SCRIPTS, CLAUDE.md + AGENTS.md,
    README, GETTING_STARTED (« 60% floor » faux retiré), `pyproject.toml`, `.gitignore` (`.coverage-*`).
  - Preuves (commandes canoniques, état final) : `task test:backend:integration` complet sous
    couverture, 1 h 58 : 5 310 passés (7 désélectionnés) + collection F006 4 passés, 2 ignorés ; le test de
    la route, écrit après le départ de la passe, a ajouté sa couverture (`--cov-append`, 7 passés).
    `task test:backend:unit:coverage` séquentiel, 46 min 58 : 46 334 passés, 17 ignorés, 9 désélectionnés,
    3 échecs = les 3 gardes documentaires en vue INDEX (attendu) ; unitaire seul 78,97 %.
    `task test:backend:coverage` : **87,47 %** (code 0 ; marge 9,47 points) ; par domaine sms 93,6,
    discussions 94,2, `infrastructure/proactive` 84,7, conversations 82,4. `task test:backend:diff-coverage` :
    952 lignes modifiées couvertes sur 1 016 (93,70 %, code 0).
  - Mutants : câblage 10/10 tués (+ le test de racine vu rouge sans `source`) ; tests de trous 11/11 (route
    ×4, crochet ×2, accusés ×5).
  - À SIGNALER : (1) la CI n'est PAS « aussi longue » comme je l'avais dit dans la question : le job de
    combinaison s'ajoute après les deux suites, environ 3 à 4 minutes de plus sur le chemin critique ;
    (2) restent sous le plancher même en union, hors périmètre de L10 : `infrastructure/startup` 56,1 % et
    `domains/google_api` 60,1 % (domaines de 300 lignes et plus) ; (3) `parallel_executor` journalise
    `error_message=str(result)` au-dessus de DEBUG (vu en analysant ses trous ; règle ADR-317, non corrigé ici).
  - Registre : 40 constats, 11 ouverts (3 P1), 15 remédiés en attente de réaudit.
  - Revue à froid de L10 : 2 défauts trouvés et corrigés avant la preuve (racine du XML de la CLI ;
    péremption locale du rapport de l'union, écrite comme limite), commentaires CI nommant le job par son
    identifiant exact. Portes après la revue : `lint:backend` (ruff, black, mypy `src` 3 630 fichiers, strict
    `TYPED_TESTS` 50), `lint:ci-parity`, `lint:hygiene`, `test:markers` (52 823 tests, aucun dans zéro job)
    verts ; aperçu documentaire vert.
- **2026-10-23** — L11, qualification du worktree (l'intégration dans `D:\` est la décision du
  propriétaire).
  - `ci:fast` par composants, état final : `lint:frontend`, `lint:i18n`, `lint:mypy-debt`,
    `lint:observability`, `lint:cycles`, `lint:cc`, `lint:lockfiles`, `lint:wake`, `lint:deps` verts ;
    `lint:backend`, `lint:ci-parity`, `lint:hygiene`, `test:markers` verts (fin de L10) ; `lint:docs` strict
    lit l'index git, où les 71 fichiers neufs n'entrent qu'à l'indexation : son aperçu est vert ;
    `test:frontend:coverage` 1 123 fichiers, 13 983 tests verts ; `test:deploy` et `test:install:hermetic`
    verts ; typage de l'E2E sur l'hôte (612 fichiers) sans diagnostic ; `release:check` vert (surfaces
    alignées sur 3.5.0, registre strict). Couverture : voir L10 (union 87,47 %, diff 93,70 %).
  - Arbre : 221 fichiers modifiés, 7 supprimés, 71 neufs (code, tests, configuration, documentation ;
    aucun fichier parasite ; données de couverture ignorées).
  - Processus orphelins (PID 15320, 15888, 45460, 58392) : absents le 23/10 à ~19:55, plus rien à demander.
  - Message de lia-ae (main réel `4ef630984`) : re-simulation concordante, réponse envoyée (l'intégration
    attend le propriétaire) ; plan mis à jour au §4 L11.
  - Rejeu A10 (AC-021 reste `presumed_closed`) et preuves Docker L4/L5 : leurs procédures construisent et
    servent dans `lia-web-dev`, qui monte `D:\` ; ils qualifieront l'état fusionné.
- **2026-10-23** — Intégration dans `D:\` (décision du propriétaire, §2), sans commit.
  - Application (`scratchpad/l11/apply_to_d.py`) : instantané de l'arbre du worktree sur un index temporaire
    (commit pendant), `git merge-tree --write-tree` contre `4ef630984`, puis chaque chemin du résultat écrit dans
    l'arbre de travail de `D:\` comme une extraction l'écrirait (`git cat-file --filters`) : 292 fichiers écrits,
    7 supprimés, 7 en conflit ; le `git status` de `D:\` égale exactement la fusion (299 chemins). Aucun index,
    aucune référence, aucun commit touchés.
  - Conflits résolus selon le plan : `notification.py` (`require_durable` gardé ; `privacy` et sa ligne de
    docstring retirés), `test_sms_cross_surface_flow.py` (`durably_delivered`, « 10h30 » dans le push, canaux
    appelés une fois), statut d'ADR-358 (les deux amendements), README (287 versions, 631 métriques), les 3
    cartes reprises de main puis régénérées (`doc_maps.py --write --refresh-icons --include-unstaged` : la
    tâche `docs:maps` juge l'existence sur l'index, où `multipart_upload.py`, neuf, n'est pas encore).
  - Portes sur l'état fusionné : `release:check` vert (surfaces alignées sur 3.5.1, registre strict) ; tous les
    `lint:*` verts (backend : mypy `src` + strict 50 ; frontend ; i18n ; aperçu documentaire ; dette ; cycles ;
    complexité ; hygiène ; lockfiles ; parité CI ; wake ; deps), `test:markers` (52 816 tests), miroir
    `AGENTS.md` ; les 3 tests SMS d'intégration (5 passés).
  - TROUVÉ par la suite rapide (xdist) sur `D:\` : `test_reply_receipts.py` (neuf en L10) nommait un cas par un
    UUID tiré à l'import → chaque exécuteur collectait des noms différents et xdist refusait la collecte
    (la passe canonique séquentielle de L10 ne pouvait pas le voir) → identifiants stables, corrigé dans les
    deux arbres. Suite rapide ensuite : 46 329 passés, 17 ignorés, 2 échecs = les gardes de liens
    documentaires en vue INDEX (attendu).
  - `.env` : les 4 du démonstrateur (2 modèles suivis déjà dans la vague, 2 vivants : +2 clés AC-028) et, à la
    demande du propriétaire, son `.env` et son `.env.prod` (+3 clés : `DATABASE_LOCK_TIMEOUT_MS`,
    `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS`, `OAUTH_REFRESH_WRITE_LOCK_TIMEOUT_MS`, chacune à la place de son
    modèle) ; sauvegardes octet pour octet dans `C:\Users\jgouv\LIA-sauvegardes`, fins de ligne CRLF gardées,
    aucune valeur affichée. Restent dans les fichiers vivants, inutilisées : `ALERTMANAGER_FINANCE_TEAM_EMAIL`
    et `OAUTH_LOCK_TIMEOUT_SECONDS`. Les copies SOPS sont régénérées par `deploy-prod.ps1` à chaque déploiement.
  - Docker dev : `lia-api-dev` redémarré pour partir proprement de l'état fusionné → sain en ~2 min (corrigé :
    une première version disait que WatchFiles ne voit pas ces écritures ; démenti à 20:14 UTC, quand les
    modifications d'une autre session l'ont fait recharger). Preuve L5 : une connexion de l'application porte
    `lock_timeout = 30s`, `idle_in_transaction_session_timeout = 5min` (= réglages), `statement_timeout = 0`.
  - Rejeu E2E A10 (`apps/web/e2e/README.md`, preuve locale stable) : bundle de production de l'état fusionné
    construit dans `lia-web-dev` (`.next-e2e`), servi sur 3100 ; suite hermétique dans l'image Playwright
    officielle sous l'enveloppe des médias natifs (sortie audio virtuelle, STUN local), `--retries=0` :
    **690 passés, 1 ignoré par conception (test HMR du seul runtime de dev), 0 échec**, 34 min.
    AC-021 `presumed_closed` → `closed` (la confirmation que demandait la révision).
  - OAuth (L4) : aucun des 2 comptes de preuve de dev n'a de connecteur ; l'échange réel SUR UN COMPTE DE
    PREUVE exige qu'un humain y connecte un fournisseur (consentement dans un navigateur) → au propriétaire.
    Observé : l'ordonnanceur de rafraîchissement tourne sur la nouvelle porte (19:20 UTC, 7 connecteurs,
    aucun à l'échéance ; passage suivant à observer).
  - Une autre session (lia-fb) modifie `D:\` à la demande du propriétaire (discussions : panneau d'attente,
    cause d'un refus « ineligible », `DISCUSSION_OPENING_PENDING_HOURS` 24 → 1) sur ses propres chemins, sans
    indexer ; feu vert donné pour les `.env` et les `translation.json` ; les portes de couverture de l'état
    fusionné attendent sa fin, pour mesurer un état stable qui inclut son changement.
  - OAuth (L4), observé sur Docker dev après la recréation de la pile (20:02 UTC) : le rafraîchissement planifié
    de 20:30 UTC a échangé 2 jetons Microsoft échus par la porte unique (`oauth_refresh_concluded`,
    `outcome=refreshed` ; `oauth_refresh_flights_total{how="claimed"}` = 2 et
    `oauth_refresh_outcomes_total{outcome="refreshed"}` = 2 ; 0 erreur, 4 connecteurs encore valides).
    Comptes de dev ordinaires, pas un compte de preuve : la preuve sur compte de preuve reste au propriétaire.
  - OAuth (L4), test du propriétaire sur Docker dev (20:10-20:31 UTC), de sa main et sur son propre compte
    d'administration de dev (pas un compte de preuve : son choix). Relevé en lecture seule (journaux, état des
    lignes ; aucun jeton, aucune adresse affichés) :
    - connexion à l'application par Google, deux fois (20:10 et 20:15 : `/auth/google/login` → `/callback`,
      `oauth_user_login`) ;
    - déconnexion puis reconnexion du service Google Contacts : `DELETE /connectors/{id}` → 204 (20:30:28),
      puis autorisation, échange du code, connecteur neuf `ACTIVE` avec un jeton de rafraîchissement
      (20:30:38) ;
    - à l'ouverture du tableau de bord (`GET /briefing/cards`, 20:12:14), trois échanges réels de jetons Google
      par la porte unique, sur les deux sortes de détenteur : 1 `grant` (l'autorisation partagée que portent
      Gmail et Drive, vérifié en base : la même ligne `oauth_grants`, mise à jour à 20:12:13.996) et
      2 `connector` (Agenda, Tâches, sans autorisation partagée), tous `refreshed`, aucun autre résultat.
    Avec le passage planifié de 20:30 (Microsoft), la porte est prouvée sur de vrais fournisseurs des deux côtés :
    l'appelant (`fresh()`) et l'ordonnanceur. La course de deux travailleurs sur un même jeton et la
    revérification d'un `invalid_grant` restent prouvées sur PostgreSQL et Redis réels, fournisseur simulé
    (`test_oauth_refresh_pg.py`) ; en réel, la seconde exigerait de révoquer un jeton chez Google.
    Compteurs : `lia-api-dev` a été redémarré à 20:37 UTC par un autre acteur, ses compteurs en mémoire sont
    repartis de zéro ; les lignes `oauth_refresh_concluded`, écrites au point même où
    `oauth_refresh_outcomes_total` est incrémenté, font foi.
- **2026-10-24** — Revue adversariale à froid de toute la vague (demande du propriétaire), dans `D:\` :
  299 chemins, plus ce que la fusion et les deux autres sessions ont changé par-dessus (aucune interférence :
  leurs ajouts sont orthogonaux, mes parties du lot L8 intactes). Relus fichier par fichier : les 77 fichiers de
  production, la configuration des outils, le Taskfile, les 5 workflows, l'infrastructure d'observabilité, les
  gabarits `.env` (aucun secret, hôte ni adresse réel) et le refactoring d'`AssistantAvatar`. Tests,
  scripts et documents : par sondes ciblées (typage des fichiers neufs, remplaçants des tests supprimés,
  renvois périmés) et par les portes, sans relecture ligne à ligne dans cette passe.
  - Sept constats, corrigés en TDD dans `D:\` seulement (le worktree n'est plus le livrable) :
    - F1, le seul qui touche l'exécution, est une régression de latence dans un cas limite. Quand l'attempt
      d'un processus levait une exception inattendue (erreur de base, client changé, budget de lecture
      épuisé), aucun verdict n'était publié : l'attendant d'un autre processus attendait toute la
      réclamation, environ 41 s aux défauts, là où l'ancien verrou relâché le libérait aussitôt.
      L'enveloppe `_attempt` publie et compte désormais l'échec, puis relance l'exception.
      Test rouge (`TimeoutError` à la borne de 5 s), puis vert ; 60 tests de la porte verts.
    - F2 : docstring de `_refresh_access_token` inexacte.
    - F3 : bloc `if TYPE_CHECKING: pass` mort dans `token_refresh.py`.
    - F4 : l'amendement d'ADR-302 complété (échanges réels observés ; résidu d'un fournisseur à rotation
      stricte, qui ne concerne ni Google ni Microsoft).
    - F5 : commentaire du bandeau Alertmanager qui affirmait trop.
    - F6 : `DIAGNOSTICS_DOMAIN.md` citait le test de matrice supprimé ; sa matrice vit dans
      `routing_matrix.yml`, en CI par `task test:alertmanager` (couverture préservée).
    - F7 : deux constructeurs de test renvoyaient `Any` (`_session`, `_db`), typés précisément.
  - Contrôles : MyPy strict, Ruff, Black verts ; 70 tests de garde verts ; fins de ligne LF. Aucune borne
    serveur atteinte sur Docker dev en 6 h (`database_bound_reached` = 0).
  - Antérieurs à la vague, signalés puis corrigés à la demande du propriétaire (« fais ») :
    - la livraison entre pairs appelait le modèle dans une transaction de lecture ouverte sur la session du
      balayage : les lectures sont maintenant commitées avant la génération (ADR-304) ; test rouge
      (`['count', 'generate']`), puis vert ;
    - sept lignes au-dessus de DEBUG journalisaient le texte d'une exception (`error=str(exc)`) dans
      `lifetime_metrics.py` et `skills/executor.py` : remplacé par son type (ADR-317). Dans `executor.py`,
      fichier au plafond de 600 lignes logiques, la lecture d'un script illisible journalise `errno`, sur une
      seule ligne ; le plafond n'a pas été relevé ;
    - `scripts/optim/verify_flagged_functions_usage.py` : les deux entrées de l'`OAuthLock` supprimé, retirées ;
    - `ALERTMANAGER_FINANCE_TEAM_EMAIL` retirée des trois `.env.alerting.*` vivants (sauvegardes dans
      `C:\Users\jgouv\LIA-sauvegardes`, fins de ligne gardées, aucune valeur affichée ; `.env` et `.env.prod`
      n'en portaient déjà plus). Gardée volontairement dans `scripts/mask_env_secrets.py` et `.sops.yaml` : un
      vieux fichier qui la porterait encore doit rester masqué et chiffré.
    - Contrôles : Ruff, Black, MyPy (6 modules), plafond de taille, garde des journaux verts ; 851 + 635 tests
      unitaires verts sur les zones touchées.
  - Indexation : non faite. L'index de `D:\` porte 298 entrées indexées (la vague) ; mes corrections et les
    ajouts des autres sessions sont des modifications non indexées par-dessus. À indexer juste avant le commit,
    une fois les écritures finies et les portes passées (geste git réservé au propriétaire, CLAUDE.md).
- **2026-10-24** — Portes finales lancées à 00:47 UTC après la fin de lia-08, puis ARRÊTÉES à 01:00 à la demande
  du propriétaire (« je n'ai pas fini ») : seul `lint:backend` avait tourné (vert, 327 s). À relancer quand le
  propriétaire aura fini et que les deux passes pytest du worktree Codex `lia-world-prototype` seront terminées.
- **2026-10-24** — Report des worktrees dans `D:\` (demande du propriétaire), en lecture seule :
  - 3 worktrees : `D:\` (main), `audit-v14`, `lia-world-prototype` (branche `codex/…`, session Codex en cours :
    exclue, avec sa remise `stash@{0}`).
  - `audit-v14` : ses 299 chemins sont tous dans `D:\`. Chaque ligne ajoutée y est présente et chaque bloc retiré
    absent, sauf 39 chemins tous expliqués (compteurs remis à jour 631 → 634 et 286 → 287, corrections de la revue
    faites dans `D:\` seul, lignes que la fusion ou les autres sessions ont complétées, blocs déplacés) ; ses
    7 suppressions sont faites ; aucun fichier ne manque.
  - Sans worktree, 3 branches (15-16/10 : `wip/base-2026-10-15`, `feat/tool-data-channel`, `codex/ui-accueil`) et
    2 remises (20/10) : leur contenu est entré dans main (« land the work in progress up to 2026-10-16 », puis
    v3.1-v3.5) et a évolué depuis, vérifié par recherche dans l'histoire de main (`git log -S`). Le seul
    comportement jamais reporté tel quel, le rafraîchissement de l'état psychique après un changement de style
    (`refreshPsyche`, `codex/ui-accueil`, 16/10 00:39), existe dans `D:\` sous une autre forme depuis 13:38 le
    même jour : `usePsyche` relit l'état à chaque changement du style confirmé (`deps: [personalityKey]`).
    Rien n'est perdu ; leur suppression éventuelle est un geste git du propriétaire.
  - Supprimées à la demande expresse du propriétaire (`git branch -D`, branches locales seules, aucune copie
    distante, aucun worktree dessus) : `wip/base-2026-10-15` (`b5e27a64a61f2e470d18052eeb50c5083dc779bc`),
    `feat/tool-data-channel` (`53a9b765794cb8bd24d09bd2964763cf4c4cbc3b`), `codex/ui-accueil`
    (`9ea4605b465b4c364c036b8db00ceb05ba19ad8e`). Recréables par `git branch <nom> <sha>` tant que git n'a pas
    nettoyé ces commits devenus inaccessibles (au moins deux semaines).
  - Puis, à la demande du propriétaire (« ok ») :
    - les huit branches locales déjà contenues dans main sont supprimées par `git branch -d`, qui refuse une
      branche dont un commit manquerait à main : `codex/http-scan-protection` (4b8016fba),
      `codex/meetings-peer-qualification-position` (e68b43326), `codex/phone-ingestion-sms` et
      `codex/proactive-discussions` (89d10bc97), `codex/ui-interface-polish` (5dd83af4b),
      `codex/v2-secret-scan-fix` (354484ed8), `integrate/tool-data-channel` (04137b040) et
      `wip/land-2026-10-16` (2735e0022) ;
    - les deux remises identiques du 20/10 sont supprimées (`7b3694bbc9cfeddf4a283a5da0ab7bffaab11df7`,
      `c57be7dbda8198052dc5707e6ab8c9f76f68fc6f`, récupérables par `git stash store <sha>`), après vérification :
      leur dernière ligne non retrouvée, l'assertion e2e « renseignez votre domicile », est dans `D:\` au
      tutoiement de l'application ;
    - le dossier vide `C:\Users\jgouv\LIA-worktrees\tool-data-channel` est retiré.
    Gardés : `stash@{0}`, celle de la session Codex en cours, et les branches `main`, `audit/v14-wave` et
    `codex/lia-world-prototype`.
- **2026-10-24** — Déploiement de production lancé par le propriétaire depuis `D:\` (arbre non commité : 431 entrées,
  HEAD `4ef630984`) : un échec, son correctif, puis un succès.
  - 03:25 (heure de Paris) : échec à l'étape 5/7, construction de l'image web. `next build` arrête la vérification
    des types sur `TS2307 Cannot find module` pour `../../coverage-exclusions.mjs` et
    `../../scripts/decision-points.mjs` (importés par `src/__tests__/coverage-exclusions.guard.test.ts`) et
    `../../scripts/double-cast.mjs` (`src/__tests__/double-cast-ratchet.test.ts`), l'outillage A03/AC-037 de la
    vague. Verdict distant 1 ; rien n'a été remplacé (les 28 conteneurs de v3.5.1, sains).
  - Cause : `prepare-prod.ps1` copie `apps/web` depuis des listes tenues à la main, et `next build` vérifie les types
    de tout ce que `tsconfig.json` inclut, tests de `src/` compris. Le CI vérifie sur le dépôt entier : aucune porte
    ne voyait l'oubli. Le balayage des 2 645 fichiers TypeScript du paquet ne trouve que ces trois modules.
  - Correctif : la liste `$webImportedModules` de `prepare-prod.ps1` les copie et refuse net la préparation quand un
    module listé manque ; la garde unitaire `apps/api/tests/unit/test_prepare_prod_web_imports_guard.py` dérive
    l'exigence des imports relatifs (résolution des extensions comprise) et refuse aussi une entrée que plus rien
    n'importe — rouge sur les trois modules avant le correctif, vert après, les mutations « import oublié » et
    « entrée périmée » détectées ; côté Pester, l'arbre factice porte les trois modules et le paquet doit les
    contenir (28 verts ; sans eux, la préparation s'arrête sur « apps/web/coverage-exclusions.mjs introuvable »).
  - 03:46 : le propriétaire relance `task deploy:prod` depuis `D:\` (le paquet porte le correctif). Verdict distant 0
    à 04:06 (`deploy.20261024-035453-dkmn`). Vérifié en lecture seule sur l'hôte : 18 conteneurs de production
    redémarrés, aucun redémarrage en boucle, tous ceux qui ont un contrôle de santé `healthy`, aucun `unhealthy` dans
    le journal du déploiement ; accès sortant, `ip_forward` à 1, socket Docker joint depuis l'API ; base à la tête
    `213b9ac595c5` (transaction en lecture seule). Journal de l'API depuis le démarrage : 5 erreurs, toutes des 404
    côté client ; 5 `connector_api_error` (Gmail, 404 amont) et 14 `http_scan_check_failed` (`check:TimeoutError`,
    une rafale à la même seconde) — deux motifs présents chaque jour dans Loki depuis le 19-20/10, donc antérieurs.
    Non vérifié : le rendu d'une page publique dans un navigateur (aucun sondage des routes publiques depuis le
    poste : l'anti-scanner bannirait l'adresse de la maison).
  - **Provenance fausse** : l'API annonce `3.5.1 4ef630984` alors que le code servi est l'arbre non commité de `D:\`.
    À rétablir au prochain déploiement fait depuis le commit.
  - Le démonstrateur : `demo:prod:down` puis `demo:prod:up` lancés par le propriétaire après le déploiement, dans
    l'ordre de la procédure.
  - Portes finales arrêtées à 01:41 UTC, toutes vertes jusque-là (lint:backend, lint:frontend, i18n, docs:preview,
    mypy-debt, observability, cycles, cc, hygiene, lockfiles, ci-parity, wake, deps), puisque le correctif modifiait
    l'arbre ; relancées sur l'état corrigé avec `task test:deploy` en plus.
- **2026-10-24** — Portes finales relancées à 02:17 UTC sur l'état corrigé :
  - Vertes : les 16 portes statiques (lint:backend, lint:frontend, i18n, docs:preview, mypy-debt, observability,
    cycles, cc, hygiene, lockfiles, ci-parity, wake, deps, test:markers, miroir AGENTS, release:check) et
    `test:deploy` (Pester compris).
  - `test:backend:unit:fast` : 46 498 réussis, 2 échecs dus au seul index git — `test_doc_maps_guard` et
    `test_doc_audit_adr_link_guard` lisent l'existence des fichiers dans l'index, où ADR-363 et ADR-364 ne sont pas
    encore (la prévisualisation `lint:docs:preview`, qui les voit, est verte) ; ils passent une fois indexés.
  - `test:backend:unit:coverage` interrompu à 98 % à 02:59 UTC, sans un test rouge jusque-là, quand la session a
    été coupée (le processus tué, sa ligne de résultat jamais écrite) ; l'intégration, la couverture combinée et
    celle du diff n'ont pas tourné. Décision du propriétaire : l'état est accepté tel quel (« on va donc dire que
    tout est ok s'il n'y avait pas eu d'erreur ») ; la CI exécute ces suites sur le commit de release.
- **2026-10-24** — Consolidation du registre : AC-007, AC-008 et AC-027 (actions A05, A04 et A03 du lot L6)
  étaient faits mais n'avaient jamais été inscrits ; ils passent en `remediated` avec leurs preuves (jointure
  bornée des tâches annulées à l'arrêt ; fermeture des clients Hue de l'activation locale et du test de
  connexion ; `.dockerignore` sans les dists `.next-*`). Registre : 40 constats, 8 ouverts (2 P1, aucun échu),
  18 remédiés en attente du prochain audit ; `findings_register.py` vert, `--strict` compris. Puis release v3.6.0
  à la demande du propriétaire.
- **2026-10-24** — Release v3.6.0, couverture du code indexé par les surfaces (question du propriétaire :
  « changelog, readme et autres n'incluent pas ce qu'il y a dans le code staged ») : les 422 fichiers du delta et
  les 30 non suivis rapprochés de l'entrée du CHANGELOG un par un. Les fonctions visibles y étaient ; manquaient
  des changements d'exploitation, ajoutés : les gabarits `.env.example`/`.env.prod.example` alignés sur la
  production (24 interrupteurs à `true`, budgets de discussion 0,10 → 5,00 USD, radio 2 → 4 EUR, analytique à
  `false`) et le gabarit minimal de l'installateur qui ne coupe plus la génération détachée (ADR-117, défaut du
  code `True`) ; la route « finance », son récepteur, `email.budget.html` et `ALERTMANAGER_FINANCE_TEAM_EMAIL`
  retirés ; `ProductAggregatesStale` entré dans le cœur chargé ; les 4 seuils `ALERT_CORE_*` nouveaux ; les
  2 panneaux `memory_hybrid_search_*` du tableau 14 ; les séries `oauth_lock_*` et `connector_token_refresh_total`
  retirées, `oauth_refresh_flights_total` ajoutée ; la route sécurité déclarée dormante. Contradiction corrigée :
  GUIDE_SELF_HOSTING disait que l'installateur ne pose aucune question anti-robot (il en pose deux depuis
  `scripts/install/turnstile.py`) — ADR-364 le dit aussi désormais ; la FAQ « Que fait l'installateur guidé ? »
  (6 langues) et son miroir `docs/knowledge/29` citent les deux paires de clés facultatives (Maps, Turnstile),
  l'entrée « administrateurs » du FAQ changelog et le README le disent.
  - Dépendances : `zod` ^4.6.7 (GHSA-mrhx-c7xc-m3w5, corrigé en 4.6.6), `vitest` ^4.1.12 et `@vitest/coverage-v8`
    4.1.12 (GHSA-qxg6-89mg-rqv8, GHSA-xp26-3454-mjgp). `pnpm audit` : aucune vulnérabilité, tous niveaux.
  - Incident d'installation sur `D:\` : `pnpm add`/`install` figé après la résolution (code 124 sous `timeout`).
    Journal ndjson : `currentLockfileExists:false`, 298 suppressions planifiées, puis plus rien ; le processus à
    ~6 cœurs et ~700 000 opérations de métadonnées par seconde, aucune lecture ni écriture. Il avait vidé les
    fichiers des 297 orphelins puis tournait sur leurs 12 618 répertoires vides ; les liens directs d'`apps/web`
    (`vitest`, `zod`, `@vitest/coverage-v8`) pointaient vers des paquets vidés (MODULE_NOT_FOUND). Réparé :
    `pnpm install --lockfile-only` (3 s), squelettes vides retirés par un script qui ne suit aucun lien et refuse
    s'il trouve un fichier, puis une installation `--frozen-lockfile` ininterrompue (961 paquets importés, aucune
    suppression, `node_modules/.pnpm/lock.yaml` réécrit).
  - Commit `afb55d4f6` poussé (le hook avait refusé deux fois : la vérification de `.env.example` demandait
    `DIFF_COVERAGE_BASE` et `GITHUB_ACTIONS`, que lisent `scripts/audit/` — exclus par emplacement, comme
    `tests/` ; puis le motif des secrets prenait la constante de revendication `_RESET_CLAIM_PASSWORD = "pfp"`
    pour un mot de passe — renommée `_RESET_CLAIM_PASSWORD_FINGERPRINT`, ce qu'elle porte). GitHub annonçait au
    push 52 alertes Dependabot : 3 dans `pnpm-lock.yaml`, corrigées par ce commit ; 42 dans la boîte à outils GPU
    du mot d'éveil (Pillow, fsspec), acceptées dans la veille ; et deux angles morts qu'aucun audit de l'espace de
    travail ne lit — `tools/lia-motion` (zod forcé à 4.6.7 par `overrides` malgré l'épinglage 4.5.4 de Remotion,
    `fast-uri` ≥ 3.1.9, `npm audit` à 0 ; deux tests de couverture éditoriale du film rouges DEPUIS v3.4.0,
    `proactive_discussions` et `sms_archive` sans temps fort — décision éditoriale laissée au propriétaire) et
    `brotli` 1.2.0 de la boîte GPU (critique, plancher 1.2.1 dans `requirements-gpu.in`, seul paquet changé).
    `datasets` reste tenu sous 4 par VoxCPM (GHSA-379c-qx7v-6h59, invisible pour la veille).
