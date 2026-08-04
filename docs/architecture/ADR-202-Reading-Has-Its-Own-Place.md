# ADR-202 : ce qui se lit a sa propre destination, ce qui se règle garde la sienne

- **Statut** : accepté
- **Date** : 2026-08-04
- **Portée** : `domains/peers`, `domains/reminders` (nouveau routeur), navigation et hub frontend

## Contexte

LIA produit cinq flux qui s'adressent au lecteur : les messages relayés entre
pairs, les notifications proactives, les notifications d'intérêt, les rappels
en attente et les actions programmées. **Aucun de ces flux n'avait de lieu de
lecture.** Chacun vivait dans le panneau de réglages qui le configure, replié
sous la fréquence, les sources et les interrupteurs qui le gouvernent.

Conséquence mesurée : pour savoir ce que LIA lui avait dit, le lecteur devait
ouvrir les réglages, trouver le bon panneau parmi une trentaine, déplier le bon
bloc — et recommencer cinq fois. Consulter était devenu une opération de
configuration.

Deux flux n'étaient d'ailleurs **pas lisibles du tout** : `peers` n'exposait
aucune route de listage des messages délivrés, et `reminders` n'avait aucune
route de lecture — seulement des écritures.

## Décision

**Une destination de navigation, « Alertes », à droite de « Relations ».** Cinq
sections repliées par défaut, paginées à dix, une par flux. C'est un lieu de
lecture : on y voit ce qui est arrivé, on n'y règle rien.

**Les écrans existants restent les réglages avancés, et leurs liens profonds
restent valides.** Le hub ne remplace rien et ne déplace rien : `?section=…`
continue d'ouvrir le panneau correspondant. Un lecteur qui avait mis un lien en
favori le garde.

**Les deux routes manquantes sont créées en LECTURE SEULE.**
`GET /peers/messages` et `GET /reminders` paginent et comptent, sans exposer
d'écriture. Un domaine qui ne savait qu'écrire ne se met pas à muter depuis un
écran de consultation.

**Le badge d'une section repliée porte son total, et le porte AVANT l'ouverture.**
Un badge sur un bloc fermé existe pour qu'on CHOISISSE quoi ouvrir. Il affichait
`—` jusqu'au dépliage : le seul nombre qui sert à décider d'ouvrir ne
s'obtenait qu'en ouvrant. Les cinq totaux viennent donc d'une **lecture de
comptage unique** au montage (`GET /notifications/hub-counts`), même forme que
la carte des capacités — sondes indépendantes rassemblées par `asyncio.gather`,
**chacune sur sa propre session**, chacune dégradant à 0 plutôt que de vider le
hub. Chaque compte réutilise le repository de la page qu'il décrit : un total
assemblé depuis un autre filtre serait pire que pas de total (ADR-185).

« Une section fermée ne coûte rien » n'a jamais porté sur l'arithmétique mais
sur les LIGNES : un agrégat sur colonne indexée n'est pas une page avec ses
jointures, et la page, elle, attend toujours le dépliage.

**Chaque section publie son total exact à côté de sa page** (ADR-185) : le
compte vient d'un agrégat sur l'ensemble, jamais de la longueur de la page
affichée. `count_delivered_messages` et `count_pending_for_user` existent pour
cela.

**La pagination est un état de section, pas un état de page.** `usePagedSection`
remet la page à 1 quand la section se replie, par ajustement pendant le rendu —
pas dans un `useEffect`, qui aurait ajouté une violation au ratchet
`react-hooks` pour un état purement dérivé.

## Conséquences

**La barre de navigation passe à six destinations.** Elle affiche donc les
icônes seules sous `xl`, les libellés au-delà, et les compteurs de jetons
reculent à `2xl`. Mesuré au navigateur : en allemand à 1280 px, la version
précédente faisait chevaucher « Hilfe » et le sélecteur de mode.

**Le résumé d'une section est visible pliée.** `SettingsDisclosure` reçoit une
`description` optionnelle rendue **à l'intérieur du `<summary>`** : replié ne
doit pas vouloir dire muet.

**Ce qui n'a pas été fait.** Le hub ne notifie pas et ne marque rien comme lu.
Il montre ce qui existe ; l'état « lu » est une notion que le produit n'a pas
et qu'il aurait fallu inventer sur cinq domaines à la fois.

## Alternatives écartées

**Déplacer les cinq blocs hors des réglages.** Cela aurait cassé six liens
profonds documentés et supprimé le lieu où ces flux se règlent, pour un gain
nul : les deux besoins — consulter, configurer — sont réels et distincts.

**Une sixième carte sur le tableau de bord.** Le tableau de bord répond à « que
se passe-t-il aujourd'hui ». Un historique paginé de cinq flux n'est pas une
réponse à cette question.

## Références

- ADR-172 — recherche rapide et liens profonds des réglages
- ADR-185 — un compte affiché est exact, ou il n'existe pas
