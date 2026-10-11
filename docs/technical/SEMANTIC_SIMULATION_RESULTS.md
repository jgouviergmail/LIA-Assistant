# Simulations factuelles des contrats et décisions sémantiques

Campagne du 6 octobre 2026, complément de la
[revue des contrats](SEMANTIC_CONTRACT_REVIEW.md). Elle combine des oracles métier
indépendants, les composants réels de LIA et une petite évaluation des modèles
configurés dans la base locale. Les corrections restent dans le checkout ;
aucun déploiement, commit ou push n'a été effectué.

## Ce qui a effectivement été mesuré

Les simulations sans fournisseur suivent les manifestes, constructeurs de
résultats, fermeture du catalogue, gardes, résolveur de références, Jinja,
adaptateurs MCP et projection ReAct réels. Les réponses externes sont fictives.
Les attentes sont des valeurs métier : adresse exacte, jour civil, unité,
identifiant distinct, forme du lot, présence d'une source disponible et
conservation du résultat canonique. Un modèle simulé ne sert jamais de preuve
de décision autonome.

La campagne comporte des cas positifs et négatifs : valeur absente, union
hétérogène, branche discriminée, objet fermé, champ obligatoire nullable,
tableau imbriqué, compte sans outil, champ optionnel et fournisseur désactivé.
Les premiers échecs sont conservés dans les journaux de travail ; le corpus a
ensuite été étendu. Les nombres initiaux et finaux ne décrivent donc pas un
échantillon identique.

## Défauts reproduits et corrigés

| Défaut observé | Oracle et correction |
|---|---|
| Une référence dans un objet à l'intérieur d'une liste restait littérale | Un lot de destinataires doit contenir des adresses concrètes. Le résolveur parcourt maintenant les listes et objets imbriqués, sans modifier le plan ni réinterpréter les données externes obtenues par une référence |
| Le header e-mail était proposé comme adresse de participant | `"Lovelace, Ada" <ada@example.test>` reste un header en `from` ; `from_email` fournit une adresse validée, nullable si illisible. Le lien vers `attendees` sélectionne cette valeur canonique |
| Une date météo civile changeait de jour à l'ouest de UTC | `2026-10-07` reste le 7 à New York et Honolulu. Un timestamp explicite continue de désigner un instant converti dans le fuseau |
| Des prérequis obligatoires imbriqués n'ouvraient pas leur source | La fermeture lit les feuilles obligatoires et les compositions, sans transformer une feuille optionnelle ou une branche incertaine en prérequis obligatoire |
| Les compositions et positions de tuples échappaient au garde | Les branches prouvées et les positions effectivement fournies sont contrôlées ; une alternative valide ne reçoit pas les contraintes de sa voisine |
| L'ontologie annonçait une source indisponible ou une adresse absente du contrat | Planner, ReAct et initiative utilisent les annotations des contrats disponibles ; ReAct transmet aussi les noms des outils effectivement liés après sélection |
| Un registre explicitement injecté mais vide était remplacé par le global | L'injection teste désormais l'absence avec `is None`, et conserve un registre vide |
| Les MCP itératifs masquaient les contrats individuels à ReAct | Les contrats des individus sont accessibles dans le contexte du compte et de leur tâche parente, sans les ajouter au catalogue du planner |
| `allOf`, siblings de `$ref`, `const` et contraintes imbriquées étaient réduits | Les contrats composés restent publiés et contraignants ; les membres tardifs et propriétés racines participent à la projection |
| Une union MCP était coercée selon sa première branche | Les alternatives restent explicites ; les valeurs valides de branches différentes passent, les valeurs hors contrat sont refusées |
| Un `null` obligatoire ou un argument nommé `_account` disparaissait au transport | Les adaptateurs admin et utilisateur conservent ces valeurs et noms réellement déclarés |
| Une sortie commune à toutes les variantes disparaissait, ou un champ propre à une branche pouvait être annoncé | Seuls les chemins garantis communs sont publiés ; leur schéma conserve les alternatives et la nullabilité |
| La projection MCP matricielle perdait des indices et compteurs | Les chemins sources, indices et nombres d'éléments sont explicites. La vue du modèle peut être limitée ; la valeur canonique utilisée par Jinja reste entière |

Premières reproductions : le corpus natif initial comportait trois échecs,
celui des MCP dix échecs sur douze cas et celui de l'exploitation structurelle
quatre échecs sur dix-sept cas. Une source fantôme et une sortie commune
d'union ont ensuite été reproduites séparément avant correction.

## Décisions des modèles réellement configurés

L'évaluation a lu `llm_config_overrides` dans PostgreSQL du Docker dev local,
chargé les caches de configuration et de capacités, puis construit les clients
avec la factory de LIA. Elle refuse l'absence d'un **fournisseur et modèle
explicitement enregistrés en base**, vérifie l'identité effective et la relit
avant chaque appel. Aucun modèle de secours ni modèle choisi dans les
constantes n'a été utilisé.

| Slot | Fournisseur / modèle DB observés | Dernière modification DB observée |
|---|---|---|
| `planner` | DeepSeek / `deepseek-flash` | 23 septembre 2026 |
| `react_agent` | DeepSeek / `deepseek-flash` | 30 septembre 2026 |

Le nom retourné par le fournisseur correspond également à `deepseek-flash`.
Les paramètres laissés à `NULL` en base conservent leur configuration effective
normale, enregistrée dans le résultat : budgets de sortie et délais, plus
reasoning pour le planner. Le fournisseur et le modèle ne sont jamais hérités
de constantes dans ce harness. Les températures observées restent celles des
slots ; elles n'ont pas été forcées pour produire un résultat favorable.

Les prompts versionnés, catalogue compact, schémas publics des outils,
validation du plan, références et coercition d'exécution sont réels. L'analyse
de requête est une **entrée contrôlée**, pas une décision évaluée de l'analyseur.
Les lectures utilisent des fixtures issues des vrais builders. Le parcours
ReAct est borné à trois appels par cas et s'arrête lorsque les arguments de
l'action sont disponibles : aucune création de brouillon, invitation ou tâche
n'a lieu.

| Cas | Planner | ReAct |
|---|---|---|
| Contact Ada → adresse exacte dans le tableau des participants | Passe après clarification du titre du cas | Passe |
| Adresse déjà donnée → événement sans recherche de contact | Passe | Passe |
| Courriel → adresse canonique de l'expéditeur → participants | Passe | Passe |
| Courriel → titre et contenu exacts de la tâche, incluant `N/A` | Passe | Passe |

Le premier essai comportait **7 réussites sur 8 décisions**. La formulation
« événement intitulé Revue avec Ada Lovelace » permettait d'interpréter
« Revue avec Ada Lovelace » comme le titre. Le planner l'a fait ; ReAct a choisi
« Revue ». Le cas a été reformulé « titre exact : Revue », puis lui seul a été
rejoué dans les deux modes : les deux passent. Aucun prompt de production n'a
été changé pour ce résultat, et cet écart n'est pas présenté comme un défaut
sémantique corrigé du modèle.

Au total : **14 appels fournisseur**, coût mesuré **0,0049054741722 €**, sous le
plafond autorisé de 2 €. Les tokens hors cache, de sortie et de lecture du cache
sont conservés par tentative avec le tarif DB capturé. La dépense est enregistrée
dans le ledger de l'instance ; aucun quota d'un utilisateur fictif n'est débité.
Les retries LangChain **et ceux du transport SDK déjà construit** sont désactivés.
Le harness vérifie une borne de coût conservatrice avant chaque tentative ; une
réponse sans usage connu arrête les appels suivants.
Ce harness exige actuellement un transport asynchrone compatible OpenAI dont
les retries peuvent être vérifiés. Un autre transport est refusé avant dépense,
sans substitution de modèle.

Ces huit décisions sur quatre demandes fictives montrent un fonctionnement sur
ce corpus. Elles ne mesurent ni un gain statistique face à l'ancienne version,
ni la recherche réelle des connecteurs, ni l'autonomie de comptes de production.
Les décisions LLM de ce benchmark portent sur les outils natifs ; les MCP sont
éprouvés par les simulations contractuelles séparées.

## Lacunes encore observées

1. **Rôle et provenance d'une valeur.** Le vrai contrat météo accepte une ville.
   Si une personne « Nancy » est résolue dans le même tour, le garde refuse
   `location="Nancy"`, mais accepte `location="Nancy, France"`. Une égalité
   textuelle avec un nom de personne ne prouve pas que le paramètre représente
   cette personne. La prochaine amélioration doit porter sur la provenance et
   le rôle des valeurs, avec une mesure indépendante des homonymes.
2. **Dialecte effectivement reçu par chaque fournisseur.** Le convertisseur
   Gemini installé réduit encore certains `allOf` à leur premier membre et
   traite partiellement `oneOf`. La conservation exacte du contrat MCP dans LIA
   et la réussite du convertisseur OpenAI ne prouvent pas la fidélité de tous
   les fournisseurs. La qualification doit vérifier le schéma transmis, puis
   le comportement réel du modèle du slot concerné.
3. **Couverture empirique.** Restent à mesurer les résultats vides/ambigus réels,
   changements de schéma des serveurs utilisateurs, longs parcours, sélection
   du catalogue, reprise ReAct et rapprochements sur des comptes représentatifs.
   Les contraintes distantes, conditionnelles ou au-delà des profondeurs
   bornées ne sont pas inventées par une inférence de nom de champ.

## Reproduction et résultats de qualification

Sans fournisseur, depuis la racine :

```powershell
task semantic:audit
task semantic:simulate
```

Le harness réel nécessite une autorisation de dépense et une API dev configurée.
La commande suivante appelle les modèles DB et facture l'instance :

```powershell
docker exec lia-api-dev python -m scripts.semantic_simulation.run --real-models --budget-eur 2 --output .tmp/semantic-real.json
```

Sans `--real-models`, le module vérifie seulement les prompts et contrats sans
appel fournisseur. `--case` permet de ne rejouer qu'un cas ; les fichiers de
résultats précédents doivent être conservés et leur dépense comptée dans le
plafond de la campagne.

Les preuves locales de cette campagne se trouvent dans
`.tmp/semantic-simulations/` : JUnit des scénarios, régressions, première
résolution de lot avant correction, préflight DB, appels et vérifications.
Dans le répertoire de sortie du module, les réponses fictives, décisions et
coûts réels complets sont conservés sous les noms `semantic-real.json` et
`semantic-real-clarified.json` ; la collision Nancy est dans
`.tmp/semantic-nancy-homonym-gap.json`. Ces fichiers de travail ne sont pas
présentés comme des fixtures versionnées.

Dernière qualification ciblée : **86 scénarios passent**, dont les contrôles
du harness ; **1 310 tests de régression passent** dans la suite consolidée
sémantique, MCP, catalogue et références. Black, Ruff et le ratchet de taille
passent sur leurs périmètres vérifiés.
MyPy limité aux six modules du harness passe ; la vérification avec leurs
imports transitifs retrouve la signature incompatible du chantier applicatif.
La prévisualisation documentaire passe, sans lien vivant cassé ni orphelin.

La suite globale exécutée durant cette campagne donne **37 501 réussites,
11 échecs et 150 tests ignorés**. Les échecs concernent les nouvelles capacités
applicatives du chantier concurrent et les liens vers les documents non stagés
vus par le garde documentaire de l'index. Le ratchet de complexité passe,
sans hausse de baseline. MyPy des imports transitifs reste bloqué par des
fichiers applicatifs concurrents ; aucune erreur n'est relevée dans les modules
du harness ou les modules sémantiques/MCP qualifiés. Le checkout global n'est
donc pas déclaré vert ni prêt au déploiement.
