# ADR-195 : un diagnostic n'est pas une question, et un paramètre fourni ne se réinvente pas

**Statut**: ✅ IMPLEMENTED (2026-08-02)
**Date**: 2026-08-02
**Décideurs**: Équipe LIA
**Complète**: [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (réparer ce qui est mécaniquement réparable), [ADR-085](ADR-085-Draft-Display-Registry.md) (assert de complétude au démarrage), [ADR-194](ADR-194-Reference-Truth-Is-A-CI-Guard.md) (mesure du silence des gardes)

## Contexte

Quand un plan de **mutation** épuise ses replans automatiques,
`semantic_validator_node` refuse de l'exécuter et bascule vers une clarification
HITL — filet de sécurité légitime, il évite d'écrire une donnée fausse.

La question posée à l'utilisateur était la **description de l'issue**. Un compte
en français a reçu, en production :

```
for_each pattern issue detected
Fabricated placeholder contact detail: step_2.to='jerome@example.com'
```

Le premier est du jargon. Le second expose un chemin d'implémentation **et une
adresse fabriquée** que l'utilisateur pouvait prendre pour une vraie.

### Ce que la mesure établit

**Fréquence réelle**, Loki, 30 jours : `semantic_validator_node_mutation_exhausted_to_clarification`
= **4** sur **205** plans validés. Le défaut n'était pas théorique.

**La cause, à la ligne près.** Le commentaire au-dessus du code affirmait « the
issue descriptions are already localized ». Vérifié : faux sur les **cinq**
sites de rejet programmatique, tous des littéraux anglais dont le docstring de
`_programmatic_rejection` dit lui-même qu'ils sont « for the trace and the
replan prompt ».

**Mais vrai pour le chemin LLM** — et c'est ce que la première version du
correctif avait manqué. Un test existant épinglait, à raison, qu'une description
LLM est localisée ET spécifique : « La date de début est incorrecte (samedi 18 à
9h30 demandé) » vaut mieux que n'importe quelle question générique. Remplacer les
deux aurait été une régression d'ergonomie.

**Reproduit en laboratoire** : la description recyclée fait 31 caractères, le
streaming ajoute un espace par mot — exactement les 32 caractères du message de
production.

### Le second défaut, et ce que la vérification a démenti

L'utilisateur avait fourni son adresse en clarification ; deux tours plus tard,
le planificateur produisait `jerome@example.com`. Trois hypothèses ont été
formulées, et la mesure en a **infirmé deux — la troisième était vraie, et
n'avait été classée fausse que parce que la vérification s'était arrêtée trop
tôt** :

| Hypothèse | Verdict |
|---|---|
| La clarification est effacée, l'information perdue | **Faux** — le planificateur reçoit `existing_plan`, mécanisme ajouté en 2026-07 contre l'oscillation |
| Les `steps` dégradés au checkpoint cassent la transmission | **Faux pour un plan valide** — mesuré sur 99 plans réels : aucun dégradé |
| `ExecutionStep` manque à l'allowlist du checkpoint | **Faux** — il n'en a pas besoin : le conteneur Pydantic revalide et recrée ses membres |

**Une quatrième hypothèse a été formulée, tenue pour établie, puis démentie —
elle mérite d'être racontée, parce qu'elle a failli être publiée.** Un test
montrait `ExecutionPlan` revenant avec ses `steps` en `dict`, ce qui accusait
`_extract_preserved_parameters` de perdre les valeurs déjà fournies. La lecture
de checkpoints **réels** a contredit le test : 99 plans, 163 étapes, **zéro
dégradée**.

Le test mentait parce que ses données mentaient : ses `ExecutionStep` n'avaient
pas d'`agent_name`, que le modèle exige pour une étape `TOOL`. La mécanique
réelle, elle, est plus intéressante que l'erreur : le sérialiseur reconstruit un
type autorisé **en appelant son constructeur**, donc un conteneur Pydantic
**revalide** ses membres et les recrée — c'est pourquoi `ExecutionStep` revient
typé sans figurer dans l'allowlist. Sous une *dataclass*, rien ne revalide, et le
membre a besoin de sa propre entrée : les deux règles sont désormais épinglées
séparément.

Reste le cas limite, qui est le vrai enseignement : **un membre qui ne repasse
pas sa propre validation revient en `dict`, sans erreur nulle part**. Et
`ExecutionStep` était précisément dans ce cas — voir la décision 4.

Ce qui subsiste sur le second défaut, sans surinterprétation : le planificateur
reçoit bien l'information, et l'a néanmoins perdue en régénérant. Défaut de
robustesse du replan. Fréquence en production :
`semantic_validation_placeholder_contact` = **0** sur 30 jours — réel (reproduit
en dev, même modèle qu'en prod), mais rare.

## Décision

**1. Un diagnostic n'est jamais une question.** Une table
`SemanticIssueType → question`, **15 types × 6 langues**, dans `i18n_hitl`. Un
assert de complétude au démarrage (ADR-085) : l'application refuse de booter si
un type peut être levé sans question derrière lui.

L'assert vérifie les **deux sens**, et ce n'est pas une précaution de style : la
première version de la table portait deux clés `ambiguous_intent` et
`missing_dependency` qu'aucune recherche ne peut atteindre. L'enum les déclare
comme **alias** de `dangerous_ambiguity` et `ghost_dependency` — un alias ne
s'itère pas et ne porte pas son propre `value`. Deux questions écrites en six
langues, invisibles à l'exécution, comptées comme de la couverture par tout
relecteur. Le sens « table → enum » les a fait tomber au démarrage ; sans lui
elles seraient parties en production.

La déduplication porte sur le **texte produit**, pas sur le type d'issue :
`cardinality_mismatch` et `for_each_missing_cardinality` sont deux diagnostics
d'une seule chose à demander, et la première version posait donc deux fois la
même phrase — reproduit, puis épinglé. Dédupliquer sur le texte préserve à
l'inverse deux descriptions LLM différentes d'un même type, qui portent chacune
leur information.

**2. Celui qui produit déclare.** `SemanticIssue.user_facing` (défaut `True`).
Les cinq rejets déterministes passent `False` : leurs descriptions sont
techniques et le disent. Le chemin LLM garde son défaut, donc sa description
spécifique et localisée **survit intacte** — c'est elle qu'on montre quand elle
existe, la question générique n'est que le repli.

Ce drapeau plutôt qu'une heuristique : deviner en aval si un texte « a l'air
technique » aurait été un pari renouvelé à chaque nouveau message.

**3. Un paramètre fabriqué est réparé, jamais réinventé.** Avant validation,
`restore_fabricated_parameters` remet la valeur que le plan précédent du **même
tour** portait, là où le replan a produit une adresse de domaine réservé
RFC 2606.

**Cette réparation ne peut pas écraser un changement d'avis**, et c'est la clé
de sa sûreté : le déclencheur n'est pas « le paramètre a changé » mais « le
paramètre est une adresse de documentation ». Personne ne demande d'écrire à
`example.com` — une telle valeur est par construction une fabrication. Une
valeur réelle nouvelle n'est jamais touchée.

Avec **une exception, et elle est déterminante** : le champ sur lequel
l'utilisateur vient de répondre. Le plan précédent ne fait plus autorité
dessus — le prompt en tire déjà la conséquence, puisque la section « PRESERVED
PARAMETERS » exclut le champ clarifié. Réparer sans cette exclusion aurait pu
défaire la réponse même que la clarification servait à obtenir. Les deux faces
partagent donc le même calcul, dans le même module : le prompt **demande** de
conserver, la réparation **garantit** ce que la demande n'obtient pas toujours.

La réparation est **comptée** (`planner_fabricated_parameters_restored_total`) :
un taux qui monte signifie que le prompt de replan perd des paramètres, ce que
cette réparation ne fait que masquer.

Elle a bien failli ne jamais s'exécuter. Le chemin nominal de planification passe
par les **stratégies** LLM ; `_plan_single_domain` est le repli en mode panique.
La première version ne câblait `existing_plan` que sur ce repli — une réparation
branchée sur la branche qui ne s'exécute presque jamais. Un test de signature
l'épingle désormais, parce que le défaut était un argument omis : aucun test de
comportement sur le service ne l'aurait vu.

**4. Ce qu'un modèle accepte, il doit savoir le relire.** `ExecutionStep`
exigeait `agent_name` pour une étape `TOOL` via un `field_validator` — qui ne
s'exécutait jamais, Pydantic ne validant pas les valeurs par défaut. L'objet
était donc accepté à la construction, et **au niveau du plan aussi** (le test qui
documentait cela parlait d'un « by design — plan-level validation catches
issues » que la mesure a démenti).

Ce n'était pas anodin : sérialisé, le champ est écrit explicitement à `null` ; au
retour le validateur, lui, se déclenche, le constructeur lève, et le sérialiseur
rend un `dict` — **sans erreur nulle part**. `parallel_executor` lit ensuite
`step.step_id` sur un mapping et meurt loin de la cause.

Un `model_validator(mode="after")` remplace les trois `field_validator` (les deux
champs `TOOL` et la `condition` d'un `CONDITIONAL` avaient le même angle mort).
Les champs requis vivent dans une table indexée par `StepType` où **chaque** type
figure, `frozenset()` compris : un assert refuse d'importer le module si un type
est ajouté sans que la question soit posée (doctrine ADR-085).

Mesuré avant d'engager : **0 étape non conforme sur 163** dans 99 plans réels —
aucune reprise existante ne casse. Le durcissement a en revanche fait tomber
**18 tests**, tous porteurs de données qu'aucun producteur ne génère : c'est le
bénéfice immédiat, ces tests mesuraient un objet impossible.

Une conséquence à connaître : la validation d'un plan **revalide ses étapes**,
donc un plan ne peut plus porter une étape invalide, même forgée. Le seul état
résiduel est la mutation après construction — `frozen=False` étant délibéré (les
étapes reçoivent leurs paramètres résolus pendant l'exécution), un test le
couvre.

## Conséquences

**Ce que la simulation a corrigé avant toute ligne de production.** La règle a
été prototypée puis soumise à 11 cas. Deux défauts majeurs de la première
version y sont morts :

- **faux négatif** : seules les chaînes étaient traitées, donc
  `attendees: [...]` — le cas le plus courant pour un événement — n'était pas
  réparé ;
- **faux positif grave** : les champs libres n'étaient pas exemptés, le
  prototype **écrasait le corps d'un message rédigé**.

Corrigés en réutilisant les constantes du détecteur (`_FREE_TEXT_PARAM_NAMES`,
`_iter_param_strings`) plutôt qu'en les redéfinissant.

**Une propriété du sérialiseur, épinglée.** Mesuré et documenté : une dataclass
reconstruit ses modèles imbriqués, un `BaseModel` non — ses membres reviennent
en `dict`, et **aucune entrée d'allowlist n'y change quoi que ce soit**. C'est
pourquoi `format_existing_plan_for_replan` et `plan_contains_mutation` portent
des replis explicites : ce ne sont pas des précautions superflues, sans eux une
reprise lève `AttributeError`. Un test les protège désormais du nettoyage.

**Une limite assumée, bornée dans le temps.** `user_facing` a pour défaut
`True`, donc un checkpoint écrit *avant* ce déploiement et repris *après* ne
porte pas le drapeau et retombe sur le défaut : une conversation déjà en vol,
suspendue exactement sur un rejet déterministe, verrait encore la description
technique. Le champ survit au round-trip (test dédié) ; c'est seulement l'état
antérieur qui ne peut pas le contenir. Aucune migration n'est justifiée pour une
fenêtre qui se referme d'elle-même.

**Trois copies fusionnées.** Le motif « lire un champ sur un objet OU un
mapping » existait en trois exemplaires identiques (`_issue_field`,
`_issue_attr`, `_step_attr`) — conséquence directe de la propriété ci-dessus.
Un seul `read_field` les remplace, avec ses propres tests — et il lit le mapping
**avant** de tenter `getattr`, car un dictionnaire porte ses propres attributs :
`read_field(d, "items")` aurait répondu la méthode native plutôt que la valeur.

**Deux morceaux de code qui rassuraient sans rien faire, supprimés.** La
reconstruction du plan à la reprise (`service.py`, « CRITICAL FIX ») ne pouvait
pas fonctionner, et la démonstration est close par cas : le sérialiseur **rend
son type** à un objet valide, donc `isinstance(plan, dict)` est faux et la
branche est sautée ; et un objet ne revient en `dict` que lorsqu'il ne repasse
plus sa validation, cas où `model_validate` échoue pour la même raison. Mesuré :
`execution_plan_restored_from_dict` = 0, et 0 dict sur 47 plans et 44 verdicts
réels. Sa moitié `ValidationResult` reconstruisait par ailleurs avec `errors=[]`,
ce qui aurait silencieusement vidé les blocages qu'ADR-184 rapporte à
l'utilisateur. Ce qui garantit réellement la propriété est une garde CI, pas du
code d'exécution — même doctrine qu'ADR-194.

**`nodes/response_builders.py` supprimé** : 342 lignes, quatre fonctions,
**aucun import depuis `src/`** depuis le commit initial — seuls ses 462 lignes de
tests l'importaient, au vert, donnant l'apparence d'un module vivant et couvert.
Il contenait `f"Please provide: {param}"`, un texte anglais destiné à
l'utilisateur alors que `HitlMessages.get_field_question` couvre déjà ce besoin
en six langues ; personne ne l'a jamais reçu, puisque rien ne l'appelait.

**Le ratchet de taille a été respecté par extraction, pas par relèvement** :
`smart_planner_service` dépassait son plafond ; `planner/parameter_restoration.py`
a été créé à côté de son module frère `parameter_bounds` et a fini par recevoir
les deux faces de la règle — `_extract_preserved_parameters` l'a rejoint, parce
qu'il calculait déjà, mot pour mot, l'ensemble de paramètres que la réparation
devait épargner. Le service perd 22 SLOC nets et la duplication avec lui.

**Le ratchet de complexité aussi** : `restore_fabricated_parameters` arrivait
pile à CC 15. La boucle interne est devenue `_restore_step_parameters`. Deux
points chauds voisins ont par ailleurs baissé (planner 83 → 75, validateur
sémantique 32 → 30) sans que le compte global bouge — ce qui a rendu la
régression visible plutôt que compensée.

## Alternatives écartées

**Supprimer le recyclage sans le remplacer** (15 min) : l'utilisateur serait
tombé sur la question générique de repli, déjà localisée. Écarté — c'est
exactement la vaguitude que le code cherchait à éviter, et son commentaire le
disait.

**Deviner en aval qu'une description est technique** : une heuristique sur la
langue ou le vocabulaire aurait été un pari à re-valider à chaque message ajouté.

**Reprendre le plan après confirmation** (1 à 2 semaines) : le chantier moteur
qui permettrait de chaîner après une mutation. Les briques existent (le FOR_EACH
HITL « replay-safe » fait déjà exactement cela), mais il faudrait d'abord
**suspendre sélectivement** les étapes dépendantes — logique fine au centre de
l'exécuteur, sur le chemin de tous les plans. Non justifié : personne n'a mesuré
qu'un utilisateur demande un tel enchaînement. Ce serait refaire l'erreur
qu'ADR-194 vient de défaire.
