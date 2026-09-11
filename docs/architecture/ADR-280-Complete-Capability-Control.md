# ADR-280 — Un commutateur par capacité, et une carte qui ne ment pas

- **Statut** : Accepté
- **Date** : 2026-09-10
- **Amende** : ADR-216 (commutateurs de plateforme), ADR-085 (assertions de
  complétude au démarrage), ADR-185 (un compteur montré est exact ou n'existe
  pas), ADR-279 (un commutateur retire la capacité, jamais l'archive)
- **Périmètre** : `PlatformCapability` (12 → 25), `CAPABILITY_SPECS`, garde de
  route et points d'étranglement de service, `PLATFORM_CAPABILITY_NODES`,
  `COUNTED_NODES` / `SWITCH_NODE_KEYS`, panneau d'administration

## Contexte

### Treize fonctionnalités sans commutateur

Le panneau d'administration offrait **douze** capacités. Le produit livrait, en
plus : un tableau de travail (ADR-276), des journaux personnels, des habitudes
apprises (ADR-214), des notifications proactives, des connexions entre comptes,
un profil psychologique, des canaux externes, des fils ouverts, la mémoire à
long terme, le suivi des centres d'intérêt, des débriefs de relation (ADR-269),
la délégation à des sous-agents (ADR-083) et un Python éphémère (ADR-249).

Treize fonctionnalités qu'un exploitant ne pouvait **ni voir ni couper** sans
redéployer. C'est exactement la dérive contre laquelle ADR-085 a posé ses
assertions de complétude, pointée cette fois sur le registre des commutateurs
lui-même.

### Une étoile qui comptait autre chose que son nom

Mesuré le 2026-09-10 : le nœud de la constellation **clé `relations`, libellé
« Relations »**, comptait des lignes `OpenLoop`. Une personne lisait
« Relations : 4 » alors que la figure était « quatre fils non terminés ». La même
erreur courait sur toute la chaîne : la destination du nœud pointait vers la
section de réglages **« fils ouverts »**, donc cliquer sur « Relations » menait
aux fils ouverts.

### Un panneau qui disait « routes » d'un point d'étranglement

`enforced_on_routes` était calculé comme `route_enforced or service_enforced`.
Le champ nommait les routes et portait les deux, si bien que le panneau
annonçait « appliqué sur les routes » d'une capacité gardée à l'intérieur d'un
service. Avec cinq nouvelles capacités de ce type, l'imprécision devenait un
mensonge courant.

## Décision

### 1. Vingt-cinq capacités, et la partition est vérifiée dans les deux sens

`PlatformCapability` passe de douze à vingt-cinq membres. Un test compare
l'énumération à une **liste tenue par une personne** — pas dérivée du code — dans
les deux directions : une fonctionnalité livrée sans commutateur échoue, et un
commutateur que personne n'a décidé d'expédier échoue aussi.

Chaque spécification est vérifiée pièce par pièce : le plafond de déploiement
existe réellement sur `settings` (un attribut mal orthographié se lirait `False`
et couperait la fonctionnalité pour toujours), la clé du magasin de réglages
existe et **porte le nom de sa capacité** (une clé nommant une autre capacité
laisserait un exploitant en couper une pour une autre), et le libellé suit la
convention que le frontend résout.

### 2. Un commutateur retire la CAPACITÉ, jamais l'ARCHIVE

C'est la leçon d'ADR-279 généralisée. Deux formes d'application, choisies par ce
que la capacité EST :

- **la route est la capacité** — un tableau, des connexions, un canal vivant, un
  profil : la garde se pose sur le routeur (`workboard`, `journals`, `peers`,
  `psyche`, `channels`, `open_loops` ; `habits` et `heartbeat` ont quitté cette
  liste le 2026-09-11, voir l'amendement ci-dessous) ;
- **la capacité est un acte de FOND qui remplit une archive que la personne
  continue de lire** — extraire une mémoire, apprendre un intérêt, écrire un
  débrief : la garde se pose sur l'ACTE, et le routeur de l'archive reste ouvert
  (`memory`, `interests`, `relation_debrief`, plus `sub_agents` et
  `python_sandbox`, qui n'ont pas de routeur du tout).

Couper la mémoire arrête l'apprentissage de nouveaux faits ; chaque mémoire déjà
apprise reste lisible et supprimable. C'est la même phrase que pour les
téléversements et la galerie.

### 3. Les points d'étranglement lisent la CAPACITÉ, pas le drapeau brut

Les cinq gardes de service lisaient `settings.<flag>` directement, donc le
commutateur de l'exploitant n'y changeait rien. Elles lisent maintenant
`is_capability_enabled`, qui compose le plafond de déploiement ET le commutateur
— et le lisent **à l'appel**, parce qu'un commutateur basculé après le démarrage
doit prendre effet sans redémarrage.

Deux d'entre eux ont dû devenir asynchrones pour cela (`_enabled` du débrief, la
porte du sous-agent) : le magasin de réglages est derrière Redis, et lire le
drapeau brut annoncerait une capacité qu'un administrateur a coupée il y a une
heure.

### 4. Le nœud dit ce qu'il compte

Le nœud `relations` devient **`open_loops`**, libellé « Fils ouverts » dans les
six langues, et pointe vers la section « fils ouverts » qu'il désignait déjà.

Une VRAIE entrée « Relations » revient comme **nœud-commutateur**, sans compteur :
la page Relations est une LENTILLE sur les contacts et les messages, elle ne
possède aucune ligne, donc elle n'a rien d'exact à compter — et inventer un
nombre est précisément ce qu'ADR-185 interdit. Elle est exemptée de destination
de réglages : sa destination EST la page, où ADR-269 place déjà l'interrupteur
du débrief.

### 5. Cinq nœuds de plus, parce que la carte ne doit pas rester en arrière

`open_loops` (renommé), `workboard`, `reminders`, `generated_files` (ADR-279) et
`relations` (redevenu réel). Deux capacités restent **hors carte** avec une
raison écrite : la délégation et le Python éphémère sont ambiants — aucune
surface REST, aucun état par compte, une étoile qui ne pourrait qu'être allumée.

Deux compteurs passent par le module qui POSSÈDE leur règle plutôt que de la
réexprimer : le tableau de travail par `visible_predicate` (« propriétaire OU
porteur »), les fichiers générés par le vocabulaire `GENERATED_ORIGINS`. Une
seconde lecture de ces règles finirait par contredire la surface qu'elle décrit.

### 6. Le panneau dit OÙ un commutateur mord, et le dit par famille

`enforced_on_routes` et `enforced_in_service` sont séparés. Le panneau dit
« appliqué à un point d'étranglement interne » quand c'en est un, et le dit avec
la phrase qui compte : *la capacité s'arrête, ce qu'elle a déjà produit reste*.

Vingt-cinq lignes identiques en une colonne sont un mur qu'un exploitant fait
défiler ; le panneau les groupe en six familles (médias et voix, mémoire et
connaissances, portée et outils, travail et initiative, personnes, assistant).
**La famille est déclarée dans la spécification backend**, pas dans le frontend :
deux tables finiraient par ne plus être d'accord sur l'appartenance d'une
capacité. L'ordre des familles est celui de la déclaration et jamais celui de la
charge utile — un exploitant qui a basculé quelque chose doit retrouver le
panneau là où il l'a laissé — et une famille que le frontend ne sait pas nommer
est dessinée **en dernier plutôt que perdue** : un commutateur invisible est pire
qu'un commutateur mal placé.

### 7. La carte lit une table à la fois

Ajouter des nœuds a rendu visible ce que le `asyncio.gather` de la carte coûtait
déjà. Mesuré le 2026-09-10 avec un gestionnaire de session instrumenté :
`resolve_capabilities` tenait **dix-huit contextes de session ouverts au même
instant**, contre un pool de `database_pool_size` 20 plus
`database_max_overflow` 10 — un seul chargement de page en prenait l'essentiel,
et un deuxième lecteur attendait sur `database_pool_timeout`.

| Stratégie | Latence (5 essais, à chaud) | Sessions simultanées |
|---|---|---|
| `gather` | 10 ms | 18 |
| boucle | 21 ms | 1 |

Onze millisecondes rachètent dix-sept sessions simultanées sur une page qui en
coûte déjà des centaines : c'est la règle du dépôt lui-même — « pour une poignée
de requêtes indexées, une simple boucle séquentielle suffit et reste plus
simple » — appliquée à l'endroit qui l'enfreignait.

La boucle rend au passage **structurelle** une promesse que le module écrivait
déjà : chaque sonde échoue en DOUCEUR. `gather(return_exceptions=False)` ne la
tenait que parce que chaque compteur portait son propre `try` ; un compteur
écrit sans lui aurait vidé la page entière. Une lecture qui échoue est rapportée
DISPONIBLE et inactive — jamais indisponible, mot réservé à « l'instance l'a
coupé », qui ferait conclure au lecteur que la fonctionnalité est éteinte.

## Conséquences

**Positives**

- Toute fonctionnalité que vit une personne se coupe sans redéploiement.
- La carte des capacités décrit le produit d'aujourd'hui, et chaque étoile
  compte ce que son nom dit.
- Le panneau distingue les trois façons dont un commutateur mord.

**Coûts et limites**

- **Vingt-cinq lectures de capacité sur le chemin de requête.** Chacune passe
  par le cache Redis d'ADR-216 et retombe sur la valeur d'environnement en cas
  d'échec — une lecture ne lève jamais.
- Les drapeaux d'environnement gardent leur nom d'origine
  (`memory_extraction_enabled` pour la capacité `memory`,
  `python_sandbox_tool_enabled` pour `python_sandbox`) : les renommer aurait
  cassé tout `.env` existant pour un gain cosmétique.
- **La carte ne compte toujours pas les relations.** C'est voulu : le domaine ne
  possède pas de lignes, et un nombre inventé serait pire qu'aucun.

## Alternatives écartées

- **Un commutateur par drapeau `*_enabled`.** Il y en a 102, dont l'immense
  majorité sont des réglages internes (`llm_cache_enabled`,
  `semantic_pivot_enabled`, `router_debug_log_enabled`). Les exposer ferait du
  panneau un tableau de bord de réglages fins, où une erreur d'exploitation coûte
  plus cher que l'absence du commutateur. Ce que le panneau offre est ce qu'une
  PERSONNE vit.
- **Garder `relations` comme nœud compté, en comptant les débriefs.** Le nombre
  aurait été exact et illisible : « Relations : 2 » sur un compte qui suit
  quarante personnes et n'a ouvert que deux fiches.
- **Grouper les familles côté frontend.** Deux tables pour une appartenance,
  c'est la dérive que ce dépôt paie régulièrement — la famille voyage avec la
  spécification.

## Amendement 2026-09-11 — `habits` et `heartbeat` sont des actes de fond, gardés à l'acte

L'audit des habitudes (ADR-214, amendement c) a mesuré sur docker dev ce que
la garde de routeur ne tenait pas : `habits` OFF laissait le job nocturne
apprendre, le ledger enregistrer, le bloc heartbeat consommer le profil et le
scoring différer les ticks ; `heartbeat` OFF laissait le balayage périodique,
le balayage des réveils et celui des moments notifier. La route (`/habits`,
`/heartbeat/settings`) n'était pas la capacité : elle en est l'ARCHIVE et le
réglage, exactement le cas de la mémoire et des intérêts.

Les deux passent donc dans la seconde famille (`service_enforced=True`,
`route_enforced=False`) :

- `habits` est lu à l'acte par le job nocturne, l'écriture du ledger
  (`record_occurrence_if_allowed`, issue `feature_disabled` sur
  `recurrence_ledger_writes_total`), la promotion, le bloc heartbeat, le bloc
  ambiant, le scoring de tick et le ping de présence (`record_presence` rend
  `disabled`). Le routeur des habitudes reste ouvert — la personne consulte,
  met en pause, supprime, oublie — et seuls `/recompute` et `/presence`, qui
  sont des ACTES, portent `capability_dependencies(HABITS)` ;
- `heartbeat` est lu à l'acte par les trois balayages (`heartbeat_notification`,
  `heartbeat_wake_sweep`, `moment_sweep`, après la capacité `moments`), qui
  répondent `capability_disabled` sans rien servir. Le routeur reste ouvert :
  l'historique des notifications, les sujets refusés et les genres de moments
  sont des réglages que la personne doit pouvoir lire et changer capacité
  coupée.

Chaque lecture se fait par `is_capability_enabled` à l'appel, jamais par le
drapeau brut (décision 3). Le garde de câblage des routes lit la
déclaration et refuse un routeur gardé pour une capacité déclarée à l'acte.
