# ADR-279 — Un fichier produit par LIA appartient à la personne, pas à la conversation

- **Statut** : Accepté
- **Date** : 2026-09-10
- **Amende** : ADR-226 (génération documentaire), ADR-185 (un compteur montré est
  exact ou n'existe pas), ADR-184 (une borne imposée est publiée), ADR-260 (une
  réinitialisation purge par famille déclarée, jamais par motif)
- **Périmètre** : `attachments.origin` / `title` / `conversation_id`,
  `/api/v1/generated-assets`, section de réglages « Mes fichiers générés »,
  garde de capacité `ATTACHMENTS`, réinitialisation de conversation

## Contexte

LIA produit trois familles de fichiers : des **images** (outil de génération),
des **documents** (rapports, présentations, classeurs — ADR-226/274) et des
**captures d'écran de navigateur** (couche de streaming). Les trois sont écrits
dans la table `attachments`, **strictement indistinguables de ce qu'une personne
a téléversé elle-même**.

Trois conséquences, toutes mesurées dans le code avant ce lot :

1. **Rien ne les listait.** Le seul chemin vers un fichier généré était la bulle
   de la conversation qui l'avait produit. Une personne qui remontait une
   conversation d'hier pour retrouver un rapport devait la retrouver d'abord.
2. **La réinitialisation les supprimait tous.** `ConversationService.reset`
   appelait `delete_all_for_user(user_id)` sans aucun filtre : « effacer cette
   conversation » effaçait aussi les douze images générées la semaine
   précédente, dans d'autres conversations.
3. **La garde de capacité était posée sur le ROUTEUR `attachments`**
   (`capability_dependencies(ATTACHMENTS)`). Un administrateur qui coupe les
   téléversements coupait donc aussi la LECTURE et la SUPPRESSION de fichiers
   que la personne ne peut plus produire mais garde légitimement.

À cela s'ajoute une échéance que personne ne voyait : `attachments_ttl_hours`
(24 h par défaut) supprime tout, fichiers générés compris. Un fichier qui
disparaît sans que rien ne l'ait annoncé est exactement le défaut contre lequel
un préavis existe.

## Décision

### 1. `origin` nomme le producteur, et le vocabulaire est CLOS

`AttachmentOrigin` prend quatre valeurs — `upload`, `generated_image`,
`generated_document`, `browser_screenshot` — dont les trois dernières forment
`GENERATED_ORIGINS`. Avec `upload` elles **partitionnent** l'énumération, ce
qu'un test vérifie : un cinquième producteur ne peut pas arriver comme une ligne
non étiquetée qu'aucune surface ne liste.

Deux règles de lecture suivent :

- **Une valeur inconnue n'est jamais lue comme « générée »**. Le côté prudent
  ici est celui qui n'accumule pas d'inconnus dans une galerie.
- **Chaque producteur estampille à l'écriture** — les quatre sites sont
  l'outil d'image (deux chemins), le générateur de documents et la couche de
  streaming du navigateur. La colonne est `NOT NULL` avec `server_default
  'upload'` : une ligne écrite par un chemin oublié est un téléversement, ce
  qu'elle était déjà.

Deux colonnes accompagnent l'origine : `title` (le nom que le producteur
connaît — « Bilan du trimestre », jamais l'UUID sur le disque ; `NULL` renvoie à
`original_filename`, tout ce qu'un téléversement a jamais) et `conversation_id`
(`SET NULL` : supprimer une conversation ne détruit pas ce qu'elle a produit,
elle laisse un fichier sans provenance affichée).

### 2. Le report lit la FORME que les producteurs ont laissée, et ne devine pas au-delà

La colonne n'existait pas quand les lignes actuelles ont été écrites. La
migration `39c7e93d85b1` fait deux passes distinctes :

- **Les images et les captures se reconnaissent à leur PRÉFIXE de nom stocké**
  (`generated_`, `browser_`), et seulement en tête de nom — un préfixe au milieu
  ne prouve rien.
- **Un document ne porte aucune marque** : le générateur le nomme d'après la
  demande de la personne, donc son nom ne prouve rien. Il est reconnu depuis les
  **métadonnées du message** qui pointent dessus (`generated_documents`,
  `generated_images` en JSONB), d'où proviennent aussi le titre et la
  conversation reportés.

Ce qu'aucune des deux passes ne prouve reste `upload` : c'est ce que la ligne
était déjà.

### 3. La réinitialisation d'une conversation CONSERVE les fichiers générés

Arbitrage du propriétaire, 2026-09-10. `delete_all_for_user` prend un paramètre
`origins`, et la réinitialisation passe `{upload}` : elle retire ce que la
personne a mis, rien d'autre. Le TTL, lui, expire toujours tout — la galerie
n'est pas un archivage, et **la rétention reste à 24 h** (arbitrage : « pour
l'instant on reste sur 24h »).

C'est la doctrine d'ADR-260 appliquée aux fichiers : une purge retire ce que sa
famille déclare, jamais ce qui lui ressemble.

### 4. Trois galeries, une par famille, et les captures ont la leur

Arbitrage du propriétaire : les captures de navigateur sont une **section à
part**, pas une sous-catégorie des images. Elles ne se cherchent pas comme un
visuel qu'on a demandé — elles se retrouvent comme la trace d'une navigation.

`GET /generated-assets?family=images|documents|screenshots` liste une famille à
la fois, avec une recherche sur le titre ET le nom de fichier, deux fenêtres de
dates (création, expiration) et quatre tris. **`upload` n'est pas listable** :
`GalleryFilters` le refuse à la construction plutôt que de renvoyer une page
vide, parce que les téléversements d'une personne appartiennent à la
conversation où elle les a mis.

Trois règles portent l'énoncé :

- **La page et son total sortent du MÊME `WHERE`** (ADR-185). `count=True`
  renvoie le même énoncé filtré, sans tri ni pagination : construits séparément,
  ils décriraient deux ensembles différents dès le premier filtre ajouté d'un
  seul côté. La réponse porte le total EXACT et la somme EXACTE des octets
  derrière lui.
- **Tout tri se termine sur la clé primaire.** Deux fichiers créés dans la même
  milliseconde se répètent ou disparaissent à la frontière d'une page sans ordre
  total.
- **Un besoin de recherche est une DONNÉE, jamais un motif.** `escape_like` lui
  est appliqué : mesuré sur PostgreSQL, un `_` non échappé matche toutes les
  lignes (le workboard l'a payé le 2026-09-10).

Le plafond de page (100) et la taille par défaut (24) sont **publiés dans la
réponse** : une borne imposée que le producteur ne peut pas lire est un piège
(ADR-184).

### 5. La garde de capacité descend du routeur vers la route de téléversement

`capability_dependencies(ATTACHMENTS)` quitte le routeur `attachments` pour se
poser sur `POST /attachments/upload` seule. **Téléverser et consulter sont deux
capacités qui partagent une table** : couper la première ne doit pas fermer la
porte sur des fichiers que la personne garde légitimement, ni l'empêcher de les
supprimer.

Le routeur `generated-assets` est inclus **sans condition** : il ne dépend
d'aucun drapeau, puisqu'il ne sert qu'à lire et effacer ce qui existe déjà.

Le garde de câblage (`test_capability_route_wiring.py`) apprend à accepter une
garde posée au niveau de la ROUTE en plus du niveau du routeur — sans quoi il
aurait lu ce déplacement comme une capacité non gardée.

**Amendement du 2026-09-12 — le plafond d'environnement n'obéissait pas à
cette règle.** Le commutateur d'opérateur la respectait ; `routes.py` incluait
encore le routeur `attachments` tout entier sous `attachments_enabled`, et
`startup/schedulers.py` n'enregistrait le balayage d'expiration que sous ce
même drapeau. Sur une instance aux téléversements coupés — le démonstrateur
public — un document généré était écrit et ne pouvait pas être ouvert
(`GET /attachments/{id}` en 404), et n'aurait jamais expiré. Le routeur est
désormais monté quel que soit le plafond (la route de téléversement porte sa
propre garde, lue à l'appel) et le balayage est enregistré sans condition :
quatre producteurs écrivent la table, et une passe qui ne trouve rien coûte
une requête indexée. Deux gardes : `test_router_mounted_whatever_the_ceiling.py`
(routes montées sous les deux valeurs du plafond, garde de téléversement
présente, `add_job` du balayage hors de tout `if` lisant le drapeau).

### 6. « Supprimé » veut dire parti

`POST /generated-assets/delete` répond `{deleted, skipped}`. Un identifiant que
l'appelant ne possède pas, un qui désigne un téléversement, et un que le
nettoyage a retiré entre le listing et le clic sont **écartés**, jamais comptés
comme supprimés — « trois supprimés » quand deux sont partis est exactement la
classe d'affirmation qu'ADR-185 interdit. L'écran dit les deux : un message de
succès pour ce qui est parti, une information pour ce qui ne l'était plus.

**Le même identifiant deux fois est UN fichier.** La première boucle parcourait
`ids` tel que reçu et consultait un dictionnaire qu'elle ne consommait pas : un
doublon supprimait deux fois la même ligne, la déliait deux fois du disque,
comptait deux retraits et la renvoyait deux fois dans `deleted` — « 2 supprimés »
pour un fichier est exactement l'affirmation qu'ADR-185 interdit. L'écran envoie
un `Set`, donc rien ne l'atteignait depuis l'application ; l'API est une surface
publique et répond à ce qu'un client poste. La liste est dédupliquée en gardant
l'ordre d'arrivée — re-trier ferait apparier les lignes au hasard côté client —
et la partition couvre chaque identifiant DISTINCT (revue à froid, 2026-09-10).

**La page suit la donnée.** Supprimer le dernier fichier de la dernière page
laissait une grille vide sous un pagineur annonçant « page 3 sur 2 » : la page
est bornée au nombre de pages du jeu, pendant le rendu comme la remise à zéro
des filtres.

### 7. Pourquoi un fichier est parti est enregistré sur l'étiquette que le tableau de bord groupe déjà

`attachments_cleanup_deleted_total` porte une étiquette `reason` dont le
vocabulaire devient **clos** : `expired`, `conversation_reset`, `user_deleted`.
Avant, une personne qui vidait sa galerie était indistinguable d'une
réinitialisation de conversation, et le panneau traçait une seule ligne pour deux
événements très différents. **Aucune métrique nouvelle** n'est créée : le panneau
existant groupe par `reason` et gagne une troisième série honnête.

### 8. L'écran est une galerie, pas un tableau

Trois onglets, **une seule galerie montée à la fois** — trois montées ensemble
ouvriraient trois pages que personne ne regarde. Chaque carte porte l'aperçu (ou
la marque de son type), le titre, la taille, la date de création et **son
échéance**, dont le ton passe au chaud à six heures de l'expiration et au
destructif une fois passée. Une échéance illisible se lit comme passée : dire
« vous avez le temps » d'une date que personne n'a pu lire est la mauvaise façon
de se tromper, parce que la personne ne sauvegarderait pas son fichier.

Sous `lg`, les filtres se replient derrière un résumé qui dit ce qu'ils
retiennent — le même mécanisme que le workboard (ADR-276, lot B3) — et la grille
descend à une colonne. Les cibles tactiles tiennent à 320 px.

## Conséquences

**Positives**

- Une personne retrouve, télécharge et supprime ce que LIA a produit pour elle,
  sans remonter les conversations.
- Un fichier généré survit à la réinitialisation de la conversation qui l'a
  produit.
- L'échéance est dite avant qu'elle ne tombe.
- Couper les téléversements ne ferme plus la porte sur ce qui existe déjà.

**Coûts et limites**

- **La rétention reste 24 h.** La galerie rend l'échéance visible ; elle ne la
  repousse pas. Une personne qui veut garder un fichier le télécharge.
- Trois colonnes et un index de plus sur `attachments`. L'index composite
  `(user_id, origin, created_at)` sert exactement la lecture de la galerie.
- Le report de la migration est **structurellement incomplet** pour les documents
  dont le message d'origine a été purgé : ils restent `upload` et n'apparaissent
  pas dans la galerie. C'est le côté prudent — inventer une origine ferait
  apparaître un téléversement de la personne comme une production de LIA.

## Alternatives écartées

- **Une table `generated_files` séparée.** Elle aurait dupliqué le stockage
  disque, la vérification de propriété, le TTL et la route de téléchargement —
  quatre mécanismes pour la même chose, et deux autorités sur « ce fichier
  existe-t-il encore ? ».
- **Déduire l'origine du nom de fichier à la lecture.** C'est ce que fait le
  report, une fois, dans une migration relue. En faire une règle de lecture
  aurait rendu la galerie dépendante d'une convention de nommage qu'aucun
  producteur ne s'était engagé à tenir.
- **Une seule galerie avec un filtre de famille.** Deux des trois familles se
  cherchent différemment (on cherche un document par son nom, une capture par sa
  date) et l'arbitrage du propriétaire demandait une section pour les captures.
- **Repousser la rétention pour les fichiers générés.** Aurait changé une
  décision de volumétrie sous couvert d'une décision d'ergonomie. La rétention
  est un réglage ; ce lot le rend visible, il ne le tranche pas.
