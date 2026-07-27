# ADR-165: Modifier une skill, c'est la régénérer entièrement — et le confirmer dans l'outil

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-118 (import de skill depuis le chat)

## Contexte

Question posée : « avec le skill-generator l'assistant peut créer des skills,
mais pas en modifier une pour l'ajuster ou l'enrichir. Ce serait possible ? »

Le moteur d'écriture existait déjà. ADR-118 a fait du ré-import de sa propre
skill un **upsert**, testé (`test_own_reimport_allowed`,
`test_quota_reimport_at_cap_allowed`, `test_swap_in_reimport_parks_previous_version`)
et atomique : `_swap_in` gare la version précédente et la restaure si la suite
échoue.

Trois verrous le rendaient inatteignable :

1. **Le manifeste était illisible.** `SKILLS_RESOURCE_SKIP_FILES` retire
   `SKILL.md` et `translations.json` de `all_resources`, et `read_skill_resource`
   refuse tout chemin hors de cette liste. `activate_skill` **retire le
   frontmatter**. L'assistant ne voyait donc jamais `description`, `category`,
   `priority`, `plan_template`, `outputs`, `dialogue` : il ne pouvait pas
   *ajuster*, seulement réécrire à l'aveugle en perdant ces champs.
2. **Perte silencieuse.** `_swap_in` remplace le répertoire entier ; tout fichier
   non renvoyé disparaît. Mesuré sur les 14 skills système : **14/14** embarquent
   `assets/preview.png`, que le chat ne peut pas transporter (`.png` absent de
   `SKILLS_IMPORT_TEXT_EXTENSIONS`). Chaque édition aurait dégradé la vignette de
   la galerie, sans avertissement.
3. **Le prompt interdisait la mise à jour.** Le SKILL.md du générateur ordonnait,
   en cas de conflit de nom, de « choisir une variante proche » — l'assistant
   était dirigé vers le doublon.

Un quatrième fait a redéfini le mécanisme de confirmation. `_skill_needs_runner`
renvoie `True` dès qu'une skill embarque un `scripts/` ; `skill-generator` embarque
`validate_skill.py`. **Tout le dialogue de génération tourne donc dans un
`ReactSubAgentRunner` sur un fil isolé**, qui ne connaît ni `draft`, ni
`interrupt`, ni `pending`. Or `hitl_required` ne sert à rien de toute façon
(la porte d'approbation du pipeline est passante) et le brouillon — seul
mécanisme qui garde les deux modes d'exécution — exige que l'outil soit appelé
depuis le graphe principal. **Le HITL est inopérant là où le générateur
s'exécute.**

## Décision

### 1. Régénération intégrale, jamais un patch

L'assistant lit le descriptif du catalogue **et** le `SKILL.md`, croise avec la
demande, puis réécrit le package entier comme une génération neuve, sous le même
nom. C'est la seule approche qui garde le manifeste, les scripts et les
références cohérents entre eux : les trois évoluent ensemble.

### 2. Ré-import plutôt que suppression puis recréation

Les deux produisent le même résultat — le répertoire entier est remplacé — mais
« supprimer d'abord » exigerait d'exposer au modèle un **outil de suppression de
skill** (il n'en existe aucun ; l'endpoint de l'interface fait `rmtree` sans
sauvegarde) et ouvrirait une fenêtre où un échec de recréation perd
définitivement la skill. Le ré-import restaure l'ancienne version si la suite
échoue. Un outil destructeur en moins entre les mains du modèle, pour un résultat
identique.

### 3. Confirmation en deux temps DANS l'outil, par jeton

Le HITL étant indisponible, la confirmation vit dans `import_user_skill` :

1. le nom entrant désigne une skill existante de l'appelant → mode remplacement ;
2. sans jeton valide, l'outil **refuse** et retourne exactement ce que le
   remplacement ajouterait, remplacerait et **supprimerait**, suivi d'un
   `replace_token` ;
3. l'assistant présente ce bilan et obtient l'accord ;
4. un second appel, mêmes fichiers et jeton recopié, exécute.

**Le jeton, et non un booléen.** Un drapeau `confirm_replace=true` n'aurait été
qu'une convention : rien n'empêche le modèle de le poser dès le premier appel, et
la garantie serait redevenue déclarative — exactement ce que ce mécanisme est
censé remplacer. Le jeton est un condensé du nom et du contenu des fichiers : le
modèle ne peut que l'avoir **reçu**, donc avoir été refusé une fois.

Il ferme aussi un trou plus discret : le condensé couvrant le contenu, un package
modifié entre le bilan et la confirmation ne correspond plus. L'utilisateur
approuve donc **exactement** ce qui sera écrit, et non une intention.

C'est l'intention que `devops_tools` énonce pour son brouillon — « la
confirmation est inconditionnelle, elle ne dépend pas d'un LLM jugeant l'action
destructrice » — transposée au seul mécanisme disponible dans ce contexte.

### 4. Le serveur reporte ce que le chat ne peut pas transporter

Après l'échange, tout fichier de la version remplacée dont l'extension n'est pas
transportable est recopié depuis la sauvegarde. **Chemin chat uniquement** : un
import zip reste un remplacement strict. Un fichier fourni par la nouvelle
version n'est jamais écrasé, et les fichiers texte ne sont jamais reportés — les
retirer doit rester possible, c'est une édition.

### 5. L'intégrité du package devient bloquante

`outputs` déclarant `frame` ou `image` sans `scripts/`, ou une ressource
annoncée sous « Ressources disponibles » absente du package : refus. Le
générateur ne validait que le **texte** du manifeste, jamais le package réel.
L'édition rend ce mode de défaillance courant — une régénération qui oublie un
script doit être rejetée, pas stockée.

### 6. Trois refus explicites

Skill **système** : jamais modifiable, et **aucun fork n'est proposé** (décision
produit). Skill d'un **autre utilisateur** : refus indifférencié, sans révéler
son existence. Skill **désactivée** : refus, avec invitation à la réactiver. Ce
troisième garde n'est pas redondant : une skill éteinte est absente du catalogue
injecté, mais `SkillsCache.get_by_name_for_user` ne filtre pas sur l'activité —
un utilisateur la nommant explicitement aurait modifié sans le savoir quelque
chose qu'il croit inactif.

## Alternatives écartées

- **Conserver la version précédente** — arbitré : non. L'irréversibilité est
  assumée, et la confirmation **est** le garde-fou. Le bilan d'impact énumère ce
  qui disparaît plutôt que d'annoncer vaguement une modification.
- **Fusion avec suppression explicite** (`delete: [...]`) — écartée au profit de
  la régénération intégrale, plus cohérente : le manifeste et les fichiers
  doivent rester d'accord.
- **Débloquer `SKILL.md` via `_discover_all_resources`** — écarté : cela l'aurait
  ajouté au bloc `<skill_resources>` de **toutes** les activations, gonflant
  chaque prompt et changeant un comportement sans rapport avec l'édition. Le
  déblocage vit dans l'outil de lecture seul.
- **Un brouillon HITL** — impossible : voir le contexte. Un brouillon créé dans
  le sous-agent isolé ne remonte jamais au graphe principal.

## Conséquences

**Positives** : « ajuste ma skill » devient une conversation ; le manifeste est
lisible, donc l'ajustement préserve les champs qu'il ne touche pas ; la vignette
de la galerie survit ; un package incohérent est refusé au lieu d'être stocké et
de ne pas fonctionner.

**Négatives** : une édition coûte deux appels d'outil — la limite de débit
d'import passe de 5 à 10 par minute pour l'absorber. Une modification ne peut pas
être annulée : la qualité du bilan de confirmation est le seul garde-fou, ce qui
en fait un point de rédaction à surveiller.

**Sécurité inchangée** : le nom est validé avant toute écriture disque (garde S1
d'ADR-118), les conflits de portée restent refusés (S2), et le refus de
confirmation intervient **avant** que quoi que ce soit ne soit mis en scène.
