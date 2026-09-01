# ADR-255 — Une seule autorité sur ce qu'un serveur MCP déclare

**Statut** : Accepté — 2026-09-02
**Portée** : `infrastructure/mcp/`, `domains/agents/services/react_tool_selector.py`, `infrastructure/observability/metrics_mcp.py`
**Voisins** : [ADR-224](ADR-224-Conformite-MCP-2026-07-28-SDK-v2.md) (conformité protocole et SDK v2), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (une contrainte appliquée doit être publiée), [ADR-148](ADR-148-Health-Daily-Rollup.md) (une métrique que personne ne voit)

## Le défaut, mesuré

Un utilisateur ajoute un serveur MCP de finances personnelles, demande « Liste
mes comptes bancaires et leur solde », et l'assistante répond qu'elle ne sait
pas faire.

| Fait | Valeur |
|---|---|
| Outils publiés par le serveur | 40 |
| Outils réellement construits | **10** |
| Outils perdus | **30 (75 %)** |
| Occurrences en 72 h de production | 270 |
| Trace laissée | un `warning`, aucun compteur |

Le routage, lui, était juste : la sélection sémantique élisait le bon serveur
avec un score de 1,0. Ce qui manquait, c'était l'outil.

## La cause

Le serveur déclare ses paramètres optionnels ainsi :

```json
"include_hidden": { "type": ["boolean", "null"], "default": false }
```

`type` peut être une **liste** de noms depuis draft-04, et c'est la façon
dominante d'écrire « optionnel » dans la nature. Une liste n'est pas hachable ;
quatre points du code s'en servaient comme clé de dictionnaire.

Et corriger le premier n'aurait rien changé en mode pipeline : le crash se
serait déplacé de la construction de l'adaptateur à celle du manifeste, dans le
même `try`. Le même outil aurait disparu, pour la même raison, une ligne plus
bas. **Deux lectures d'une même déclaration finissent toujours par diverger** —
c'est ce qui était arrivé ici, sans que rien ne le dise.

## La décision : un module, deux consommateurs, aucune deuxième lecture

`infrastructure/mcp/json_schema.py` devient l'unique autorité sur ce que dit une
déclaration. L'adaptateur LangChain (qui construit un modèle Pydantic) et le
catalogue du planificateur (qui construit des `ParameterSchema`) le lisent tous
les deux ; un test de parité l'exige.

Toute fonction y est **totale**. Le module ne lève jamais, parce que lever coûte
un outil, et qu'un outil perdu est une capacité que l'utilisateur n'a plus sans
que rien ne l'en avertisse. Décider de **jeter** une information reste le travail
de l'appelant ; décider de ce qu'une déclaration **dit** est celui de ce module.

## Conformité : la spec admet tout mot-clé, pas seulement `type`

> *« any JSON Schema 2020-12 keyword may appear alongside `type` — including
> composition keywords (`oneOf`, `anyOf`, `allOf`, `not`), conditional keywords
> (`if`/`then`/`else`), reference keywords (`$ref`, `$defs`, `$anchor`) »*

Le repli précédent renvoyait « pas de schéma » dès qu'une **seule** propriété
utilisait l'un d'eux. Mesuré, ce repli n'était pas neutre : LangChain publie
alors l'outil au modèle sous la forme d'un unique `kwargs` opaque — ni noms de
champs, ni descriptions, ni liste des paramètres obligatoires. L'outil est listé
et inappelable.

`resolve_property` réduit désormais toute déclaration 2020-12 : déréférencement
des `$ref` **locaux uniquement** — jamais de requête réseau depuis un schéma
tiers —, réduction de `anyOf`/`oneOf`/`allOf`/`const`, inférence depuis `enum`,
garde de cycle et profondeur bornée à 8. Ce qui reste indécidable — `not`, un
`if`/`then` nu, une référence introuvable — le dit honnêtement, et l'appelant
garde la propriété en la typant permissivement plutôt que de la perdre.

Deux réductions restent **partielles, et écrites comme telles** dans le
docstring : les frères d'un `$ref` (seuls `description` et `default` sont
récupérés en aval) et la fusion des membres d'`allOf`. Aucune des deux
n'apparaît dans les sept serveurs MCP vivants mesurés ; les élargir serait de la
spéculation, et une limite tue est un piège.

## Une contrainte appliquée doit être publiée (ADR-184), avec deux audiences

Les `enum` et les bornes rejoignent le vocabulaire `ParameterConstraint`
**existant** : les outils MCP héritent ainsi du rendu au planificateur, de la
validation de plan et du clampage numérique que les outils natifs avaient depuis
toujours, sans deuxième mécanisme.

Une nuance a été trouvée en revue, après que les tests soient passés au vert, et
elle est le cœur de la décision : **un `enum` a deux lecteurs qui n'attendent pas
la même chose**.

| Fonction | Lecteur | Le membre `null` |
|---|---|---|
| `constraint_enum` | validateur de plan | **reste** — il décrit ce que le serveur accepte |
| `publishable_enum` | déclaration provider | **part** — la nullabilité voyage dans l'annotation |

Le validateur teste `value not in expected`. Retirer le `null` des deux côtés
faisait d'un `direction: null` — valeur que le serveur accepte — une violation de
contrainte, donc `is_valid=False`, donc un re-planning que rien ne justifiait.

`pattern` est **délibérément absent** des contraintes, et c'est une décision de
sécurité : le validateur compile un motif avec `re.match` sur un chemin async.
Un regex écrit par un serveur tiers y présente deux dangers — un motif ECMA-262
que Python ne compile pas, et un backtracker catastrophique qu'aucun `except`
n'interrompt, qui gèlerait la boucle d'événements et tous les flux SSE. Il reste
publié aux providers, qui se contentent de le lire.

## Les annotations resserrent, jamais l'inverse

La spec est normative :

> *« For trust & safety and security, clients **MUST** consider tool annotations
> to be untrusted unless they come from trusted servers. »*

Une mutation déclarée est donc crue — au pire, un serveur menteur s'achète une
confirmation de trop. Une prétention de `readOnlyHint: true` ne l'est pas :
une catégorie déclarée **bat** l'heuristique de nom dans
`_declared_mutation_flag`, si bien que la croire retirerait l'outil du filet
anti-mutation, de la détection de portée HITL et de l'exigence de lecture seule
de la phase d'initiative, sur la parole d'un tiers.

Le gain est concret, et il se voit surtout en mode itératif : là,
`_expand_iterative_user_mcp` donne à **tous** les outils d'un serveur le même
drapeau HITL. Un utilisateur qui désactive la confirmation pour un serveur
surtout consultatif la désactivait aussi pour ses rares outils destructeurs. Or
aucun de `cancel_subscription`, `upgrade`, `disconnect_institution` ou `forget`
ne porte l'un des neuf verbes de mutation : l'heuristique de nom les classait
tous en lecture seule.

## Invariants

1. **Toute fonction de `json_schema.py` est totale.** Un schéma tiers ne peut
   pas la faire lever ; les cas hostiles sont épinglés par des tests.
2. **Les deux consommateurs lisent la même réduction.** Un test de parité
   compare le type du manifeste au champ de l'adaptateur pour sept formes de
   déclaration. La seule asymétrie tolérée — un paramètre indécidable, que le
   manifeste doit bien nommer d'un type — est elle-même épinglée.
3. **Un `$ref` ne sort jamais du document.** Aucune requête réseau ne part d'un
   schéma fourni par un tiers.
4. **Une annotation ne peut que resserrer.** `declared_tool_category` ne renvoie
   jamais `readonly` ; renvoyer `None` laisse l'heuristique de nom décider,
   exactement comme avant.
5. **Un outil abandonné est compté.** `mcp_tool_registration_failures_total`
   porte des labels bornés par construction (`scope` × `error_type`) ; le nom du
   serveur et celui de l'outil voyagent dans le log, qui n'a pas de budget de
   séries.
6. **Parité des gardes.** Le chemin admin protège par outil comme les chemins
   utilisateur le faisaient déjà : un outil inadaptable coûte son propre outil,
   plus l'ensemble du MCP admin.

## Ce que la revue de code a corrigé après coup

Les suites étaient vertes, `task lint` à zéro, la CI à zéro. La revue à froid a
quand même trouvé quatre défauts, dont un fonctionnel :

- **Le `null` de l'enum**, décrit plus haut — les tests eux-mêmes encodaient
  l'erreur, aucun n'aurait pu la voir.
- `compact_schema` recopiait `enum` et `required` sans vérifier que ce sont des
  listes ; un serveur envoyant autre chose le poussait tel quel dans le prompt du
  planificateur, comme s'il s'agissait d'un ensemble fermé.
- Un commentaire de douze lignes, expliquant l'exclusion de `pattern`, s'était
  retrouvé rattaché au mauvais symbole après une insertion.
- Un docstring manquait sa section `Returns` sur une fonction touchée.

Et un « correctif » a été **annulé** par la vérification : remplacer
`text-[11px]` par `text-xs` au nom de la charte, alors que les tailles
arbitraires sont un patron établi sur 108 fichiers du frontend.

## Conséquences

**Ce qui devient possible.** Un serveur généré depuis Pydantic ou zod — donc
truffé de `$defs`, `$ref` et `anyOf` — est désormais lu entièrement : un
paramètre objet montre ses champs imbriqués et leurs obligatoires, un tableau
ses éléments typés, un enum son ensemble fermé. Ce que le modèle devait deviner,
il le lit.

**Ce qui devient visible.** Un outil abandonné a un compteur, deux panneaux et un
seul événement de journal — le chemin est un champ, plus trois noms différents
pour la même chose.

**Ce qui coûte.** Publier les contraintes ajoute environ 175 caractères au
catalogue pour un outil à sept paramètres ; publier la structure d'un objet
imbriqué en ajoute environ 130 à sa signature. C'est le prix d'un paramètre que
le modèle pouvait sinon seulement deviner.

**Ce qui reste hors périmètre, et pourquoi.** `outputSchema` et
`structuredContent` restent le report assumé d'ADR-224 : la spec impose déjà au
serveur de doubler le contenu structuré en bloc texte, donc rien n'est perdu
aujourd'hui. Les `icons` demanderaient de charger une image depuis une URL
arbitraire, ce qui toucherait la CSP épinglée par test. Et `execution.task_support`
n'a pas besoin de garde : sans support des tâches, un serveur qui l'exige échoue
visiblement — il ne se tait pas.
