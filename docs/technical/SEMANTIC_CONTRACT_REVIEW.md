# Revue des contrats sémantiques et des ontologies

Revue du 6 octobre 2026 dans le checkout de travail de LIA. Les corrections
portent sur les manifestes, l'ontologie et leurs lecteurs effectifs dans le
planner, le catalogue, l'initiative et ReAct. Elles ne nécessitent aucune
migration de données et n'ont pas été déployées en production.

Les décisions architecturales issues de cette revue et de sa qualification sont
consignées dans [ADR-335](../architecture/ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md)
(preuves et dépendances) et [ADR-338](../architecture/ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md)
(contrats et identités MCP). Les mesures ci-dessous conservent leur périmètre historique.

## Périmètre et méthode

L'inventaire hors ligne parcourt toutes les familles natives, y compris les
outils optionnels et les manifestes séparés : disponibilité calendrier,
person360, pièces jointes, préférences e-mail, envoi à soi-même et outils
applicatifs présents dans le checkout. Les réexports sont dédupliqués ; deux
déclarations différentes portant le même nom constituent une erreur.

Les annotations sont vérifiées contre les modèles, constructeurs de résultats,
exemples de références et fixtures de payloads. L'ontologie est contrôlée sur
ses parents, propriétés, références, inverses et cycles. Les lecteurs sont
testés dans le contexte réel d'un catalogue par requête, y compris un catalogue
explicitement vide et des contrats MCP différents entre comptes.

Les schémas MCP sont analysés à leur découverte. Ce premier inventaire ne fait
aucun appel aux comptes ou aux serveurs MCP de production, ni aux fournisseurs
payants. La [campagne complémentaire de simulations](SEMANTIC_SIMULATION_RESULTS.md)
ajoute les reproductions métier et une évaluation bornée des modèles DB locaux.

## Corrections significatives

| Constat | Correction et conséquence |
|---|---|
| L'inventaire ne connaissait pas toutes les familles et les manifestes séparés | Collecteur commun complet ; les contrôles d'intégrité et la mesure de couverture utilisent le même inventaire |
| Des dates, identifiants, statuts et attributs récents étaient sans annotation | Types distincts ajoutés pour les valeurs vérifiées ; feuilles de payloads déclarées dans les familles e-mail, calendrier, contacts, fichiers, tâches, tickets, santé, activité, mémoire, journal et autres familles récentes |
| Certains chemins ou types JSON ne correspondaient pas au résultat réel | Correction des propriétaires de fichiers, coordonnées, pays, mesures météo formatées, horodatages et propriétés conditionnelles ; retrait des chemins fictifs |
| Un nom de label pouvait être assimilé à son identifiant, une pièce jointe à un fichier | Vocabulaires séparés ; aucune conversion implicite entre ces identifiants |
| Les liens éditoriaux et le registre global pouvaient omettre ou réintroduire des outils | Producteurs et consommateurs dérivés des manifestes disponibles du compte ; un catalogue vide reste vide |
| Les providers utiles pouvaient être exclus par une limite arbitraire de chemins | Protection des sources réellement disponibles, de lecture seule, utiles à un autre domaine actif |
| La recherche de références ignorait les MCP utilisateurs et la forme de la valeur | Références sur les sorties disponibles, correspondance de type exacte et vérification scalaire/tableau/objet ; sélection explicite d'un élément ou construction d'un tableau contenant la référence scalaire |
| Les suggestions de sources n'avaient pas de lecteur dans la révision de plan | Sources concrètes injectées dans le contexte de replanification |
| Le garde de paramètres ne lisait pas les objets MCP imbriqués | Contrôle des feuilles explicitement annotées avec chemin précis dans l'erreur |
| Le nettoyage pouvait effacer un contenu légitime tel que « N/A » | Les types de contenu conservent les valeurs littérales de la personne |
| Une annotation Text pouvait relier le corps d'un e-mail au titre d'une tâche | Text et QuantitativeValue restent descriptifs ; ils ne créent pas de dépendance ni de substitution automatique |
| outputSchema et structuredContent MCP étaient perdus ou remplacés par du texte | Conservation des contrats déclarés et des résultats structurés exacts ; texte auxiliaire conservé ; projection ReAct paginée sans duplication des collections |
| Les propriétés et relations de l'ontologie avaient dérivé | Références et inverses validés ; registre protégé des modifications accidentelles par ses exports et ses vues |

Les adresses e-mail des propriétaires de fichiers justifient désormais le
rapprochement `file → event`, notamment pour retrouver les participants d'une
réunion. Une proximité sémantique n'autorise toujours pas une mutation : les
contrôles de permissions et d'approbation existants s'appliquent.

## Mesure de couverture

La mesure compare les mêmes outils natifs. Le point de départ est reconstruit
depuis leurs manifestes avant cette revue, en conservant les travaux applicatifs
déjà présents au début. Le nombre de sorties augmente lorsque des feuilles
réelles jusque-là absentes du manifeste deviennent adressables.

Instantané mesuré le 6 octobre 2026 :

| Mesure | Avant revue | Après revue |
|---|---:|---:|
| Outils natifs inventoriés | 130 | 130 |
| Paramètres annotés | 138 / 393 (35,1 %) | 212 / 393 (53,9 %) |
| Sorties annotées | 152 / 557 (27,3 %) | 387 / 674 (57,4 %) |
| Types de l'ontologie | 101 | 121 |
| Propriétés déclarées de l'ontologie | 21 | 43 |

L'inventaire final emploie 93 types distincts. Il ne comporte aucune annotation
inconnue et la validation des références et de la hiérarchie ne trouve aucune
erreur. Les planchers de couverture sont relevés dans les tests pour empêcher
la disparition silencieuse de ces annotations.

Un outil applicatif ajouté par le chantier concurrent pendant la qualification
porte la dernière lecture à **131 outils**, **214/394 paramètres annotés** et
**391/675 sorties annotées**. Le tableau conserve l'instantané sur le périmètre
de comparaison ; la commande d'audit reste la référence pour le checkout courant.

Les résultats détaillés et les champs restant sans annotation sont produits
par la commande ci-dessous. Les pourcentages mesurent les annotations sur les
champs déclarés, pas l'exactitude ou l'autonomie du modèle. Une annotation
générique de contenu n'est pas comptée comme preuve de relation métier.

## Contrats MCP utilisateurs

Les outils de chaque personne sont imprévisibles avant leur connexion. Le
registre exploite donc les schémas publiés par les serveurs du compte, sans
catalogue universel de leurs objets. Les extensions sémantiques reconnues et
les formats explicites e-mail, URI, date et date-heure fournissent une preuve
déclarative. Un champ nommé `id`, `address` ou `query` ne suffit pas.

Les références locales sont bornées, les alternatives de schéma conservées et
les feuilles incertaines ne sont pas annoncées comme des chemins certains.
Les sorties sans schéma restent inconnues. Les clés incompatibles avec le DSL
de références ne sont pas proposées au planner. Les données des serveurs
restent du contenu externe, y compris après leur projection pour ReAct.

## Limites conservées

- Les booléens, compteurs, contrôles d'exécution, requêtes libres, conteneurs
  arbitraires et paramètres acceptant plusieurs significations peuvent rester
  sans type sémantique. Le JSON Schema continue de décrire leur forme.
- Les unités et représentations de tous les types historiques ne sont pas
  converties universellement. Les cas vérifiés, comme les dates calendaires et
  les timestamps Unix, sont distingués ; aucun moteur de conversion ou de
  raisonnement OWL n'a été ajouté.
- La fermeture du catalogue garantit la présence d'une source déclarée ; elle
  ne prouve pas qu'un futur graphe arbitraire de dépendances est exécutable.
- Les compositions MCP, nullables et alternatives ont été éprouvées et
  corrigées dans la campagne complémentaire. La fidélité du dialecte transmis
  aux différents fournisseurs reste une limite distincte, notamment pour le
  convertisseur Gemini installé ; les profondeurs de références et de
  publication restent bornées.
- Un schéma déclaré par un serveur n'est pas une preuve que tous ses résultats
  futurs le respecteront. La pertinence des réponses et les comportements
  réels des comptes de production ne sont pas mesurés par les tests unitaires.

## Reproduire la revue

Depuis la racine du dépôt :

```powershell
task semantic:audit
```

Le rapport `.tmp/semantic-contracts.json` contient tous les outils et champs,
les formes JSON, les types imbriqués, les producteurs et consommateurs par
chemin, les annotations inconnues et les erreurs d'ontologie. Il ne dépend
ni d'une base de données, ni des feature flags, ni de serveurs MCP connectés.

Les tests spécifiques se trouvent dans
`apps/api/tests/unit/domains/agents/semantic/`,
`apps/api/tests/unit/semantic/`, les tests de fermeture du catalogue et
`apps/api/tests/unit/infrastructure/mcp/test_semantic_schema.py`.

## Qualification du checkout

Dernière qualification du 6 octobre 2026 :

| Contrôle | Résultat |
|---|---|
| Suite consolidée sémantique, MCP, contrats de résultats, fermeture, initiative et ReAct | **1 310 tests passent**, aucun avertissement |
| Vérification MyPy du périmètre sémantique/MCP et des helpers | **36 sources passent** |
| Ruff et Black des fichiers de cette revue | Passent avec la configuration du backend |
| `task lint:frontend` | Passe : ESLint, ratchets et TypeScript ; accès Windows local nécessaire |
| `task lint:docs:preview` | Passe : aucun lien vivant cassé, aucun document orphelin, faits et cartes cohérents |
| `task lint:cc` et `task lint:cycles` | Passent, aucune baseline relevée |
| Hygiène, lockfiles, parité CI, i18n, observabilité et dette MyPy | Passent |
| `task test:backend:unit:fast` | **37 416 passent, 11 échouent, 150 ignorés** |
| `task lint` et MyPy global | Qualification globale incomplète sur le chantier applicatif concurrent |

Les échecs de la suite globale concernent les nouvelles capacités applicatives :
famille `application_action` absente des labels d'effets et de l'expressivité,
contrat des feature flags, table `application_commands` non classifiée,
`setting_agent` non classifié pour la génération de skills, import direct de
`pydantic_core` non déclaré et handler d'exception vide dans le domaine
applicatif. Les vérifications de démarrage refusent à raison la famille dont
les labels sont incomplets. Le MyPy global signale également une signature
incompatible dans `draft_executor_types.py`, modifié par ce chantier.

Le garde documentaire sur l'index voit les liens vers les nouveaux documents
non stagés comme cassés, y compris celui de cette revue. La prévisualisation
les valide tous : ce point nécessite le staging lors de la livraison, aucune
suppression de liens ni réduction du contrôle. Aucun fichier n'a été stagé,
commité ou poussé par cette revue. Les contrôles globaux ne sont donc pas
présentés comme verts, et aucune qualification de production n'est revendiquée.

La référence du système est le [README sémantique](../../apps/api/src/domains/agents/semantic/README.md).
