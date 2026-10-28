# Alertes GitHub : analyse de sécurité et plan de remédiation

> Exécution strictement inline, sans sous-agent, sans commit ni push. L’analyse initiale est conservée comme historique ; les classements et corrections ensuite autorisés sont consignés en section 0. Les changements locaux ne modifient pas les révisions des PR et ne relancent pas leur CI distante.

**Objectif :** qualifier les 43 alertes Dependabot et les 33 alertes CodeQL, définir les corrections nécessaires et leurs preuves de sortie, sans confondre correction, absence d'exposition observée et classement d'un signal légitime.

**Architecture :** préserver les domaines, contrats HTTP/WebSocket, registres, budgets et contrôles existants. Traiter séparément le graphe de dépendances du kit GPU, les limites de modélisation du scanner et le nettoyage de code effectivement justifié.

**Stack :** FastAPI/Python pour l'application, Next.js/TypeScript pour le navigateur, Python/CUDA dans une image distincte pour le kit vocal. Les versions et commandes normatives restent celles des manifests, Dockerfiles et de `Taskfile.yml`.

**Spécification :** ce document contient le cadrage, les deux inventaires exhaustifs, les décisions, les risques et le plan de tests. Il constitue la spécification du plan ci-dessous.

## 0. Décision de périmètre production et fermetures exécutées

Le 26 octobre 2026, après l'analyse initiale, le mainteneur a demandé d'écarter et de fermer avec commentaire tout ce qui concerne l'apprentissage du mot d'éveil ou uniquement le développement. Cette décision remplace les propositions de remédiation de ces éléments dans les sections historiques suivantes.

**45 alertes ont été fermées sur GitHub et leurs états et commentaires relus :**

- Les 43 alertes Dependabot du seul `scripts/wake-word/requirements-gpu.lock.txt`, avec motif `tolerable_risk` et commentaire précisant le périmètre apprentissage/développement, l'absence du graphe dans les images applicatives de production et les bundles d'auto-hébergement, et l'obligation de réexaminer avant tout usage en production. Les versions ne sont pas présentées comme corrigées.
- Les alertes CodeQL [#971](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/971) et [#972](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/972), avec motif `won't fix` et commentaire identifiant les benchmarks JEV exécutés manuellement en développement. Le commentaire précise que leur présence dans l'image API ne signifie pas qu'ils sont appelés par les flux de production.

À cette première étape, la relecture paginée trouvait **0 alerte Dependabot ouverte et 31 alertes CodeQL ouvertes**, exactement les identifiants initiaux moins #971/#972. L’exécution supplémentaire autorisée ci-dessous ramène CodeQL à une seule alerte ouverte. Le journal détaillé et les réponses de contrôle se trouvent dans `.tmp/security-analysis-20261026/development-dismissal-results.jsonl` et les fichiers `*-after-disposition*` / `*-dismissed-check.json`.

| Reste sur le code applicatif destiné à la production | Nombre | Traitement nécessaire |
|---|---|---|
| Faux positifs qualifiés | 28 | Classées `false positive`, individuellement, après contre-vérification de l’identité des sources et des règles |
| Usages intentionnels de `BaseException` (#983 et #960) | 2 | Classées `won't fix` avec justifications individuelles ; cleanup, annulation et règlement du coût conservés |
| Affectation redondante `budget_key` (#984) | 1 | Affectation morte supprimée localement ; fixture de minuit stabilisée ; 53 tests de diagnostic passent. Reste ouverte sur GitHub jusqu’à livraison et nouvelle analyse |

Le signal [#949](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/949) appartient à ce périmètre : son worker détecte le mot d'éveil dans le navigateur utilisateur en production ; il ne sert pas à l'apprendre. Son diagnostic de faux positif sur l'origine des messages reste celui de la section 5.

Les fonctionnalités produit optionnelles restent dans le périmètre production même si leur activation dépend d'un drapeau. Cette qualification porte sur le code applicatif destiné à être livré, pas sur une nouvelle inspection dynamique de l'instance actuellement déployée.

### PR ouvertes : périmètre vérifié après les classements

La lecture des sept PR ouvertes trouve uniquement des mises à jour Dependabot, distinctes des alertes CodeQL. La consigne d'exclusion a été appliquée à deux PR supplémentaires, fermées sans fusion et avec un commentaire ensuite relu :

- [PR #296](https://github.com/jgouviergmail/LIA-Assistant/pull/296) : seul le lock GPU d'apprentissage du mot d'éveil est modifié, pour datasets. Même exclusion que les 43 alertes correspondantes.
- [PR #295](https://github.com/jgouviergmail/LIA-Assistant/pull/295) : seule l'image `redis-base` de `infrastructure/docker/compose.services.yml` passe de Redis 7 à Redis 8. Le Compose de développement et un outil de preuve local lisent ce fichier ; production et démonstrateur déclarent leurs propres images, conservées à Redis 7. Cette PR ne constitue donc pas une migration de production coordonnée et changerait seulement l'environnement de développement.

La relecture de GitHub confirme **5 PR encore ouvertes**, aucune fusion effectuée. Leurs diffs ont été inspectés ; les échecs ci-dessous sont les contrôles observés, pas une attribution prouvée de leur cause aux mises à jour.

| PR | Périmètre réel | État à la première lecture, avant les corrections locales |
|---|---|---|
| [#306](https://github.com/jgouviergmail/LIA-Assistant/pull/306) | 33 mises à jour frontend/mobile et outillage, dont Next, React, Radix et client ElevenLabs | Pertinent pour le produit ; lint frontend, E2E, hygiène, build Docker et tests backend en échec à la lecture ; intégration backend encore en cours |
| [#305](https://github.com/jgouviergmail/LIA-Assistant/pull/305) | Outillage E2E et accessibilité exécuté en CI et pour les preuves locales | Pas une dépendance du runtime applicatif ; garde de qualification production à conserver. Le diff passe Playwright à 1.64, TypeScript à 7 et les types Node à 26, alors que les images E2E des workflows restent à Playwright 1.63 et le runner Node à 24. Ces contrats doivent être qualifiés et alignés ; E2E et tests backend actuellement en échec |
| [#302](https://github.com/jgouviergmail/LIA-Assistant/pull/302) | Actions GitHub de CI, sécurité, artefacts et promotion des releases | Chaîne de livraison production, pas uniquement environnement de développement ; Trivy et tests backend en échec |
| [#294](https://github.com/jgouviergmail/LIA-Assistant/pull/294) | Prometheus de production, développement et démonstrateur | Observabilité production ; hygiène et tests backend en échec ; vérifier la cohérence avec toutes les références de livraison |
| [#289](https://github.com/jgouviergmail/LIA-Assistant/pull/289) | Node 24 vers Node 26 dans le Dockerfile du sandbox | Runtime du sandbox de production ; changement majeur à qualifier, build Docker et tests backend en échec |

Ces cinq PR ne sont pas cinq vulnérabilités supplémentaires et aucune n'est entièrement validée par ses contrôles à cette lecture. Ne pas les fusionner pour réduire le compteur. Les travaux E2E et GitHub Actions sont conservés parce qu'ils sécurisent les livraisons et ne sont pas spécifiques au seul environnement de développement.

**Plan production : L1 est exécuté pour les 30 dispositions ; L2 est corrigé localement pour #984 ; les cinq diffs et leurs adaptations de CI sont préparés localement, avec les preuves de qualification ci-dessous. Les travaux GPU de L3/L4 et l'arbitrage d'une distribution dérivée sont retirés du programme de remédiation production.** Les scanners et leurs règles restent activés. Les exceptions existantes de la veille fournisseurs ne sont ni supprimées ni élargies par ces classements GitHub.

### Exécution des lots autorisés et qualification de la CI (27 octobre 2026)

Les **30 classements applicatifs** sont exécutés : 28 faux positifs et 2 constructions intentionnelles. Chaque écriture vérifie le chemin, la règle et le hash de source relu, puis contrôle le motif et le commentaire retournés. Journal : `.tmp/security-remediation-20261026/codeql-dispositions.jsonl`. Seule #984 reste ouverte ; sa correction est locale et n’est pas faussement classée comme un faux positif.

Les cinq diffs Dependabot ont été appliqués ensemble dans le checkout existant, sans changer de branche ou d’index. Les changements concurrents d’observabilité et `oauth_grant_runtime.py` sont préservés.

| PR | Cause prouvée dans les journaux de sa révision | Correction locale / qualification |
|---|---|---|
| #306 | 8 erreurs de hooks, fixtures ElevenLabs sans `event_id`, 20 faits documentaires périmés ; intégrations World sans `TEST_REDIS_URL` | Dépendances de callbacks complètes, valeurs scalaires d’identité, refs synchronisées après commit React ; événements typés ; faits régénérés ; Redis CI explicitement jetable en DB 15 et garde testée. Le ratchet révèle ensuite une migration distincte du linter, détaillée ci-dessous. |
| #305 | Postinstall axe attaché à 4.10.2, images Playwright désalignées ; TypeScript 7 supprime les API utilisées par les fixtures | Patch 4.13.0 revérifié sur le tarball officiel, hashes CJS/ESM exacts et refus conservés ; Playwright aligné ; types Node alignés au runner 24 ; TypeScript 6 conservant l’API ; contraste de quatre illustrations `/more` corrigé après le véritable scan navigateur. |
| #302 | Ancienne fixture de release incomplète ; cinq résultats Trivy sur `tools/lia-motion/package-lock.json` | La base actuelle corrige déjà la fixture ; fast-uri 3.1.9 et zod 4.6.7 dans le lock actuel remplacent les versions vulnérables de l’ancien SARIF. Scan Trivy 0.74.0 des métadonnées publiques, sans réseau : aucun HIGH/CRITICAL. Actions mises à jour comme dans le diff de PR. |
| #294 | promtool et catalogue d’auto-hébergement désalignés de Prometheus | Image, deux commandes Taskfile, provisionnement CI, catalogue et faits documentaires alignés ; règles et scénarios promtool passent sur 3.15.0. |
| #289 | Node du sandbox différent de l’API et de sa déclaration ; commandes node/npm/npx en erreur 127 | Node 26.10.0 et checksums officiels amd64/arm64 alignés dans API prod/dev et sandbox ; `libatomic1`, nouvellement requis et vérifié par `ldd`, ajouté. Véritable image sandbox : 25 bibliothèques, 18 commandes, 2 absences vérifiées. |

**Décision appliquée : migration du linter React.** Le graphe de #306 passe `eslint-plugin-react-hooks` de 7.0.1 à 7.1.1. Sur exactement les mêmes sources, l’ancien plugin relève 2 diagnostics dans les 36 fichiers examinés et le nouveau 43 : **41 nouveaux diagnostics**, tous `set-state-in-effect`. Le ratchet complet relève 67 occurrences sur 56 fichiers et refuse 36 fichiers ; ses seuils ne sont pas augmentés. Le maintien temporaire de 7.0.1 a été refusé par le contrôle automatique d’approbation, qui le considère comme un contournement de CI. L’override proposé n’a pas été appliqué. Le mainteneur a explicitement choisi la remédiation des 41 diagnostics ; le plugin 7.1.1 est conservé.

La remédiation est effectuée et vérifiée par lots, avant la qualification globale : (1) hydratation et état navigateur via les abonnements externes existants, sans mismatch SSR ni changement de focus ; (2) réinitialisations à la navigation et au changement de compte, sans réponse tardive réinjectée ; (3) chargements administrateur et préférences avec annulation, filtres, pagination et traitement d’erreur conservés ; (4) disponibilité API, SSE, FCM, géolocalisation, quotas, statistiques et workboard, avec leurs invariants de concurrence. Aucune règle n’est désactivée et aucune baseline n’est augmentée. Les copies de props sont remplacées par des états conditionnés à leur source ; les données navigateur utilisent le snapshot d’hydratation ou un abonnement externe ; les lectures reprennent le contrat existant de `useApiQuery` (annulation des IO non démarrées après setup/cleanup). La connexion SSE conserve son démarrage immédiat et expose son état via un store Zustand créé par instance du hook, sans persistance ni donnée d’un autre compte. Les callbacks de rafraîchissement publics gardent leur signature sans argument et démarrent immédiatement. L’inventaire ligne par ligne est `.tmp/security-remediation-20261026/hooks-migration-ledger.json`.

La qualification finale remplace les mesures intermédiaires par les preuves suivantes. Les ignorés ne sont pas présentés comme exécutés.

| Porte / contrat | Résultat local et preuve |
|---|---|
| Backend, installation, release et contrats de versions | **458 réussis, 6 ignorés** pour contraintes POSIX sur Windows ; les 53 tests de diagnostic y sont inclus. `backend-green.xml`, `diagnostics.xml`. |
| Intégration World SQL/Redis | **91 réussis**, sur services jetables dédiés, ensuite supprimés ; aucune réinitialisation de la base de développement. `world-integration.xml`. |
| Frontend complet avec couverture | **1 241 fichiers, 14 681 tests réussis, 4 ignorés**, code de sortie 0. Tous les seuils globaux et par périmètre sont satisfaits : statements 86,16 %, branches 80,88 %, fonctions 84,46 %, lignes 87,74 %. Même tâche et mêmes cas ; parallélisme borné à 4 workers, sans délai augmenté. `linux-coverage-complete.log`, `coverage-complete/coverage-final.json`. |
| Contrats d’hydratation et de concurrence | Nouveaux tests de SSR/hydratation, abonnement viewport, StrictMode, démontage immédiat et annulation d’une lecture remplacée ; 4 nouveaux cas de métadonnées de conversation prouvent le rejet des réponses et erreurs tardives de l’ancien compte, l’annulation du transport et l’absence d’appel hors session. Les 30 tests de conversation passent après une véritable reproduction rouge de la course. |
| E2E Chromium et axe | **768 scénarios distincts finalement réussis, 1 ignoré**, avec relectures ciblées explicites : la passe globale sans interface réseau produit 754 réussis et 14 échecs ; les 14 sont tous rejoués avec succès, sans changement de code ni d’assertion, parmi 13 + 8 parcours sur le build final et le réseau interne. Le wrapper média existant fournit STUN local et sink audio natif, sans fournisseur externe. Les identités `testId` des 14 cas sont rapprochées des rapports HTML pour exclure tout trou de couverture ou double compte. Ce résultat agrégé n’est pas présenté comme une seule commande E2E entièrement verte. `linux-e2e-verified.log`, `e2e-native-final.log`, `e2e-live-native-final.log`, `e2e-reconciled.json`. |
| Docker dev | **6 parcours réussis** en Next dev isolé : connexion, session révoquée, flux remplacé, `/more` animé et en pause en clair/sombre. Le garde E2E exige HTTP : une tentative directe contre le serveur partagé HTTPS est refusée par ce garde ; la preuve finale utilise donc son propre Next dev HTTP, sans modifier le garde ni redémarrer le service partagé. `docker-dev-http-browser.log`. |
| Statique frontend | `task lint:frontend` : ESLint, accessibilité, hooks, complexité, doubles assertions, catalogue World et TypeScript non incrémental passent. Les 41 nouveaux diagnostics sont corrigés ; il reste **26 occurrences héritées dans 22 fichiers**. La baseline React est resserrée par son générateur pour verrouiller les deux baisses mesurées ; aucun plafond n’augmente. Complexité : 37 fonctions au seuil, maximum 46, sous les caps existants. Contrôle TypeScript propre supplémentaire sur l’hôte réussi. |
| CI et hygiène | CI parity, lockfiles, hygiène, Ruff/Black ciblés et documentation en preview passent. La couverture des marqueurs collecte 53 668 tests backend, ne trouve aucun orphelin et conserve les exclusions déclarées. Aucun staging requis pour obtenir artificiellement un succès documentaire. |
| Images et outils | Builds de production API, web et sandbox réussis. Dans l’image API, commandes de version Node/npm/Claude réussies sans réseau. Le sandbox vérifie 25 bibliothèques, 18 commandes et 2 absences ; 3 sondes supplémentaires confirment le proxy HTTP, le CONNECT HTTPS refusé et l’absence de proxy sans activation, sur mock local. Aucun service applicatif n’est déployé. |
| Observabilité et dépendances | Règles et scénarios promtool réussis avec l’image alignée ; audit pnpm sans vulnérabilité selon la politique existante, exceptions inchangées ; Trivy sans HIGH/CRITICAL sur les manifests publics actuels. Les cinq anciennes occurrences du SARIF #302 sont reliées à leurs versions remplacées. |

L’échec World de restauration de focus découvert pendant la couverture vient du double de test : le hook appelle `requestAnimationFrame` global, le test espionnait celui de `window`. Le double vise désormais `globalThis`, sans modifier le hook ; les neuf cas passent sur Windows et Linux. Les autres ajustements de fixtures suivent l’IO annulable réellement utilisée, sans retirer d’assertion de confidentialité ou augmenter les délais.

**Intégrité de la preuve et de l’espace de travail :** `frontend-runtime-source-proof.json` compare les 43 fichiers de runtime modifiés avec les sources de la passe E2E, exactement identiques après normalisation LF. `preservation-final.json` vérifie HEAD inchangé, index vide, 14 modifications préexistantes préservées (seul le pin Prometheus est superposé dans deux Compose) et sources des 30 alertes classées inchangées. Seule la source de #984 diffère parmi les 23 fichiers qualifiés. Le fichier OAuth non suivi et la spécification World apparue concurremment sont laissés intacts. Les preuves brutes citées ci-dessus sont sous `.tmp/security-remediation-20261026/`, ignoré par Git.

**État GitHub relu après exécution :** 0 alerte Dependabot ouverte, 1 alerte CodeQL ouverte (#984), les cinq PR toujours ouvertes et leurs SHA de tête inchangés. Les 43 vulnérabilités du kit GPU sont classées par décision de périmètre, pas annoncées comme corrigées. #984 attend la livraison de sa correction et le nouveau scan. Les contrôles distants des PR restent ceux de leurs révisions existantes ; aucune relance distante ne peut qualifier ces modifications locales non publiées.

**Limites et suites de livraison :** aucune décision métier ne bloque la préparation locale. Une publication ultérieure devra intégrer le candidat consolidé sur des branches à jour, exécuter les contrôles GitHub sur ces nouvelles révisions et relire CodeQL. Il ne s’agit pas d’une nouvelle exécution de toute la CI backend ni de tous les workflows de sécurité, d’un build arm64, d’une inspection de production, d’une preuve sur téléphone physique ou d’un appel réel à un fournisseur payant. Aucun schéma de données, prompt, budget LLM, quota plateforme ou registre persistant n’est modifié ; les contrôles de minuit, d’annulation, d’attribution et d’isolation par compte restent couverts. L’analyse initiale ci-dessous conserve ses réserves historiques sur le kit GPU désormais exclu.

La première commande Trivy montant tout le code dans un conteneur connecté a été refusée par le contrôle d’approbation. Le scan effectivement exécuté ne monte que 17 manifests/lockfiles du dépôt dont la visibilité publique a été vérifiée ; il utilise une base préchargée, `--network none`, un système en lecture seule et aucun fichier d’environnement. Il vérifie les vulnérabilités de dépendances, pas tous les contrôles d’un futur job distant.

Les sections 1 à 9 ci-dessous conservent l'analyse initiale du snapshot et ses preuves ; leurs mentions d'alertes encore ouvertes ou d'actions GPU proposées décrivent l'état antérieur à cette décision.

## 1. Verdict et alignement

La demande vise à réduire le risque réel et à rendre chaque alerte explicable et traitable. Une baisse du compteur obtenue en excluant des règles ou en cachant un lockfile n'atteindrait pas cet objectif.

| Ensemble vérifié | Qualification | Traitement nécessaire |
|---|---|---|
| 43 alertes Dependabot | Vulnérabilités réelles de versions installées dans le kit GPU : Pillow 41, fsspec 1, datasets 1 | Résoudre le graphe amont ou qualifier une distribution d'inférence réduite ; conserver une acceptation temporaire explicite en attendant, sans présenter les alertes comme corrigées |
| 28 alertes CodeQL | Faux positifs au regard de l'usage et des contrôles effectivement présents | Conserver les contrats, attacher les preuves à chaque alerte puis proposer un classement individuel |
| 4 alertes CodeQL | Constructions réellement présentes mais intentionnelles : deux interceptions de `BaseException`, deux concaténations de chaînes | Documenter l'intention et ses tests ; classement individuel, sans désactiver les règles |
| 1 alerte CodeQL, #984 | Affectation initiale de `budget_key` écrasée avant lecture | Nettoyage mineur de `diagnose_incidents`, après stabilisation du test de changement de jour |

Les 43 alertes ne constituent donc pas 43 défauts indépendants de l'assistant. Elles partagent trois paquets dans un même graphe. Inversement, leur localisation dans un outil de développement ne les transforme pas en faux positifs.

Aucun contournement de HITL, aucune exploitation distante de l'application, aucun stockage de mot de passe en SHA-256 et aucun SSRF exploitable ne sont établis par ces 33 alertes après inspection. Cette conclusion porte sur ces sites et ce snapshot ; elle ne certifie pas toute l'application ou l'environnement de production.

## 2. Périmètre, traçabilité et limites

- Dépôt : `jgouviergmail/LIA-Assistant` ; inventaires REST paginés avec `state=open`, sans filtre de gravité.
- Snapshot analysé par GitHub et initialement identique au checkout : `78905c86ecabf31c3168eec24f200920fc2c2368`.
- Les 33 instances les plus récentes portent toutes ce SHA et `refs/heads/main`.
- Analyses SARIF relues : Python `2031593401`, JavaScript `2031568624` ; driver CodeQL `2.27.3`. Le nombre total de résultats SARIF inclut des résultats déjà classés et ne remplace pas le décompte des alertes ouvertes.
- Workflow Security correspondant : `40404571537`, terminé avec succès. Son succès atteste l'exécution des scanners, pas l'absence de vulnérabilités ou de dette CodeQL.
- Le ruleset applicable à `main` exige les contrôles de CI et de sécurité, y compris les trois analyses CodeQL, avec actualisation stricte de la branche. L'endpoint historique de protection répond 404, mais cela ne signifie pas que `main` est dépourvu de protection : le ruleset a été lu séparément.
- Un acteur concurrent a livré pendant l'analyse le commit documentaire `3be6294f1c9f4f59083cd35b11b4b58dba964cdb`. Une comparaison des **23 fichiers sources** concernés par les alertes avec le SHA analysé ne trouve aucune différence, fins de ligne normalisées. Ses changements ne sont pas attribués à cette analyse.
- La relecture de fin d'analyse confirme exactement les mêmes 43 et 33 identifiants ; `main` distant désigne encore le snapshot analysé. Le commit documentaire concurrent est présent localement, sans être présumé livré sur le distant.
- Le fichier non suivi `apps/api/src/domains/connectors/oauth_grant_runtime.py` était déjà présent et a été laissé intact.
- Instructions consultées : `CLAUDE.md`, `apps/web/CLAUDE.md`, index mémoire Codex et index mémoire Claude. La mémoire a servi d'orientation ; les conclusions techniques sont fondées sur les sources et lectures de cette session.
- Preuves locales brutes : `.tmp/security-analysis-20261026/` contient les inventaires JSON, les deux SARIF, les métadonnées PyPI, les sources du wheel contrôlé, les sondes et les journaux de tests. Ce répertoire de travail est ignoré par Git ; les conclusions nécessaires sont consignées dans ce document.

Ne sont pas revendiqués : inspection des conteneurs de production, exploitation des CVE, nouvelle synthèse GPU, reconstruction propre du kit GPU, nouveau déploiement, validation sur téléphone physique, suite CI complète ou nouvelle exécution de CodeQL après correction. L'analyse n'a appelé aucun modèle payant ni fournisseur métier.

## 3. Contraintes globales et arbitrages

1. Garder les manifests comme source des exigences et recompiler les locks avec les tâches existantes, hashes inclus. Ne jamais forcer un conflit de contraintes, installer avec `--no-deps` ou retoucher les métadonnées d'un paquet installé pour rendre un environnement artificiellement cohérent.
2. Conserver les suites et le périmètre CodeQL. Aucun nouvel `query-filters.exclude` global, retrait de chemin, `continue-on-error` ou assouplissement de niveau d'audit.
3. Ne pas remplacer les empreintes SHA-256 par bcrypt/Argon2 : ces sites ne vérifient pas des mots de passe. Un changement de format de clé de quota doit traiter le déploiement avec plusieurs générations de workers.
4. Garder les modèles, prompts, plafonds de tokens, tarification, quotas, registres d'effets et consultations inchangés. L'analyse n'identifie aucun besoin d'ajouter un appel LLM.
5. Conserver les modes Pipeline/ReAct, la mémoire, les checkpoints, les scopes d'autorité, les annulations et les interfaces frontend existantes.
6. Les seuils, baselines et ratchets restent ceux du dépôt et ne peuvent qu'être améliorés. Les tests caractérisent un comportement ; ils ne servent pas à faire disparaître une alerte par construction.
7. Les classements GitHub décrits sont **proposés**, pas exécutés. Une acceptation de risque d'une dépendance vulnérable ne sera pas qualifiée de faux positif.

### Cinq points de revue particulièrement sensibles

| Condition | Comportement à préserver | Lot responsable |
|---|---|---|
| Annulation pendant une dépense ou un nettoyage | Propagation de l'annulation, règlement unique du coût déjà engagé, libération bornée | L1 |
| Ancien et nouveau worker pendant un déploiement | Un seul plafond de concurrence par compte, aucune deuxième famille de quota | L1 ; contrainte de non-changement |
| Identifiant vocal contenant une URL ou des séparateurs | Refus avant fournisseur à l'entrée HTTP ; hôte fournisseur conservé dans le client | L1 |
| Changement de compte et réponse frontend tardive | Aucun résultat publié au nouveau compte ; promesse et statut conservés | L1 |
| Dépendance absente dans une distribution GPU réduite | Échec explicite au build/qualification ; aucune installation opportuniste ou import de secours | L4 |

## 4. Analyse des 43 vulnérabilités

### 4.1 Preuve de présence et séparation des environnements

Les 43 alertes désignent exclusivement `scripts/wake-word/requirements-gpu.lock.txt` : `pillow==12.3.0`, `fsspec==2025.3.0`, `datasets==3.6.0`. Le graphe est introduit par `voxcpm==2.0.3` dans `requirements-gpu.in` et comprend `gradio==6.29.0`.

Le `Dockerfile.gpu` installe ce lock avec `--require-hashes` dans une image Python distincte. Les Dockerfiles applicatifs et les allowlists de `build_self_host_bundle.py` / `build_self_host_source_context.py` ne livrent pas ce kit. Les trois locks Python de l'application contiennent déjà Pillow 13.0.0 ; le lock CPU du kit contient fsspec 2026.9.0. Ces constatations portent sur les entrées de build, pas sur une preuve des images actuellement déployées.

Le parcours `wakeword/clone.py::_model` télécharge une révision de modèle épinglée et appelle `VoxCPM.from_pretrained(path, load_denoiser=False)`. `_generate` fournit du texte et éventuellement un WAV local ; il n'appelle pas de décodeur d'image, de constructeur de dataset de dossiers ou de `ReferenceFileSystem`.

Le wheel officiel VoxCPM 2.0.3 a été téléchargé sans installation ni exécution et son SHA-256 vérifié : `24da58a30d094a9e9a7ead450ae9cffda0d31eaeba620b61ad99179dd87e486b`. `voxcpm/__init__.py` ouvre `core`, le débruiteur est importé seulement dans sa branche activée, et les API datasets sont dans les modules de training. Les imports directs du code d'inférence inspecté ne comprennent pas Gradio, datasets ou PIL. **Cela ne prouve pas que tous les imports transitifs les évitent à l'exécution.** C'est précisément une porte de qualification de L4.

### 4.2 Preuve du conflit de résolution

Métadonnées officielles PyPI relues le 26 octobre 2026 :

| Correction requise | Contrainte incompatible constatée | Conclusion |
|---|---|---|
| Pillow >=13.0.0 pour les 41 avis | VoxCPM 2.0.3 exige Gradio >=6,<7 ; les 37 versions stables non retirées de Gradio 6 imposent Pillow <12 ou <13 | Intersection vide avec la génération corrigée |
| fsspec >=2026.6.0 | VoxCPM exige datasets >=3,<4 ; les 13 versions stables non retirées de datasets 3 plafonnent fsspec au plus à 2025.3.0 | Intersection vide avec le correctif |
| datasets >=5.0.1 | L'exigence VoxCPM >=3,<4 exclut cette version | Intersection vide |

Les dernières versions lues sont VoxCPM 2.0.3, Gradio 6.30.0, datasets 5.1.0, Pillow 13.0.0 et fsspec 2026.9.0. Passer Gradio de 6.29 à 6.30 ne lève pas le blocage. Ces observations sont datées et doivent être rafraîchies au démarrage de L4 ; elles ne sont pas des exigences permanentes de version.

Sources : [VoxCPM 2.0.3](https://pypi.org/pypi/voxcpm/2.0.3/json), [Gradio](https://pypi.org/pypi/gradio/json), [datasets](https://pypi.org/pypi/datasets/json), [Pillow 13](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html), [avis fsspec](https://github.com/advisories/GHSA-27vj-qcqg-25rc), [avis datasets](https://github.com/advisories/GHSA-379c-qx7v-6h59).

### 4.3 Qualification du risque et correction cible

Pillow peut exposer exécution native, corruption mémoire, divulgation et déni de service si les formats ou opérations concernés deviennent accessibles. fsspec expose l'interprétation de modèles dans `ReferenceFileSystem` ; datasets expose la traversée de chemins dans ses constructeurs fondés sur des dossiers et métadonnées non fiables. Les paquets vulnérables restent installés même si ces API ne sont pas appelées par le parcours inspecté.

L'exposition applicative est réduite par la séparation du kit et le parcours audio borné. Le risque résiduel concerne l'opérateur, le montage de données, une évolution du code, des entrées externes ou un appel transitif non observé. La mémoire d'une ancienne mesure GPU n'est pas une preuve de non-exploitabilité actuelle.

La cible de remédiation est un **graphe réellement installable et scanné**, qui conserve clone vocal et entraînement du détecteur sans les versions vulnérables. Deux voies techniques sont recevables :

- version officielle de VoxCPM compatible avec les correctifs ; c'est la voie préférée dès qu'elle existe ;
- distribution reproductible et explicitement maintenue de son inférence, séparant les extras UI, entraînement VoxCPM et débruitage inutilisés par LIA. Cette voie est plausible au vu des imports directs, **pas encore qualifiée**. Il faut contrôler toute la fermeture transitive, les licences, les imports réels et la synthèse CUDA avant de la retenir.

Une simple suppression de Gradio/datasets à l'installation ou une relaxation arbitraire de leurs bornes n'est pas une troisième voie. Une suspension du clone GPU ferait perdre une capacité du kit ; elle ne doit pas être décidée implicitement sous couvert de nettoyage.

Les mesures transitoires doivent nommer chaque GHSA, propriétaire, périmètre, raison, échéance et condition de retrait. Elles ne ferment pas les alertes. Les 22 références Pillow et la référence fsspec présentes dans le registre automatisé ont une date de revue au 31 décembre 2026 ; les 19 autres références Pillow et datasets sont documentées séparément dans `CI_CD.md`, avec revue au 31 octobre 2026. Ne pas confondre ces dates.

`dependency_watch.py` lit les avis publiés par les dépôts fournisseurs, pas l'intégralité du catalogue global Dependabot. `judge()` rejette aussi une acceptation qui ne correspond à aucun constat de ses sources. Ajouter les 20 avis globaux manquants à ce registre sans changer son contrat rendrait donc la veille incohérente. Utiliser son mécanisme actuel et une section explicite pour les avis globaux, ou étendre la veille dans un lot dédié ; ne pas introduire un deuxième registre de risque anonyme.

### 4.4 Inventaire individuel des 43 alertes

Gravités GitHub constatées : 5 critiques, 24 élevées, 14 modérées. Chaque ligne requiert L3/L4 ; le classement « faux positif » n'est proposé pour aucune de ces vulnérabilités.

| Alerte | Paquet | Gravité | Avis / condition | Première version corrigée |
|---|---|---|---|---|
| [#326](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/326) | pillow | critical | [GHSA-5x8w-8jj5-q52h](https://github.com/advisories/GHSA-5x8w-8jj5-q52h) — Pillow: Heap buffer overflow in FlashPix (FPX) JPEG decoding leads to code execution | 13.0.0 |
| [#325](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/325) | Pillow | medium | [GHSA-654x-cwwv-5j9c](https://github.com/advisories/GHSA-654x-cwwv-5j9c) — Pillow: Arrow export leaks stale heap memory when PILLOW_ALIGNMENT > 1 | 13.0.0 |
| [#322](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/322) | pillow | high | [GHSA-78g4-xqwv-q3g8](https://github.com/advisories/GHSA-78g4-xqwv-q3g8) — Pillow: Bundled libopenjp2 2.5.4 in all wheels since 11.1.0 carries OSV-2025-219 heap-buffer-overflow write reachable from Image.open().load() | 13.0.0 |
| [#321](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/321) | Pillow | high | [GHSA-g7cr-3p24-7wf7](https://github.com/advisories/GHSA-g7cr-3p24-7wf7) — Pillow: Heap buffer overflow writing JPEG comment after ICC profile fills buffer | 13.0.0 |
| [#320](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/320) | Pillow | high | [GHSA-9v9v-9qvf-h2hj](https://github.com/advisories/GHSA-9v9v-9qvf-h2hj) — Pillow: Heap over-read in WMF/EMF rendering via 16-bit dimension truncation (Windows builds) | 13.0.0 |
| [#319](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/319) | Pillow | high | [GHSA-g4qv-2jxx-769h](https://github.com/advisories/GHSA-g4qv-2jxx-769h) — Pillow: PNG eXIf chunk makes EXIF parsing run in quadratic time | 13.0.0 |
| [#318](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/318) | Pillow | high | [GHSA-3j72-p6qg-6xp7](https://github.com/advisories/GHSA-3j72-p6qg-6xp7) — Pillow: TarIO negative size field causes infinite CPU-spin loop | 13.0.0 |
| [#317](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/317) | pillow | medium | [GHSA-4rm8-3hmm-39fg](https://github.com/advisories/GHSA-4rm8-3hmm-39fg) — Pillow: Reachable undefined behavior in native integer operations, potentially leading to denial of service or logic integrity compromise | 13.0.0 |
| [#316](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/316) | Pillow | high | [GHSA-mrfp-p49p-3hf2](https://github.com/advisories/GHSA-mrfp-p49p-3hf2) — Pillow PDF append accepts malformed shared page-tree DAG causing resource exhaustion | 13.0.0 |
| [#315](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/315) | Pillow | critical | [GHSA-v9pv-5gc8-w2m6](https://github.com/advisories/GHSA-v9pv-5gc8-w2m6) — Pillow multi-frame loaders can reuse stale native image storage after mode transitions | 13.0.0 |
| [#314](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/314) | pillow | medium | [GHSA-24rc-8hj2-v98c](https://github.com/advisories/GHSA-24rc-8hj2-v98c) — Pillow: BMP RLE decoder memory-amplification DoS via unbounded delta escape / absolute mode | 13.0.0 |
| [#313](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/313) | pillow | high | [GHSA-g842-9rc4-69pw](https://github.com/advisories/GHSA-g842-9rc4-69pw) — Pillow: Decompression bomb check bypass in SpiderImagePlugin.seek() leads to unbounded allocation DoS | 13.0.0 |
| [#312](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/312) | Pillow | medium | [GHSA-p8hx-v2p6-rp84](https://github.com/advisories/GHSA-p8hx-v2p6-rp84) — Pillow: Decompression-bomb protection bypass via multi-frame seek() in MPO and DCX (MpoImageFile.seek / DcxImageFile.seek) | 13.0.0 |
| [#311](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/311) | Pillow | high | [GHSA-xvh5-g6gv-559v](https://github.com/advisories/GHSA-xvh5-g6gv-559v) — Pillow: Memory disclosure and segfault in libtiff encoder via crafted TIFF tags | 13.0.0 |
| [#310](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/310) | Pillow | critical | [GHSA-332p-7hrc-92wf](https://github.com/advisories/GHSA-332p-7hrc-92wf) — Pillow: Heap buffer overflow in _tiffWriteProc when saving TIFF to BytesIO | 13.0.0 |
| [#309](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/309) | pillow | medium | [GHSA-4rr5-89j8-mwwm](https://github.com/advisories/GHSA-4rr5-89j8-mwwm) — Pillow: Heap use-after-free when encoding TIFF to an in-memory buffer | 13.0.0 |
| [#308](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/308) | Pillow | high | [GHSA-f2g6-542v-9j58](https://github.com/advisories/GHSA-f2g6-542v-9j58) — Pillow: Infinite loop in PdfParser.rewrite_pages on page tree Parent cycle | 13.0.0 |
| [#307](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/307) | Pillow | high | [GHSA-5xm2-6676-qcp9](https://github.com/advisories/GHSA-5xm2-6676-qcp9) — Pillow: APNG background disposal allocates full canvas before decompression bomb check | 13.0.0 |
| [#306](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/306) | pillow | high | [GHSA-gg2r-wvfm-q9rx](https://github.com/advisories/GHSA-gg2r-wvfm-q9rx) — Pillow: MSP RLE decoder expands a tiny file into unbounded memory | 13.0.0 |
| [#305](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/305) | Pillow | high | [GHSA-jg86-v3jv-hrpm](https://github.com/advisories/GHSA-jg86-v3jv-hrpm) — Pillow: Quadratic-time DoS in PDF save_all (PdfParser.next_object_id) | 13.0.0 |
| [#304](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/304) | Pillow | medium | [GHSA-254f-3936-288h](https://github.com/advisories/GHSA-254f-3936-288h) — Pillow: PdfParser can recurse without limit in get_value() and linearize_page_tree() | 13.0.0 |
| [#303](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/303) | Pillow | medium | [GHSA-xgh8-jp6q-p5x8](https://github.com/advisories/GHSA-xgh8-jp6q-p5x8) — Pillow: ReDoS in XbmImagePlugin: 512-byte file stalls Image.open() for minutes | 13.0.0 |
| [#302](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/302) | Pillow | medium | [GHSA-rfgq-q3w2-pmv2](https://github.com/advisories/GHSA-rfgq-q3w2-pmv2) — Pillow: Image.quantize() with empty palette leaks uninitialized stack memory | 13.0.0 |
| [#301](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/301) | Pillow | medium | [GHSA-74r2-7ff9-mjj2](https://github.com/advisories/GHSA-74r2-7ff9-mjj2) — Pillow: Quadratic GIF comment concatenation allows DoS in Image.open() | 13.0.0 |
| [#300](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/300) | Pillow | high | [GHSA-22hg-r758-rrw9](https://github.com/advisories/GHSA-22hg-r758-rrw9) — Pillow: Infinite loop in MIC n_frames when the embedded TIFF | 13.0.0 |
| [#299](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/299) | pillow | medium | [GHSA-fc9g-5qg7-mf45](https://github.com/advisories/GHSA-fc9g-5qg7-mf45) — Pillow: Quadratic GIF comment copying during save | 13.0.0 |
| [#298](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/298) | Pillow | high | [GHSA-27h8-gf7j-v5hc](https://github.com/advisories/GHSA-27h8-gf7j-v5hc) — Pillow: NULL dereference in ImagingExpand via rank filters on zero-size images | 13.0.0 |
| [#297](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/297) | pillow | high | [GHSA-cp9v-662q-vvx9](https://github.com/advisories/GHSA-cp9v-662q-vvx9) — Pillow: NULL pointer dereference in Image.merge via an unvalidated band 0 | 13.0.0 |
| [#296](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/296) | pillow | high | [GHSA-j4m9-6w36-pw47](https://github.com/advisories/GHSA-j4m9-6w36-pw47) — Pillow: Invalid free in FreeType glyph rendering when a stroker is active | 13.0.0 |
| [#295](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/295) | Pillow | high | [GHSA-7mwm-ghpf-9vrm](https://github.com/advisories/GHSA-7mwm-ghpf-9vrm) — Pillow: Double free in ImagingScaleAffine on calloc failure via Image.transform | 13.0.0 |
| [#294](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/294) | Pillow | medium | [GHSA-4558-3h8r-v8xp](https://github.com/advisories/GHSA-4558-3h8r-v8xp) — Pillow: P;2L and P;4L decoders may read 1 to 3 bytes past the passed buffer size | 13.0.0 |
| [#293](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/293) | Pillow | critical | [GHSA-w889-685w-c8fh](https://github.com/advisories/GHSA-w889-685w-c8fh) — Pillow: Argument Injection in Ghostscript call, potentially leading into RCE | 13.0.0 |
| [#292](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/292) | Pillow | high | [GHSA-58r4-6rv3-gfh8](https://github.com/advisories/GHSA-58r4-6rv3-gfh8) — Pillow: Out-of-bounds access in _imagingmorph on a zero-width image | 13.0.0 |
| [#291](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/291) | Pillow | high | [GHSA-65qm-jvmh-6pqg](https://github.com/advisories/GHSA-65qm-jvmh-6pqg) — Pillow: GIF seek keeps rejected size after DecompressionBombError, allowing DoS | 13.0.0 |
| [#290](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/290) | Pillow | medium | [GHSA-vx6w-vv9f-6gvg](https://github.com/advisories/GHSA-vx6w-vv9f-6gvg) — Pillow: EPS load(scale) lets Ghostscript render past the decompression bomb limit | 13.0.0 |
| [#289](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/289) | Pillow | high | [GHSA-q45j-58j2-45rg](https://github.com/advisories/GHSA-q45j-58j2-45rg) — Pillow: TiffDecode returns uninitialized memory as pixels for short JPEG strips | 13.0.0 |
| [#288](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/288) | Pillow | high | [GHSA-pchr-8j38-3x4p](https://github.com/advisories/GHSA-pchr-8j38-3x4p) — Pillow: TIFF encoder ColorMap plane-size mismatch causes a heap out-of-bounds read | 13.0.0 |
| [#287](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/287) | pillow | high | [GHSA-p4wg-p73j-c528](https://github.com/advisories/GHSA-p4wg-p73j-c528) — Pillow: Unbounded recursion parsing a PDF page tree or trailer chain (incomplete fix for CVE-2026-42310) | 13.0.0 |
| [#286](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/286) | pillow | medium | [GHSA-462x-pgg6-55fp](https://github.com/advisories/GHSA-462x-pgg6-55fp) — Pillow tiled-TIFF decoder reads past tile buffer in copy4 (Unpack.c:1290) | 13.0.0 |
| [#285](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/285) | Pillow | high | [GHSA-c6hw-5grf-ff96](https://github.com/advisories/GHSA-c6hw-5grf-ff96) — Pillow: OOB read in TiffDecode.c tile and RGBA paths leaks heap memory into pixels | 13.0.0 |
| [#284](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/284) | Pillow | critical | [GHSA-8g5g-8vmr-9782](https://github.com/advisories/GHSA-8g5g-8vmr-9782) — Pillow: Heap buffer overflow in ImagingJpegDecode | 13.0.0 |
| [#281](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/281) | fsspec | high | [GHSA-27vj-qcqg-25rc](https://github.com/advisories/GHSA-27vj-qcqg-25rc) — fsspec: Server-Side Template Injection in ReferenceFileSystem leads to Remote Code Execution | 2026.6.0 |
| [#280](https://github.com/jgouviergmail/LIA-Assistant/security/dependabot/280) | datasets | medium | [GHSA-379c-qx7v-6h59](https://github.com/advisories/GHSA-379c-qx7v-6h59) — Hugging Face Datasets folder-based builders allow path traversal through file_name metadata | 5.0.1 |

## 5. Qualification individuelle des 33 alertes CodeQL

Dans le tableau, **FP** signifie faux positif sur le site inspecté ; **intentionnel** signifie que la construction existe mais répond à un contrat identifié ; **corriger** désigne le nettoyage avéré. Les numéros sont liés aux alertes GitHub afin que leur preuve et leur décision puissent être suivies séparément.

| Alerte | Règle | Site exact | Qualification et preuve | Action |
|---|---|---|---|---|
| [#1004](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/1004) | `py/exit-from-finally` | `apps/api/src/domains/world/router.py:191` | **FP** — La ligne est une lambda appelée par le cleanup ; l’AST ne contient aucun return dans finally. | Conserver le règlement et la propagation ; justification individuelle L1. |
| [#1003](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/1003) | `js/missing-await` | `apps/web/src/features/world/useWorldMessages.ts:90` | **FP** — check retourne une promesse booléenne ; ?? ne teste que son absence. | Conserver le retour de promesse et le refus du compte obsolète, L1. |
| [#1002](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/1002) | `js/missing-await` | `apps/web/src/features/world/useWorldMessages.ts:83` | **FP** — translate retourne la promesse du client ou la promesse unavailable. | Conserver le contrat SendOutcome et les protections de compte, L1. |
| [#1001](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/1001) | `js/missing-await` | `apps/web/src/features/world/useWorldMessages.ts:75` | **FP** — sendPublic retourne la promesse du client ; elle n’est pas testée comme booléen. | Conserver le résultat et l’idempotence, L1. |
| [#1000](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/1000) | `js/missing-await` | `apps/web/src/features/world/useWorldMessages.ts:67` | **FP** — send transmet la promesse ; le fallback ne s’applique qu’en absence de ressource. | Conserver le contrat et les AbortSignal, L1. |
| [#998](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/998) | `py/unused-local-variable` | `apps/api/src/domains/account_export/builder.py:499` | **FP** — published est lu si __aexit__ lève après publication ; un test exécute ce chemin. | Conserver la reprise de l’archive publiée lors d’une annulation, L1. |
| [#997](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/997) | `py/weak-sensitive-data-hashing` | `apps/api/src/core/security/utils.py:209` | **FP** — HMAC-SHA-256 sur le hash bcrypt stocké, pour une empreinte de révocation ; aucun mot de passe brut haché avec SHA-256. | Conserver HMAC, séparation de domaine et comparaison ; L1. |
| [#988](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/988) | `py/exit-from-finally` | `apps/api/src/domains/connectors/place_route_service.py:255` | **FP** — La lambda de settlement dans finally n’est pas un return du gestionnaire. | Conserver le règlement de chaque appel Routes payé une fois, L1. |
| [#986](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/986) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/sms/identity_store.py:78` | **FP** — Empreinte d’autorité : identifiant de grant ou credentials chiffrés, avec connector.id. | Conserver invalidation et partition de compte ; pas de KDF de mot de passe, L1. |
| [#985](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/985) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/connectors/discussion_authority.py:86` | **FP** — Hash d’identité de compte du connecteur, pas vérification de mot de passe. | Conserver le binding partagé avec content_source_binding et les scopes, L1. |
| [#984](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/984) | `py/multiple-definition` | `apps/api/src/domains/diagnostics/diagnosis.py:612` | **corriger** — L’affectation initiale est écrasée dans la boucle avant toute lecture. | L2 : stabiliser le faux temps événementiel, puis supprimer cette seule affectation. |
| [#983](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/983) | `py/catch-base-exception` | `apps/api/src/infrastructure/browser/pool.py:448` | **intentionnel** — Cleanup best effort d’une réservation ; tous les appelants réémettent ensuite leur échec primaire. | L1 : garder la borne, le nettoyage local et la réémission ; documenter l’usage large. |
| [#982](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/982) | `py/unreachable-statement` | `apps/api/src/domains/connectors/clients/apple_email_client.py:374` | **FP** — La sortie du with SMTP peut lever après sendmail ; le handler est atteignable. | Garder le log de fermeture sans transformer un envoi accepté en échec, L1. |
| [#981](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/981) | `py/uninitialized-local-variable` | `apps/api/src/infrastructure/browser/session.py:49` | **FP** — R est un paramètre de type de fonction PEP 695, pas une variable locale à initialiser. | Conserver le typage générique et le cleanup ; sonde et TU de cycle de vie, L1. |
| [#980](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/980) | `py/uninitialized-local-variable` | `apps/api/src/infrastructure/browser/session.py:49` | **FP** — P est le ParamSpec déclaré dans [**P, R] ; sa portée comprend la fonction imbriquée. | Conserver la signature typée, L1. |
| [#979](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/979) | `py/uninitialized-local-variable` | `apps/api/src/domains/voice/fishaudio/library_service.py:507` | **FP** — PinsFull appelle _refuse_full -> refuse -> raise BaseAPIException ; aucune lecture après retour normal de ce chemin. | Conserver le 409 et l’audit ; scénario concurrent de pins, L1. |
| [#978](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/978) | `py/unused-local-variable` | `apps/api/src/domains/connectors/clients/apple_email_client.py:364` | **FP** — accepted est lu quand le gestionnaire SMTP sort avec une exception après acquittement. | Conserver l’état d’acceptation ; preuve TU du QUIT en échec, L1. |
| [#977](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/977) | `py/partial-ssrf` | `apps/api/src/domains/voice/fishaudio/voices.py:191` | **FP** — Flux admin validé par 32 hex ; chemin préfixé /model/ sur hôte fixé, redirections non suivies. | Conserver les contrôles d’entrée et de capacité ; tests frontière HTTP et transport, L1. |
| [#976](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/976) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/voice/voices_catalog.py:288` | **FP** — Digest de clé API servant à partitionner un cache de voix, pas stockage de mot de passe. | Conserver isolation du cache entre comptes, L1. |
| [#975](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/975) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/voice/fishaudio/voices.py:340` | **FP** — Digest de compte pour le cache Fish Audio ; le secret n’est pas la clé Redis en clair. | Conserver rotation et invalidation du catalogue, L1. |
| [#974](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/974) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/voice/provider_capacity.py:100` | **FP** — Clé de capacité du compte fournisseur ; elle doit rester identique entre générations de workers. | Ne pas changer son format et doubler le quota pendant le rolling deploy, L1. |
| [#973](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/973) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/llm_config/credential_fence.py:15` | **FP** — Fingerprint interne comparé à un credential fraîchement relu sous verrou partagé. | Conserver comparaison constante et clôture d’autorité, L1. |
| [#972](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/972) | `py/implicit-string-concatenation-in-list` | `apps/api/scripts/jev_semantic/questions_v2.py:238` | **intentionnel** — Trois littéraux forment une seule instruction de prompt suivie d’une ligne vide. | Conserver le texte exact ; pas de virgules ajoutées, L1. |
| [#971](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/971) | `py/implicit-string-concatenation-in-list` | `apps/api/scripts/jev_semantic/questions.py:171` | **intentionnel** — Concaténation intentionnelle du paragraphe d’instructions du benchmark JEV. | Conserver prompt, tokens et protocole de mesure, L1. |
| [#960](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/960) | `py/catch-base-exception` | `apps/api/src/domains/interests/services/content_sources/content_generator.py:419` | **intentionnel** — Règle exacte mais interception pour facturer un résultat payé puis abandonné ; les non-Exception sont réémises. | Garder la comptabilité ; éprouver l’annulation pendant embedding et règlement unique, L1. |
| [#958](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/958) | `py/weak-sensitive-data-hashing` | `apps/api/src/domains/avatars/accounts.py:40` | **FP** — Empreinte d’une clé de compte avatar, pas un vérificateur de mot de passe. | Conserver partition et fencing du compte, L1. |
| [#955](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/955) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/ticket_run_labels.py:124` | **FP** — ActorKind est un Enum dont les valeurs sont admises par __contains__ sous le Python ciblé. | Conserver le vocabulaire et les traductions ; sonde de tous les membres, L1. |
| [#954](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/954) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/ticket_run_labels.py:120` | **FP** — RunError accepte ses valeurs dans le test d’appartenance ; inconnu retourne une chaîne vide. | Conserver l’absence d’exposition de message d’exception brut, L1. |
| [#953](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/953) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/ticket_run_labels.py:115` | **FP** — RunOutcome est bien un conteneur de valeurs via EnumType.__contains__. | Conserver labels et branche inconnue, L1. |
| [#952](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/952) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/components/ticket_fields.py:50` | **FP** — AssigneeKind accepte les valeurs de l’enum ; sonde sur tous les membres. | Conserver la présentation et le vocabulaire central, L1. |
| [#951](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/951) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/components/ticket_fields.py:32` | **FP** — TicketPriority est un Enum compatible avec l’appartenance des valeurs. | Conserver priorité et ton sémantique, L1. |
| [#950](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/950) | `py/member-test-non-container` | `apps/api/src/domains/agents/display/components/ticket_fields.py:24` | **FP** — TicketStatus est un Enum ; les sept valeurs réelles passent l’appartenance. | Conserver cartes et statut inconnu ; aucune liste parallèle, L1. |
| [#949](https://github.com/jgouviergmail/LIA-Assistant/security/code-scanning/949) | `js/missing-origin-check` | `apps/web/src/lib/audio/wake-word/worker.ts:31` | **FP** — Entrée d’un Worker dédié de module créé par detector.ts, pas window.postMessage. | Conserver le canal du worker ; ne pas ajouter un filtre d’origine de fenêtre, L1. |

### 5.1 Contrats qu'une correction mécanique casserait

**Empreintes (#997, #986, #985, #976, #975, #974, #973, #958).** #997 calcule un HMAC-SHA-256 avec séparation de domaine sur le hash bcrypt déjà stocké, tronqué à 128 bits, pour invalider les liens après changement de mot de passe. Les autres sites identifient un compte, une autorité, un cache ou une génération de credential ; ils ne sont pas un vérificateur de mot de passe. Les clés elles-mêmes restent chiffrées ou privées. Ne pas appliquer un KDF de mot de passe aux clés Redis et ne pas changer leur format uniquement pour le scanner. En particulier, `provider_capacity.py` précise que le rolling deploy doit garder la clé ElevenLabs existante : deux familles indépendantes permettraient de dépasser la limite du même compte. Une évolution séparée vers HMAC devrait définir versionnement, bascule atomique et compatibilité de tous les lecteurs ; rien dans les alertes ne la rend nécessaire.

**Flux d'exception (#1004, #988, #998, #982, #978, #983, #960).** Les deux premiers sites sont des lambdas dans `finally`, sans instruction `return` dans ce bloc : une analyse AST des fichiers exacts le confirme. `published` et `accepted` sont lus lorsqu'une sortie de gestionnaire de contexte lève après l'effet. Supprimer ces variables ou les handlers pourrait laisser un export publié après annulation ou provoquer une nouvelle émission d'un email déjà accepté. Les interceptions larges de nettoyage ne sont pas des handlers généraux du produit : le pool réémet l'échec primaire chez tous ses appelants et le générateur réémet les exceptions qui ne dérivent pas de `Exception`, après règlement du contenu déjà payé.

**Promesses (#1000 à #1003).** Les callbacks retournent l'objet promesse du client ou une promesse de repli avec `??`. Ils n'utilisent pas une promesse comme un booléen ; `??` teste `null`/`undefined`. Leur consommateur peut attendre le résultat. Ajouter `async`/`await` ne corrige aucun défaut démontré et modifie la frontière de promesse sans nécessité.

**Typage et énumérations (#981, #980, #979, #950 à #955).** P/R sont des paramètres de type PEP 695, pas des variables locales ordinaires. `_refuse_full()` est `NoReturn` et aboutit toujours à `raise BaseAPIException`. Les tests d'appartenance aux enums acceptent leurs valeurs depuis Python 3.12 ; les six enums réels ont été exercés avec tous leurs membres et une valeur invalide sous l'interpréteur du projet. Sources : [Enum](https://docs.python.org/3.14/library/enum.html#enum.EnumType.__contains__), [paramètres de type](https://docs.python.org/3.14/reference/compound_stmts.html#type-params).

**SSRF (#977).** Le flux SARIF part de `get_fish_voice`, qui exige l'administrateur et applique `VOICE_ID_PATTERN.fullmatch`, exactement 32 caractères hexadécimaux minuscules. Le client utilise la racine Fish Audio et le chemin `/model/{voice_id}`, avec redirections désactivées par défaut. Une sonde locale HTTPX construisant sept identifiants, dont des formes d'URL et de traversée, conserve l'hôte ; aucune requête réseau n'est envoyée par cette sonde. Le helper `fish_request` reste générique : toute nouvelle source de chemin absolu exigerait sa propre analyse. La preuve du flux courant ne dispense pas de valider les nouveaux appelants.

**Worker (#949).** Le scanner assimile `self.onmessage` à une entrée de fenêtre. `detector.ts` crée un `Worker` dédié de module et ne publie pas son handle à une autre fenêtre ; le message est reçu sur ce canal privé. Ajouter `event.origin === location.origin` peut refuser les messages légitimes d'un worker et ne constitue pas sa frontière de sécurité. [Contrat du worker dédié](https://developer.mozilla.org/en-US/docs/Web/API/DedicatedWorkerGlobalScope/message_event). Les limites de payload et la gestion d'un message malformé restent des sujets de robustesse distincts à tester si cette entrée évolue.

**Chaînes (#971, #972).** Les littéraux adjacents forment intentionnellement un seul paragraphe suivi d'une ligne vide. Insérer des virgules changerait les prompts de mesure JEV, donc potentiellement les tokens et les résultats. Aucun changement de texte n'est justifié pour ces alertes.

### 5.2 Nettoyage #984 et piège du test temporel

`diagnose_incidents` affecte `budget_key` avant la boucle, puis le réaffecte dans la boucle avant toute lecture. `_budget_key()` est un calcul de date ; l'affectation initiale est inutile. Garder les relectures avant les incidents et avant chaque langue : elles empêchent d'émettre un appel après épuisement du budget et gèrent le passage de minuit UTC.

Le test existant `test_crossing_utc_midnight_reads_the_new_day_before_the_next_language` simule le temps par une suite de résultats de `_budget_key`. Sa séquence contient actuellement l'appel inutile. Le supprimer seul peut faire échouer le test sans régression réelle. Remplacer d'abord ce faux temps par un jour mutable qui change après le premier faux appel modèle, puis supprimer l'affectation. L'oracle reste : une première langue est produite, la seconde lit le jour suivant et est bloquée si son budget est épuisé. Ne pas assouplir cet oracle.

## 6. Cartographie des impacts et matrice des risques

| Surface | Impact direct / indirect | Risque d'une mauvaise remédiation | Mesure concrète |
|---|---|---|---|
| API de diagnostic | Suppression d'une affectation sans modification de signature | Décaler le faux temps du test ou retirer une vraie relecture de budget | Temps déclenché par événement ; tests budget nul, épuisé, plusieurs langues, minuit |
| Authentification et récupération | Aucune modification requise | Liens antérieurs encore valides, exposition du hash, invalidation erronée | Garder HMAC et bcrypt ; tests existants de liaison au compte et au mot de passe |
| SMTP Apple | Aucune modification requise | Double envoi après QUIT en échec, refus partiel présenté comme succès | Tests acceptation, refus partiel, TLS, échec avant/après acceptation ; aucun retry automatique |
| Export RGPD / disque / SQL | Aucune migration requise | ZIP publié après annulation, nettoyage sur la boucle, état SQL contradictoire | Tests d'annulation à la sortie de transaction, de rollback et de suppression hors boucle |
| Navigateur, Redis et leases | Conserver propriété et annulation | Capacité perdue, contexte abandonné, ancien propriétaire qui libère le nouveau | Matrice échec primaire/nettoyage/Redis ; TTL, reprise et token de propriété |
| Voix, credentials et quotas | Ne pas changer les clés de cache et de capacité | Mélange entre comptes, données périmées, double budget pendant un déploiement | Clés actuelles conservées ; tests rotation/révocation, caches, capacité multi-worker |
| Intérêts, registres et coûts | Garder le règlement du contenu payé mais rejeté | Perte/double comptage, faux succès d'une consultation, annulation avalée | Annulation pendant embedding ; capture facturée une fois ; refus explicites et run_id stable |
| Cartes Workboard | Enums et rendu inchangés | Champs absents ou exceptions sur valeurs inconnues ; divergence des six langues | Exercer membres réels, valeur absente/invalide, HTML échappé et rendu traduit |
| Monde : messagerie et traduction | Contrats de promesse, autorité et consentement inchangés | Résultat tardif pour un autre compte, doublon après timeout, focus perdu | Tests génération/AbortSignal ; statuts incertain/rejeté/accepté ; E2E conditionnels |
| Worker vocal et téléphone | Maintenir le calcul hors thread principal | Détecteur silencieux après filtre origin inadapté ; CPU/mémoire excessifs | Worker réel, buffers transférés, chargement remplacé, erreur d'intégrité, arrêt/reprise |
| Kit GPU / chaîne de build | Revoir packaging et fermeture transitive | Import manquant, incompatibilité CUDA, paquet vulnérable toujours présent, dérive de qualité | Build propre avec hashes ; pip check ; SBOM ; audit des cinq locks ; synthèse témoin et qualification du détecteur |
| GitHub / veille / documentation | Classer chaque site et suivre chaque vulnérabilité | Compteur artificiellement vert, acceptation périmée, doublons ou constats masqués | Registre daté, audit paginé avant/après, règles globales inchangées, échec sur source indisponible |

Les risques dominants de la remédiation sont la rupture du kit GPU et la dégradation d'un invariant sain pour satisfaire le scanner. Le nettoyage #984 présente un risque applicatif faible mais un vrai risque de faux rouge du test temporel identifié ci-dessus.

### LLM, coûts, quotas, registres et mémoire

- Aucun ajout de prompt, contexte, outil, modèle, donnée de catalogue ou appel fournisseur n'est nécessaire pour la remédiation CodeQL. Les deux prompts de mesure JEV doivent rester identiques octet pour octet si leur forme Python change.
- Les plafonds existants du diagnosticien restent relus avant les appels ; la révision #984 ne doit jamais augmenter le nombre de générations. Les tests utilisent un faux modèle et un faux registre de coût, pas les clés plateforme.
- Les contenus d'intérêts déjà générés restent facturés une fois même s'ils sont rejetés lors de l'embedding. La clé personnelle conserve la politique actuelle d'affichage et d'enregistrement ; aucun nouveau chemin de facturation n'est introduit.
- Les empreintes d'autorité, les familles Redis, la rotation des credentials, les générations et les fence tokens restent identiques. Ne créer ni nouvelle copie d'un scope ni nouveau champ de `MessagesState` pour cet audit.
- Ni mémoire longue durée, ni checkpoint LangGraph, ni schéma SQL, ni migration de données ne sont nécessaires. Un éventuel registre analytique d'alertes est un document de maintenance, pas une nouvelle mémoire applicative.
- Le kit GPU consomme du calcul local et peut télécharger des poids ; ce coût est distinct des tokens LLM. L4 prévoit un petit lot de synthèse et une réutilisation contrôlée des poids, sans relancer la génération des corpus par défaut.

### UX, responsive et accessibilité

Aucun écran, texte utilisateur ou composant partagé n'a à changer pour le classement des alertes ou #984. Préserver la messagerie réactive, les résultats de traduction, les états incertains, le focus et l'isolation de compte. Si un futur correctif touche ces interfaces, appliquer les primitives existantes, les six langues, les noms accessibles, le clavier, le retour du focus, `aria-busy` et la conservation des brouillons lors d'un refresh.

Le test navigateur ciblé d'un changement frontend devra couvrir une largeur de téléphone de 320/375 px et un écran de bureau, plus clavier et reflow ; WebKit est pertinent pour le parcours audio mobile. Un classement documentaire ne justifie pas une refonte UI ou un nouveau parcours utilisateur.

## 7. Plan de tests directeur

### 7.1 Preuves réellement exécutées pendant l'analyse

| Vérification | Résultat et limites |
|---|---|
| Lecture REST paginée | 43 Dependabot + 33 CodeQL ; même SHA pour les instances CodeQL ; 76 identifiants inventoriés |
| PyPI + wheel officiel | Métadonnées des 37 Gradio 6 et 13 datasets 3 vérifiées ; aucun n'admet les versions corrigées ; wheel contrôlé par hash, pas importé |
| TU backend ciblés, groupe A | 84 passés, code 0 ; récupération de mot de passe, cycle de vie navigateur, SMTP Apple, export, comptabilité d'itinéraire, capacité vocale |
| TU backend ciblés, groupe B | 57 cas passés, code 0 ; catalogue Fish Audio, registre de consultations, facturation de contenu rejeté, diagnostic et budget |
| TU frontend ciblés | 5 fichiers, 30 tests passés, code 0 ; hooks/clients de messagerie du monde et worker/détecteur vocal |
| Sondes locales | Six enums réels ; décorateur générique sur succès/annulation ; deux `finally` sans `return` ; sept identifiants d'URL Fish Audio sans changement d'hôte |

Cela représente **171 tests ciblés passés**, plus les sondes. Les logs n'ont pas signalé de test ignoré ou d'avertissement de framework ; des logs applicatifs WARNING sont attendus dans les simulations d'échec, notamment nettoyage et libération de capacité. Ces tests ne sont ni une mesure de couverture complète, ni une qualification GPU, ni une recette de production.

Les premiers lancements Python sous confinement n'ont pas abouti et ont été interrompus ; ils ne sont pas comptés comme tests réussis. Le préchargement des tables publiques tiktoken a été effectué, puis les deux groupes backend ont été exécutés avec la permission locale nécessaire. Aucun garde réseau de la suite n'a été désactivé.

Commandes des groupes backend, depuis `apps/api`, avec `TIKTOKEN_CACHE_DIR` pointant vers le cache de travail de cet audit :

```powershell
.venv/Scripts/python -X utf8 -m pytest tests/unit/core/security/test_password_reset_token.py tests/unit/infrastructure/browser/test_pool.py tests/unit/infrastructure/browser/test_pool_lifecycle.py tests/unit/infrastructure/browser/test_session_activity.py tests/unit/domains/connectors/clients/test_apple_email_client.py tests/unit/domains/account_export/test_export_disk_off_loop.py tests/unit/domains/connectors/test_place_route_accounting.py tests/unit/domains/voice/test_provider_capacity.py --no-cov -q -p no:cacheprovider --tb=short
.venv/Scripts/python -X utf8 -m pytest tests/unit/domains/voice/fishaudio/test_voices.py tests/unit/domains/interests/test_content_source_consultations.py tests/unit/domains/interests/test_discarded_reflection_billing.py tests/unit/domains/diagnostics/test_diagnosis.py --no-cov -q -p no:cacheprovider --tb=short -o log_cli=false
```

Commande frontend, depuis `apps/web`, avec `NEXT_PUBLIC_API_URL` vide comme l'exige la tâche frontend :

```powershell
pnpm exec vitest run src/features/world/__tests__/useWorldMessages.test.tsx src/features/world/__tests__/mailbox-client.test.ts src/features/world/__tests__/public-mailbox-client.test.ts src/lib/audio/wake-word/__tests__/worker-core.test.ts src/lib/audio/wake-word/__tests__/detector.test.ts --reporter=dot
```

### 7.2 Matrice de validation de l'implémentation

| Famille | TU / simulations | Intégration ou flux | E2E / recette |
|---|---|---|---|
| Diagnostic #984 | Budget nul, épuisé, plusieurs incidents/langues, faux temps événementiel, minuit UTC | Persistance et comptage via le contrat existant si le règlement est touché | Aucun nouvel E2E pour une affectation supprimée |
| Hash et identités | Changement de mot de passe, None, clé tournée/révoquée, même credential entre workers, comptes distincts | Réutiliser `tests/integration/domains/voice/test_provider_key_fence.py` et `test_browser_pool_redis.py` si ces contrats changent | Réinitialisation de mot de passe et sélection de voix seulement si leur comportement est modifié |
| Export et SMTP | Annulation à la sortie de transaction ; exception du `__exit__` après acceptation ; refus partiel ; TLS refusé | Fichier réellement publié puis retiré ; aucune deuxième émission SMTP ; tests DB hermétiques si transactions changées | Export/téléchargement et action email avec HITL si les chemins sont modifiés |
| Nettoyages BaseException | Échec primaire, cleanup et Redis en panne ; annulation répétée ; embedding annulé après génération ; coût capturé une fois | Bail expiré/repris et ancien propriétaire ; transactions séparées pour règlement | Aucun résultat annoncé comme réussi sur annulation |
| NoReturn et enums | PinsFull en concurrence aboutit à 409 sans lecture de `pinned` ; toutes les valeurs d'enum, vide/inconnue | Réutiliser `test_library_router.py` pour le flux de pin avec audit et contrôle admin | Cartes traduites et pins si interface réellement touchée |
| Fish Audio URL | ID valide ; slash, backslash, `%2f`, URL absolue, userinfo, `?`, `#`, CRLF ; zéro transport avant refus | MockTransport : hôte attendu ; 302 vers privé non suivi ; 401/403/404/429/5xx, timeout, JSON malformé | Accès admin/non-admin, contrôle de clé et absence d'effet avant attestation |
| Messagerie du monde | Promesse acceptée/rejetée ; pas de client ; compte obsolète ; unmount ; réponse tardive ; statut incertain | Conserver idempotence et consultation de statut, aucune réémission d'un envoi incertain | Clavier, focus, brouillon, changement de compte, responsive si le hook change |
| Worker vocal | load/audio/reset, message inconnu ou malformé, langue invalide, buffer vide/trop grand/détaché, chargements concurrents | Worker réel : génération obsolète ignorée, intégrité et réseau en panne, arrêt libère les ressources | Docker dev ; Chromium et WebKit si modifié ; téléphone physique pour toute revendication iOS |
| Chaînes JEV | Comparaison exacte du prompt avant/après ; mêmes marqueurs et schéma de tool | Pas de modèle réel pour prouver une concaténation Python | Aucun |
| Graphe GPU | Exigences contradictoires refusées ; lock/hash/metadata contrôlés ; imports optionnels bloqués | Image propre Python du kit, `pip check`, SBOM, scan, modèle épinglé, sans réseau après préchargement | Petit lot voix conçue + clonée ; train minimal ; mesure et golden CPU existants ; six langues et commandes avant de remplacer des modèles livrés |
| Inventaires / veille | Pagination, source indisponible, avis retiré/republié, changement de casse Pillow, doublon, acceptation expirée/inutilisée | Parité endpoint global / sources fournisseurs expliquée ; alertes fixées par SHA après scan | Relecture GitHub avant/après et de toutes les catégories CodeQL, pas seulement du compteur |

Les simulations de robustesse proposées pour le worker ou les URL ne prouvent pas un défaut actuel : elles protègent une frontière si on la modifie. Les nouvelles assertions réellement nécessaires portent sur les trous de contrat ; on ne crée pas une suite artificielle pour chaque ligne d'un classement documentaire.

## 8. Plan d'actions consolidé et séquencé

### L0 — Figer et réconcilier les preuves (réalisé pour cette analyse)

**Livrable :** les deux tableaux ci-dessus et les données brutes locales. Aucun changement de produit.

- [x] Lire les inventaires complets et les instances, le commit, les SARIF et les contrats de build.
- [x] Contre-vérifier les métadonnées officielles et les 23 sources concernées.
- [x] Séparer paquets vulnérables, exposition statique, faux positifs et code inutile.
- [ ] Au démarrage de l'implémentation, refaire les inventaires et identifier seulement les écarts ; ne pas remplacer les alertes de ce snapshot par un ancien total.

### L1 — Consolider les preuves et proposer les 32 dispositions CodeQL

**Fichiers sources concernés :** les 22 fichiers du tableau autres que `diagnosis.py`, conservés en l'état sauf défaut démontré par une nouvelle preuve. **Tests à réutiliser :** ceux listés en section 7 ; pour les pins, `apps/api/tests/unit/domains/voice/test_library_router.py`.

**Interface :** conserver toutes les signatures, valeurs de statut, promesses, identifiants et clés Redis. **Sortie :** une justification par numéro, SHA, règle, précondition de sécurité et référence de test. Aucun classement global par règle.

- [ ] Vérifier les chemins d'annulation et de refus que les tests existants ne couvrent pas encore : règlement après embedding annulé, annulation réitérée pendant cleanup, PinsFull concurrent, 302 non suivi et entrée refusée avant transport. Ajouter seulement les tests comportementaux manquants.
- [ ] Si un test révèle un vrai défaut, retirer ce site de la proposition de classement, décrire la cause et ouvrir un petit cycle TDD isolé. Ne jamais conserver le décompte « 28 FP » contre une preuve contraire.
- [ ] Préparer les 28 motifs de faux positif et les 4 motifs d'usage intentionnel. Pour `BaseException`, citer la propagation de l'échec primaire, le périmètre de cleanup et les délais, pas seulement une annotation.
- [ ] Soumettre les dispositions individuelles ; les appliquer sur GitHub seulement dans la phase de remédiation autorisée. Garder une trace des raisons pour la prochaine analyse.
- [ ] Relire les alertes ouvertes après la prochaine analyse, y compris les nouvelles occurrences des mêmes règles. Aucun filtre global supplémentaire.

### L2 — Nettoyer #984 sans altérer le budget

**Modifier :** `apps/api/src/domains/diagnostics/diagnosis.py`, affectation initiale avant la boucle. **Test :** `apps/api/tests/unit/domains/diagnostics/test_diagnosis.py`.

**Interface :** `diagnose_incidents(...) -> int` et toutes ses dépendances restent identiques. **Sortie :** aucune affectation morte initiale ; budget toujours relu avant toute langue et tout incident.

- [ ] Rendre d'abord le test de minuit indépendant du nombre de lectures de date : jour mutable avancé par le faux appel modèle. Garder l'attente d'un seul appel et de la lecture du budget du jour suivant.
- [ ] Exécuter ce test et les cas budget nul/épuisé pour caractériser le comportement actuel.
- [ ] Retirer uniquement l'affectation morte initiale. Ne toucher ni aux deux relectures utiles, ni au suivi de coût, ni au prompt.
- [ ] Exécuter `test_diagnosis.py`, le test de langues/preuves associé et les gates backend pertinents. Attendre le nouveau résultat CodeQL du commit de correction avant d'annoncer #984 fermé.

Ce nettoyage peu risqué ne nécessite pas un nouveau test qui compterait une affectation interne : l'oracle fonctionnel de budget et de temps est la bonne protection.

### L3 — Maintenir un traitement transitoire honnête des 43 vulnérabilités

**Fichiers de référence :** `docs/technical/CI_CD.md`, `scripts/wake-word/README.md`, `scripts/audit/dependency_watch_accepted.json`, `scripts/audit/dependency_watch.py`. Le commit documentaire concurrent a déjà complété une partie de ce travail ; le relire avant toute écriture.

**Interface :** conserver le contrat de `judge()` : une acceptation correspond exactement à un constat lu, possède un responsable et expire. **Sortie :** aucun avis sans responsable ou échéance ; aucune acceptation inutilisée ajoutée à la veille.

- [ ] Réconcilier les 43 GHSA de l'inventaire avec les décisions effectivement présentes après le commit concurrent ; ne pas redoubler son travail.
- [ ] Signaler séparément les échéances du registre automatisé et celles des avis globaux. Revoir chaque acceptation lors de L4, puis la retirer quand sa raison disparaît.
- [ ] Conserver l'interdiction d'étendre le kit aux images, UI publique, débruiteur ou constructeurs de dataset sans résoudre les avis correspondants.
- [ ] Inclure le kit GPU dans la validation du lot de dépendances : l'audit backend courant de `Taskfile.yml` ne lit que les trois locks applicatifs. Définir la tâche proposée `security:scan:wake-word`, depuis `scripts/wake-word`, avec le même `UV` et `PIP_AUDIT_VERSION` que `security:scan:backend` et `pip-audit --desc --disable-pip -r requirements.lock.txt -r requirements-gpu.lock.txt`. Elle complète la porte ; elle ne remplace ni Dependabot ni la veille fournisseurs. Son résultat rouge attendu sur le graphe actuel demeure visible ; ne la transformer en prérequis vert qu'une fois L4 qualifié, sans ignorer les 43 avis pour la faire passer.
- [ ] Si l'automatisation du catalogue global est retenue, l'ajouter à la veille existante avec identité de source et preuves de pagination/indisponibilité ; étendre ses tests dans le même lot. Ne pas introduire d'échéance silencieuse ou de deuxième système d'acceptation.

### L4 — Qualifier un graphe GPU corrigé (porte technique explicite)

**Fichiers existants :** `scripts/wake-word/requirements-gpu.in`, `requirements-gpu.lock.txt`, `Dockerfile.gpu`, `wakeword/clone.py`, `Taskfile.yml` (`wake:deps:lock`, `wake:image:gpu`, `wake:run:gpu`) et les tests du kit. Les nouveaux fichiers de recette de distribution ne sont nécessaires que si la voie officielle reste incompatible.

**Interface :** garder `_model() -> VoxCPM`, les entrées texte/WAV, les paramètres de génération, les seeds, le format des banques, l'entraînement du détecteur et ses sorties navigateur. Ne pas entraîner VoxCPM lui-même ni activer son UI pour ce lot.

- [ ] Rafraîchir les métadonnées PyPI. Si une version officielle admet les correctifs, utiliser cette voie avec des floors explicites dans le manifest et les tâches de lock existantes.
- [ ] Sinon, réaliser un spike isolé de packaging d'inférence : source amont épinglée et vérifiée, licence/NOTICE conservés, extras UI/training/débruitage séparés, dépendances directes réellement importées déclarées. Garder les algorithmes amont ; toute modification supplémentaire doit être justifiée séparément.
- [ ] Vérifier la fermeture transitive complète : le retrait des dépendances directes ne suffit pas si FunASR, ModelScope ou un autre paquet les ramène. Un import manquant ou une réintroduction de version vulnérable rend le spike non qualifié.
- [ ] Ajouter les tests de frontière de packaging avant de l'intégrer : aucune résolution incompatible ; aucune installation cachée ; imports UI/datasets/PIL interdits pendant le smoke d'inférence s'ils sont annoncés supprimés ; hooks d'import observables ; mêmes entrées/sorties de clone.
- [ ] Produire un wheel ou sdist reproductible et clairement identifié si une distribution maintenue est retenue. Ne jamais modifier le `METADATA` d'un environnement déjà installé pour contourner le resolver.
- [ ] Recompiler par `task wake:deps:lock`, contrôler les diffs CPU/GPU et leurs hashes, puis construire une image sans cache avec installation cohérente et `pip check`. Exiger les floors Pillow >=13, fsspec >=2026.6 et datasets >=5.0.1 si ces paquets restent présents, ou prouver leur absence dans la fermeture installée.
- [ ] Scanner le lock et l'image, générer un SBOM du kit et établir pour chacun des 43 GHSA « paquet corrigé » ou « paquet absent ». Aucune acceptation n'est supprimée avant cette preuve.
- [ ] Faire une synthèse CUDA bornée de voix conçue et de voix clonée, modèle/révision et seeds inchangés, poids préchargés et réseau ensuite coupé. Vérifier WAV, taux, durée, valeurs finies et absence de chemins interdits ; puis entraînement minimal.
- [ ] Si le code ou la recette de génération a changé, qualifier les distributions de clips et le détecteur par les mesures/golden CPU existants avant de remplacer des banques ou modèles livrés. Conserver la génération précédente tant que la nouvelle n'est pas qualifiée ; aucune régénération massive par défaut.
- [ ] Si le spike échoue, conserver l'état antérieur et produire la dépendance exacte qui bloque ; ne pas annoncer « 43 corrigées ». Le choix maintien temporaire / distribution maintenue / suspension du clone reste explicite.

### L5 — Qualification et clôture

- [ ] Exécuter les portes correspondant aux vrais changements : statique backend/frontend, lockfiles, CI parity, docs et ratchets. Réutiliser les tâches existantes ; les seuils restent ceux de leurs sources.
- [ ] Avant toute livraison : `task ci:fast`, puis les suites hermétiques et de services pertinentes et les scans de sécurité. Les migrations et tests PostgreSQL utilisent des cibles jetables, jamais la base de dev à réinitialiser.
- [ ] Une modification de source frontend exige sa vérification Docker dev et les flux Playwright concernés ; le classement d'une alerte sans source modifiée ne la réclame pas.
- [ ] Relire les deux inventaires GitHub paginés et les SHA après analyse du commit livré. Distinguer alertes corrigées, classées, risques acceptés et nouveaux constats ; la seule réussite du workflow Security ne suffit pas.
- [ ] Retirer les acceptations obsolètes, conserver leurs preuves historiques et réconcilier les documents. Aucun commit, push, déploiement, message ou classement GitHub n'est inclus dans cette analyse.

## 9. Arbitrages résiduels et auto-évaluation

Il n'existe pas de décision métier bloquante pour L1/L2 ni pour la tenue honnête du risque en L3. L4 peut démarrer par sa contre-vérification et son spike sans choix produit supplémentaire.

En revanche, si l'objectif impose **zéro alerte Dependabot à une date proche**, la voie officielle actuelle ne suffit pas. La décision qui dépasse l'analyse technique est l'acceptation de la maintenance d'une distribution d'inférence dérivée, ou la suspension temporaire du clone GPU si la qualification échoue. Le code ne permet pas de déduire le budget de maintenance ou la tolérance fonctionnelle de l'exploitant. Aucune de ces décisions n'est présumée approuvée.

| Critère demandé | Verdict formel | Justification / réserve |
|---|---|---|
| Exhaustivité des alertes visées | Oui pour l'inventaire et la qualification de ce snapshot | 43 + 33 lignes, identifiants uniques, 23 sources concernées et traces SARIF relues |
| Hypothèses confrontées au code réel | Oui pour les conclusions retenues | Contrats, appels, versions, build, hashes et syntaxes vérifiés ; les limites des imports transitifs et du runtime GPU sont explicitement réservées |
| Tokens, coûts et quotas intégralement cadrés | Oui dans le périmètre | Aucun nouvel appel ; invariants de budget, annulation, attribution et clé de capacité conservés ; tests payants exclus |
| Registres, persistance et mémoire cadrés | Oui | Aucun nouveau schéma ; scopes, générations, registres et sérialisation conservés ; risque de migration de hash identifié et évité |
| Responsive et accessibilité cadrés | Oui | Pas de changement UI requis ; critères précis et tests conditionnels si le frontend est touché |
| Plan de tests et lots démarrables | Oui pour L1-L3 ; L4 démarre par une qualification | Fichiers, contrats, scénarios et preuves de sortie définis ; aucune garantie prématurée de compatibilité GPU |
| Conviction de 100 % sans réserve sur toute l'implémentation | Non, ce serait excessif | L'environnement CUDA réduit et tous ses imports transitifs n'ont pas été exécutés ; la compatibilité du graphe cible reste une porte mesurable, pas un fait acquis |

L'analyse est exploitable immédiatement pour le triage et le nettoyage borné. La résorption des 43 vulnérabilités dépend d'une preuve de compatibilité ou d'un arbitrage de maintenance clairement isolé ; aucun résultat GPU ou état de production n'est extrapolé.
