# Recette manuelle de la sémantique, des ontologies et des MCP

Guide du 7 octobre 2026 pour vérifier dans l'application les ajustements décrits
dans [la qualification](TAXONOMY_QUALIFICATION.md) et les ADR
[335](../architecture/ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md),
[336](../architecture/ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md),
[337](../architecture/ADR-337-Checkpointed-ReAct-Read-Segments-And-Turn-Local-Reuse.md)
et [338](../architecture/ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md).

Cette recette juge le comportement complet, avec les modèles et connecteurs
effectifs de l'instance. Une réponse juste ne démontre pas, à elle seule, chaque
liaison sémantique interne. Les contrôles de structure et les cas difficiles à
provoquer depuis l'interface conservent leurs tests automatisés.

## Préparation

1. Tester une instance qui charge les fichiers modifiés du checkout. Les
   ajustements ont été qualifiés localement ; leur présence en production n'est
   pas certifiée. Si nécessaire, reconstruire ou recharger le backend de recette.
2. Vérifier les modèles effectivement configurés en base pour l'analyse, le
   planner, ReAct et la réponse. Conserver ces modèles pendant les essais ; noter
   les modèles réellement utilisés dans les diagnostics disponibles.
3. Choisir Pipeline dans l'en-tête du chat, puis refaire les parcours en ReAct.
   Garder les mêmes données et dates. Un message envoyé constitue un nouveau
   tour : plusieurs demandes indépendantes sont regroupées dans le même message
   lorsqu'il faut observer leurs dépendances ou leur exécution commune.
4. Utiliser des objets identifiables par le préfixe `LIA SEM`. Pour les envois et
   invitations, employer une adresse que le testeur contrôle. Observer les
   brouillons avant de les confirmer ; les cas de refus doivent rester sans effet.
5. Activer le panneau de débogage si l'accès est autorisé dans l'instance.
   L'administrateur doit permettre cet accès pour un utilisateur ordinaire.
   Noter le routage, les outils, les étapes, les budgets et les éventuelles passes
   Recovery. Le panneau n'expose pas toutes les preuves de champs ni tous les
   arguments ; un contrôle de ceux-ci exige une trace backend appropriée.

Faire un premier passage, puis deux répétitions des cas ambigus ou complexes.
Garder les échecs dans le relevé : ne pas remplacer silencieusement le prompt
jusqu'à obtenir une réponse favorable.

## Données d'essai

`D` désigne demain dans le fuseau du compte. Noter sa date ISO avant les essais,
puis remplacer `DATE_D` dans les prompts. Utiliser une date encore couverte par
le fournisseur météo. Les dates d'un scénario doivent rester cohérentes entre
son événement, sa demande et son résultat attendu.

| Objet | Donnée contrôlée |
|---|---|
| Contact `Nancy SEM` | Adresse postale `20 quai Claude Bernard, Lyon, France` ; adresse e-mail contrôlée |
| Contact `LIA SEM Sans Adresse` | Aucune adresse postale ; ne pas fournir d'adresse de remplacement dans la demande |
| Deux contacts `Alex SEM` | Même nom affiché, adresses e-mail distinctes ; ne pas les identifier comme une même personne |
| Deux contacts `LIA SEM Liste 01` et `LIA SEM Liste 02` | Seulement ces deux contacts contiennent `LIA SEM Liste` |
| Événement `LIA SEM Réunion` | `D`, de 10 h à 11 h, lieu `20 quai Claude Bernard, Lyon, France` |
| Événement `LIA SEM Sans Lieu` | `D`, sans lieu ni adresse |
| Événement `LIA SEM Fuseau` | `D`, à 00 h 30 dans `Europe/Paris`, compte également configuré dans ce fuseau |
| Fichier Drive `LIA SEM Budget.pdf` | Fichier réel dans un dossier `LIA SEM Archives` ; noter les propriétaires et leurs e-mails si le fournisseur les expose |
| Document importé dans un espace | Texte distinct : `CODE_ESPACE=ORANGE42` |
| Fichier Drive distinct | Texte : `CODE_DRIVE=BLEU17` |
| E-mails d'essai | Messages reconnaissables par leur objet `LIA SEM` et leur date ; au moins trois pour tester une liste limitée |

Les données peuvent être préparées dans leurs applications ou interfaces de
gestion. Une fonctionnalité sans connecteur ou données adéquates reçoit le statut
« non testable » ; ce n'est pas un succès ni une régression.

## Parcours prioritaires — Pipeline puis ReAct

| ID | Prompt ou manipulation | Résultat attendu et critère d'échec |
|---|---|---|
| N01 — ville | « Donne la météo pour DATE_D à Nancy, France. Nancy désigne ici la ville. » | Lieu Nancy et date demandée. Aucune adresse du contact substituée. |
| N02 — personne | « Donne la météo pour DATE_D chez Nancy SEM. Retrouve son adresse postale complète dans mes contacts. » | Le contact lyonnais est retrouvé et sa localisation utilisée. Une météo pour Nancy-ville est un échec. Une carte météo intitulée seulement « Lyon » ne prouve ni ne réfute l'utilisation de l'adresse complète : vérifier la trace si nécessaire. |
| N03 — source absente | « Donne la météo chez LIA SEM Sans Adresse en utilisant son adresse postale dans mes contacts. » | Adresse manquante signalée ou clarification pertinente. Aucun lieu déduit arbitrairement du nom. |
| N04 — identité ambiguë | « Retrouve Alex SEM et prépare-lui un e-mail intitulé LIA SEM Identité. » | L'identité et l'adresse choisies sont justifiées ou une clarification est demandée. Aucun mélange des deux contacts. Vérifier le destinataire du brouillon puis refuser. |
| N05 — agenda vers trajet | « Retrouve LIA SEM Réunion et calcule un trajet à pied depuis 1 place Bellecour, Lyon, jusqu'au lieu de ce rendez-vous. » | Destination issue du bon événement, mode à pied conservé. Une destination inventée ou celle d'un autre événement est un échec. |
| N06 — agenda vers météo | « Retrouve LIA SEM Réunion et donne la météo au lieu et à la date de cet événement. » | Deux résultats utiles : événement identifié, météo à son lieu et à sa date. La date du jour ne remplace pas celle du rendez-vous. Le rôle principal attendu est météo, avec agenda comme préalable ; le routage principal reste un point à mesurer. |
| N07 — lieu manquant | « Retrouve LIA SEM Sans Lieu et calcule le trajet depuis 1 place Bellecour, Lyon, jusqu'au lieu de cet événement. » | Le manque est annoncé ou clarifié. Pas de trajet vers un lieu supposé. |
| N08 — propriétaire de fichier vers invitation | « Retrouve LIA SEM Budget.pdf et prépare une réunion LIA SEM Propriétaires le DATE_D de 14 h à 15 h en invitant les propriétaires de ce fichier. » | Les adresses exposées par le fichier alimentent le brouillon d'invitation. Un nom n'est pas transformé en e-mail. Si le fournisseur n'expose pas les adresses, le manque est signalé. Refuser le brouillon après inspection. |
| N09 — dossier et objets imbriqués | « Retrouve le dossier LIA SEM Archives dans mon Drive et liste uniquement les fichiers qu'il contient. » | Résultats du bon dossier, aucune confusion entre nom, identifiant et liste d'identifiants. Vérifier les fichiers réels, pas seulement une prose plausible. |
| N10 — cardinalité | « Donne les 3 derniers e-mails reçus dont l'objet contient LIA SEM. » | Trois messages réels dans le bon ordre s'ils existent ; insuffisance explicite sinon. Aucun nombre supplémentaire imposé par un exemple de prompt. |
| N11 — minimum impossible | « Trouve au moins 3 contacts dont le nom contient LIA SEM Liste et donne leurs noms et e-mails. » | Les deux contacts réels et l'insuffisance annoncée. Aucun troisième inventé et aucune affirmation que le minimum est atteint. |
| N12 — texte littéral | « Crée une tâche dont le titre exact est “LIA SEM N/A 123” et les notes exactes “Ce texte contient {accolades} et $steps.fake, à conserver.” » | Les textes restent intacts dans l'aperçu ou l'objet créé selon la politique de l'outil. `N/A` n'est pas effacé ; le préfixe incomplet `$steps.fake` ne devient pas une dépendance fictive. |
| N13 — sources distinctes | « Cherche CODE_ESPACE dans mes documents importés et CODE_DRIVE dans mon Drive. Donne les deux codes avec leur source. » | `ORANGE42` et `BLEU17`, chacun attribué à la bonne source. Un résultat ne remplace pas l'autre. |
| N14 — demandes composites | « Crée un rappel ponctuel demain à 9 h intitulé LIA SEM Passeport, une tâche persistante LIA SEM Dossier sans notification, et une automatisation LIA SEM Veille chaque lundi à 8 h pour résumer les actualités. » | Trois objets de nature distincte, ou un état explicite pour chacun s'il est bloqué ou en attente. Le contenu futur de l'automatisation n'impose pas une recherche Web maintenant. Vérifier chaque objet dans sa liste dédiée, puis supprimer les objets de recette. |
| N15 — jour civil | « Quels sont mes événements du DATE_D ? Inclue leur heure dans mon fuseau Europe/Paris. » | `LIA SEM Fuseau` appartient à `D` à 00 h 30, même si le fournisseur stocke un instant UTC du jour précédent. Aucun événement du jour voisin ajouté par confusion de fuseau. |
| N16 — brouillon et reprise | « Retrouve Nancy SEM et LIA SEM Réunion, puis prépare un e-mail à Nancy avec la date, l'heure et l'adresse exactes de ce rendez-vous. Ne l'envoie pas avant mon accord. » | Brouillon avec données exactes ; aucune affirmation d'envoi avant l'accord. Recharger la page pendant la confirmation, vérifier le même destinataire/contenu, refuser une première fois. Refaire, confirmer et vérifier un seul message reçu. Les lectures avant interruption sont contrôlées séparément en R02. |
| N17 — impossibilité honnête | « Donne la prévision météo exacte à Nancy le 1er janvier 2036. Si elle est indisponible, indique cette limite sans inventer de température. » | Indisponibilité expliquée. Une climatologie ou une autre date n'est pas présentée comme la prévision exacte. En ReAct, une vraie lacune peut déclencher une reprise bornée ; zéro passe n'est pas un échec automatique si l'impossibilité a été reconnue sans appel défaillant. |

Pour N02, N05, N06, N08 et N09, comparer les valeurs des cartes et des objets réels
aux sources. Un simple voyant « VALID » du Semantic Validator ne suffit pas : ce
verdict est informatif, et l'exécution/résultat doit être vérifié.

Refaire N10 et N11 avec « trois » en lettres comme variante de compréhension.
Le résultat fonctionnel attendu reste identique. Limite actuelle :
[`_constraints_anchored`](../../apps/api/src/domains/agents/analysis/requested_outcomes.py)
exige la quantité en chiffres dans la citation et la demande pour conserver une
contrainte `min_count`. Une réponse correcte avec « trois » ne prouve donc pas
que ce contrôle interne a été exercé ; cette variante identifie une complétion
encore nécessaire.

## ReAct — efficacité et interruptions

Ces tests sont conditionnels aux appels réellement choisis par le modèle. La
lecture des contacts, de l'agenda, des fichiers, des routes et de certaines données
météo dispose de contrats explicites ; toutes les lectures ne sont pas admissibles
au parallélisme ou à la réutilisation. Une délégation MCP opaque ne l'est pas.

| ID | Essai | Attendu et preuve nécessaire |
|---|---|---|
| R01 — même tour | « Dans cette seule demande, consulte deux fois Nancy SEM avec les mêmes paramètres de recherche, puis compare les résultats. » | Si deux appels identiques admissibles sont effectivement émis dans leur durée de validité, sans modification ni rafraîchissement demandé entre eux, une seule invocation native peut fournir les deux réponses correctement associées. Si le modèle fait une seule lecture, le cache n'a pas été exercé. Les seules durées ou réponses identiques ne le prouvent pas ; il faut un compteur d'invocations ou un test instrumenté. |
| R02 — reprise | Faire N16 en ReAct ; relever les lectures déjà terminées, recharger à la confirmation, puis confirmer. | Les lectures terminées avant l'interruption ne sont pas rejouées ; l'envoi a lieu une fois. Recharger le navigateur ne démontre pas à lui seul une reprise sur un autre worker. Contrôler les invocations dans une trace ou un serveur instrumenté. |
| R03 — mutation | Dans la même demande : « Lis la note actuelle de Nancy SEM, remplace-la par LIA SEM Note Nouvelle, puis relis-la et donne la valeur réellement enregistrée. » | Après une mutation exécutée, la nouvelle valeur est relue, sans réutilisation de l'ancienne preuve. Ne pas traiter un aperçu de modification comme une écriture réalisée. Si l'approbation termine ce tour avant la relecture, le mécanisme n'a pas été exercé dans ce parcours : compléter par le test instrumenté. |
| R04 — lectures indépendantes | « Donne la météo actuelle à Lyon, Bordeaux, Nantes et Toulouse, avec une ligne par ville. » | Les quatre résultats correspondent aux quatre villes. Si le modèle émet ensemble des lectures admissibles, leurs invocations peuvent se chevaucher sous la borne du code. Des appels séquentiels choisis par le modèle ne constituent pas une défaillance du moteur. Une réponse rapide ne prouve pas le parallélisme : relever début/fin des invocations. |
| R05 — budget | Sur une instance de recette avec un budget ReAct volontairement réduit, demander plusieurs recherches indépendantes jusqu'à provoquer un arrêt par budget. Puis envoyer une demande simple. | Le premier tour dit ce qui a été obtenu et ce qui manque, sans promettre des appels qui ne s'exécuteront pas. Les appels abandonnés sont clos et la demande suivante reste utilisable. Si aucun arrêt par budget n'a eu lieu, marquer le cas non exercé. Restaurer le budget de recette ensuite. |

Répéter une question dans deux messages ne teste pas R01 : le cache de résultats
concerné est limité à un tour. Une économie d'appels au fournisseur peut aussi
venir d'un autre cache ; il faut distinguer appel du modèle, invocation de l'outil
et requête externe.

## MCP — selon les serveurs disponibles

Pour une preuve reproductible, utiliser des serveurs contrôlés A et B, avec
identifiants distinctifs `A-001` et `B-001`. Pour un MCP tiers non modifiable,
adapter uniquement les cas réellement possibles et noter les autres non testables.
Le mode itératif du serveur est distinct du mode Pipeline/ReAct du chat et dépend
aussi de son activation sur l'instance.

| ID | Manipulation et prompt | Attendu |
|---|---|---|
| M01 — homonymes | Donner à A et B des noms proches, par exemple `Catalogue Polaris` et `Catalogue-Polaris`. Demander « Dans Catalogue Polaris uniquement, lis A-001 », puis la fiche de B dans l'autre connexion. | Bon serveur et bon RPC ; aucune confusion entre alias proches. Vérifier les identifiants distinctifs et, si possible, le journal du serveur. |
| M02 — désactivation | Désactiver A dans les paramètres adaptés à son origine, garder B actif. Demander A-001 uniquement dans A, puis B-001 dans B. | A indisponible, B toujours accessible. Pas de repli silencieux d'A vers B. Le serveur désactivé peut rester visible dans les paramètres : c'est l'offre à l'assistant qui compte. |
| M03 — compte | Répéter une lecture depuis deux comptes dont les connexions renvoient des marqueurs différents. | Aucune donnée ni capacité du premier compte dans le second. Utiliser deux sessions de navigateur séparées. |
| M04 — contrat neuf | Ajouter un outil au serveur ou rendre un paramètre obligatoire. Cliquer « Tester la connexion », puis demander la nouvelle capacité. Conserver auparavant une description personnelle ancienne. | Contrat actuel utilisé, nouvelle capacité accessible ; le texte personnel stocké n'est pas réécrit arbitrairement. La découverte forcée reste locale au worker : une instance multiworkers nécessite de vérifier le worker ou l'expiration effective de chacun. |
| M05 — expiration active | Modifier le catalogue, rester actif sur le serveur et attendre l'âge maximal effectif depuis sa dernière découverte. Faire une demande après expiration. | La découverte ne reste pas indéfiniment ancienne parce que le serveur est utilisé. Prendre la configuration effective de `MCP_USER_POOL_TTL_SECONDS`, pas une durée supposée. L'UI seule ne montre pas forcément l'âge du cache. |
| M06 — valeurs structurées | Serveur contrôlé : sortie structurée avec une liste de personnes, e-mail nullable et date ISO déclarée. Renvoyer une adresse correcte, puis `null`, puis une valeur mal formée. Demander les valeurs exactes et préparer une action seulement avec les valeurs valides. | Liste et valeurs non vides exploitées ; absence non inventée ; valeur mal formée conservée comme donnée reçue et non présentée comme une date/adresse valide. Vérifier le contrat déclaré et les observations backend. Le nom d'un champ seul ne lui donne pas une signification métier. |
| M07 — résultat partiel | Serveur contrôlé renvoyant seulement deux éléments, avec un marqueur de résultat partiel. Demander au moins 3 éléments puis une liste exhaustive. | Les limites sont dites ; deux éléments ne deviennent pas trois et une page partielle n'est pas annoncée exhaustive. Le cumul entre pages ne possède pas encore de preuve générale d'identité/pagination. |
| M08 — visibilité | Un serveur contrôlé renvoie zéro outil, ou uniquement des outils réservés à son application. Tester sa connexion et demander une lecture par l'assistant. | Aucun domaine ou proxy assistant fantôme. Une connexion valide et des outils bruts affichés dans les paramètres ne prouvent pas qu'ils sont offerts au modèle. |
| M09 — capacité omise autrefois | Serveur avec plusieurs capacités courtes, dont une située après les premières dans sa liste ; demander explicitement cette capacité. | Elle reste atteignable si elle est réellement construite et autorisée. Une longue liste peut avoir une description résumée : l'omission doit être annoncée, pas confondue avec l'absence de l'outil. |
| M10 — cible et confirmation | « Dans A, crée un objet d'essai nommé LIA SEM MCP-01. » Refuser, puis refaire et confirmer. Répéter en français et anglais, éventuellement chinois. | Carte avec le vrai serveur et l'action/RPC, sans hash d'alias comme nom humain. Ponctuation adaptée à la langue. Refus : aucune création ; confirmation : une seule création dans A et aucune dans B. Compter dans le serveur. |
| M11 — délégation | Sur un serveur itératif, provoquer un résultat explicitement partiel ou un rapport ne contenant aucune observation d'action vérifiable. | Le rapport n'est pas une preuve de chaque opération annoncée ; aucune reprise de lecture ne doit rejouer automatiquement une délégation opaque. Distinguer cela des décisions de la boucle et des effets réellement observés côté serveur. |

Les collisions forcées de préfixes UUID, une substitution de cible interne, l'échec
d'import du proxy, les courses de rafraîchissement et les lectures terminées
pendant une mutation ne sont pas tous provoquables depuis l'UI. Les régressions
[d'identité](../../apps/api/tests/unit/infrastructure/mcp/test_callable_identity.py),
[de cible](../../apps/api/tests/unit/infrastructure/mcp/test_task_identity.py),
[de publication](../../apps/api/tests/unit/infrastructure/mcp/test_admin_catalogue_publication.py)
et [de reprise](../../apps/api/tests/unit/domains/agents/nodes/test_react_checkpointed_execution.py)
complètent cette recette.

## Balayage des familles de la taxonomie

Le [corpus indépendant](../../apps/api/scripts/semantic_simulation/taxonomy_corpus.py)
reste la référence pour les attentes de routage. Les demandes ci-dessous servent
de balayage fonctionnel, avec les capacités actives du compte. Une information
déjà disponible dans le contexte vérifié n'impose pas un nouvel appel d'outil.

| Famille | Demande courte adaptée à ses données |
|---|---|
| Activité | « Quelles actions as-tu effectuées pour moi cette semaine ? » |
| Automatisation | « Crée une automatisation LIA SEM hebdomadaire le lundi à 8 h. » |
| Brave | « Utilise Brave Search pour chercher des articles sur les trains de nuit. » |
| Navigateur | « Ouvre avec le navigateur interactif une page accessible que je te fournis et lis son titre. » |
| Calcul | « Calcule exactement 17 × 23 + 8. » Résultat : 399. |
| Contacts | « Quelle adresse e-mail est enregistrée pour Nancy SEM ? » |
| DevOps | « Lis les logs API de mon serveur connecté, sans redémarrer ni modifier quoi que ce soit. » |
| Documents importés | « Retrouve CODE_ESPACE dans mes espaces de documents. » |
| Génération de document | « Crée un CSV téléchargeable avec Produit, Quantité et la ligne Pommes, 3. » |
| E-mails | « Retrouve mon dernier e-mail dont l'objet contient LIA SEM. » |
| Agenda | « Quels rendez-vous ai-je demain ? » |
| Drive | « Retrouve LIA SEM Budget.pdf dans mon Drive. » |
| Galerie de fichiers générés | « Retrouve le CSV déjà généré ; ne crée aucun nouveau fichier. » |
| Santé | « Combien de pas mes données connectées ont-elles enregistrés hier ? » |
| Hue | « Liste mes ampoules et leur état actuel. » |
| Image | « Modifie le fond de cette image en forêt enneigée. » Joindre une image de test ; vérifier l'édition demandée. |
| Journal LIA | « Dans ton propre journal, retrouve une directive existante sur notre manière de travailler. » |
| Mémoire | « Dans tes souvenirs de nos conversations, retrouve un fait personnel connu que je précise. » |
| Pairs | « Liste mes connexions acceptées aux autres utilisateurs LIA. » |
| Perplexity | « Utilise Perplexity pour rechercher des informations avec leurs sources. » |
| Lieux | « Trouve les boulangeries près de la place Bellecour à Lyon. » |
| Rappel | « Rappelle-moi une seule fois demain à 9 h de LIA SEM Passeport. » |
| Trajet | « Calcule un trajet à pied entre les deux adresses de N05. » |
| Paramètres | « Quel fuseau horaire est enregistré dans mes paramètres LIA ? » |
| Tâche | « Ajoute une tâche LIA SEM persistante, sans notification. » |
| Téléphonie | « Prépare un appel au numéro de test que je contrôle. » Selon les permissions et la politique de confirmation réellement actives. |
| Workboard | « Montre mes tickets ouverts. » |
| Météo | « Quelle météo prévoit-on demain à Lyon ? » |
| Page précise | « Lis le contenu de cette URL précise que je fournis. » |
| Recherche Web | « Compare plusieurs sources Web sur les trains de nuit. » |
| Wikipédia | « Lis le résumé de l'article Wikipédia sur Ada Lovelace. » |

Tester aussi les séparations : mémoire/journal, documents importés/Drive/galerie,
contacts/pairs, tâche/rappel/automatisation et recherche Web/lecture d'une URL.
Une source différente peut être un repli pertinent, mais il doit être annoncé et
respecter une restriction explicite de la demande.

## Relevé et verdict

Pour chaque essai, noter : ID, mode, numéro de répétition, date/fuseau, modèle
effectif disponible, prompt exact, sources préparées, outils observés, réponse,
objets réellement créés, état de confirmation et identifiant de trace disponible.

- **Réussi** : résultat conforme aux sources, toutes les parties demandées obtenues
  ou leur limite exacte déclarée selon l'oracle du cas, effets réels corrects.
- **Échec** : mauvaise personne, source, date, valeur ou cible ; partie oubliée ;
  résultat partiel présenté comme complet ; effet absent, supplémentaire ou dupliqué.
- **Non exercé** : le parcours n'a pas déclenché le mécanisme visé, par exemple une
  seule lecture dans R01 ou aucune interruption dans R02.
- **Non testable** : connecteur, droits, données ou contrôle serveur nécessaires
  indisponibles. Conserver cette limite dans le bilan.

Ne pas additionner un taux de réussite fonctionnelle et un taux de mécanismes
internes vérifiés. La couverture des annotations, des types, des propriétés et
des dépendances structurelles se contrôle séparément avec `task semantic:audit`
et `task semantic:simulate`. La seule UI ne certifie pas leur exhaustivité.
