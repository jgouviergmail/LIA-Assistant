# ADR-278 — La fenêtre de contexte appartient au poste, pas à l'instance

- **Statut** : Accepté
- **Date** : 2026-09-10
- **Amende** : ADR-267 (Ollama fournisseur natif), ADR-244 (catalogue de capacités)
- **Périmètre** : `llm_config_overrides.context_window`, découverte Ollama,
  quatre lecteurs de la fenêtre, dialogue d'administration, `OLLAMA_NUM_CTX`
  (supprimé)

## Contexte

ADR-267 a posé un invariant qui tient toujours : **ce que LIA compte est ce que
LIA demande**. Un serveur Ollama à qui l'on ne demande rien alloue selon la VRAM
de sa machine (4 k sous 24 GiB) et **tronque le début d'un prompt plus long en
silence** ; si LIA compte autre chose, la compaction se déclenche au mauvais
moment et personne ne voit passer la coupure.

Le nombre qui portait cet invariant était `OLLAMA_NUM_CTX` : **une variable
d'environnement pour toute l'instance**, lue sur la branche Ollama de
l'adaptateur. Mesuré sur la production du propriétaire le 2026-09-10 :
`OLLAMA_NUM_CTX=128000`, donc *chaque* modèle Ollama — un 4 B comme un 27 B —
se voyait demander la même fenêtre.

Deuxième constat, mesuré le même jour sur Ollama 0.33.2 (treize tags) :

| Source | Capacités | `context_length` |
|---|---|---|
| `GET /api/tags` | pour **tous** les tags, cloud compris | pour **tous** les tags |
| `POST /api/show` | tags locaux + 4 tags cloud sur 8 | idem |

`/api/show` ne répond **rien** pour `kimi-k2.5:cloud`, `glm-5:cloud`,
`deepseek-v3.2:cloud` et `qwen3-vl:235b-instruct-cloud`. La découverte lisait ce
silence comme une déclaration : ces quatre modèles étaient publiés « sans
outils, sans pensée, plafonnés au palier VRAM local » — et ce profil `discovered`
**gagne** sur toute ligne de catalogue qu'un administrateur peut éditer. Deux
d'entre eux déclarent 262 144 jetons de contexte dans le listing.

## Décision

### 1. Le listing d'abord, `/api/show` en repli, et le silence ne déclare rien

`discover_ollama_models` lit `GET /api/tags` et n'interroge `POST /api/show` que
pour un tag que le listing a décrit **incomplètement**. Sur le serveur mesuré,
cela retire treize appels HTTP du démarrage et de chaque ouverture de la liste
admin.

Un tag que ni l'un ni l'autre n'a décrit **ne reçoit aucun profil** :
`build_discovered_profile` répond `None`, le tag redevient inconnu du runtime —
le comportement d'avant ADR-267 — et il est **nommé** (log `ollama_models_undescribed`,
liste `undescribed` dans la réponse admin, avis sous le sélecteur). Publier un
profil bâti sur une liste de capacités vide, c'était affirmer une négation que
personne n'avait vérifiée.

### 2. Un tag cloud se reconnaît à son HÔTE, jamais à son nom

`remote_host` / `remote_model` sont présents dans le listing pour un modèle
cloud et absents pour un modèle local. Le suffixe `-cloud` / `:cloud` est une
convention de nommage, pas un contrat : `my-cloudy-model:latest` n'est pas un
modèle cloud.

Cette distinction a une conséquence directe : **le plafond protège la mémoire de
CETTE machine**. Un tag local est plafonné à `OLLAMA_NUM_CTX_DEFAULT_CAP`
(32 768, le palier 24-48 GiB d'Ollama) ; un tag cloud garde **toute** sa fenêtre,
puisqu'il n'y a aucune VRAM à nous à protéger sur la machine de quelqu'un
d'autre.

### 3. La fenêtre est une colonne du POSTE configuré

`llm_config_overrides.context_window`, nullable. `NULL` signifie « ce que le
modèle déclare lui-même ». Le champ d'administration est **pré-rempli** avec ce
que le serveur a dit du tag et affiche le maximum du modèle en dessous :
l'opérateur n'enregistre une valeur que s'il veut s'en écarter, et vider le
champ rend le poste au modèle. Il saisit en **k** (binaire) ; la colonne stocke
des jetons.

Deux postes sur le même modèle peuvent donc légitimement différer — un routeur
économe et un répondeur généreux — ce que la variable d'instance rendait
impossible.

La résolution a un seul point d'entrée,
`get_effective_context_window_for_slot(agent_type)` :

1. la surcharge du poste, quand un opérateur en a posé une ;
2. ce que le modèle déclare (`get_effective_context_window` : profil découvert,
   puis ligne de catalogue curée, puis table à la main, puis défaut).

Les quatre lecteurs de la fenêtre partent tous d'un poste et lisent donc celle
du poste : seuil de compaction (`response`), budget ReAct (`react_agent`),
middleware de résumé (`response`, sauf quand un appelant nomme un modèle — ce
modèle-là n'appartient à aucun poste) et synthèse de réunion. Le lecteur par
modèle reste pour les surfaces de catalogue, qui n'ont pas de poste.

### 4. `OLLAMA_NUM_CTX` est supprimé

Champ `Settings`, entrées dans les quatre fichiers `.env`, documentation. La
migration `c6e1523d8222` ajoute la colonne puis **reporte** la valeur sur les
lignes de surcharge Ollama **uniquement si la variable est encore présente au
moment où elle tourne** : un déploiement qui l'avait posée garde son
comportement, sous une forme visible par poste au lieu d'un global silencieux ;
rien n'est inventé pour une instance qui ne l'avait jamais posée.

`OLLAMA_NUM_CTX_DEFAULT_CAP` reste une constante : ce n'est plus un défaut mais
un **plafond** de protection matérielle, et l'opérateur le dépasse par poste, là
où il voit de quel modèle il parle.


### Correction du 2026-09-10 — la fenêtre se consomme au point d'étranglement

Première implémentation : la fabrique passait `context_window` par le canal
générique `**kwargs`, celui que **chaque branche de fournisseur reforward à son
SDK**, et seule la branche Ollama le consommait. Mesuré dans le conteneur, cinq
fournisseurs sur sept recevaient `context_window` dans leurs `model_kwargs` —
deepseek, anthropic, gemini, qwen, perplexity — et **chaque appel mourait à la
requête** sur `AsyncCompletions.create() got an unexpected keyword argument
'context_window'`, indépendamment de toute configuration : la fabrique passe
toujours la clé, `None` compris.

`context_window` est une notion de LIA, pas un paramètre de fournisseur : seul
Ollama sait l'exprimer (`num_ctx`). Elle est donc consommée **une fois**, dans
`create_llm`, au même endroit que `provider_config`, puis remise **nommément** à
la seule branche qui sait l'exprimer — jamais laissée dans le sac générique.

C'est ADR-267 (« une branche de fournisseur ne passe JAMAIS une valeur stockée à
un SDK ») appliqué à une valeur qui n'est même pas stockée pour eux. Le garde de
couture qui existait déjà pour cette classe de défaut ne pouvait pas la voir :
il vérifiait le TYPE des valeurs — pas de dataclass, sérialisable JSON — et un
entier passe. Il vérifie désormais aussi les CLÉS, sur les sept branches, avec
et sans valeur.

### Correction du 2026-09-10 — un modèle RETIRÉ n'est pas un incident passager

Le même incident a rendu visible ce que LIA répond quand une étiquette cloud
disparaît. Mesuré sur les huit étiquettes du serveur : deux répondent `200`,
deux `402` (crédits épuisés) et **quatre `410`**, corps
« *étiquette* was retired at *date* » — les dates s'échelonnant du 2026-06-16 au
2026-07-31. Le ladder d'ADR-220 ne nommait pas `410` :
le code tombait dans « inconnu », dont le texte générique se termine par
« Veuillez réessayer » — un conseil qui ne marchera JAMAIS pour une étiquette
que le fournisseur a retirée.

`410 Gone` est le frère permanent de `404` : l'étiquette a existé, elle n'existe
plus. Elle prend donc la même catégorie `not_found`, dont le message dit déjà la
seule chose utile — le modèle configuré n'existe pas chez le fournisseur,
vérifiez son nom dans Paramètres → Administration → Configuration LLM — et le
dit dans les six langues. **Aucune catégorie, aucune clé, aucun message
nouveaux** : ce qui manquait était une ligne du ladder, et le ladder a un seul
lecteur pour ses quatre appelants.

Ce que cette correction ne fait PAS : le sélecteur de modèles continue de
proposer les quatre étiquettes retirées, parce qu'il liste ce que
`GET /api/tags` déclare et que c'est le serveur qui se contredit — les faire
disparaître demanderait de sonder chaque étiquette à chaque listage. La
personne l'apprend maintenant au premier essai, avec l'écran où le corriger.

Vérifié de bout en bout dans le conteneur, par le chemin réel : l'exception que
`ChatOllama` lève est une `ResponseError` portant `status_code = 410`, que
l'extracteur lit, que le ladder classe `not_found`, et dont le compteur
d'exploitation garde la trace (`category=not_found status_code=410`). Un test
épingle désormais la forme de cette exception : la garde précédente n'utilisait
qu'un objet de substitution, qui répond d'avance à la question posée.

## Conséquences

- Deux autorités sur une même question deviennent une seule. Une variable
  d'instance et une colonne de poste auraient fini par se contredire.
- L'invariant d'ADR-267 est préservé partout : un poste sans fenêtre connue
  demande le plafond plutôt que rien, parce que **ne rien demander n'est pas
  neutre** — c'est laisser le serveur choisir un palier et tronquer en silence.
- Le profil découvert cesse d'écraser le catalogue pour des tags qu'il n'a pas
  su lire. C'est ADR-244 appliqué à la découverte : `discovered` vaut pour ce
  que le serveur a dit, pas pour ce qu'il a tu.
- Coût de déploiement : une migration additive, aucun service, aucun seed.
  L'opérateur doit ressaisir sa fenêtre par poste s'il veut s'écarter du modèle
  — la migration le fait pour lui quand la variable est encore là.

## Alternatives écartées

- **Garder `OLLAMA_NUM_CTX` en défaut, avec surcharge par poste.** Deux
  autorités ; et le défaut serait resté faux pour tous les modèles sauf un.
- **Mettre la fenêtre dans `provider_config`.** Cette soupape n'est éditable que
  pour la TTS, `get_effective_context_window` ne la lit pas, et un `num_ctx`
  qui n'atteint que l'appel sans atteindre la comptabilité casse l'invariant
  d'ADR-267. Le `num_ctx` typé dans `provider_config` est donc **refusé** pour
  Ollama : une seule autorité.
- **Corriger le catalogue pour les tags cloud aveugles.** Le profil découvert
  gagne sur le catalogue ; corriger le second n'aurait rien changé au premier.
- **Reconnaître un tag cloud à son suffixe.** Une convention de nommage n'est
  pas un contrat, et le serveur publie déjà la réponse.

## Preuves

- Sonde du serveur Ollama 0.33.2 du propriétaire, 2026-09-10 : 13 tags,
  `/api/tags` complet pour tous, `/api/show` muet pour 4 tags cloud sur 8 ;
  `/api/ps` confirme `qwen3.8:27b` chargé avec 32 768 de contexte.
- `tests/unit/infrastructure/llm/providers/test_ollama_tags_discovery.py` :
  charges utiles transcrites de la sonde, y compris le tag cloud aveugle.
- `tests/unit/core/test_slot_context_window.py` : la surcharge gagne, deux
  postes peuvent différer, une fenêtre nulle est refusée à la construction.
- `apps/web/src/lib/llm-config/__tests__/context-window.test.ts` : k binaire,
  virgule décimale, aller-retour sur toutes les valeurs affichables.
- `task db:migrate:replay-check` vert (le greffon `comments` valide le
  commentaire de colonne).
