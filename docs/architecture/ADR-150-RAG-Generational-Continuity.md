# ADR-150 : Continuité générationnelle de la recherche RAG pendant une réindexation

**Status**: ✅ IMPLEMENTED (2026-07-25)
**Date**: 2026-07-25
**Deciders**: jgouvier + Claude
**Technical Story**: Audit qualité 2026-07-24 (constat AC-001). `retrieval.py` lisait un flag Redis global `rag_reindex_in_progress` et retournait `None` pour **toutes** les recherches sur espaces utilisateur pendant une réindexation. Un changement de modèle d'embedding (opération admin) suspendait donc globalement la recherche documentaire — la seule fonctionnalité utilisateur affectée directement par la maintenance.

## Contexte mesuré

La réindexation (`start_reindexation`, déclenchée après un changement de `RAG_SPACES_EMBEDDING_MODEL`) rejoue chaque document via `process_document`, dont l'échange de chunks est **atomique par document** : `delete_by_document` puis `bulk_create_chunks` dans une transaction ([processing.py](../../apps/api/src/domains/rag_spaces/processing.py)). Un document reprocessé n'a donc, à tout instant, **que** ses chunks de la nouvelle génération.

Conséquence décisive : un simple filtre « ne servir que l'ancienne génération » ne suffit pas — chaque document reprocessé **disparaîtrait** (ses anciens chunks supprimés, ses nouveaux filtrés), créant une fenêtre vide progressive. Le blocage global évitait cela au prix de l'indisponibilité totale.

Deux invariants pgvector cadrent la solution :
- `RAGChunk` n'a **aucune contrainte d'unicité** sur `(document_id, chunk_index)` — deux générations coexistent sans conflit de lignes.
- Une colonne `vector(N)` a une dimensionnalité **fixe** : deux générations de dimensions différentes ne peuvent pas cohabiter dans la même colonne.

## Decision

**Générations côte-à-côte pilotées par un pointeur de service durable par espace** (continuité pleine, même dimension) :

- **Colonne durable `rag_spaces.serving_embedding_model`** ([migration `c1d2e3f4a5b6`](../../apps/api/alembic/versions/2026_07_25_0700-c1d2e3f4a5b6_add_rag_space_serving_model.py)) — `NULL` = génération unique, servir tous les chunks (régime permanent, rétro-compatible sans backfill). Non-`NULL` = génération à embedder les requêtes ET filtrer les chunks. C'est le point de bascule atomique.
- **Build côte-à-côte** — au démarrage, `start_reindexation` **épingle** les espaces concernés sur l'ANCIEN modèle **dans la même transaction atomique** que le requeue durable (F001/V8). `process_document` lit ce pointeur : quand `serving != cible`, il ne supprime **que** la génération cible (`delete_by_document_and_model`), préservant la génération servie. La décision est portée par l'état durable, donc le **drain ET le reaper** se comportent correctement sans threading de paramètre.
- **Bascule atomique par espace** — après le drain, chaque espace dont tous les documents sont `READY` sur le nouveau modèle est basculé en **une transaction** : pointeur remis à `NULL` + suppression des chunks de l'ancienne génération. Un lecteur concurrent voit soit l'ancienne génération (pleinement servie), soit la nouvelle — **jamais un mélange ni une fenêtre vide**.
- **Résumable après crash** — le pointeur épinglé survit ; l'ancienne génération n'est jamais supprimée avant la bascule. Le reaper RAG rebâtit les documents requeués (côte-à-côte, car `serving` reste l'ancien) puis `flip_pinned_spaces_if_ready` déclenche la bascule que le drain interrompu n'a pas atteinte. « Échec → on garde N » : un document définitivement en échec laisse son espace épinglé sur la génération stable, pleinement servie.
- **Retrieval générationnel** — `retrieve_rag_context` groupe les espaces actifs par génération servie (≤ 2), embed la requête **avec le modèle de chaque génération** (`embed_rag_query_cached(query, model=…)` + cache de clients per-modèle) et filtre les chunks à cette génération, puis fusionne. En régime permanent (`serving=NULL` partout) : un seul groupe, sans filtre — **exactement le chemin historique**.

**Invisibilité temporaire assumée pour les uploads pendant la migration** (arbitrage produit) : un document uploadé pendant la fenêtre est embeddé avec le NOUVEAU modèle (singleton déjà basculé) donc invisible sous `serving=ancien` jusqu'à la bascule — propriété élégante : il est **déjà** dans la génération cible, aucun retraitement au flip. Observable via le statut de réindexation ; jamais un résultat faux.

**Changement de DIMENSION = fenêtre de maintenance documentée** (AC-001b, décision explicite) : deux dimensions ne cohabitant pas dans une colonne pgvector, le chemin destructif historique (`_alter_vector_dimensions_if_needed` : purge des chunks + `ALTER` + rebuild de l'index HNSW, le tout durable et résumable via le requeue `PENDING`) est **conservé**. La continuité côte-à-côte ne s'active que si `current_dims == new_dims`. Un changement de dimension est donc une opération de maintenance rare, à planifier hors des heures de forte activité — voir le runbook RAG.

## Consequences

- **Disponibilité** : la recherche utilisateur reste servie pendant un changement de modèle même-dimension (le cas courant). Plus de blocage global.
- **Intégrité** : aucune génération n'est purgée avant que son remplaçant soit prêt (règle systémique CLAUDE.md respectée). Bascule atomique, résumable après crash — prouvé par 8 tests d'intégration PostgreSQL réels ([test_reindex_generational.py](../../apps/api/tests/integration/domains/rag_spaces/test_reindex_generational.py)) couvrant : lecture pendant build (pas de fenêtre vide, pas de mélange), bascule + reclaim, flip différé sur échec, reprise reaper, primitives repository.
- **Coût** : `process_document` lit le pointeur de l'espace par document (lookup PK indexé, négligeable). Un `Counter` `rag_reindex_space_flips_total{outcome}` rend les bascules observables.
- **Périmètre non couvert** : changement de dimension (fenêtre de maintenance, ci-dessus) ; le système d'espaces reste indexé séparément (SystemSpaceIndexer, non concerné).
