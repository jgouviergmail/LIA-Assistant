# ADR-168: Suppression de la recherche hybride mémoire, morte depuis v1.14.0

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Supersede**: [ADR-037](./ADR-037-Semantic-Memory-Store.md) (partie recherche hybride)

## Contexte

`infrastructure/store/semantic_store.py` (421 lignes) exposait une recherche
hybride mémoire combinant BM25 et pgvector, plus les primitives
`StoreNamespace`, `MemoryNamespace`, `search_semantic`, `compute_emotional_state`.

Recherche exhaustive au 2026-07-27 sur `apps/api/src` **et** `apps/api/tests` :
`search_hybrid` n'apparaît que dans son propre module et dans le
`__init__.py` qui le réexporte. **Aucun appelant.** Idem pour tous les autres
symboles exportés. Le rapport de couverture le confirmait sans ambiguïté :
**21 %** de couverture, 100 lignes sur 127 jamais atteintes, alors que le module
est importé au démarrage.

Cause : la mémoire long terme a migré vers un modèle PostgreSQL/pgvector dédié
en v1.14.0 (`domains/memories/`). Le chemin de recherche a suivi
(`search_by_relevance`, multi-vecteurs contenu + mots-clés), le chemin hybride
non. `compute_emotional_state` a été **dupliqué** dans
`domains/memories/emotional_state.py` — la copie vivante — sans que l'original
soit retiré.

Trois conséquences, toutes vérifiées :

1. **421 lignes de code mort** importées à chaque démarrage.
2. **Quatre réglages orphelins** (`MEMORY_HYBRID_ENABLED`, `_ALPHA`,
   `_MIN_SCORE`, `_BOOST_THRESHOLD`) présents dans `Settings`, dans
   `.env.example` **et** `.env.prod.example`, plus deux métriques Prometheus
   sans émetteur.
3. **Une affirmation fausse faite à l'utilisateur** : `app_identity_prompt.txt`
   annonçait « Long-term memory with hybrid search (BM25 + semantic) ». LIA
   décrivait une capacité qu'elle n'avait plus. La même affirmation vivait dans
   quatre documents et dans le panneau de debug, qui affichait un témoin
   « hybrid: ON/OFF » figé sur OFF.

## Décision

Supprimer le module, ses réglages, ses métriques et ses affirmations.

**Risque runtime : nul, et prouvé** — `MEMORY_HYBRID_ENABLED=false` figurait
déjà dans les deux fichiers `.env` de référence. Le chemin était donc inactif
partout avant la suppression.

Périmètre exact :

| Surface | Action |
|---|---|
| `infrastructure/store/semantic_store.py` | supprimé (421 lignes) |
| `infrastructure/store/__init__.py` | réduit aux exports BM25 ; docstring corrigée (elle décrivait `AsyncPostgresStore`, abandonné) |
| `core/config/agents.py` | 4 champs + 3 imports retirés ; `memory_bm25_cache_max_users` **conservé** (consommé par `bm25_index.py`) |
| `core/constants.py` | 3 constantes retirées ; `MEMORY_BM25_CACHE_MAX_USERS_DEFAULT` conservée |
| `.env.example`, `.env.prod.example` | 4 lignes chacune |
| `observability/metrics.py` | 2 métriques sans émetteur retirées ; le cache BM25 conservé |
| `services/response_context.py` | `hybrid_enabled` retiré du payload de debug |
| `types/chat.ts`, `MemoryInjectionSection.tsx` | champ et témoin ON/OFF retirés |
| `prompts/v1/app_identity_prompt.txt` | « hybrid search (BM25 + semantic) » → « multi-vector semantic search (content + keyword embeddings) » |
| `GETTING_STARTED.md` | ligne de variable retirée |
| `HYBRID_SEARCH.md`, `ARCHITECTURE.md`, `LONG_TERM_MEMORY.md`, `INDEX.md` | bandeau/annotation « historique », corps conservé comme trace de conception |

**Ce qui reste vivant et ne doit pas être confondu :**

- `infrastructure/store/bm25_index.py` — consommé par
  `domains/rag_spaces/retrieval.py`. La recherche hybride des **RAG Spaces**
  fonctionne, c'est celle des **mémoires** qui était morte.
- `v3_tool_selector_hybrid_enabled` — homonyme sans rapport, réglage du
  sélecteur sémantique d'outils, bien actif.

## Conséquences

**Positives**
- Le prompt d'identité décrit à nouveau une capacité réelle.
- Un réglage documenté dans deux `.env` ne pilote plus rien d'inexistant.
- La couverture cesse d'être diluée par un module jamais exercé.

**Négatives / limites assumées**
- Un rétablissement futur de la recherche hybride mémoire repartirait de zéro.
  Le corps de `HYBRID_SEARCH.md` est conservé pour cela : le scoring, la
  formule de fusion et le calibrage y restent lisibles.
- `ADR-037` reste en place comme trace historique ; sa section hybride est
  désormais superseded.

## Alternatives écartées

- **Réactiver le chemin** plutôt que le supprimer. Il aurait fallu le rebrancher
  sur le modèle `Memory` actuel (`search_hybrid` parle encore de
  `AsyncPostgresStore` et de namespaces), le retester et le calibrer — pour un
  gain de rappel non mesuré sur la population réelle. Rien ne justifiait cet
  investissement maintenant ; si le besoin revient, il repartira d'une mesure.
- **Garder le module « au cas où »**. C'est exactement la posture que la
  doctrine interdit : un sous-système non branché coûte à chaque changement et
  fausse la couverture.
- **Corriger seulement le prompt.** Aurait supprimé le mensonge en laissant la
  cause : quatre réglages, deux métriques et 421 lignes continuant à suggérer
  qu'un chemin existe.

## Références

- Suppression : `apps/api/src/infrastructure/store/`
- Chemin vivant des mémoires : `domains/memories/repository.py::search_by_relevance`
- Chemin vivant du BM25 : `domains/rag_spaces/retrieval.py`
- ADR d'origine : [ADR-037](./ADR-037-Semantic-Memory-Store.md)
