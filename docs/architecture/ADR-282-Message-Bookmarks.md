# ADR-282 — Une réponse conservée appartient à la personne, pas à la conversation

- **Statut** : Accepté
- **Date** : 2026-09-12
- **Amende** : ADR-279 (un fichier produit par LIA appartient à la personne ;
  un commutateur retire la capacité, jamais l'archive), ADR-280 (un
  commutateur par capacité), ADR-185 (un compteur montré est exact ou n'existe
  pas), ADR-184 (une borne imposée est publiée), ADR-276 (les lignes d'une
  exécution hors tour sont cachées au chat)
- **Périmètre** : table `message_bookmarks`, `/api/v1/bookmarks`, capacité
  `BOOKMARKS`, action « bookmark » sur chaque bulle de l'assistant, onglet
  « Bookmarks » de « Mes fichiers générés », nœud `bookmarks` de la carte des
  capacités

## Contexte

Une réponse de l'assistant n'existe que dans la conversation qui l'a produite.
La conversation est UNE par compte, et « la réinitialiser » — geste courant —
supprime ses messages. Une personne qui voulait garder une synthèse, un
itinéraire ou une réponse bien tournée n'avait que deux gestes : copier vers un
autre outil, ou télécharger un `.md` (UX P4). Ni l'un ni l'autre ne restait
DANS LIA, ni ne se retrouvait plus tard.

Le besoin (propriétaire, 2026-09-12) : sur chaque bulle de l'assistant, à côté
de « copier », une icône « bookmark » conserve le message ; les messages
conservés vivent dans un nouvel onglet « Bookmarks » de « Mes fichiers
générés » ; chacun est horodaté et rattaché à la requête qui l'a produit ;
chacun se supprime, se partage et se télécharge en Markdown ; la mise en forme
est restituée. Deux arbitrages pris dans la conversation de conception :
l'icône est une **bascule** (pleine quand conservé, second clic retire), et le
`.md` porte la requête en citation au-dessus de la réponse.

## Décision

**Un bookmark est une COPIE, pas un pointeur.** Au clic, la réponse (markdown
ou document HTML `lia-response`, tel quel), la requête qui l'a produite et la
date de la réponse sont copiées dans `message_bookmarks`. Les deux références
que la ligne garde — `message_id`, `conversation_id` — sont en
`ON DELETE SET NULL` : elles ne servent qu'à la bascule de la bulle tant que la
conversation vit ; quand elle meurt, le bookmark reste entier. Deux
alternatives ont été écartées : un pointeur seul (meurt avec la conversation),
et une pièce jointe `.md` dans la galerie ADR-279 (TTL de 24 h, stockage
disque, et « restituer la mise en forme » aurait voulu dire re-parser un
fichier).

1. **La requête est résolue côté serveur.** Le dépôt des bookmarks lit la
   table des messages sous `visible_only` et se déclare `VISIBLE_ONLY` dans
   `conversations/message_readers.py` : la requête est le dernier message
   `user` VISIBLE avant la réponse — jamais la question synthétique d'une
   exécution hors tour (ADR-276), jamais un message d'un autre compte. Une
   notification que LIA a envoyée de sa propre initiative (`message_metadata.type`
   préfixé `proactive_`, préfixe déclaré UNE fois dans `core/constants.py` et
   lu par ses cinq écrivains) ne répond à aucune requête : le bookmark n'en
   garde aucune plutôt qu'une fausse.
2. **La bascule est idempotente par construction.** Index unique PARTIEL sur
   `(user_id, message_id) WHERE message_id IS NOT NULL` : conserver deux fois
   répond 200 avec le bookmark existant (le clic demandait un ÉTAT, pas une
   ligne), un bookmark détaché n'est l'identité de rien, et le plafond ne borne
   que les lignes NOUVELLES.
3. **Le plafond est publié parce qu'il est imposé** (ADR-184) :
   `BOOKMARKS_MAX_PER_USER` (500 par défaut) est appliqué au `POST` et publié
   par la liste, avec `max_limit` de page. Le refus est une classe à part
   (`BookmarkLimitReachedError`, 409) dont la phrase est traduite en six
   langues côté API — la classe, elle, ne l'est pas.
4. **Le total est exact** (ADR-185) : page et compte viennent d'UN même
   `WHERE` (`bookmarks/queries.py`, `count=True`), l'ordre finit sur la clé
   primaire (`answered_at DESC, id DESC` — un bookmark est daté par sa RÉPONSE,
   pas par le clic), l'aiguille de recherche passe par `escape_like`.
5. **Un commutateur retire la capacité, jamais l'archive** (ADR-279/280) :
   `PlatformCapability.BOOKMARKS` (famille `knowledge`, plafond
   `BOOKMARKS_ENABLED`, `route_enforced`) garde le `POST` seul ; lister,
   l'état de bascule, supprimer et exporter restent ouverts. Le nœud
   `bookmarks` de la carte est COMPTÉ et pointe sur l'onglet de la section
   des fichiers (`?section=generated-assets&tab=bookmarks`) par une table
   dédiée `CAPABILITY_SECTION_TAB`, parce que `CAPABILITY_SECTION` est une
   bijection — une section, un statut sur sa carte d'aperçu — et que la
   section appartient déjà à `generated_files`.
6. **Le cycle de vie est déclaré** : `message_bookmarks` est `USER_PURGED` +
   export `FULL` dans `user_data_map`, purgé par `build_purge_statements`,
   rendu en entier par l'export de compte. Une réinitialisation de
   conversation ne touche jamais un bookmark : c'est tout l'objet.
7. **Un seul état pour toute la conversation.** Le chat lit
   `GET /bookmarks/state` UNE fois par montage (borné par le plafond) via un
   contexte React ; chaque bulle y lit sa bascule, optimiste, retour arrière
   sur refus avec la phrase du serveur. En dehors du fournisseur le contexte
   est inerte : une bulle rendue seule ne dessine pas de bascule. La bascule
   est offerte sur TOUTE bulle archivée de l'assistant qui porte du texte —
   une notification proactive comprise, c'est une réponse qu'on peut vouloir
   garder — jamais sur un flux en cours (son id n'est pas encore connu).
8. **La forme est restituée par le composant de la bulle** :
   `MarkdownContent`, donc markdown ET documents HTML enrichis (ADR-177). Le
   `.md` est construit côté client par le chemin du chat (`downloadMarkdown` +
   `messageToPlainText`), avec la requête citée ligne à ligne et la date en
   tête ; le nom de fichier suit la convention `lia-YYYY-MM-DD-HH-mm`.

## Conséquences

- Une nouvelle table, une migration (`d8a4c6e2f7b1`), un domaine
  `domains/bookmarks/` (modèle, requêtes, dépôt, service, routeur, erreurs),
  une entrée de capacité, un nœud de carte, une section `[96]` dans les quatre
  `.env`.
- Le frontend gagne un contexte (`lib/bookmark-state-context.tsx`), un bouton
  de bulle, un hook de liste, un onglet, une carte, un module d'export ; la
  section « Mes fichiers générés » lit `?tab=` à l'arrivée.
- Gardes qui ont refusé pendant le lot, tous verts à la livraison : partition
  des capacités (les deux sens), câblage de route, carte des capacités (nœud,
  destination, six libellés), carte des données, lecteurs de messages, parité
  des formes de fil (le backend lit `types/bookmarks.ts`), ratchet de taille
  (`core/exceptions.py` est gelé : les raisers vivent dans le domaine, comme
  ceux des pièces jointes et des réunions).
- Ce qui n'est pas fait, en le disant : pas de ré-injection d'un bookmark dans
  une conversation (« réutiliser dans le chat »), pas de dossiers ni
  d'étiquettes, pas de bookmark de message utilisateur. Chacun serait une
  décision, pas une omission.
