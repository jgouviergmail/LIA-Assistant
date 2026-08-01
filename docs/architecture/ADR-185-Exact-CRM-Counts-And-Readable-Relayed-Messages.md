# ADR-185 : un compteur est une affirmation, et la source lisible est la seule source

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Date**: 2026-07-31
**Décideurs**: Équipe LIA
**Complète**: [ADR-176](ADR-176-Personal-CRM-Relations.md) (CRM personnel),
[ADR-180](ADR-180-Peer-Connections.md) (connexions entre utilisateurs, §11 D2)

## Contexte

Deux chantiers distincts ont convergé sur la même exigence d'honnêteté.

**1. Les messages relayés n'apparaissaient nulle part.** Le pont CRM prévu par
la spec peers §11 (décision D2) n'avait livré qu'un booléen `is_peer`. Deux
conséquences mesurées :

- un peer connecté **sans** open loop ni appel n'avait **aucune carte** — le
  badge « LIA » n'avait littéralement personne à décorer ;
- les messages échangés par assistants interposés, pourtant le cœur de la
  fonctionnalité, restaient invisibles hors du fil de conversation.

**2. Les compteurs du CRM étaient faux, et se taisaient.** `build_overview`
chargeait une fenêtre de lignes (`relations_max_items × 4`) puis comptait la
longueur du résultat ; `build_detail` chargeait 200 open loops, 200 appels et
**500 mémoires** avant de filtrer en Python. Trois défauts en découlaient :

- **incomplétude silencieuse** : `list_open_for_user` trie par échéance
  (`due_hint asc nulls_last`), donc au-delà de 200 engagements ceux **sans
  échéance** d'une personne donnée tombaient hors fenêtre — la fiche « 360° »
  pouvait être partielle sans le dire ;
- **coût invisible** : une normalisation NFKD du contenu **entier** de 500
  mémoires à chaque ouverture de fiche, pour n'en retenir que quelques-unes ;
- **troncature muette** : `[:per_section]` coupait à 10 sans jamais indiquer
  combien restaient.

## Décision

### 1. La source lisible est la seule source

Le registre `peer_messages` **efface le contenu à la livraison** (spec peers
§8.4) : cette décision de confidentialité n'est pas revenue en arrière. Le
texte livré ne survit que dans l'archive de conversation du **destinataire**.

Le CRM lit donc **deux magasins, chacun pour ce que lui seul peut donner** :

- le **registre** est l'épine dorsale — identité par **clé étrangère**, donc un
  renommage ne scinde jamais une chronologie, un homonyme n'en fusionne jamais
  deux, et un compte supprimé disparaît de lui-même ;
- l'**archive** fournit le texte, et **uniquement pour les messages reçus** :
  un message envoyé n'a laissé aucune copie chez son auteur.

**Un message dont le texte n'existe plus garde sa date et le dit.** Une
conversation réinitialisée dégrade l'entrée exactement comme un message
envoyé — jamais en entrée manquante. Aucun compteur ne promet donc un texte
qui ne peut pas être affiché.

**Bornage prouvable** : la lecture d'archive est plafonnée par l'instant
d'**enfilement** du plus ancien message hydraté, qui précède nécessairement
son archivage. La requête épouse ainsi l'index `(conversation_id, created_at)`
au lieu de balayer un historique entier. Une marge de 5 minutes absorbe un
éventuel décalage d'horloge : les deux `created_at` viennent de l'horloge
**applicative** (`TimestampMixin`), écrits par deux processus différents.

### 2. Un compteur est une affirmation : il est exact ou il n'existe pas

- **L'aperçu ne compte plus des lignes, il interroge des agrégats.** Chaque
  source expose un `GROUP BY` sur son orthographe brute (`NameActivity` :
  `raw_name`, `count`, `last_at`). La fenêtre `relations_max_items × 4`
  disparaît, et une personne dont la seule activité était hors fenêtre obtient
  enfin sa carte.
- **La fiche interroge chaque source POUR CETTE PERSONNE.** Les orthographes
  exactes viennent des mêmes agrégats, pliées en Python : le SQL matche des
  chaînes brutes (`IN (...)`) et n'a **jamais** d'avis sur qui est la même
  personne. `fold_name` reste l'unique implémentation de l'identité.
- **Chaque section porte son total exact à côté de sa page.** L'UI affiche les
  10 premiers, révèle le reste à la demande, et énonce ce que la page n'a pas
  pu porter. Un plafond est dit, jamais appliqué en silence.

Seules les **mémoires** gardent un prédicat SQL (`unaccent` + `ILIKE` des deux
côtés, l'exact pattern de la recherche de messages) : elles matchent par
sous-chaîne, il n'existe pas d'orthographe à énumérer. Deux divergences avec
le pliage Python qu'il remplace sont assumées et documentées — `unaccent`
n'étend pas les ligatures comme NFKD, et `lower()` n'étend pas `ß` comme
`casefold()`. En échange, le plafond de 500 lignes disparaît : le rappel
augmente. Le caractère best-effort de ce rattachement était déjà énoncé à
l'écran (ADR-176) ; il le reste.

### 3. La connexion elle-même devient lisible, dans les deux sens

Le bloc `lia_peer` que la spec §11 réservait est livré : **connectés depuis**,
**ce que je partage**, **ce qu'ils partagent**. Les deux directions sont
énoncées — décrire seulement ce que l'utilisateur a réglé donnerait une vue
unilatérale d'un arrangement bilatéral. Le bloc reste en **lecture seule** :
le partage s'accorde et se révoque dans les réglages Connexions, jamais ici.

Une **seule** lecture du domaine peers sert le badge ET le bloc
(`list_accepted_peer_profiles`) : interroger deux fois le même domaine pour la
même page, c'est inviter les deux réponses à diverger.

### 4. Une relation en sommeil, et une liste qu'on peut interroger

Un silence de plus d'un trimestre porte une pastille « en sommeil » — une
invitation à agir, jamais un verdict sur la personne. Elle sert aussi de
filtre, aux côtés d'un filtre « sur LIA » et d'un tri (récence / nom /
volume). **Tout est client**, sur des lignes déjà chargées : une préférence
d'affichage ne vaut pas un aller-retour serveur, et le classement du serveur
reste le défaut, pour que la page s'ouvre sur ce qui compte le plus.

### 5. Répondre préremplit, et ne part jamais

Les actions rapides de la fiche — **écrire**, **appeler**, **suivre un
engagement** — utilisent toutes `?draft=`, **jamais** `?intent=`. Les deux
liens profonds coexistent dans le même composant et leur différence est
structurante : `?intent=` est **auto-envoyé** (QW-24, ADR-173), ce qui est
légitime pour « préparer un point 360° » — le clic sur un bouton nommé EST
l'acte délibéré — mais pas pour ce qui atteint un autre humain ou déclenche
un appel (contrat A4 des peers pour le relais). L'action « écrire »
n'apparaît d'ailleurs que sur une connexion encore active : la proposer après
une suppression promettrait un relais impossible.

Une action, **un seul endroit** : le bouton de relais a quitté l'en-tête de la
section messages pour rejoindre cette barre, où il existe même quand aucun
message n'a encore été échangé.

## Conséquences

**Positives**

- Le pont D2 de la spec peers est enfin livré, et au-delà de la lettre
  (contenu, pas seulement la date du dernier relais).
- Les compteurs deviennent exacts. Les chiffres qui changent sont ceux qui
  étaient faux.
- L'ouverture d'une fiche cesse de charger 500 mémoires et de les normaliser
  en Python ; l'aperçu ne lit **aucune** archive JSONB — cette lecture est
  confinée à la seule fiche que l'utilisateur a ouverte.
- Deux défauts de contraste **réels** (AA) ont été corrigés au passage,
  révélés par un scan axe ajouté sur une page qui n'en avait aucun.

**Négatives / assumées**

- Un utilisateur verra certains compteurs augmenter : ils étaient plafonnés.
- Les agrégats couvrent tout l'historique, donc une personne appelée une fois
  il y a trois ans peut réapparaître dans la liste — le tri par récence et le
  plafond `relations_max_items` la placent en fin de liste.
- `relations_max_items_per_section` passe de 10 à 25 (plafond 50 → 200) :
  c'est désormais la taille de page renvoyée, pas ce qui est affiché.
- Les divergences `unaccent`/NFKD sur les mémoires sont documentées et
  couvertes par un test, pas silencieuses.

**Ce qui N'A PAS été fait, et pourquoi**

- **Conserver le contenu dans `peer_messages`** aurait rendu l'hydratation
  triviale — et serait une régression de confidentialité. Le relais ne garde
  pas copie.
- **Un index partiel sur `message_metadata`** a été envisagé pour l'aperçu ; il
  est devenu inutile dès lors que l'aperçu ne lit plus l'archive du tout.
- **Fusion/séparation manuelle d'identités** corrigerait les faux positifs à
  la racine, mais créerait une table et un second verbe d'écriture : Relations
  cesserait d'être une lentille. À décider sur un dossier propre.

## Alternatives écartées

| Alternative | Pourquoi non |
|---|---|
| Compter depuis le registre et lire le texte depuis l'archive, sans dégradation | Divergence garantie après une réinitialisation : « 3 messages » avec une section vide |
| Prédicat SQL d'identité (`unaccent(lower(...)) =`) pour loops et appels | Deuxième autorité sur « même personne », divergente de `fold_name` sur `ß` et les ligatures |
| Préfiltre SQL large + autorité Python, sans agrégats | Ne donne pas de total exact sans charger tout le jeu |
| Statut de présence « en ligne / absent » | Aucune utilité (les messages sont asynchrones), divulgation forte des rythmes de vie, infrastructure entière à créer. La disponibilité issue du partage calendrier **déjà consenti** sert le même besoin |
