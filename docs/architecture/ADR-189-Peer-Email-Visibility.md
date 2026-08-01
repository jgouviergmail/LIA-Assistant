# ADR-189 : être trouvable et donner son adresse sont deux consentements

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Date**: 2026-07-31
**Décideurs**: Équipe LIA
**Complète**: [ADR-180](ADR-180-Peer-Connections.md) A6 (fragment d'email masqué), [ADR-187](ADR-187-Discovery-By-Address.md)

## Contexte

Le programme peers masque l'adresse d'un pair **partout**, y compris entre
personnes connectées : la garde A6 ne montre qu'un fragment (`j…@g….com`),
conçu pour départager deux homonymes dans un résultat de recherche.

Ce masque avait un sens à l'instant de la découverte, face à un inconnu. Il en
a beaucoup moins entre deux personnes qui se sont **mutuellement acceptées** :
elles se connaissent, elles échangent des messages relayés, elles se partagent
un agenda. Leur cacher une adresse qu'elles ont sans doute déjà relève du rite,
pas de la protection. Et depuis ADR-187, l'adresse est aussi ce qui permet de
**retrouver** quelqu'un : ne jamais pouvoir la lire rend ce chemin inutilisable
entre gens qui se connaissent.

## Décision

### 1. Un second opt-in, jamais une conséquence du premier

Nouvelle colonne `users.peer_email_visible`, **défaut off**, distincte de
`discovery_enabled`. La tentation était d'en faire une seule case (« être
visible ») ; ce serait une régression de consentement : **accepter d'être
trouvé n'est pas accepter de donner son adresse**. Deux colonnes, deux
verbes, et deux tests qui vérifient qu'activer l'un ne touche jamais l'autre.

### 2. Seulement aux connexions ACCEPTÉES

L'adresse n'apparaît que sur une paire `accepted`. Sur une demande en attente,
elle est **délibérément jetée** — l'annuaire la charge, la liste des demandes
la déballe et l'ignore, avec le commentaire qui dit pourquoi : *pas encore
accepté n'est pas connecté*. Un requérant ne doit pas obtenir en demandant ce
qu'il n'obtiendrait qu'en étant accepté.

La recherche de découverte, elle, ne change pas : un inconnu ne reçoit jamais
que le fragment masqué, opt-in ou pas. Sinon l'oracle d'appartenance d'ADR-187
deviendrait un moissonneur d'adresses.

### 3. L'adresse OU le masque, jamais les deux

La carte de connexion affiche l'adresse réelle quand elle existe, le fragment
sinon. Montrer les deux ferait lire deux informations différentes sur une même
personne. Le champ `peer_email_hint` reste sur le fil — il est épinglé
(spec §12.8) et sert encore partout ailleurs.

### 4. Le PUT devient partiel

`PUT /peers/me` accepte désormais chaque champ indépendamment, avec « au moins
un » exigé. Envoyer systématiquement les deux laisserait un onglet écraser le
réglage qu'un autre vient de changer, en renvoyant une valeur périmée lue au
chargement. Deux consentements indépendants méritent deux écritures
indépendantes.

### 5. Ce que cet opt-in ne fait PAS

Il **n'alimente pas** les sections fournisseurs du CRM ([ADR-188](ADR-188-CRM-Provider-Sections.md)).
Celles-ci résolvent les adresses depuis le **carnet d'adresses de
l'utilisateur**, et cette frontière reste : si l'email d'un pair devenait une
source d'adresses par effet de bord, ce réglage-ci cesserait d'être le seul
endroit qui décide de son exposition. Le jour où on veut ce raccourci, il se
décide ici, explicitement.

## Conséquences

**Positives**

- Deux personnes connectées peuvent enfin se lire une adresse, si elles l'ont
  décidé chacune de leur côté.
- La chaîne de consentement reste lisible : trouvable → connecté → adresse.

**Négatives / assumées**

- Une colonne de plus sur `users`. Le prix d'un consentement qui ne se déduit
  pas d'un autre.
- L'opt-in est global, pas par connexion. Une granularité par personne
  demanderait une table ; rien ne prouve encore ce besoin (YAGNI), et le
  blocage reste la réponse à « pas celle-là ».

## Alternatives écartées

| Alternative | Pourquoi non |
|---|---|
| Réutiliser `discovery_enabled` | Ferait d'un consentement la conséquence d'un autre |
| Montrer l'adresse à toute connexion, sans opt-in | Retire à l'utilisateur une décision qui le concerne seul |
| La montrer aussi sur une demande en attente | Donnerait en demandant ce qui s'obtient en étant accepté |
| La montrer dans les résultats de découverte | Transformerait l'oracle d'appartenance d'ADR-187 en moissonneur d'adresses |
| Un opt-in par connexion | Une table pour un besoin non prouvé ; le blocage couvre déjà le cas « pas celle-là » |
| PUT non partiel (les deux champs requis) | Un onglet écraserait le réglage qu'un autre vient de changer |
