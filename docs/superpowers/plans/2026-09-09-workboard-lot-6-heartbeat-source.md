# Lot 6 — la source heartbeat `WORKBOARD` (ADR-276 D14, spec §9)

> Vérifié et challengé le 2026-09-09, chaque contrainte MESURÉE avant d'être
> écrite. Rien ici n'est déduit d'une lecture : les chiffres viennent des
> compteurs du dépôt, lancés avec l'interpréteur du projet.

## 1. Ce que la spécification demande

`fetch_workboard_context`, sur le patron des boucles ouvertes : les tickets du
tableau de la personne qui sont **en retard**, **dus dans
`workboard_nudge_due_hours`**, ou **en `waiting` depuis plus de
`workboard_nudge_waiting_hours`**, hors d'un refroidissement par ticket
(`workboard_nudge_cooldown_days`), plafonné. Câblage : le libellé de source, le
n-uplet de l'agrégateur, les listes de politique, la table de domaines de la
surface de consultation (`workboard` vers `ticket`), la section de prompt, et
`_bump_used_workboard` après une notification DÉLIVRÉE qui a utilisé la source.

## 2. Analyse systémique — ce qui est déjà là, et ce qui bloque

### Déjà livré par les lots précédents (vérifié)

| Pièce | État |
|---|---|
| `workboard_tickets.last_nudged_at` + `nudge_count` | colonnes présentes (lot 1) |
| `workboard_nudge_due_hours` / `_waiting_hours` / `_cooldown_days` | réglages présents (lot 1) |
| `ticket` dans `TREATMENT_DOMAIN_LABELS` ×6 | présent (lot 3), libellé français corrigé le 2026-09-09 |
| `WorkboardRepository.visible_predicate` | la porte de visibilité à réutiliser |

Il ne manque donc **ni migration, ni colonne, ni table**. Ce lot est du câblage
et une requête.

### Le blocage réel, mesuré

`src/domains/heartbeat/context_aggregator.py` est un fichier **GELÉ** par le
ratchet de taille :

| Mesure | Valeur |
|---|---|
| SLOC logique actuel | 700 |
| Plafond gelé (audit +2 %) | 705 |
| Marge | 5 lignes |

Or ajouter une source coûte au minimum : 1 ligne d'import, 1 ligne dans le
n-uplet `specs`, 3 lignes dans la chaîne `elif` de `_apply_source_result`. **La
mise en œuvre naïve fait rougir le ratchet.**

Et `_apply_source_result` porte une **complexité cyclomatique de 35**. Le
ratchet CC ne rougirait pas — il compte les fonctions au-dessus de 15, où elle
est déjà, et le maximum du dépôt, qui est 81 — mais la règle écrite est plus
stricte que la garde : « ne pas faire croître un point chaud existant ». Passer
de 35 à 36 viole la règle sans que rien ne l'arrête. **Une garde qui ne voit pas
une règle ne la supprime pas.**

### Le cycle d'imports : vérifié, il n'y en a pas

`heartbeat` importerait `workboard`. Contre-vérification faite dans les deux
sens : `workboard` importe `peers`, `users`, `shared`, `chat` et
`conversations` — et **aucun de ces cinq n'importe `heartbeat`** (compté : zéro
occurrence chacun). L'arête est donc nouvelle mais acyclique. Elle sera
**prouvée** par le ratchet de couplage plutôt que supposée :
`test_coupling_cycles_ratchet_guard` tourne avant et après.

### Ce que le lot doit AJOUTER côté réglages

Un plafond d'entrées n'existe pas : `workboard_max_tickets_per_user` vaut 2 000,
ce qui n'est pas un nombre de lignes qu'on met dans un prompt.
**`workboard_nudge_max_items`** est à créer (constante + réglage +
`.env.example` + `.env.prod.example`), pour la raison d'ADR-184 : ce que le
système applique, son producteur doit pouvoir le lire.

## 3. Plan d'action

### Tâche 0 (préalable, et c'est une amélioration) — remplacer la chaîne `elif` par une table

`_apply_source_result` est une **table de correspondance écrite en branches** :
quatorze fois « si le nom est X, poser le résultat sur l'attribut Y et ajouter X
aux sources disponibles ». La forme correcte est celle que le dépôt impose
partout ailleurs (`DOMAIN_REGISTRY`, `HEARTBEAT_SOURCE_KEYS`) : **une table,
plus un assert de complétude au démarrage** — doctrine ADR-085, l'application
refuse de démarrer sur une entrée manquante.

Effet attendu, à mesurer et non à espérer :

| Grandeur | Avant | Attendu |
|---|---|---|
| CC de `_apply_source_result` | 35 | environ 5 |
| Fonctions au-dessus de CC 15 (`over` du ratchet) | 329 | 328 |
| SLOC de `context_aggregator.py` | 700 | environ 670 |

Les trois gains sont indépendants et chacun débloque quelque chose : la place
pour la source, le respect de la règle du point chaud, et **un ratchet qu'on
peut abaisser** (`over` de 329 à 328), ce qui est la seule façon honnête de
resserrer un ratchet — en le méritant.

Les branches qui ne sont PAS de simples affectations — la météo, qui pose trois
attributs, et les fenêtres d'anti-redondance — restent explicites : une table
qui ment sur une entrée est pire qu'une branche.

**Tests d'abord** : un test de caractérisation qui compare, pour les quatorze
sources, l'état de `HeartbeatContext` produit par l'ancienne et la nouvelle
forme — capturé AVANT l'extraction, comme le fichier d'or d'ADR-269.

### Tâche 1 — `fetch_workboard_context`

Dans `heartbeat/context_sources.py` (406 SLOC, 194 de marge : aucun souci).

- Court-circuit si `workboard_enabled` est faux — le patron des boucles
  ouvertes, et le seul comportement qui ne fait pas payer une requête à une
  personne qui a coupé la fonctionnalité.
- **La requête vit dans le repository du tableau**, jamais dans le heartbeat :
  `WorkboardRepository.list_nudge_worthy(...)`. Elle réutilise
  `visible_predicate` — le tableau de la personne, propriétaire OU détenteur —
  et **exclut les colonnes closes** (`done`, `cancelled`) ainsi que `idea`,
  jamais exécutée et jamais réclamée.
- Trois motifs, un par ligne, **nommés dans l'entrée** (`reason`) : `overdue`,
  `due_soon`, `waiting`. Un motif nommé est ce qui permet au prompt de dire
  pourquoi, plutôt que de le deviner.
- Les dates sont rendues dans **le fuseau de la personne** (`resolve_user_tz`,
  `format_utc_datetime`), comme les boucles ouvertes.
- L'entrée porte l'`id` du ticket : c'est ce que le bump consomme.
- Plafond `workboard_nudge_max_items`, appliqué en SQL **avec un `ORDER BY`
  explicite** — priorité décroissante, puis échéance croissante, puis clé
  primaire. Un plafond sans tri rend les lignes les plus anciennes, piège
  mesuré en production (ADR-273).

### Tâche 2 — le câblage, six endroits, aucun facultatif

1. `HeartbeatSourceLabel` reçoit `WORKBOARD` (`schemas.py`).
2. `HeartbeatContext.workboard`, plus la liste de `has_content()` et la section
   de `to_prompt_context()`.
3. `HEARTBEAT_SOURCE_KEYS` et `HEARTBEAT_SOURCE_ORDER` reçoivent `workboard`
   (`source_policy.py`) ; `assert_source_registry_complete` les vérifie déjà.
4. La table de la tâche 0, plus le n-uplet `specs`.
5. `consultation_surfaces.py` : `workboard` vers `ticket` dans la surface
   `heartbeat`. **Sans cette ligne, le balayage lit le tableau sans laisser de
   trace** — exactement la famille de trou qu'ADR-263 a fermée pour seize
   sources.
6. Le prompt de décision : la source doit y être décrite, sinon le modèle reçoit
   un bloc qu'aucune consigne ne lui apprend à peser.

### Tâche 3 — le refroidissement après délivrance

`metadata["workboard_ticket_ids"]` au moment de la notification, puis
`_bump_used_workboard` dans `heartbeat/proactive_task.py` (460 SLOC, 140 de
marge), calqué sur `_bump_used_open_loops` : il ne tourne **que** si `WORKBOARD`
est dans `sources_used`, et les identifiants malformés sont ignorés. Côté
tableau, `WorkboardRepository.bump_nudged(ids, user_id=...)` fait un seul UPDATE
— `last_nudged_at` à maintenant, `nudge_count` incrémenté par arithmétique côté
serveur, jamais un SELECT puis un incrément en Python.

**Le `user_id` n'est pas décoratif** : il est la clause qui empêche un
identifiant venu d'ailleurs de toucher le ticket d'autrui.

### Tâche 4 — l'écran des réglages

La source apparaît dans le panneau des sources du heartbeat, qui **lit l'ordre
publié par l'API** (`HEARTBEAT_SOURCE_ORDER`) : il n'y a donc pas de vocabulaire
à redéclarer côté front. Restent le libellé et sa description dans les six
locales, et la vérification que l'interrupteur reste atteignable au clavier et
lisible sous 375 px — le panneau existe, ce lot y ajoute une ligne.

### Tâche 5 — jetons, coût et quotas

La source **allonge le prompt de décision de chaque tick**. Trois garde-fous, et
ils sont dans cet ordre :

1. le plafond d'entrées (tâche 1), qui borne la contribution ;
2. le refroidissement par ticket, qui empêche le même ticket de repayer sa place
   à chaque tick ;
3. l'interrupteur de source, qui la retire entièrement.

Aucun appel modèle n'est ajouté : la source enrichit un prompt qui partait de
toute façon. La dépense reste sur la route déjà déclarée pour le heartbeat, donc
**rien à ajouter au registre des routes de dépense** — à vérifier plutôt qu'à
supposer, le garde le dira.

## 4. Plan de test

**Unitaire**

- Les trois motifs, un test chacun, et leurs bords : un ticket dû à la seconde
  près dans la fenêtre, un ticket en retard d'une seconde, un `waiting` à la
  limite exacte.
- Le refroidissement : un ticket récemment poussé est absent ; le même, une fois
  la fenêtre passée, revient.
- **Les exclusions** : `done`, `cancelled` et `idea` ne sortent jamais ; un
  ticket qu'un pair détient sort sur le tableau des DEUX.
- Le plafond : plus d'entrées que le plafond, et l'ordre décide — le test le
  fixe (priorité, puis échéance, puis clé).
- Source coupée : `None`, et **aucune requête** (compter les exécutions).
- `workboard_enabled` faux : `None`.
- Le bump : sans `WORKBOARD` dans `sources_used`, rien ne bouge ; avec, seuls les
  tickets de la personne bougent.
- La table de la tâche 0 : caractérisation des quatorze sources, plus le refus de
  démarrage sur une entrée manquante.
- La surface de consultation : le balayage qui a lu le tableau écrit une ligne
  `ticket`.

**Intégration PostgreSQL**

- La requête réelle avec son tri et son plafond : les lignes rendues sont les
  BONNES, pas les plus anciennes.
- Le bump concurrent : deux ticks ne poussent pas `nudge_count` au-delà du compte
  réel.
- Un ticket détenu par un pair apparaît bien sur les deux tableaux.

**Ratchets, avant et après**

- couplage : l'arête `heartbeat` vers `workboard` ne ferme aucun cycle ;
- taille : `context_aggregator.py` doit AVOIR BAISSÉ, pas seulement tenir ;
- CC : `over` doit passer à 328, et le baseline être abaissé en conséquence ;
- couverture métrique, F006, i18n, documentation.

**Preuve runtime en conteneur** : un ticket en retard sur le compte de dev, un
tick de heartbeat déclenché à la main, la décision qui cite `WORKBOARD` dans
`sources_used`, la notification reçue, et `last_nudged_at` renseigné — puis un
second tick immédiat qui ne le ressort PAS.

## 5. Ce que ce lot ne fait pas

Pas de relance par le tableau lui-même : le heartbeat décide, le tableau
fournit. Pas de notification par ticket — le heartbeat parle une fois, d'une
seule voix. Pas de changement de statut automatique : un ticket en retard reste
en retard, c'est la personne qui tranche.

## 6. Risques, et comment chacun est réfuté

| Risque | Réfutation |
|---|---|
| Le ratchet de taille rougit | tâche 0 mesurée AVANT la tâche 1 ; le fichier doit baisser |
| Un cycle d'imports | compté à zéro dans les cinq directions, et re-prouvé par le ratchet |
| Le balayage lit sans laisser de trace | la ligne de `consultation_surfaces` est dans le plan, pas dans une relecture |
| Un plafond rend les mauvaises lignes | tri explicite, fixé par un test PostgreSQL |
| Le prompt grossit sans borne | plafond, refroidissement et interrupteur, dans cet ordre |
| Le bump touche le ticket d'autrui | `user_id` dans la clause, et un test qui l'exerce |


---

## 7. Ce que l'exécution a réellement livré (2026-09-09)

Le plan tenait. Les trois grandeurs de la tâche 0 sont sorties comme prédit :

| Grandeur | Prévu | Mesuré |
|---|---|---|
| CC de `_apply_source_result` | environ 5 | 4 (la fonction sort du classement) |
| Fonctions au-dessus de CC 15 | 328 | 328 |
| SLOC de `context_aggregator.py` | environ 670 | 676, plafond resserré 705 → 690 |

Deux choses que le plan n'avait pas vues, trouvées en branchant :

1. **`departure` était placée en ligne dans la seconde passe**, pas par le
   répartiteur — l'assert de complétude l'a refusé au premier import. Elle passe
   désormais par la même table : une exception de moins, deux lignes de moins.
2. **Le registre revendiquait des lectures qui n'avaient jamais eu lieu.**
   L'agrégateur enregistrait comme « consultées » toutes les sources que le
   refus de la PERSONNE laissait passer ; or cinq récupérateurs se
   court-circuitent sur un drapeau de DÉPLOIEMENT et rendent `None` sans rien
   ouvrir. Défaut préexistant, de la famille exacte qu'ADR-263 ferme, et ma
   sixième source allait en ajouter une instance.
   `HEARTBEAT_SOURCE_FEATURE_FLAGS` + `is_source_available` le ferment dans les
   deux passes.

Une garde ajoutée au passage, et falsifiée : **une source publiée sans libellé
s'affiche par sa clé brute** dans les six langues à la fois, toutes gardes
vertes. La parité i18n prouve que les langues s'accordent entre elles, jamais
qu'une clé existe.

Preuve runtime du 2026-09-09, conteneur `lia-api-dev`, compte de dev réel : les
deux portes ouvertes, la source publiée au panneau, 3 tickets sur 5 remontés
(`idea` et `done` écartés), les trois motifs corrects, la section de prompt
rendue avec priorité, statut et échéance dans le fuseau de la personne, puis
6 tickets estampillés et **0 entrée au tick suivant** — le refroidissement
tient. Environnement nettoyé.


## 8. Ce que la revue à froid des lots 4 à 6 a encore trouvé (2026-09-09)

Quatre corrections, aucune signalée par un outil :

1. **Un ticket que LIA tient n'est pas en retard pour la personne.** Le premier
   jet relançait la personne sur une échéance que LIA elle-même devait tenir.
   La requête et le motif appliquent la même règle : les motifs d'échéance ne
   concernent que les tickets tenus par une personne ; `waiting` et
   `validating` concernent tout le monde. `validating` rejoint les motifs : un
   résultat livré qui attend depuis des jours est exactement ce qu'une relance
   sert à dire.
2. **La consigne demandait « ce qu'il attend » sans le fournir.** Le run écrit
   sa question dans son propre commentaire ; l'entrée la cite désormais
   (`waiting_on`, extrait de `excerpt_of`, une requête pour l'ensemble) et la
   règle 22 dit de la répéter, jamais de la paraphraser.
3. **L'historique du panneau disait « Confié » pour un ticket rendu** au départ
   d'un pair (lot 4 × lot 5). Sélecteur de libellé sur la charge utile, deux
   libellés dans six langues, une garde back sur le vocabulaire des événements,
   falsifiée.
4. **Un espace latin entre deux phrases chinoises** dans la notification de
   retrait du lot 5.

Vérifié sans correction : l'horloge du `waiting` n'est estampillée que sur un
vrai changement de statut, et chaque appelant le garde ; le chemin de réveil par
push ne touche que le courrier et l'agenda, qui n'ont pas de drapeau ; les
titres de tickets, écrits par un pair, atteignent le prompt de décision comme
les sujets de courriels le font déjà — une exposition du heartbeat entier, pas
de ce lot, laissée hors périmètre avec ce constat.
