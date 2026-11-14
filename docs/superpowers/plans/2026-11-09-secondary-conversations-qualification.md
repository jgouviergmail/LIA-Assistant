# Discussions annexes — qualification de livraison

## Comportement livré

**Principale** est la discussion permanente. Elle reçoit les notifications, rappels et messages automatiques. Son bouton **Réinitialiser** ouvre une confirmation qui nomme la discussion. Le badge au centre de l’en-tête donne accès à la liste et à la création d’une annexe avec un titre obligatoire. On peut ouvrir, renommer ou supprimer une annexe. Le retour à Principale après la suppression de l’annexe active intervient après confirmation du serveur.

Chaque discussion a son historique, son brouillon enregistré dans le navigateur, son contexte de travail et ses propres chiffres de session. Les réglages, la mémoire et le journal restent communs au compte. Les quotas s’appliquent au compte et à la plateforme. Le Live reste lié à la discussion dans laquelle il a commencé. Le [contrat technique](../../technical/SECONDARY_CONVERSATIONS.md) détaille la transition et le [registre de décision](../../architecture/ADR-378-Permanent-Main-And-Isolated-Discussion-Runtimes.md) décrit les choix d’architecture.

## Corrections issues des contre-revues

- Sur Docker dev, la suppression signalée en échec retournait `422`. Le `DELETE` transportait le reçu de confirmation en JSON sans déclarer ce format. Le client annonce désormais `application/json` pour ce corps. Le même test a échoué avec l’en-tête absent et réussi avec la correction. L’API réelle valide le corps et retourne `202`. La discussion retirée répond ensuite `404`.
- Le parcours à deux onglets a reproduit une perte du brouillon dans Firefox et WebKit après suppression de sa copie persistée par l’autre onglet. Le compositeur remet son dernier texte à l’écran de récupération pendant sa fermeture. Ce texte reste en lecture seule dans l’onglet. Le brouillon de Principale est conservé et aucune requête de message n’est émise.
- Le bouton partagé changeait de nœud HTML lors d’un changement de variante, ce qui faisait perdre le focus. Le test d’interaction du sélecteur de fichiers a guidé la correction. Le retour à la discussion d’origine du Live a aussi été repositionné après un clic intercepté par le compagnon à petite et grande largeur.
- Les tests ont isolé un coût reçu après le retrait de son contexte, le premier coût Live sans discussion et un résultat de veille qui arrivait après la clôture. Le correctif conserve le coût dans les registres du compte et de l’instance. Le badge affiche uniquement les coûts attribués à la discussion courante. Le résumé de veille complète la même carte après la fin de la session.
- Les tests d’import et de fichiers partagés engagent désormais leurs comptes de test sur PostgreSQL pour que les écrivains indépendants puissent les lire. Le test de récurrence exécute le protocole de verrouillage sur Redis. Les assertions de rollback, de reprise et de conservation des fichiers restent exercées.
- Les tests de retrait de compte utilisent les adaptateurs de nettoyage installés au démarrage et le Store PostgreSQL natif. Le test du dernier favori provient d’une annexe identifiée. Il exclut une réponse plus récente de Principale et vérifie le refus après retrait de l’annexe.
- Les anciens parcours de réinitialisation utilisent l’adaptateur de nettoyage natif. Le test de comptage lit maintenant les lignes de facturation PostgreSQL de deux discussions. Le test de retrait d’un fichier observe son retrait des lectures, sa trace de nettoyage et le retour à l’état disponible après rollback. Une seconde connexion vérifie la visibilité transactionnelle.
- Le test de concurrence entre retrait et upload bornait la session HTTP de test. L’écrivain attendait dans sa propre session PostgreSQL. Le moteur de preuve applique maintenant la même configuration de borne à chaque connexion. Les quatre variantes vérifient le refus SQL et le cas upload vérifie que la lecture du fichier n’a pas commencé.

## Matrice des preuves

Les identifiants reprennent la matrice de [l’analyse](2026-11-09-secondary-conversations-analysis.md). Les scénarios de panne utilisent des entrées contrôlées et les véritables frontières de persistance quand l’ordre des commits fait partie du résultat.

| Cas | Contrôles exécutés |
|---|---|
| T01–T05, T30, T39 | Rejeu et aller-retour Alembic. Routes authentifiées sur PostgreSQL, Principale migrée, création répétée et concurrente, titres, page vide et plusieurs pages, refus propriétaire/révision et création désactivée. Les anciennes requêtes restent servies par Principale. |
| T06–T11, T33, T35–T36 | Checkpoints et Store PostgreSQL, Redis natif, reprise et annulation de flux, clôture des producteurs et refus des anciennes écritures. Les tests du frontend exercent retards et abandon du lecteur. Les parcours Playwright exercent changement de discussion avec et sans exécution en arrière-plan, intentions périmées et mises à jour sans rechargement. |
| T12, T16, T24–T25, T37 | Destinations automatiques, références de cartes, limites de source, notifications et intents. Les parcours Web couvrent les interactions HITL et la synchronisation. Les intégrations ciblent le rattachement à Principale et la publication après commit. |
| T13–T15, T20–T22 | Tests de parité des extractions et de consentement, sources retirées, consolidation de plusieurs historiques, coûts tardifs et prix capturés. Le vrai cache de traduction avec Redis distingue deux comptes et réutilise un texte identique entre discussions du même compte. Des refus compte et instance bloquent la même API avant tout appel. Les registres gardent les pointeurs nuls et les copies de favoris. |
| T17–T19, T26, T34, T38, T40 | Retrait atomique de la cible, rollback, reprise de reçu, refus de purges, ressources partagées et états d’occupation. Les tests observent le stockage natif et les connexions SQL pendant l’attente, avec exports et retrait de compte sur données jetables. |
| T23 | Réservation Live avant fournisseur, délégation, Direct, veille, fermeture et reconnexion. PostgreSQL et Redis valident les deux ordres de la veille et de la fermeture, la reprise après accusé perdu et le rattachement d’un résultat tardif à la même carte. |
| T27–T29 | Gestion du catalogue et UX sur Chromium, Firefox et WebKit. Clavier, focus, axe, libellés traduits, titres longs, cinq largeurs, thèmes et compagnon. World et Live sont également exercés sur le bundle optimisé. |
| T31–T32 | Pagination de métadonnées sur une base réelle avec le même nombre de lectures SQL pour une ligne ou une page pleine. Deux onglets partagent un compte et sélectionnent des discussions différentes. Les gardes couvrent le périmètre des lecteurs et producteurs, i18n, le typage, les métriques, les cycles, la taille et la complexité. |

## Portée des résultats

Les simulations ont utilisé des fournisseurs contrôlés et les vraies bases PostgreSQL et Redis jetables pour les intégrations. Le navigateur a exécuté le bundle optimisé avec des API simulées et des échanges SSE contrôlés. Le responsive et l’accès au clavier ont été observés dans les moteurs de bureau, jusqu’à 320 pixels CSS. ADB n’a détecté aucun appareil connecté. Le clavier tactile physique, le lecteur d’écran, la charge de production et les appels à des modèles facturés restent hors des mesures de cette livraison.

La migration additive a été appliquée à Docker dev après le rejeu jetable. L’API dev a répondu avec la création d’annexes et les exécutions en arrière-plan activées. Elle a accepté le précontrôle CORS du `DELETE` JSON depuis l’origine web de développement. Après un blocage de compilation, le redémarrage du service web a rétabli les réponses HTTP 200 de la configuration web et de la page de connexion. Le signalement du 500 chat du 10 novembre précède les journaux disponibles. L’admission HTTP et le flux SSE ont été vérifiés avec des réponses contrôlées. Le [runbook](../../runbooks/alerts/ConversationLifecycle.md) décrit l’inspection d’une purge en attente.

## Exécutions vérifiées

| Commande ou contrôle | Résultat observé |
|---|---|
| `pytest --no-cov` ciblé sur les conversations, le streaming, le Live, les pièces jointes et les gardes | 912 tests passés et 3 désélectionnés selon les marqueurs CI. Les alertes ont chacune une recette de diagnostic dont les sources de métriques et de journaux sont vérifiées. |
| Intégrations PostgreSQL et Redis jetables avec `pytest --no-cov` | 650 tests passés pour conversations, Live, fichiers, journal, décisions, exports et favoris. Après la correction de la fixture des favoris, la suite complète a été rejouée. Un test supplémentaire de profil SQL du catalogue est passé. |
| Rejeu Linux ciblé des routes de catalogue et d’historique | 69 tests passés avec de nouvelles bases de preuve et les vocabulaires tiktoken vérifiés. Le badge lit les tokens du checkpoint de l’annexe et zéro pour Principale dans ce scénario. |
| Rejeux natifs des cas indirects | 72 tests passés pour les imports, plugins et la récurrence sur Windows. 40 tests repassés après le contrôle de typage. Les 33 scénarios supplémentaires d’import de plugins ont passé sous Windows. Un rejeu Linux des imports de plugins et de skills a passé 75 tests. Sous Linux, 10 tests ont passé pour le retrait de compte et les favoris, et 13 pour les suites Redis de dédoublonnage et de limitation HTTP. Ces rejeux se recouvrent. |
| Compatibilité historique, transactions de fichier et notifications | 46 tests de réinitialisation, historique, badge et fichiers passés sous Linux et sous Windows. Les 15 scénarios de déplacement et de retrait de documents ont passé sur la base et le Redis de test. Les deux tests SMS ont passé sous Windows. Dans le conteneur Linux, chacun va jusqu’à l’écriture de son rapport de preuve, que le montage en lecture seule refuse. |
| Synchronisation Drive et mail | 24 tests passés après correction des fixtures de comptes engagés. Les scénarios conservent les oracles de capacité, de fin de traitement, de remplacement atomique, de perte d’accusé de réception et d’expiration de bail. |
| `task test:frontend` et `task test:frontend:coverage` avant le correctif du brouillon à deux onglets | 20 696 tests passés à chaque exécution. Couverture agrégée de 90,09 % des lignes et 83,27 % des branches avec les seuils atteints. |
| `task test:frontend:coverage` après les derniers correctifs de discussion | Sortie 0, 20 864 tests dans 1 513 fichiers. Couverture de 90,10 % des lignes et 83,31 % des branches. Les seuils agrégés et par périmètre sont atteints. |
| Playwright avec le bundle optimisé final et des API contrôlées | 60 parcours Chromium de régression, 36 parcours de catalogue, de synchronisation et d’accessibilité sur les trois moteurs, et 6 contrôles de disposition Firefox et WebKit. Le parcours à deux onglets attend que le texte ait été enregistré avant de supprimer l’annexe. |
| `task lint:frontend`, `pnpm type-check` et typage des specs de discussion | Sorties 0. Les ratchets d’accessibilité, de hooks, de complexité et d’assertions tiennent. Le TypeScript de l’application a été vérifié sans cache incrémental. |
| `task db:migrate:replay-check` | Une tête Alembic. Rejeu complet, retour à la révision précédente, montée, équivalence du schéma et `alembic check` réussis sur la base jetable. Le rejeu passe aussi avec la révision Workboard ajoutée en parallèle. |
| `task test:alerts` | Règles Prometheus et tests de déclenchement et de retour à la normale réussis sur l’image épinglée. |
| `task mobile:test` | 15 tests des contrats de préparation des shells exécutés avec succès. |
| `task lint:backend` puis Black, Ruff et MyPy strict sur les fixtures corrigées | Sorties 0. Le dernier contrôle global a validé 4 126 modules de production et 134 modules de tests sous MyPy. La correction finale du test de verrouillage a passé les contrôles ciblés. |
| `task lint:docs:preview` | Liens, faits, cartes à six langues et contrôle de langue validés au premier passage. Une exécution ultérieure relève l’entrée manquante de l’ADR-379 dans la carte historique. |

## Vérifications agrégées du dépôt

| Commande | Verdict du passage |
|---|---|
| `task test:backend:unit:fast` | 54 587 réussites, 30 sauts de plateforme et 9 échecs. Les trois suites de contrats mail, filtrage et SMS ont passé leurs 36 tests lors du rejeu sur les sources actuelles. Deux gardes documentaires continuent à lire l’index. |
| `task test:backend:unit:coverage` | 54 361 réussites, 30 sauts, 9 désélections et 8 échecs. Les gardes de recettes d’alerte, d’exposition démo et de durabilité concernés ont passé leur rejeu ciblé. Cette collecte mesure la partie unitaire. |
| `task test:backend:integration` sous Windows | Le watchdog a interrompu le passage dans un test volumineux de recherche de comptes rendus. Le fichier a passé ses 24 tests dans le conteneur Linux avec PostgreSQL et Redis réels. |
| Première collecte Linux avec les marqueurs et la couverture de la tâche d’intégration | 6 244 tests sélectionnés. Le journal enregistre 5 926 réussites, 87 échecs et 5 sauts avant l’arrêt du watchdog. Le verrou attendu de l’upload bloquait sur une connexion jetable dépourvue de la borne du test. Les erreurs de fixtures et les cas résiduels ont fait l’objet des rejeux ciblés ci-dessus. |
| Rejeu de la fin de la collecte Linux, 38 fichiers | Sortie 0, 248 tests réussis et 2 sauts réservés à Windows. Le rejeu inclut les quatre cas de concurrence entre le retrait et l’écriture. |
| Collecte Linux des intégrations rangées parmi les tests unitaires et agents | Sortie 1. Trois préparations PostgreSQL ont été bloquées par le garde réseau unitaire et le test Store attendait la composition de démarrage. Les trois cas SQL ont rejoint la suite d’intégration. Après correction, 6 tests natifs ont passé sous Linux et 15 contrôles de pagination et de Store sous Windows. Le garde réseau unitaire continue à s’appliquer aux cas HTTP hermétiques. |
| `task lint` | Le contrôle documentaire fondé sur l’index a signalé des liens vers des fichiers présents dans le dossier de travail. Le preview confirme zéro lien vivant cassé et zéro chemin vivant obsolète. |

Les journaux détaillés sont dans `output/analysis/secondary-conversations-20261109`.

## Auto-évaluation

| Critère | Verdict |
|---|---|
| Périmètre fonctionnel et décisions | Vérifié sur les entrées normales du chat et de World. Principale conserve les automatismes. Les annexes ont leur historique, leur brouillon et leur badge de session. Les confirmations et les anciennes routes ont des oracles indépendants. |
| Robustesse, sécurité et performances | Les essais vérifient la propriété, la révision, les écritures tardives, le rollback, le rejeu, les abandons de flux et l’absence de requête par discussion dans le catalogue. Les purgeurs exposent un état et un reçu jusqu’à leur clôture. |
| Contexte et coûts | Le compteur lit le checkpoint de la discussion affichée. Les tests vérifient l’attribution historique et l’application des deux plafonds aux entrées Main et annexes. Le plan conserve une seule génération de chat par compte. |
| UX et accessibilité | Le clavier, le focus, axe, les libellés et le reflow ont été vérifiés sur les moteurs de bureau. La validation sur appareil physique et avec lecteur d’écran reste ouverte. |
| Verdict de livraison | Les preuves ciblées et la vérification Docker dev permettent de valider les parcours de discussion éprouvés. Une qualification globale sur un même instantané, avec couverture backend combinée et contrôle documentaire de l’index, reste ouverte. |
