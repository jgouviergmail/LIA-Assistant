# ADR-200 : un panneau de réglages montre ce qu'il a produit, et le montre plié

- **Statut** : accepté
- **Date** : 2026-08-03
- **Portée** : `domains/interests`, `domains/heartbeat`, réglages frontend

## Contexte

Deux panneaux de réglages décident quand LIA a le droit d'interrompre le
lecteur : la proactivité (heartbeat) et les centres d'intérêt. Tous deux
laissaient régler la fréquence, les sources et les sujets **sans jamais montrer
ce que ces réglages avaient produit**. Un lecteur pouvait donc baisser une
fréquence sans savoir ce qu'il coupait, ou la monter sans savoir ce qu'il
recevrait de plus.

ADR-199 a fermé la moitié de ce trou côté proactivité. Il restait deux
problèmes.

### Ce que la lecture du code établit

**Le contenu des notifications d'intérêt n'était pas conservé.**
`interest_notifications` est une table d'audit construite pour la déduplication :
elle stocke un SHA-256 et un embedding. Le texte existe pourtant au moment de
l'écriture (`result.content` dans `interests/proactive_task.py`) et était
simplement jeté. Aucun rattrapage n'est possible — un hash ne s'inverse pas.

**Le panneau de proactivité était devenu un mur.** Il empile un formulaire de
fréquence, onze interrupteurs de source et dix lignes d'historique. Affichés
d'un bloc, cela fait défiler bien au-delà de ce que le lecteur venait changer.

## Décision

**Le contenu est conservé.** Une colonne `content` nullable sur
`interest_notifications`, en miroir de `HeartbeatNotification.content`. Les
lignes antérieures portent `NULL` et la carte s'affiche **sans son paragraphe**
plutôt qu'avec un résumé inventé : une absence honnête vaut mieux qu'un contenu
reconstruit.

**Les deux historiques partagent une seule carte.** `NotificationHistoryList`
porte la forme, l'ordre des états et les trois règles déjà corrigées une fois
(erreur vérifiée AVANT la vacuité, spinner de premier chargement dérivé de
l'absence de données et jamais de `error`, total exact à côté de la page —
ADR-185). Chaque panneau ne fournit que son **vocabulaire** : l'historique
d'intérêt n'a pas de priorité (une actualité n'est jamais urgente) et ses
pastilles nomment le sujet puis le fournisseur.

**Trois blocs se replient, et se replient FERMÉS** : les onze interrupteurs,
l'historique proactif, l'historique d'intérêt. La section devient un index que
l'on ouvre, non une page que l'on parcourt — même raisonnement que la fiche 360°
(ADR-185), où le compte porté par l'entête est ce que l'on choisit tant que tout
est fermé.

**Fermé signifie démonté, pas masqué.** Un `<details>` conserve son contenu dans
le DOM : un hook à l'intérieur continuerait de s'exécuter et de requêter. Les
enfants ne sont rendus que pendant l'ouverture, et l'état d'ouverture pilote le
`enabled` de la requête — la différence entre « non affiché » et « non payé ».

**Le repli ne cache pas une décision.** Le nombre de sources refusées reste
porté par l'entête : plié, c'est la seule chose qui reste à juger.

## Conséquences

L'historique d'intérêt ne montre le texte que pour les notifications émises à
partir de cette version. C'est visible et assumé plutôt que masqué par un
remplissage.

La carte partagée rend impossible la dérive entre les deux panneaux : une
correction faite d'un côté vaut pour l'autre, et une divergence visuelle
devient un changement délibéré plutôt qu'un oubli.

Les sémantiques de dépliage viennent de la plateforme (`<details>`/`<summary>`,
comme `UsageStatistics` et la FAQ publique) : clavier, annonce d'état et rôle
sont acquis, là où un basculement maison en devrait trois et en raterait un.

## Alternatives écartées

**Rejoindre le message archivé en conversation par `run_id`.** Le contenu y est,
et la jointure éviterait la migration — mais elle porterait sur
`message_metadata->>'run_id'`, sans index, et disparaîtrait à la première
réinitialisation de conversation. Une colonne dit ce qu'elle contient.

**Ouvrir les blocs par défaut et se contenter de les rendre repliables.** Cela
n'aurait rien réglé : le mur est ce que l'on voit en arrivant.
