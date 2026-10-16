# Accueil — lot implémenté, validation utilisateur en attente

Branche `codex/ui-accueil`, worktree dédié `ui-accueil`.
Base `wip/base-2026-10-15` : `b5e27a64a61f2e470d18052eeb50c5083dc779bc`.
Le dossier principal et son index appartiennent au travail parallèle ; aucune écriture applicative, installation ou commande Docker depuis ce worktree. Pas de push ni de fusion sans nouvelle autorisation.

## Contrat du lot

Un seul écran : Accueil. Les composants réellement nécessaires font partie du lot. Aucune autre page sélectionnée ne commence avant validation utilisateur.

- Date du jour dans la langue de l’UI et le fuseau du compte, sans année ; minuit, DST, focus et SSR couverts.
- Accueil compact : salutation et point de LIA, Chat puis Services, raccourcis puis radio ; commandes Mon dashboard à leur emplacement actuel.
- Cartes de hauteur cohérente, contenu défilant, aucune réduction des listes reçues ni changement de leurs maxima serveur. Couleurs de domaine discrètes et thèmes préservés.
- Actualisation visible et accessible ; données et focus conservés ; une pression répétée ne génère pas une seconde facture.
- Consommation Période/Total, valeurs exactes et absences distinctes du zéro ; sections ouvertes au départ.
- Mêmes actions, permissions, coûts, navigation, radio et propriétaires média.

## Suivi

- [x] Isoler la couche UI dans le worktree et sauvegarder les 28 fichiers.
- [x] Implémenter les comportements principaux en TDD ; preuves antérieures à l’isolation conservées dans les rapports des sous-tâches.
- [x] Compléter les tests de reprise réseau, erreurs/compte, mutations concurrentes et navigation.
- [x] Passer les gates frontend, i18n, types et couverture sans abaisser de ratchet.
- [x] Vérifier les routes réelles dans un runtime isolé et les parcours hermétiques multi-formats.
- [x] Deux lectures adversariales indépendantes ; corrections de concurrence, reprise réseau, focus et propriétaires média revalidées par tests ciblés. Résultats dynamiques consignés ci-dessous.
- [x] Produire le rapport factuel du lot.
- [ ] Obtenir la validation de l’utilisateur avant le lot suivant.

## Décisions

Ruling: conserver le contenu défilant plutôt qu’un aperçu tronqué et un nouveau lecteur — instruction utilisateur la plus récente — aucune donnée ni action reçue ne doit être supprimée.

Ruling: le nouveau worktree part de l’instantané de l’index, et non du seul HEAD historique de main — les contrats analysés incluent la base en attente — aucune migration ou publication de cette base n’est revendiquée.

Ruling: aucune opération de fusion dans le dossier principal tant que les travaux ne sont pas sauvegardés et leur intégration convenue — les branches partagent la base mais pas les fichiers de travail ni les index.

## Intégration technique

Le lot conserve les dix renderers et les maxima serveur. `BriefingCard` fournit le cadre, la fraîcheur, le contrôle d’actualisation et une région de lecture défilante nommée. Le contenu garde son propriétaire pendant une erreur avec données conservées. La synthèse reste unique et se replie sans démonter son lecteur.

`DashboardDateHeading` lit la langue de l’interface et le fuseau du compte. `HomeConsumptionTable` présente le même payload dans deux colonnes ; aucun compteur n’est estimé et le format financier français suit la charte existante. Les statistiques et limites sont remontées seulement au changement de compte, sans remonter la radio lors des polls.

Les commandes manuelles et les invalidations après mutation ont deux contrats distincts. La sérialisation locale tient compte du vol partagé serveur : une relecture forcée après mutation commence après le build précédent. Les sections modifiées restent réunies jusqu’à une réponse courante. Les révisions de cartes et de texte sont distinctes pour conserver le texte réellement payé et son usage. Les sections masquées ne sont jamais forcées. Aucune génération LLM automatique n’est ajoutée.

L’API additive `acceptData` publie une réussite serveur dans la durée de vie de la requête ; le setter local existant conserve sa sémantique. Données, erreurs et continuations audio sont isolées par compte. Les ressources audio sont annulées/libérées à l’arrêt, au démontage et au changement de compte.

Un prérequis hérité empêchait le build Next.js : la route média déclarait un `Request` optionnel, incompatible avec le garde de types généré. Sa signature attend maintenant la requête HTTP toujours fournie par Next ; ses filtres, caches et comportements restent identiques. Les tests existants utilisent une requête concrète.

## Vérifications et limites

Les scénarios ciblés vérifient des conséquences observables : double appui, réponses inversées, mutations pendant actualisation, vol partagé serveur simulé, reprise d’erreur, données anciennes entre comptes, focus et brouillons, dates civiles/DST, audio différé et consommation exacte. Les tests de query utilisent le vrai client avec transport remplacé ; ceux des mutations conservent les vrais dialogues/formulaires.

Les parcours navigateur chargent le vrai build de production et interceptent toutes les API. Le garde réseau rejette toute requête non déclarée ; aucun fournisseur ni backend réel n’est contacté. Leur matrice couvre des pages reçues pleines, textes longs, tailles d’interface, thèmes, états dégradés, scroll et clavier, avec axe sans exclusion de règle. Les simulations audio ne remplacent pas un essai de périphérique physique.

Le cache Vitest appartient au checkout, même quand les dépendances sont des jonctions. La réduction de complexité est verrouillée dans le ratchet ; aucune exclusion ou couverture minimale n’est abaissée. Les journaux détaillés et captures sont des artefacts locaux hors versionnement.

Résultats mesurés le 15 octobre 2026 dans le worktree :

| Vérification                            | Résultat                                                                                                                                                |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Suite frontend complète avec couverture | 1 046 fichiers, 12 695 tests réussis ; aucun échec ou skip                                                                                              |
| Couverture                              | Statements 87,05 %, branches 81,17 %, fonctions 84,69 %, lignes 88,55 % ; seuils globaux et scopes validés                                              |
| Ratchets                                | Complexité resserrée ; seuils globaux de couverture renforcés dans `apps/web/vitest.config.mts`, sans exclusion supplémentaire                          |
| Lint et types                           | `task lint:frontend` réussi, dont accessibilité, React strict, complexité et TypeScript sans incrémental                                                |
| Langues et hygiène                      | `task lint:i18n` et `task lint:hygiene` réussis                                                                                                         |
| Build réel                              | Build Next.js de production complet, puis serveur autonome isolé à partir des sources du worktree                                                       |
| Parcours Accueil                        | 33/33 réussis sur Chromium, Firefox et WebKit ; 6 formats de 320 à 1 440 px, FR/DE, thèmes et échelle de texte                                          |
| Accessibilité                           | 21 scans axe sur cette matrice, aucun défaut sérieux ou critique ; toutes les règles conservées                                                         |
| Parcours conservés                      | 35 réussites et 1 skip explicite sur 36 cas d’authentification, avatar et radio ; Firefox headless sans sortie audio pour le cas de reprise après flash |
| Revue froide                            | Deux lectures indépendantes et un addendum différentiel ; corrections relues, aucun défaut actionnable résiduel identifié                               |

Après le dernier ajustement de largeur du bouton Chat en desktop, les 9 vérifications différentielles ont réussi : 390, 1 024 et 1 440 px sur les trois moteurs, dont 9 scans axe sans défaut sérieux ou critique. Ce sous-ensemble rejoué ne compte pas comme neuf scénarios uniques supplémentaires. Le rapport local détaille les empreintes des sources, les résultats et les captures.

Un essai initial à deux workers a rencontré un défaut d’intégrité du transport axe existant. Le garde n’a pas été désactivé ; ses tests propres ont réussi, puis la matrice entière a été rejouée avec un worker et a réussi. Cela prouve les parcours sérialisés, sans prétendre résoudre la cause du défaut de transport parallèle.

Les tests remplacent le transport API et audio : aucune génération LLM réelle, aucun compte de production, ni périphérique physique iOS/Android n’est revendiqué. Le compagnon flottant et ses règles de déplacement existantes sont conservés ; sa position peut recouvrir du texte. Aucune capture n’est retouchée pour masquer ce comportement global.

## Coexistence avec le travail parallèle

`feat/tool-data-channel` part du même instantané `wip/base-2026-10-15`. Chaque branche garde son propre worktree et son propre index. Le développement de l’Accueil ne modifie ni le checkout principal, ni ses fichiers indexés, ni les fichiers du travail parallèle.

Avant toute future intégration, enregistrer les travaux de chaque branche, comparer les fichiers communs depuis la base, puis convenir du sens de l’intégration. Le seul HEAD historique de `main` ne représente pas la base en attente. Aucune fusion, aucun push et aucun déploiement ne font partie de la livraison locale de ce lot. Le lot suivant attend la validation utilisateur.
