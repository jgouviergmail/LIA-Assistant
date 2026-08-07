# ADR-217 : un interrupteur qui n'enlève rien à l'assistant n'en est pas un

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Date**: 2026-08-06
**Contexte programme**: démonstrateur public libre (lot 3/8)

## Contexte

LIA sait déjà désactiver une famille de connecteurs pour toute l'application
(`ConnectorGlobalConfig` : une ligne par type, un `is_enabled`, une révocation
en cascade). Rien d'équivalent n'existait pour les capacités **non
connecteur** : transcription, synthèse vocale, images, téléversements, espaces
documentaires, recherche web, navigation, compétences, MCP, téléphonie.

Ces capacités n'avaient qu'un plafond de déploiement — une variable
d'environnement, donc un redéploiement pour changer d'avis. Le propriétaire a
demandé la même chose que pour les connecteurs, « aussi bien dans
l'application réelle que dans la version démonstrateur » : couper une
fonctionnalité depuis l'administration, immédiatement.

Trois d'entre elles n'avaient même pas de plafond : la synthèse vocale (le
sélecteur avait migré vers `llm_config_overrides` en v1.20.x sans laisser
d'interrupteur), la recherche web et la navigation.

## Décision

Un registre de **capacités de plateforme** (`domains/feature_switches/`), avec
une déclaration par capacité et trois modes d'application explicites.

### 1. Deux bornes composées, la plus petite gagne

| Borne | Origine | Rôle |
|---|---|---|
| Déploiement | variable d'environnement | ce que l'exploitant autorise |
| Opérateur | réglage d'administration (base) | ce qu'il choisit à l'intérieur |

L'effectif est un ET logique. Un déploiement qui interdit une capacité
court-circuite la lecture du réglage : il n'y a rien qu'un administrateur
puisse y changer. Trois plafonds manquants ont été créés
(`voice_tts_enabled`, `web_search_enabled`, `browser_enabled`, tous à `true`)
pour que le modèle soit uniforme — une capacité sans plafond aurait été
l'exception qui complique tout.

Le panneau d'administration affiche les **deux** bornes plus l'état réellement
appliqué. Un interrupteur qu'un opérateur peut basculer mais qui ne change
rien est un piège ; la capacité interdite par le déploiement porte donc un
badge « Indisponible » et dit pourquoi.

### 2. Une déclaration, et le magasin est alimenté par génération

Les clés de réglage sont **générées** depuis le registre de capacités, dans le
magasin typé posé au lot 1 (ADR-216). Dix blocs recopiés auraient dérivé ; ici
l'assert de complétude du magasin couvre gratuitement toute capacité ajoutée
ensuite.

Le sens de la dépendance est unique : `feature_switches → system_settings`.
Placer la génération du côté du magasin l'aurait fait importer le domaine
capacités — le cycle exact déjà cassé au lot 1. **Un magasin ne connaît jamais
ses clients.**

### 3. Trois modes d'application, déclarés honnêtement

- **`agents`** — les outils de la capacité disparaissent du catalogue offert
  au planificateur. L'exclusion emprunte `exclude_tools`, le post-filtre qui
  existait déjà pour le refus de sous-agent (F6) : un mécanisme, pas deux.
  Coût nul quand rien n'est coupé (aucune capacité désactivée, aucun parcours
  du catalogue).
- **`route_enforced`** — une dépendance de routeur refuse en 403 avec un code
  stable (`capability_disabled`) et le nom de la capacité, jamais une phrase :
  le frontend dit quelle fonctionnalité est coupée, dans la langue du lecteur.
- **`service_enforced`** — un point d'étranglement interne. La synthèse vocale
  n'a **aucune route** : elle est produite dans le flux de chat. Une
  dépendance de routeur n'y aurait rien appliqué ; la coupure vit à
  `_should_start_voice`, qui garde déjà tous les points de départ de la voix.

La première rédaction déclarait le TTS « route_enforced ». C'était faux, et
seule la vérification du câblage réel l'a montré. La déclaration dit
maintenant où chaque capacité est **vraiment** appliquée.

### 4. Ce qui est déclaré est vérifié au démarrage

Deux gardes, doctrine ADR-085 :

- chaque capacité qui nomme des agents nomme des agents **qui existent dans le
  catalogue** — sinon son interrupteur filtrerait le vide en ayant l'air de
  marcher. La garde a immédiatement attrapé deux noms inventés
  (`image_agent`, `rag_agent` ; les vrais sont `image_generation_agent` et
  `document_agent`). Les capacités que le déploiement interdit sont exemptées :
  leurs manifestes sont légitimement absents ;
- chaque capacité déclarée « route » garde **son routeur réel** — vérifié en
  parcourant les objets routeur, pas le texte des fichiers, pour qu'un
  déplacement de route soit suivi.

### 5. Lire un interrupteur ne casse jamais une requête

Ces lectures sont sur le chemin de requête. Un magasin injoignable résout à la
valeur de déploiement — le comportement d'avant l'interrupteur — jamais à un
« activé » surprise ni à une erreur 500. Le filtrage du planificateur dégrade
de même vers « rien de masqué » : amputer le produit sur un incident passager
serait pire que de laisser les routes refuser, ce qu'elles font toujours.

## Conséquences

**Positives**

- Couper une fonctionnalité prend deux secondes, sur le démonstrateur comme
  sur une instance privée qui ne veut pas payer d'images ce mois-ci.
- Le planificateur ne propose plus ce que les routes refuseraient : les plans
  restent exécutables et le prompt rétrécit.
- Ajouter une capacité = une entrée dans un dictionnaire ; les clés, le cache,
  l'audit, l'invalidation et la garde de démarrage suivent.

**Coûts assumés**

- Une lecture (cache Redis, TTL 5 min) par capacité et par planification,
  faites en parallèle.
- Deux registres nommés « capacité » cohabitent : `PlatformCapability` (ce
  qu'un opérateur coupe) et `DirectiveCapability` (ce qu'un client invoque,
  ADR-191). Noms et modules distincts, distinction écrite dans les deux
  docstrings.

**Non couvert**

- Les interrupteurs sont d'instance, jamais par utilisateur : un plan par
  compte reste un autre sujet.
- `domains/capabilities` (la carte des capacités d'un compte) ne consomme pas
  encore ces interrupteurs pour marquer « indisponible » — l'intégration est
  naturelle et sans cycle, elle n'est simplement pas faite.

## Preuves

- 50 tests du socle (registre, garde de route, câblage des routeurs,
  administration), 8 du filtrage planificateur, 7 de la section frontend.
- Runtime (conteneur, catalogue et base réels) : couper `browser` masque
  `browser_agent`, retire `browser_task_tool` du catalogue, fait refuser la
  route en 403 `capability_disabled` ; la restauration remet tout.
- Gates : `task lint` vert (cycles, complexité, taille de fichier, parité
  i18n 7317 clés × 6), MyPy strict 1145 fichiers, 16914 tests backend,
  5369 tests frontend.

## Alternatives écartées

- **Étendre `ConnectorGlobalConfig`** : le modèle est typé sur
  `ConnectorType`, et une capacité n'a ni jeton à révoquer ni OAuth.
- **Un drapeau d'environnement de plus par capacité** : c'est ce qui existait,
  et cela demande un redéploiement pour changer d'avis.
- **Un décorateur `@requires_capability` sur chaque outil** : cohérent avec
  `@track_tool_metrics`, mais il faut y penser à chaque nouvel outil. Le
  filtrage du catalogue et la garde de routeur couvrent par construction.
