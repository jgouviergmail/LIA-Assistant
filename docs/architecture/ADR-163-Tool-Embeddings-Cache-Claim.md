# ADR-163: Un seul worker calcule les embeddings d'outils — revendication par fichier

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Complète**: [ADR-162](ADR-162-System-Knowledge-Indexation-Single-Writer.md) (mono-écrivain de l'indexation FAQ)

## Contexte

ADR-162 a donné un volume au cache d'embeddings d'outils. Le premier démarrage
après ce déploiement a révélé ce que le volume seul ne réglait pas.

### Ce qui a été mesuré (production, 2026-07-27T11:36:22Z)

Le volume était neuf, donc vide. Les quatre workers uvicorn ont tous manqué le
cache et ont tous embarqué **les mêmes 713 textes du catalogue en même temps** —
2 852 contenus. Le fournisseur a répondu un `429 RESOURCE_EXHAUSTED` d'une nature
différente de celle d'ADR-162 : « *Resource exhausted. Please try again later* »
avec un lien Vertex AI, soit une saturation de **capacité**, pas un dépassement de
quota nommé.

Le sélecteur d'outils n'a **aucun retry** — ADR-162 avait délibérément limité son
retry borné à l'indexeur FAQ — et son échec remonte hors du lifespan. Résultat
dans les journaux :

```
11:37:21  semantic_tool_selector_cache_miss   × 4
11:37:26  semantic_tool_selector_initialization_failed
11:37:26  Application startup failed. Exiting.
11:37:27  Application startup failed. Exiting.
11:37:35  semantic_tool_selector_initialized  (les 2 survivants)
11:37:52  semantic_tool_selector_cache_hit    (les 2 respawnés)
```

**Deux workers sur quatre sont morts.** Ils ne se sont pas dégradés : ils ont
quitté, uvicorn les a respawnés, et leurs remplaçants ont relu le cache que les
survivants venaient d'écrire — pids 51/54 à 5 min 21 d'ancienneté contre 188/189 à
4 min 33. Le service a tourné à deux workers pendant **~48 s**.

Ce rétablissement fonctionne **par accident** : il exige qu'au moins un worker
réussisse. Si les quatre avaient échoué ensemble, il n'y aurait eu aucun cache à
relire.

### La fenêtre d'exposition

Le cache persiste maintenant, donc un démarrage ordinaire fait quatre succès de
cache et zéro appel — vérifié au second déploiement (`cache_hit` 4, série `miss`
inexistante, zéro erreur). La rafale ne revient qu'au **premier démarrage après un
changement du catalogue d'outils**, ce qui change l'empreinte et invalide le cache.

## Décision

### 1. Supprimer la rafale, pas la subir

Sur un défaut de cache, un worker prend une revendication exclusive par
`os.open(lock, O_CREAT | O_EXCL)` : le système de fichiers désigne le gagnant. Les
autres attendent son résultat au lieu de le dupliquer.

Pourquoi ce mécanisme et pas un autre :

- **Ni Redis ni base.** Le sélecteur s'initialise dans `init_agent_registry` ; y
  introduire une dépendance de coordination pour une optimisation de démarrage
  serait un couplage disproportionné. Le verrou fonctionne entre processus qui ne
  partagent que le volume — exactement ce que sont quatre workers uvicorn.
- **Ni `flock`, ni `os.kill(pid, 0)`.** Les deux donneraient une détection de
  détenteur mort plus fine, au prix d'une branche par plateforme (le dépôt se
  développe sous Windows et tourne sous Linux). Le §4 explique pourquoi la
  précision supplémentaire n'en vaut pas le coût.

### 2. Rendre l'échec non fatal a été envisagé, mesuré, et rejeté

C'était la première proposition. Les compteurs de production la réfutent : `8
semantic_tool_selector_initialized` et `4 initialization_failed` — soit, à deux
émetteurs chacun, **4 réussites et 2 échecs**, et **4 workers finalement sains**.

Un worker qui survit avec un sélecteur non initialisé saute le scoring sémantique
pour **le reste de sa vie** : `router_node_v3` garde sur `is_initialized()`, les
scores restent vides, et la garde d'exclusion de `normal_filtering` étant fausse,
tous les outils du domaine partent au LLM sans classement. Un worker qui **quitte**
est respawné et revient pleinement fonctionnel.

Mourir est donc la meilleure dégradation ici. On aurait échangé 48 s
d'indisponibilité partielle contre une dégradation permanente.

### 3. Trois propriétés rendent la revendication sûre plutôt que maligne

- **Un détenteur mort ne peut pas bloquer un démarrage.** Une revendication trop
  vieille est volée : sans cela, un seul crash ferait attendre le délai complet à
  chaque démarrage suivant, puis embarquer quand même — pire que pas de
  coordination.
- **Un détenteur qui échoue passe la main.** La revendication est relâchée dans un
  `finally`, même quand l'appel lève. Les tentatives se **sérialisent** (713
  textes à la fois) au lieu de se paralléliser (2 852 d'un coup).
- **Perdre la coordination n'est jamais fatal.** Délai expiré ou verrou impossible
  ⇒ on calcule sans revendication, soit le comportement d'avant, et
  `result="miss_unclaimed"` le dit sur un tableau de bord.

### 4. Le seuil de péremption est découplé du délai d'attente

Les deux échouent en sens **opposés** : attendre trop peu coûte un calcul inutile,
juger périmée une revendication *vivante* fait calculer deux workers à la fois —
la rafale même. Une valeur unique était donc fausse : un délai court rendait tout
verrou instantanément périmé. La péremption vaut `max(délai, 30 s)`.

`_is_stale` compare une **mtime**, donc une horloge murale, sans source monotone
possible. Un saut NTP vers l'avant supérieur au TTL — ce qui arrive au démarrage
sur le Pi — peut faire passer une revendication vivante pour abandonnée. Ce qui
rend l'heuristique acceptable : **ses deux erreurs sont bornées par le
comportement d'avant**. Voler une revendication vivante ⇒ deux workers calculent,
ce que faisait chaque démarrage avant cet ADR. Ne pas voler une morte ⇒ attente
bornée puis calcul non revendiqué, soit le même comportement plus un délai. Aucune
des deux ne crée un mode de défaillance nouveau.

### 5. Le délai par défaut est dérivé du budget de santé, pas choisi au ressenti

Les attendeurs bloquent **dans le lifespan**, donc avant qu'uvicorn ne serve. Si le
détenteur est tué par SIGKILL, sa revendication est encore fraîche, donc non
volable, et les autres attendent le délai complet.

| Terme | Valeur mesurée |
|---|---|
| Tolérance du healthcheck | `start_period 60 s + 3 × interval 30 s` = **150 s** |
| Démarrage normal en prod | **~90 s** (conteneur 11:36:22 → workers prêts 11:37:35) |
| Budget d'attente restant | **~60 s** |
| Embedding d'un catalogue complet | **~14 s** (713 textes) |

Le défaut est **40 s** : ~3× la durée réelle, 20 s de marge sous le budget. Un
premier réglage à 90 s aurait mis le conteneur en `unhealthy` sur un démarrage
(90 + 90 = 163 s > 150 s) ; `restart: unless-stopped` ne redémarre pas sur
`unhealthy`, donc pas de boucle, mais un état alarmant inventé de toutes pièces.

La dissymétrie justifie d'errer court : un délai trop bref **dégrade** vers le
comportement d'avant, un délai trop long **invente** un état neuf.

### 6. Le concern a son module

`tool_embeddings_cache.py` porte la résolution du chemin, la lecture, l'écriture
atomique et la revendication. `tool_selector.py` **descend de 515 à 462** SLOC
logiques. Aucun cycle d'import ajouté.

## Conséquences

### Positives

- Le premier démarrage après un changement d'outil passe de **2 852 contenus
  simultanés à 713**, calculés par un seul worker.
- Aucun ralentissement au cas nominal : sur cache chaud, le verrou n'est même pas
  touché ; sur défaut, les perdants se réveillent dans les 0,5 s de l'écriture du
  gagnant, soit ~14,5 s contre ~14 s aujourd'hui.
- Quatre issues distinguées sur `tool_embeddings_cache_total{result}` :
  `hit`, `hit_after_wait`, `miss`, `miss_unclaimed`.

### Négatives / acceptées

- Un détenteur tué par SIGKILL coûte **jusqu'à 40 s** au démarrage courant (les
  autres attendent, puis calculent sans revendication). Le vol de verrou ne
  soigne que le démarrage *suivant*.
- L'heuristique de péremption reste sensible à l'horloge murale (§4), avec la
  borne qui la rend acceptable.
- **La preuve runtime manque.** Ce chemin ne s'exerce qu'au premier démarrage
  après un changement du catalogue d'outils ; le provoquer demanderait de vider le
  volume en production. Les journaux devront alors montrer un `cache_miss` avec
  `claimed=true`, trois `tool_embedding_cache_claim_waiting`, trois
  `hit_after_wait`, et zéro `Application startup failed`.

## Vérifications

| Propriété | Preuve |
|---|---|
| Cache servi ⇒ le verrou n'est pas touché | `test_a_served_cache_takes_no_claim_at_all` |
| Premier sur un défaut ⇒ prend la revendication | `test_the_first_worker_on_a_miss_takes_the_claim` |
| Second ⇒ attend et reçoit le résultat, n'embarque rien | `test_a_second_worker_waits_and_is_served_the_result` |
| **Volume neuf ⇒ revendication immédiate, aucune attente** | `test_a_fresh_volume_claims_immediately_instead_of_waiting` |
| Emplacement impossible ⇒ calcul immédiat, pas de sondage | `test_a_read_only_location_degrades_instead_of_waiting` |
| Revendication périmée volée | `test_a_stale_claim_is_stolen` |
| Revendication vivante **jamais** volée | `test_a_fresh_claim_is_never_stolen` |
| Relâchement ⇒ le suivant prend la main | `test_releasing_hands_the_claim_to_the_next_worker` |
| Échec de l'embedding ⇒ revendication relâchée, relais effectif | `test_released_when_the_embedding_call_fails` |
| Cache écrit entre la lecture et l'acquisition ⇒ utilisé, pas recalculé | `test_a_cache_written_between_the_read_and_the_claim_is_used` |
| Détenteur qui ne finit jamais ⇒ démarrage non bloqué | `test_a_holder_that_never_finishes_does_not_hang_the_boot` |
| Délai zéro ⇒ aucune attente (retour au comportement d'avant) | `test_a_zero_timeout_disables_waiting` |
| Écriture atomique, aucun préfixe observable, aucun résidu | `test_a_reader_never_observes_a_partial_document` et voisins |

28 tests dans `tests/unit/domains/agents/services/test_tool_embeddings_cache.py`,
plus le câblage dans `test_tool_selector_cache.py`.

## Références

- [ADR-162 — Indexation de la connaissance système, mono-écrivain](ADR-162-System-Knowledge-Indexation-Single-Writer.md)
- [ADR-089 — Métriques Prometheus multiprocess](ADR-089-Prometheus-Multiprocess-Metrics.md)
- Runbook voisin : [SystemKnowledgeIndexationFailing](../runbooks/alerts/SystemKnowledgeIndexationFailing.md)
