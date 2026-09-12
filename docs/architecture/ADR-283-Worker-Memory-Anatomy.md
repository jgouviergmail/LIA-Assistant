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
   dans un `try` de module. PyMuPDF passe par un accesseur `_fitz()`.
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
- Le démonstrateur n'est pas dans le garde du plancher : sans `shared_buffers`
  explicite (128 Mo) et avec 3 × 12 backends, son plancher fait 37 % de son
  `mem_limit` de 1 Gio — sain, et documenté ici plutôt que gardé par un second
  lecteur de compose.
- Un `docker cp` vers `/tmp` d'un conteneur (tmpfs) écrit SOUS le montage :
  une sonde se passe par `docker exec -i … python -` (stdin).

## Références

- Runbook : `docs/runbooks/alerts/ApiWorkerMemoryHigh.md`
- Tests : `tests/unit/test_serve_launcher.py`,
  `tests/unit/test_lazy_heavy_imports_guard.py`,
  `tests/unit/domains/voice/test_sherpa_recognizer_cache.py`,
  `tests/unit/infrastructure/observability/test_process_memory.py`,
  `tests/unit/infrastructure/startup/test_worker_memory_sampler.py`,
  `tests/unit/test_postgres_memory_floor_guard.py`,
  `infrastructure/observability/prometheus/tests/alerts_core_test.yml`
