# ADR-187 : une seule boîte, deux identités, un seul arbitre

**Statut**: ✅ IMPLEMENTED (2026-07-31)
**Date**: 2026-07-31
**Décideurs**: Équipe LIA
**Révise**: [ADR-180](ADR-180-Peer-Connections.md) §5.1 (recherche par nom exact uniquement)

## Contexte

La découverte de pairs ne cherchait que par **nom complet exact**. Deux
conséquences vécues :

- les homonymes se départagent avec un fragment d'email masqué (`j…@g….com`,
  garde A6) — indice utile, mais qui arrive **après** la recherche, quand on
  connaissait déjà l'adresse et qu'on aurait pu la donner d'emblée ;
- une personne dont on possède l'adresse mais dont on ignore l'orthographe
  exacte du nom (accents, particule, second prénom) reste introuvable, alors
  qu'on tient l'identifiant le plus discriminant qui soit.

La demande produit : chercher aussi par adresse email.

## La tension à trancher

La spec citait un précédent contraire :
`GET /users/search/by-email` est **superuser-only**, avec pour justification
écrite « prevents account enumeration » (`domains/users/router.py:148`).

Le précédent tient, mais il ne dit pas ce qu'on lui fait dire. Il interdit une
recherche `%pattern%` **par sous-chaîne** sur **tous** les comptes : c'est un
outil d'énumération. La découverte de pairs est l'inverse sur les deux axes —
**égalité stricte**, et **uniquement sur les gens qui ont demandé à être
trouvés** (`discovery_enabled`, désactivé par défaut). Reste un oracle
d'appartenance : « cette adresse a-t-elle un compte visible ? ». Il ne
concerne que des volontaires, il exige de **déjà connaître l'adresse** (un
secret plus fort qu'un nom), et il est limité par le même quota que la
recherche par nom.

## Décision

### 1. Une seule boîte, et le backend décide

`DiscoverySearchRequest.full_name` devient `query`. Ce n'est pas un simple
renommage : c'est le refus d'une **seconde autorité**. Si le frontend devait
choisir le champ à remplir, il porterait sa propre heuristique de « ceci est
une adresse » — et deux couches finiraient par ne pas être d'accord sur la
même chaîne. `looks_like_email` (`peers/discovery.py`) est cet arbitre unique,
et il est délibérément plus permissif qu'une validation RFC : il ne fait que
**choisir une branche**, jamais rejeter. Une adresse à moitié tapée est donc
cherchée comme un nom et répond « aucun résultat » — au lieu d'un 422 sur une
frappe en cours.

Conséquence UI : le champ reste `type="text"`. Un `type="email"` ferait
refuser « Marie Dupont » par le navigateur avant même la soumission.

### 2. Deux plis, jamais mélangés

`fold_name` reste NFKD + casefold : deux orthographes d'une **personne** sont
la même personne. `fold_email` (nouveau, même module) est volontairement plus
faible — `strip()` + `lower()`, rien d'autre :

- pas de NFKD : `jérôme@x.com` et `jerome@x.com` sont deux boîtes différentes ;
- pas de `casefold()` : il transforme `ß` en `ss` et fusionnerait
  `straße@x.com` avec `strasse@x.com`.

**Sous-matcher coûte un « aucun résultat » ; sur-matcher coûte une identité.**
La casse, elle, doit être pliée : l'inscription conserve la casse de la partie
locale (Pydantic `EmailStr` ne minuscule que le domaine), donc
`Jean.Dupont@gmail.com` doit répondre à `jean.dupont@gmail.com`.

### 3. Le même balayage, les mêmes gardes

Les deux branches partagent la requête, les exclusions (soi-même, opt-out,
inactif, supprimé, sans nom) et les gardes par ligne (blocage dans un sens ou
l'autre invisible, annotation de relation identique). Aucune ne peut devenir
silencieusement la permissive. La comparaison reste **en Python** pour les
deux : l'exprimer en SQL ferait de la base une seconde autorité sur « quelle
boîte est laquelle » — exactement la faute qu'ADR-185 a corrigée sur les noms.

Une personne **sans `full_name` reste introuvable par les deux branches** : le
résultat doit porter un nom d'affichage, et être sans nom est déjà la raison
documentée de ne pas apparaître.

### 4. Ce qui n'est pas exposé

Le payload de réponse ne change pas. `email_hint` reste masqué même quand on a
cherché par adresse : le chercheur connaît déjà l'adresse qu'il a tapée, donc
le dé-masquer n'apporterait rien — et **une seule forme de réponse** vaut mieux
que deux. Rendre l'adresse d'un pair visible est un sujet distinct, avec son
propre réglage (chantier C-bis).

## Conséquences

**Positives**

- On trouve quelqu'un avec l'identifiant qu'on possède réellement.
- Les homonymes disparaissent quand on cherche par adresse (colonne UNIQUE).
- `looks_like_email` documente et teste, en un seul endroit, ce que le produit
  appelle une adresse.

**Négatives / assumées**

- Oracle d'appartenance sur les comptes **découvrables** : accepté, limité par
  le quota, et réservé à des volontaires.
- Deux boîtes ne différant que par la casse peuvent coexister (l'index UNIQUE
  porte sur la chaîne brute) ; la recherche renvoie alors **les deux** plutôt
  qu'un choix arbitraire — la liste rend cette rareté lisible.
- `full_name` disparaît du contrat `POST /peers/discovery/search`. Aucun
  consommateur tiers : le frontend de ce dépôt est le seul appelant, et il
  part dans le même changement. Pas d'alias de compatibilité — un champ mort
  se garde éternellement.

## Alternatives écartées

| Alternative | Pourquoi non |
|---|---|
| Deux champs (`full_name` OU `email`) | Force le frontend à décider, donc à porter une seconde heuristique — et une adresse à moitié tapée devient un 422 |
| Deux modes explicites dans l'UI (« par nom / par email ») | Fait porter à l'utilisateur un arbitrage que la chaîne tapée suffit à trancher |
| Filtrer l'adresse en SQL (`lower(email) = …`) | Ferait de la base une seconde autorité sur l'identité des boîtes (même faute qu'ADR-185 côté noms) |
| Réutiliser `fold_name` pour les adresses | Fusionne `jérôme@` et `jerome@`, `straße@` et `strasse@` : un faux positif rend le compte de quelqu'un d'autre |
| Réserver la recherche par email aux superusers | Confond une égalité stricte sur des volontaires avec le balayage `%pattern%` sur tous les comptes que ce garde-fou vise |
