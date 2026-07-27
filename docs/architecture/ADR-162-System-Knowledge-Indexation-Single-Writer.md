# ADR-162: L'indexation de la connaissance système a un seul écrivain, et son cache survit au déploiement

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-058 (System RAG Spaces), ADR-089 (métriques multi-worker)
**Complète**: ADR-119 (socle d'alerting minimal)
**Amendé par**: [ADR-163](ADR-163-Tool-Embeddings-Cache-Claim.md) — donner un volume
au cache d'embeddings d'outils ne suffisait pas. Le premier démarrage sur ce volume
neuf a fait manquer le cache aux quatre workers **en même temps**, et le §4 de cet
ADR laissait cette rafale sans coordination : le fournisseur a répondu un 429 de
capacité et deux workers sont morts au démarrage. Depuis le 2026-07-27, un seul
worker calcule, revendication par fichier.

## Contexte

Deux classes d'erreur remontaient des journaux de production, sans lien apparent.
Elles avaient une cause commune : **rien ne coordonnait les quatre workers
uvicorn au démarrage**.

### Ce qui a été mesuré (2026-07-27, conteneur `lia-api-prod`)

`GoogleGenerativeAIError` — **19 minutes distinctes sur 8 jours**, 70 lignes, dont
69 sur le chemin d'indexation FAQ au démarrage et 1 sur une requête utilisateur.
Toujours le même refus :

```
429 RESOURCE_EXHAUSTED
quotaMetric : generativelanguage.googleapis.com/embed_content_paid_tier_requests
quotaId     : EmbedContentPerMinutePerProjectPerUserPerModel-PaidTier
quotaValue  : 3000   |  retryDelay : 39s
```

Le 429 tombait **+17 à +21 s après le début du démarrage**, sur les quatre
workers en 1 à 3 secondes, sur **11 démarrages sur 11** tracés par Loki en 4
jours. Cette régularité d'horloge disqualifiait la course marginale contre un
consommateur externe : la cause était déterministe et interne.

Le volume par démarrage, calculé sur les données réelles :

| Consommateur | Contenus / worker | Requêtes HTTP / worker |
|---|---|---|
| Sélecteur d'outils (1 appel, 713 textes) | 713 | 8 |
| Indexation FAQ (3 appels de 100/100/69) | 269 | 10 |
| **× 4 workers** | **3 928** | **72** |

Deux mécanismes indépendants produisaient ce volume, tous deux inutiles :

1. **Le cache d'embeddings d'outils ne survivait pas à un déploiement.** Il
   résolvait vers `/app/data/tool_embeddings_cache.json`, dans la couche
   inscriptible du conteneur, que `docker compose up -d --force-recreate`
   détruit. Sur 14 jours : **108 `cache_miss`, zéro `cache_hit`**, soit 27
   démarrages où chacun des 4 workers réembarquait les 713 textes du catalogue —
   pour une charge dont le `content_hash` était **identique** à celui du cache de
   développement daté de 4 jours plus tôt (`d86297a8c574…`).
2. **L'indexation FAQ n'avait aucun verrou.** Le contrôle de péremption lisait
   `space.content_hash` avant que quiconque n'ait commité, donc les 4 workers le
   passaient tous et réindexaient tous.

`PermissionError` — 12 lignes, 4 tentatives d'import de compétence, toutes
échouées. Cause distincte, traitée en v1.25.25 : le point de montage du volume
`skills_data` n'existait pas dans l'image, donc Docker l'avait fabriqué en
`root:root`. Cet ADR ne couvre pas ce défaut, il en reprend la garde
(`test_volume_mount_ownership_guard.py`) pour la durcir.

### Le dégât que personne ne voyait

L'entrelacement des quatre transactions `delete`-puis-`insert` laissait des
lignes derrière lui : chaque `DELETE` ne supprime que ce qui était visible à son
démarrage, donc les insertions d'un pair survivaient. État constaté en
production :

```
total_chunks | distinct_contents
         807 |               269      ← 3 copies de chaque réponse
3 documents « lia-faq.md »
```

`retrieval.py` trie par score puis tronque à `RAG_SPACES_RETRIEVAL_LIMIT` (5), et
des doublons exacts obtiennent un score identique. Le top-5 contenait donc
**2 réponses distinctes au lieu de 5** : la connaissance que LIA a d'elle-même
était dégradée d'un facteur ~2,5, sans qu'aucun test, aucune métrique et aucun
journal ne le dise.

Et l'échec était **mal classé**. L'exception s'échappait du bloc
`get_db_context`, qui journalisait `database_session_error` en ERROR avec une
trace complète sous `src.infrastructure.database.session`. 69 refus de quota
enregistrés comme des erreurs de base de données : quiconque instruisait le
problème commençait dans la mauvaise couche. Le seul signal juste était un
WARNING avalé par l'étape de démarrage.

## Décision

### 1. Un seul worker indexe — `FOR UPDATE SKIP LOCKED` sur la ligne du space

`RAGSpaceRepository.claim_system_space_for_reindex` prend le droit exclusif de
réindexer, ou décline immédiatement. `SKIP LOCKED` et non l'attente : sérialiser
quatre workers derrière un appel d'embedding de ~20 s ajouterait ce délai à
chaque démarrage. Les perdants retournent `skipped` avec
`reason="claimed_by_another_worker"`.

`execution_options(populate_existing=True)` n'est pas cosmétique : l'appelant a
**déjà lu** cette ligne au contrôle de péremption. Sans cela, SQLAlchemy rend
l'instance de sa *identity map* avec son `content_hash` périmé, et le perdant
d'une course réindexe par-dessus le travail du gagnant.

Pourquoi pas un verrou Redis (le pattern de `reindex.py`) : il découplerait « qui
travaille » de la transaction, au prix d'une dépendance supplémentaire au
démarrage et de deux mécanismes à maintenir. Le verrou de ligne est déjà la
doctrine du dépôt (`scheduled_actions/repository.py`), il est sûr au crash sans
TTL à calibrer, et le maintenir pendant l'embedding coûte un verrou sur **une**
ligne de `rag_spaces` que rien d'autre ne lit en écriture.

### 2. On embarque avant de détruire

Les vecteurs sont calculés **avant la première instruction destructrice**. Un
refus de quota ne coûte alors rien : aucune ligne supprimée, aucun verrou sur
`rag_chunks` tenu pendant un appel réseau, le corpus précédent toujours servi.
L'échange `delete`/`insert` qui suit est une transaction inférieure à la seconde.

Avant, l'embedding tournait *à l'intérieur* de la transaction destructrice, et
seul un `rollback` sauvait le corpus.

### 3. Le hash ne suffit pas — le corpus est compté

`_corpus_is_current` exige un hash concordant **et** `chunks == entrées parsées`
**et** `documents == 1`. C'est ce qui transforme le prochain démarrage en
réparation : la production portait le hash **correct** sur 807 chunks, donc un
contrôle par hash seul aurait figé le dégât pour de bon, longtemps après que la
concurrence qui l'a produit ait été corrigée. La vérification couvre aussi
l'inverse — une insertion morte à mi-course — tout aussi invisible à un hash.

Coût mesuré sur le Pi de production : **0,74 ms** (deux `COUNT`, seq scan sur
1 237 lignes), une fois par worker et par démarrage.

### 4. Le cache d'embeddings d'outils vit sur un volume, et son écriture est atomique

`TOOL_EMBEDDINGS_CACHE_DIR` est un réglage. Un chemin relatif est ancré sur la
racine applicative (`apps/api`, `/app` dans l'image) et **jamais** sur le
répertoire courant — c'est ce qui fait atterrir le cache au même endroit sous
pytest et sous l'image. La valeur par défaut `data/tool_cache` résout donc vers
`/app/data/tool_cache`, exactement le point de montage du volume
`tool_cache_data` : **la correction ne dépend d'aucune variable d'environnement à
poser**.

L'écriture passe par un fichier temporaire portant le pid, puis `os.replace`.
Les quatre workers écrivent le même chemin, et le document pèse des dizaines de
mégaoctets : un `write_text` laisse un lecteur observer un préfixe, dont la seule
issue est de tout réembarquer. Persister sans rendre l'écriture atomique aurait
transformé un dégât invisible en corruption durable.

### 5. Un retry borné, classé sur le code de statut

`google-genai` construit son client sans options de retry, ce qui sélectionne sa
stratégie « never retry » (`_api_client.py`: *« If None, the 'never retry' stop
strategy will be used »*). Un seul 429 transitoire coûtait donc un cycle de
péremption complet.

Le retry est borné par **deux** réglages — nombre de tentatives et budget total
de temps partagé par tous les lots — parce qu'il se déroule sous la revendication
de la ligne. Il ne vit **que** sur ce chemin de démarrage : un utilisateur qui
attend une réponse de chat ne doit pas patienter le temps d'une fenêtre de quota.

La classification est **structurelle** : le code de statut porté par la chaîne
`__cause__` (`google.genai.errors.APIError.code`), plus les échecs de transport.
Jamais une correspondance de texte dans un message d'exception — c'est ainsi
qu'un changement de formulation chez un fournisseur transforme silencieusement un
retry en échec définitif.

L'exception d'origine est **relevée telle quelle**, pas enveloppée : son code de
statut est le diagnostic. C'est pourquoi `retry_with_backoff`
(`infrastructure/utils/retry.py`) n'a pas été réutilisé — il classe par type
d'exception, n'a pas de budget partagé, et remplace l'erreur par
`MaxRetriesExceededError`.

### 6. L'échec est observable et alertable

- L'échec est capturé **dans** le contexte de session : plus de
  `database_session_error` attribué à tort à la base de données. Un ERREUR du
  domaine, un WARNING du démarrage, fin de l'histoire.
- `tool_embeddings_cache_total{result}` rend visible la classe de défaut qui
  s'était cachée 27 démarrages durant.
- `SystemKnowledgeIndexationFailing` rejoint le socle d'alerting (ADR-119), en
  `warning` avec son runbook. Deux échecs en six heures, pas un : un refus
  transitoire se soigne désormais au démarrage suivant, et le corpus qui sert
  entre-temps est le précédent, intact.

### 7. La course à la création est adoptée, pas signalée

Sur une base neuve, les quatre workers créent le space. L'index unique partiel
`uq_rag_spaces_system_name` en laisse passer un ; les autres adoptent sa ligne au
lieu de journaliser un échec. Le résultat est **relu** plutôt que déduit du code
de statut : si le space n'existe toujours pas, l'échec était réel et doit
remonter.

## Conséquences

### Positives

- Volume d'embedding au démarrage : **3 928 → 269 contenus**, **72 → 10
  requêtes** (÷14,6 et ÷7,2). Sous n'importe quel modèle de comptage du quota, la
  marge devient large.
- Le corpus dupliqué de production se répare au prochain démarrage, sans geste
  manuel.
- La qualité de récupération sur la FAQ système retrouve 5 réponses distinctes
  sur 5.
- Un échec d'indexation cesse d'être invisible.

### Négatives / acceptées

- Le premier démarrage après un changement du catalogue d'outils réembarque
  encore 713 textes **par worker** : ils ne partagent pas le calcul, seulement
  son résultat sur disque. Acceptable — une fois par changement d'outil au lieu
  d'une fois par déploiement. Une revendication étendue au cache pourrait le
  réduire à un worker ; non fait, faute de bénéfice mesurable.
- Le retry est tenu sous la revendication de la ligne, donc le budget de temps
  borne aussi la durée de ce verrou. Documenté dans la description du réglage.
- Deux `COUNT` par worker et par démarrage. Mesurés à 0,74 ms en production.
- L'unité de comptage du quota Gemini (contenus ou requêtes HTTP) reste
  **non établie** : la page publique de Google ne documente ni les RPM par palier
  pour les modèles d'embedding, ni la règle de comptage des lots. La correction a
  donc été calibrée pour supprimer la redondance *entièrement* plutôt que pour
  repasser juste sous un seuil supposé.

## Vérifications

| Propriété | Preuve |
|---|---|
| Une seule transaction indexe, les autres déclinent sans attendre | `tests/integration/domains/rag_spaces/test_system_index_single_writer.py::TestTheClaimItself` |
| La revendication recharge la ligne qu'elle verrouille | idem, `test_the_claim_reloads_the_row_it_locks` |
| 2 puis 4 workers concurrents ⇒ un seul corpus | idem, `TestConcurrentIndexations` |
| **Sans la revendication, la duplication revient** | idem, `TestFalsification` |
| Un corpus dupliqué à hash correct est réparé | idem, `TestRepairOfADivergedCorpus` |
| On embarque avant de détruire | `tests/unit/domains/rag_spaces/test_system_indexer_single_writer.py::TestEmbedBeforeDestroy` |
| Retry borné en tentatives et en temps, erreur d'origine préservée | idem, `TestBoundedRetry` |
| Classification sur le statut, chaîne `__cause__`, chaîne cyclique | idem, `TestRetryReason` |
| Écriture du cache atomique, aucun préfixe observable | `tests/unit/domains/agents/services/test_tool_selector_cache.py::test_a_reader_never_observes_a_partial_document` |
| Chemin du cache indépendant du répertoire courant | idem, `test_relative_path_ignores_the_working_directory` |
| Hit/miss du cache mesurés de bout en bout | idem, `TestCacheOutcomeIsMeasured` |
| L'échec ne bloque jamais le démarrage, ni ne salit la couche base | `tests/unit/infrastructure/startup/test_integrations_system_rag.py` |
| Tout volume nommé est créé **et** chowné avant le `USER` | `tests/unit/test_volume_mount_ownership_guard.py` (6 falsifications) |
| L'alerte tire à deux échecs, pas à un | `infrastructure/observability/prometheus/tests/alerts_core_test.yml` (promtool) |

## Références

- [ADR-058 — System RAG Spaces](ADR-058-System-RAG-Spaces.md)
- [ADR-089 — Prometheus multiprocess](ADR-089-Prometheus-Multiprocess-Metrics.md)
- [ADR-119 — Socle d'alerting minimal](ADR-119-Alerting-Reactivation-Minimal-Core.md)
- [ADR-150 — Continuité générationnelle RAG](ADR-150-RAG-Generational-Continuity.md)
- Runbook : [SystemKnowledgeIndexationFailing](../runbooks/alerts/SystemKnowledgeIndexationFailing.md)
