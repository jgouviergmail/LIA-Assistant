# ADR-283 — Un worker API a une anatomie déclarée et mesurée

- **Statut** : Accepté
- **Date** : 2026-09-12
- **Amende** : ADR-119 (le noyau alerte sur le `working_set`, jamais sur
  l'`usage`), ADR-123 (une étape de démarrage est une fonction dans son module
  et un appel dans le lifespan), ADR-148 (une métrique que personne ne voit est
  une métrique sur laquelle personne n'agit), ADR-184 (une borne imposée est
  publiée), audit F004 (le budget de connexions borne la POINTE)
- **Périmètre** : `src/serve.py` et le `CMD` de `Dockerfile.prod`,
  `voice/stt/sherpa_stt.py` (cache des recognizers), `document_generation/
  renderers/pdf_layout.py` (import de PyMuPDF), `observability/
  process_memory.py` (`lia_worker_memory_bytes`), `voice_stt_recognizers_loaded`,
  l'alerte `ApiWorkerMemoryHigh`, `connection_budget.persistent_total`,
  `docker-compose.prod.yml` (plafond Postgres) et les profils `.env`
  (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `VOICE_STT_MAX_RECOGNIZERS`,
  `WORKER_MEMORY_SAMPLE_INTERVAL`)

## Contexte

Le 2026-09-12, la production (Raspberry Pi 5, 16 Go) tenait 10 Go dont 6 Go
pour les deux API (production et démonstrateur), et l'alerte
`ContainerMemoryNearLimit` avait cyclé cinq fois sur `lia-postgres-prod` dans
la nuit du 11, entre 95,6 et 99,65 % de son plafond. Rien de tout cela n'était
une fuite. Chaque poste a été mesuré, sur l'hôte, dans des processus jetables,
avant d'être touché :

| Poste | Mesure | Cause |
|---|---|---|
| Superviseur uvicorn | 437 Mo (prod), 407 Mo (démo), aucune requête servie | `uvicorn.main.run` (0.48) importe l'application dans le superviseur (`config.load_app()`) pour un message d'erreur précoce, puis la garde |
| Worker API | ~1 Go après une journée, dont 386 Mo de bibliothèques à l'import | PyMuPDF importé au boot par un `import fitz` de premier niveau (43 Mo par processus sur arm64) pour un rendu PDF qu'un worker peut ne jamais faire |
| Worker ayant servi une session vocale | **+1,6 Go**, jamais rendus, croissant à l'usage (+151 Mo sur un décodage identique) | un recognizer whisper PAR LANGUE demandée (516 Mo à la création, +300 après le premier décodage), dans un singleton par processus ; deux workers ont porté le conteneur de 4,2 à 7,0 Go pour un plafond de 8 Gio |
| Postgres | 900-950 Mio toute la nuit sur 1 Gio, 272 Mo en zram au matin | `shared_buffers` 512 Mo + 88 backends inactifs × 7 Mo = 1 128 Mo de mémoire NON récupérable, la sauvegarde `@daily` remplissant les buffers à 02:00 |
| La croissance du conteneur | 2,5 → 5,3 Go en deux jours (8-10/09), par paliers | **inexpliquée** : cAdvisor voit le conteneur, quatre workers vivent dedans, et le mode multiprocess de `prometheus_client` n'exporte aucune métrique `process_*` |

Trois faits d'instrumentation méritent d'être écrits, parce qu'ils ont coûté
chacun une fausse conclusion avant d'être corrigés : un chiffre d'import mesuré
en dev x86_64 ne vaut pas pour l'arm64 (PyMuPDF : 118 Mo contre 43) ;
`pg_settings.setting` de `shared_buffers` est en blocs de 8 kB, et concaténer
`setting||unit` affiche `655368kB` qu'on lit 640 Mo à tort ; le modèle
whisper-small de production est DÉJÀ en INT8 (112 + 262 Mo), les 1,6 Go sont la
mémoire de travail d'ONNX Runtime, pas les poids.

## Décision

**Ce qu'un processus charge est déclaré, mesuré par processus, et borné là où
il se multiplie.**

1. **Le superviseur ne charge pas l'application.** `python -m src.serve`
   remplace la CLI uvicorn dans le `CMD` de l'image : même chaîne
   `Config → Server → Multiprocess`, mêmes drapeaux un pour un, sans
   `load_app()`. Le module n'importe rien de `src` au niveau module (garde
   AST). Ce qu'il abandonne — l'erreur d'import précoce — est rendu par le
   health check du conteneur, que le déploiement lit (ADR-250). Mesuré en dev :
   34 Mo au lieu de ~600 sur x86_64.
2. **Une bibliothèque lourde est importée où elle sert, jamais au boot.**
   `tests/unit/test_lazy_heavy_imports_guard.py` déclare `LAZY_ONLY` avec le
   coût mesuré de chacune (fitz, pymupdf, pandas, sherpa_onnx, onnxruntime,
   playwright) et refuse tout import de premier niveau sous `src/`, y compris
   dans un `try` de module. PyMuPDF passe par un accesseur `_pymupdf()` (`_fitz()`
   jusqu'au lot 8 du programme dépendances : PyMuPDF 1.28 déprécie le nom `fitz`).
3. **Le STT garde UN recognizer résident par worker.** Le cache est un
   `OrderedDict` borné par `VOICE_STT_MAX_RECOGNIZERS` (1 par défaut),
   évincé au moins récemment utilisé ; rien n'est chargé à la construction, la
   première transcription paie un chargement pour la langue qu'elle demande.
   Une éviction rend la mémoire à l'OS (mesuré : −1 166 Mo pour deux
   recognizers, un plancher de ~430 Mo restant) ; un décodage en cours garde sa
   propre référence, le cache ne lâche que la sienne. Le nombre résident est
   une jauge par worker (`voice_stt_recognizers_loaded`, `liveall`).
4. **Chaque worker publie ce qu'il tient.** `lia_worker_memory_bytes{kind}` est
   lue par chaque worker dans son propre `/proc/self/status` (`RssAnon`,
   `RssFile`, `RssShmem`), toutes les `WORKER_MEMORY_SAMPLE_INTERVAL` secondes,
   sous `multiprocess_mode="liveall"` — une série par worker vivant, qui
   disparaît avec lui. L'échantillonneur a un propriétaire (démarré dans le
   lifespan, annulé à l'arrêt par `stop_worker_memory_sampler`) et se retire
   seul là où il n'y a pas de procfs. Deux panneaux côte à côte sur le tableau
   03 (mémoire `anon` par worker, modèles STT par worker) et l'alerte
   `ApiWorkerMemoryHigh` (`max by (pid)` du tas, seuil publié
   `ALERT_CORE_API_WORKER_ANON_MB`, recette de preuve, runbook) ferment la
   boucle ADR-148 : la métrique est lue, tracée, et nomme le `pid`.
5. **Le budget de connexions a un PLANCHER, et le plafond mémoire de Postgres
   est dimensionné contre lui.** `ConnectionBudget.persistent_total` compte
   ce que chaque worker garde OUVERT (pool + minimums checkpointer et store) ;
   `tests/unit/test_postgres_memory_floor_guard.py` lit `shared_buffers` et
   la limite dans `docker-compose.prod.yml`, les pools dans
   `.env.prod.example`, et exige `shared_buffers + persistant × 7 Mo ≤ limite / 2`.
   Le profil de l'incident (1 Gio, 20 persistantes) y répond « 110 % ». Le
   profil livré : plafond **2 Gio**, pool **5** persistantes / **15** en
   débordement par worker (28 backends, 708 Mo, 35 %). Le débordement s'ouvre
   à la demande et se referme : la capacité de pointe par worker reste 20.

## Conséquences

- Gains mesurés ou bornés : −390 Mo × 2 (superviseurs), −43 Mo × 9
  processus (PyMuPDF), −420 Mo de backends Postgres, le STT ramené de
  1,6 Go croissant à ~0,9 Go par worker qui l'utilise, et Postgres avec la
  moitié de son plafond pour le cache là où il n'avait plus rien.
- Ce que le lot ne fait PAS : la croissance multi-jours d'un worker hors STT
  reste à instruire — c'est précisément ce que la jauge par worker permet
  maintenant (un recensement d'objets dans un worker vivant, `sys.remote_exec`
  PEP 768, reste une décision d'exploitation). La rétention des checkpoints
  LangGraph (3 Go sur 3,25 de base, seule purge : le reset d'une conversation)
  est un lot à part : elle doit garder les blobs référencés par les
  checkpoints conservés, LangGraph ne réécrivant que les canaux modifiés.
  Mesuré le 2026-10-12 : l'état restauré était renvoyé ENTIER en entrée du
  graphe, donc chaque canal reprenait une version à chaque tour (`__start__`
  ≈ 1 Mo, `agent_results` 600 Ko réécrits inchangés) ; l'entrée est depuis le
  diff du tour (ADR-022, amendement 2026-10-12).
- Le démonstrateur n'est pas dans le garde du plancher : sans `shared_buffers`
  explicite (128 Mo) et avec 3 × 12 backends, son plancher fait 37 % de son
  `mem_limit` de 1 Gio — sain, et documenté ici plutôt que gardé par un second
  lecteur de compose.
- Un `docker cp` vers `/tmp` d'un conteneur (tmpfs) écrit SOUS le montage :
  une sonde se passe par `docker exec -i … python -` (stdin).

## Amendement 2026-09-20 — une connexion tenue pendant une réponse qui dure

Le plancher de connexions (F004, ci-dessus) comptait les pools ; il ne
voyait pas ce qu'une REQUÊTE tient. Mesuré sur dev (`pg_stat_activity`,
`state = 'idle in transaction'`, revue ADR-301) :

- **un stream SSE par onglet ouvert pinçait un backend PostgreSQL en `idle in
  transaction` pour la vie de l'onglet** (deux backends, 14 min à la lecture,
  rouverts une seconde après chaque redémarrage du worker) : la dépendance
  `yield` `get_db` vit jusqu'à la fin de la réponse, et le SELECT d'auth de
  `get_current_session` ouvre la transaction. Corrigé par une porte propre aux
  routes qui streament (`get_current_active_session_for_stream`, ADR-045 : une
  session ouverte et fermée dans la dépendance, même authentification, ligne
  détachée seulement lue), gardée sur toutes les routes servies
  (`tests/_routes.served_routes`) ; mesuré après : un stream
  ouvert ne pince rien, l'instance n'a plus aucun backend dans cet état ;
- **un runner vocal tenait la session de son appelant pendant tout le tour
  relayé** (8,9 s) : ADR-301, règle du runner workboard appliquée ;
- **reste ouvert, mesuré** : le moteur de chat tient lui-même une session
  pendant un tour (`SELECT user_mcp_servers…`, 8,5 s sur un tour court) — une
  connexion par tour en cours, à instruire comme les deux précédents. Un
  `commit()` rend la connexion au pool (mesuré `checked out` 1 → 0) : la
  règle est « une session ne vit pas plus longtemps que les requêtes qu'elle
  sert », jamais « autour » d'une attente.

## Amendement 2026-10-12 — ce qu'un worker retient, recensé, et quatre retenues fermées

La croissance « inexpliquée » du tableau ci-dessus (2,5 → 5,3 Go en deux
jours, par paliers) a été instruite sur la production le 2026-10-12, avec le
recensement que la décision 4 rendait possible : `sys.remote_exec` (PEP 768)
dans un worker vivant, lancé par `docker exec -u 0 --privileged` (le profil
seccomp par défaut refuse `process_vm_writev` sans `CAP_SYS_PTRACE`), six
secondes de pause par worker, des nombres seuls en sortie (types, tailles,
chaînes de référents), jamais un contenu. Trois faits, chacun mesuré avant
d'être touché :

1. **Les paliers sont des tours de chat, et c'est de la rétention, pas de la
   fragmentation.** Chaque saut de 150 à 540 Mo coïncide avec un tour (jetons
   consommés, 50 à 115 opérations de checkpoint, appels connecteurs). Sur un
   worker de 1 238 Mo contre un worker léger de 925 Mo de la même génération,
   pymalloc tenait 811 Mo alloués pour 1,5 Mo libres et glibc 396 Mo en usage
   pour 22 Mo libres : les octets sont vivants. Un `gc.collect()` y a rendu
   123 763 objets et 120 Mo — des cycles qui attendaient une collection
   complète, laquelle n'arrive, sur un tas de 1,6 million d'objets
   longue durée, qu'après quelque 400 000 nouveaux survivants.
2. **Le premier poste est le sélecteur sémantique d'outils**, qui gardait un
   vecteur de 1 536 flottants par description ET par mot-clé d'outil sous la
   forme de `list[float]` Python (49 Ko le vecteur : 24 octets le flottant,
   8 la case) : 1 585 vecteurs du catalogue natif (78 Mo par worker), plus
   une copie des vecteurs des serveurs MCP de la personne par contexte de
   requête encore vivant — 2 650 vecteurs sur le worker léger, 3 722 sur le
   lourd. Le même vecteur pèse 6 Ko en `float32`.
3. **Le second poste est une classe pydantic par outil MCP et par tour**
   (`create_model("MCPToolInput")` dans `tool_adapter.py`) : 682 classes et
   690 validateurs compilés de plus en cinq heures sur le worker lourd, chacune
   un graphe de cycles que seule une collection complète libère.

Hors de cause en production, et pourtant corrigé : l'index BM25 des espaces de
connaissances (2 058 chunks, aucune série `bm25_*` en sept jours) mettait le
md5 du corpus ENTIER dans sa clé de cache — recalculé à chaque requête par une
jointure de tout le corpus — et chaque changement du corpus laissait un index
complet de plus en mémoire, jusqu'à cent.

**Décision.**

- **Un vecteur tenu par un worker est un tableau `float32`, jamais une liste
  de flottants Python** (`agents/services/tool_vectors.py` : `as_vector`,
  `as_matrix`, `cosine_rows`). Le sélecteur convertit ce que le cache disque ou
  l'embarqueur lui tend et ne garde rien d'autre ; les mots-clés d'un outil
  forment une matrice, notée en un produit. Les vecteurs des serveurs MCP d'une
  personne sont **parsés une fois par catalogue et par worker**
  (`ServerVectorCache`, clé serveur × modèle × empreinte du catalogue, borne
  `MCP_SERVER_VECTOR_CACHE_MAX`) : la liste des serveurs qui sert le tour
  diffère la colonne `tool_embeddings_cache` (`defer`), relue seule, par
  `get_tool_embeddings_cache`, à la première rencontre du catalogue — chaque
  tour en parsait auparavant un millier de vecteurs depuis le JSON de la ligne.
  Sa lecture est best-effort : un échec coûte au tour le classement de ces
  outils, jamais les outils.
- **Une classe d'arguments MCP est construite une fois par schéma**
  (`build_args_schema`, clé = JSON canonique du schéma, borne
  `MCP_ARGS_SCHEMA_CACHE_MAX`) : le même schéma rend la même classe.
- **Le tas du démarrage est gelé en dernier** (`startup/process_heap.py`,
  appelé à la fin du lifespan, après tout ce qui est résident) : `gc.collect()`
  puis `gc.freeze()`, ce que le boot a construit sort du collecteur cyclique,
  et une collection complète n'attend plus le quart d'un tas qui ne sera jamais
  un déchet. Garde : `test_process_heap.py` (l'appel est le dernier avant le
  `yield`).
- **Un index BM25 par clé, remplacé quand son corpus change**
  (`infrastructure/store/bm25_index.py`) : l'empreinte du corpus est portée par
  l'entrée, calculée par identifiant trié sans jointure, et une entrée ne
  survit pas à son corpus.

Mesuré sur dev après le changement, un boot complet en conteneur jetable : 305
descriptions et 1 280 lignes de mots-clés, toutes `float32`, 9,3 Mo au lieu
d'environ 78 ; aucune liste de flottants vivante ; 1 322 144 objets gelés et
287 objets restant au collecteur après le gel.

Ce que l'amendement ne fait pas : la mesure après déploiement reste à faire sur
la production (le worker léger et le worker lourd de la même génération donnent
la projection : −68 Mo par worker sur le catalogue natif, −46 Mo par contexte
MCP vivant, et les 120 Mo de cycles rendus au rythme des collections). Deux
coûts restent, nommés : la recherche BM25 lit encore le corpus ENTIER à chaque
requête pour en calculer l'empreinte (une version de corpus publiée par le
dépôt l'éviterait) ; et un objet du démarrage remplacé à l'exécution — un cache
de configuration rechargé sur invalidation — garde sa version gelée résidente,
une copie, une fois, jamais par rechargement. Un troisième recensement — les
référents de 3 722 vecteurs parcourus un à un — a fait mourir un worker de
production (relancé par le superviseur en six secondes) ; seul le recensement
par types et tailles, sans parcours des référents, est tenu pour sûr.

## Références

- Runbook : `docs/runbooks/alerts/ApiWorkerMemoryHigh.md`
- Tests de l'amendement 2026-10-12 :
  `tests/unit/domains/agents/services/test_tool_vectors.py`,
  `tests/unit/domains/agents/services/test_tool_selector_cache.py`
  (`TestTheVectorsAreStoredCompact`),
  `tests/unit/infrastructure/mcp/test_user_context_vectors.py`,
  `tests/integration/domains/user_mcp/test_repository_envelope.py` (PostgreSQL
  réel : la colonne différée, la lecture seule),
  `tests/unit/infrastructure/store/test_bm25_index_manager.py`,
  `tests/unit/infrastructure/startup/test_process_heap.py`,
  `tests/unit/infrastructure/mcp/test_tool_adapter.py`
  (`TestArgsSchemaIsBuiltOncePerSchema`)
- Outil : `apps/api/scripts/ops/worker_census.py` — le recensement par types et
  tailles, injecté par `sys.remote_exec` ; sa notice dit ce qu'il ne doit jamais
  faire
- Tests : `tests/unit/test_serve_launcher.py`,
  `tests/unit/test_lazy_heavy_imports_guard.py`,
  `tests/unit/domains/voice/test_sherpa_recognizer_cache.py`,
  `tests/unit/infrastructure/observability/test_process_memory.py`,
  `tests/unit/infrastructure/startup/test_worker_memory_sampler.py`,
  `tests/unit/test_postgres_memory_floor_guard.py`,
  `infrastructure/observability/prometheus/tests/alerts_core_test.yml`
