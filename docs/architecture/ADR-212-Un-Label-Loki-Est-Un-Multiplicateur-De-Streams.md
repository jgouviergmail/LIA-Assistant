# ADR-212 : un label Loki est un multiplicateur de streams, pas un champ de recherche

**Statut** : ✅ IMPLEMENTED (2026-08-05)
**Contexte** : audit des logs de production API sur 7 jours (2026-07-29 → 2026-08-05)

## Contexte

Le pipeline Promtail promouvait en **labels indexés** tout ce qui semblait utile à
la recherche : `event`, `logger`, `trace_id`, `node_name`, `intention`,
`error_type`. Or les streams Loki sont le **produit cartésien des valeurs de
labels** : promouvoir un champ dont l'ensemble de valeurs est ouvert n'est pas
« plus cherchable », c'est un OOM différé.

Mesuré sur l'instance de production le 2026-08-05 :

```
/loki/api/v1/label/event/values     -> 1416 valeurs distinctes
/loki/api/v1/label/logger/values    ->  140
/loki/api/v1/label/trace_id/values  ->  107   (une par requête : non borné)
loki_ingester_memory_streams         ->  771, en croissance
```

avec **quatre OOM kernel du conteneur Loki** sur la semaine auditée — dont deux
déclenchés par une seule requête de 7 jours. L'outil s'effondrait au moment
précis où l'on en avait besoin.

Un second défaut aggravait la lecture. Le stage `output: source: message`
**remplace la ligne** par le contenu d'un champ : toute entrée structlog portant
une clé `message` arrivait dans Loki dépouillée de son JSON. L'audit les a
d'abord prises pour des `print()` égarés dans le code — c'était un artefact de
transport.

## Décision

**Un champ ne devient un label que si son ensemble de valeurs est petit et
fermé. Tout le reste se filtre à la lecture.**

1. Seul `level` (4 valeurs) est promu depuis le payload, plus les labels
   statiques et ceux dérivés du relabeling Docker (`container`, `environment`,
   `service`, `project`, `job`).
2. Les champs démis restent **entièrement interrogeables**, sans créer de
   stream :
   `{container="lia-api-prod"} |= "chat_run_started" | json | event="chat_run_started"`.
   Le filtre de ligne `|=` précède le parsing pour que Loki saute les chunks sans
   rien analyser.
3. **Aucun stage `output`** : un pipeline ne détruit pas la charge utile qu'il
   transporte.
4. Le stage `json` n'extrait que ce que les stages suivants consomment
   (horodatage, niveau) : extraire quinze champs pour n'en promouvoir aucun
   coûtait du CPU par ligne sur le Pi sans rien apporter.

## Conséquences

- Les requêtes de tableau de bord qui **sélectionnaient** sur ces champs devaient
  migrer. Sur 15 sélecteurs inventoriés, 11 étaient des métriques Prometheus
  (non concernées) et 4 requêtes Loki ont été réécrites.
- Le mode de défaillance évité est le pire pour un tableau de bord : un sélecteur
  portant un non-label **n'échoue pas**, il ne correspond à aucun stream — le
  panneau reste vide en ayant l'air sain.
- Filtrer à la lecture coûte du parsing par requête. C'est le compromis
  volontaire : payer à la requête plutôt qu'à l'ingestion, où le coût est
  permanent et partagé.

## Preuves

- `apps/api/tests/unit/test_promtail_label_cardinality_guard.py` — les champs à
  forte cardinalité ne sont pas des labels, tout label promu figure sur une
  liste explicite, aucun stage `output` ne réécrit la ligne, et une classe
  vérifie que **les tableaux de bord n'interrogent que ce que le pipeline indexe
  réellement** : l'ensemble interdit y est **dérivé** de la config Promtail, donc
  les deux ne peuvent plus diverger.
- Vérification runtime en dev après redémarrage : les nouveaux streams ne
  portent que `container/environment/job/level/project/service`, et les lignes
  récupérées commencent bien par `{` — le JSON survit.

## Écartés

- **Augmenter la mémoire de Loki** : traite le symptôme ; la cardinalité de
  `trace_id` croît sans borne, aucune limite ne suffirait.
- **Garder `logger` comme label** (140 valeurs, « raisonnable ») : il croît avec
  chaque module, et se combine multiplicativement aux autres.
- **Conserver `output` en ciblant un autre champ** : le défaut n'est pas le champ
  choisi, c'est le principe de remplacer la ligne.
