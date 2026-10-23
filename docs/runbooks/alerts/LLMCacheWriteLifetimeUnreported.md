# LLMCacheWriteLifetimeUnreported — Runbook

**Sévérité** : warning
**Composant** : agents
**Impact** : une réponse Claude reçue en flux a écrit dans le cache de prompt
**sans dire quelle part de ces écritures valait une heure**. Toutes ses
écritures ont donc été facturées au tarif de cinq minutes (1,25× l'entrée) : une
écriture d'une heure (2×) est sous-facturée de 0,75× le prix d'entrée dans
`token_usage_logs`, dans `message_token_summary`, dans les statistiques de la
personne et dans les plafonds de dépense (compte et instance). C'est un coût que
la plateforme paie et que le registre enregistre trop bas.

---

## Définition

```promql
sum by (model) (increase(llm_cache_write_breakdown_missing_total[1h])) > 0
```

Le seuil zéro est volontaire. Le compteur est incrémenté par le crochet de flux
(`apps/api/src/infrastructure/llm/providers/anthropic_hooks.py`,
`with_stream_write_breakdown`) quand le début d'une réponse en flux
(`message_start`) annonce des écritures (`cache_creation_input_tokens > 0`) sans
leur ventilation par durée (`cache_creation`) ; le même événement produit un log
`llm_cache_write_breakdown_missing` en WARNING, avec le modèle et le nombre de
jetons écrits. Une réponse qui n'écrit rien n'est pas comptée. L'auto-diagnostic
joint à l'incident ces deux séries et ce log (recette `LLMCacheWriteLifetimeUnreported`,
ADR-266).

### Pourquoi cette alerte existe

Claude ne dit quelles écritures valent une heure qu'au DÉBUT d'un flux ; la fin
du flux, d'où `langchain-anthropic` lit l'usage, ne porte que leur total
(mesuré le 2026-10-22, `MessageDeltaUsage` sans `cache_creation` dans anthropic
0.122.0). Le crochet recopie la ventilation du début dans l'usage du flux, sans
quoi chaque écriture d'une heure de la boucle ReAct — qui diffuse en flux —
serait facturée au tarif de cinq minutes (ADR-362). Les tests de contrat
(`apps/api/tests/unit/infrastructure/llm/providers/test_anthropic_hooks.py`)
attrapent en CI un client qui changerait de forme ; cette alerte attrape ce
qu'aucun test ne voit : un flux que le fournisseur aurait changé côté serveur.

---

## Diagnostic

### 1. Quel modèle, quel volume ?

```promql
sum by (model) (increase(llm_cache_write_breakdown_missing_total[24h]))
```

Rapprocher du volume d'écritures du même modèle sur la même période
(tableau de bord 05, rangée « Prompt-cache writes by lifetime (ADR-362) ») :

```promql
sum by (lifetime) (increase(llm_cache_write_tokens_total{model="<modèle>"}[24h]))
```

Une part `extended` tombée à zéro alors que des tours fréquents ont eu lieu
confirme que la ventilation ne parvient plus. Les journaux nomment chaque
réponse concernée :

```bash
docker logs lia-api-prod 2>&1 | grep llm_cache_write_breakdown_missing
```

### 2. Le flux a-t-il changé de forme ?

- Une montée de version de `anthropic` ou de `langchain-anthropic` est-elle
  passée depuis le dernier déploiement ? Si oui, relancer les tests de contrat
  ci-dessus contre la version installée.
- Sinon, le fournisseur a changé son flux. Le confirmer par une mesure
  (PAYANTE, budget validé d'abord) : `task llm:cache:probe -- --budget 0.2`
  sur dev ; l'hypothèse H2 de son rapport montre les clés de l'usage au début
  et à la fin du flux.

### 3. Le montant sous-facturé

Il n'est pas récupérable ligne à ligne (la ventilation n'a pas été reçue). Il est
borné par 0,75 × le prix d'entrée du modèle × les écritures comptées `short`
pendant la période, puisque toute écriture d'une heure y a été rangée.

---

## Résolution

1. Adapter le crochet de flux à la nouvelle forme (là où le fournisseur place
   désormais la ventilation), avec un test de contrat qui pilote le vrai client.
2. Vérifier que le lecteur unique (`apps/api/src/infrastructure/llm/usage_metadata.py`,
   `_cache_writes`) lit la nouvelle source et ne compte rien deux fois : il
   prend la plus grande des sources qui décrivent les mêmes écritures.
3. En attendant le correctif, `PROMPT_CACHE_EXTENDED_TTL_ENABLED=false` (lu au
   démarrage : redémarrer l'API) ramène toutes les écritures à cinq minutes :
   plus rien n'est sous-facturé, au prix des relectures d'un tour à l'autre
   au-delà de cinq minutes.

---

## Références

- ADR-362 — le cache de prompt de Claude d'un tour à l'autre
- `docs/runbooks/alerts/LLMCallsWithoutUsage.md` — la même famille, pour un
  appel dont l'usage manque entièrement
- `apps/api/src/infrastructure/llm/providers/anthropic_hooks.py` — le crochet
- `apps/api/src/infrastructure/cache/pricing_cache.py` —
  `cache_write_extended_multiplier`
