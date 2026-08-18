# ADR-229: La carte des capacités est la source unique de l'état — et elle ne peut plus prendre du retard

**Statut**: ✅ IMPLEMENTED (2026-08-18)
**Date**: 2026-08-18
**Décideurs**: Propriétaire (arbitrage « option (a) : endpoint agrégé, et bien documenter pour ne jamais oublier ») + Équipe LIA

## Contexte

Deux constats indépendants, une seule cause.

### 1. La carte des capacités décrivait un produit d'il y a six mois

`/capacities` (page « Capacités », constellation + liste) publiait **13 nœuds**
figés depuis sa création. Entre-temps le produit a livré la génération d'images,
la **génération de documents** (v1.30.8, ADR-226), les **Agent Plugins**
(v1.30.7, ADR-225), les **habitudes apprises** (v1.28.0, ADR-214), les serveurs
MCP utilisateur et la téléphonie. Aucun n'apparaissait. La surface qui répond
« ce que ton assistant sait faire » était donc la moins à jour de l'application
— exactement l'inverse de sa raison d'être.

Pire, elle lisait les drapeaux `settings.*_enabled` **bruts**. Depuis les
interrupteurs de capacités (`feature_switches`), un administrateur peut couper
la génération d'images ou MCP à chaud, à l'intérieur du plafond de déploiement.
La carte pouvait donc annoncer « disponible » ce que l'opérateur avait coupé une
heure plus tôt.

### 2. La Vue d'ensemble des réglages ne disait que ce qu'une section EST

ADR-227 a livré la coquille master-détail avec une Vue d'ensemble en cartes,
délibérément **sans aucune donnée** : brancher chaque carte sur l'endpoint de sa
section aurait remis ~30 requêtes sur le chemin d'atterrissage que la refonte
venait justement de dégager. Le suivi était consigné comme arbitrage
propriétaire ; l'arbitrage est tombé : **option (a) — un agrégat unique**.

Or l'agrégat demandé existait déjà : c'est exactement ce que résout
`/capabilities`.

## Décision

**Une seule agrégation répond à « où en est cette capacité », et les deux
surfaces la lisent.**

### 1. La carte couvre le produit, et un assert l'y oblige

`domains/capabilities/service.py` déclare ses nœuds dans des tables :

- `COUNTED_NODES` — les capacités dont la vitalité est « ce compte en possède au
  moins un » (connecteurs, mémoire, intérêts, routines, relations, journaux,
  spaces, canaux, compétences, **plugins**, **habitudes**, **serveurs MCP**,
  **téléphonie**) ;
- `SWITCH_NODE_KEYS` — celles qu'on allume (voix, proactivité, personnalité,
  **images**, **documents**), qui ne publient donc **aucun décompte**
  (`detail=None`, doctrine ADR-185 : un compte est exact ou n'existe pas) ;
- `PLATFORM_CAPABILITY_NODES` et `CAPABILITIES_OFF_THE_MAP` **partitionnent**
  l'énumération `PlatformCapability`, avec une **raison écrite** pour chaque
  exclusion.

`_assert_capability_map_coverage()` s'exécute **à l'import** : une capacité
ajoutée sans décider de son sort sur la carte fait **échouer le boot**, pas
échouer en silence (doctrine ADR-085). C'est le mécanisme demandé pour « ne
jamais oublier lors des futures évolutions » — une consigne écrite se périme, un
assert non.

### 2. La disponibilité publiée est l'effective, pas celle du déploiement

`disabled_capabilities()` est lu **une fois** par requête (les états sont déjà
rassemblés en une passe) et composé dans chaque sonde. Une capacité coupée par
l'administrateur est absente de la charge utile, comme une capacité absente du
déploiement — le gate-keeper d'ADR-061 vaut pour les deux bornes, et une
capacité indisponible n'est même pas interrogée en base.

### 3. Une table de correspondance capacité ↔ section, lue dans les deux sens

`lib/capability-sections.ts` déclare `CAPABILITY_SECTION` et **dérive** son
inverse. La constellation demande « où configure-t-on ceci ? » (le seul pas
suivant qu'une étoile éteinte existe pour offrir), la Vue d'ensemble demande
« que contient cette section ? ». Deux tables écrites à la main auraient fini
par se contredire sur la même paire.

### 4. Les cartes de la Vue d'ensemble portent une ligne d'état

Une carte qui a une réponse la porte, **dans les mots de la liste des capacités**
(`activeLabel`) : deux surfaces qui décrivent une capacité ne doivent jamais la
formuler différemment. Trois propriétés tiennent l'honnêteté :

- **une requête, pas trente** — l'agrégat existant, sur le chemin
  d'atterrissage ;
- **le silence bat la supposition** — pendant le premier chargement, en cas
  d'échec, ou pour une section dont l'agrégat ne dit rien (un thème, un export,
  un panneau d'administration), la carte ne dit rien. « À configurer » affiché
  pendant le chargement accuserait un compte d'être vide avant tout comptage ;
- **la ligne n'est pas le nom du bouton** (`aria-hidden`) : le nom accessible
  reste la destination.

## Conséquences

### Acquis

- La carte publie **19 nœuds** au lieu de 13, et ne peut plus retarder : le boot
  refuse une capacité non décidée, et un garde lit les **trois** surfaces
  clientes (les emplacements de la constellation, les liens « pas suivant », les
  six locales) — un garde qui n'aurait surveillé que Python aurait laissé passer
  la moitié TypeScript de la dérive.
- Une capacité coupée à chaud disparaît des deux surfaces immédiatement.
- La Vue d'ensemble répond enfin « où en est-ce ? » sans rendre le chemin
  d'atterrissage plus cher qu'avant ADR-227.

### Coût assumé

- Une requête supplémentaire sur la Vue d'ensemble des réglages. Pas de cache :
  le lecteur revient souvent au hub juste après avoir changé quelque chose, et
  un compte périmé de soixante secondes serait précisément le mensonge
  qu'ADR-185 interdit. La requête est un agrégat de `COUNT(*)` indexés, lancés
  en parallèle, chacun sur sa propre session.
- `documents` n'a **pas** de section de réglages (la capacité se pilote au
  niveau de l'instance) : son étoile pointe vers la racine des réglages, et
  cette exemption est déclarée dans le garde, pas subie.

### Défaut de documentation corrigé au passage

`core/config/document_generation.py` affirmait qu'un opt-in par utilisateur
vivait sur le modèle `User` (`document_generation_enabled`). Cette colonne
n'existait pas — la carte s'apprêtait à publier un état « dormant » que personne
n'aurait jamais pu allumer. Docstring corrigée dans le même changement (règle
« une docstring qui décrit un comportement absent est un bug »).

## Alternatives écartées

- **Un second endpoint `/settings/overview`** : une deuxième agrégation des
  mêmes faits, donc deux réponses possibles à « combien de connecteurs ? ». La
  carte des capacités posait déjà la question.
- **Brancher chaque carte sur l'endpoint de sa section** : ~30 requêtes sur le
  chemin d'atterrissage — le problème qu'ADR-227 venait de supprimer.
- **Un cache Redis court sur l'agrégat** : moins cher, mais un compte périmé
  juste après une modification est un mensonge visible.
- **Mélanger des valeurs client (langue, fuseau, thème) aux comptes serveur** :
  gratuit en réseau, mais deux sources sur la même ligne doublent la surface où
  une carte peut contredire sa section. Une source, une forme, un contrat.
- **Une consigne écrite dans CLAUDE.md plutôt qu'un assert** : c'est exactement
  ce qui a échoué entre v1.28.0 et v1.30.9.

## Références

- ADR-085 (asserts de complétude au boot), ADR-061 (gate-keeper), ADR-185 (un
  compte est exact ou n'existe pas), ADR-204 (la carte des capacités contre la
  dispersion client), ADR-227 (coquille master-détail des réglages).
- `apps/api/src/domains/capabilities/service.py`,
  `apps/api/tests/unit/domains/capabilities/test_capability_coverage_guard.py`,
  `apps/web/src/lib/capability-sections.ts`,
  `apps/web/src/components/settings/SettingsOverview.tsx`.
