# ADR-151 : Le workflow CI orchestre, le Taskfile implémente

**Status**: ✅ IMPLEMENTED (2026-07-25)
**Date**: 2026-07-25
**Deciders**: jgouvier + Claude
**Technical Story**: Des gates étaient découverts par un build rouge **après** que tous les gates locaux soient passés au vert. Le gate de couverture par markers (v1.25.20), le ratchet de complexité frontend et les parcours a11y (v1.25.16), les seuils de couverture par fichier (v1.25.12) : à chaque fois, la même séquence — vérifier en local, pousser, découvrir en CI. La cause n'était pas l'inattention.

## Contexte mesuré

`.github/workflows/ci.yml` contenait **144 lignes de commandes — dont 97 de gates écrits inline** — et **zéro** appel à une tâche du `Taskfile.yml` (mesuré sur `2c716153` avec la méthode de comptage de `check_ci_parity.py` : 97 gates, 42 lignes de provisionnement, 5 CI-only). La CI et le Taskfile étaient deux implémentations parallèles du même pipeline, libres de diverger — et elles divergeaient.

La comparaison commande par commande, menée avant toute modification, a montré que `task ci` **ne reproduisait pas** la CI même là où il en avait l'air :

- `test:backend:unit:fast` troque la couverture contre le parallélisme xdist (bon choix pour un hook de commit à budget 5 min, mauvais pour reproduire la CI) : **le plancher de 60 % n'existait pas en local** ;
- `lint:docs` n'avait pas `--fail-on-stale`, faisant du gate local le **plus permissif des deux** ;
- trois blocs entiers — hygiène de code, parité des lockfiles, gate de markers — n'avaient **aucun** équivalent local par construction : ils étaient écrits en bash inline dans le YAML.

Un quatrième écart n'a été révélé que par la conversion : ce `Taskfile.yml` déclare `dotenv: - .env` **globalement**, donc chaque tâche hérite de l'environnement du développeur, que le runner n'a pas. Mesuré le 2026-07-25 : `NEXT_PUBLIC_API_URL` étant posée, `voice-input-service.ts` tombe à 80 % de couverture de branches contre un plancher de 83 %, parce que le code lit `process.env.NEXT_PUBLIC_API_URL || ''` et que la branche vide cesse d'être exercée. Un test vert en CI, rouge en local, pour une variable d'environnement.

## Decision

**Chaque étape `run:` de `ci.yml` est un appel `task <nom>`.** La logique vit dans `Taskfile.yml` ; la CI exécute *littéralement* la commande que le développeur lance.

- **15 appels `task`** ; le workflow perd 128 lignes nettes (149 ajoutées, 277 retirées).
- **Portage des contrôles inline** vers [`scripts/audit/check_code_hygiene.py`](../../scripts/audit/check_code_hygiene.py) — en **Python et non en bash** : l'hôte de développement est Windows et le runner Linux, donc un contrôle bash-only est un contrôle qu'un seul des deux peut jouer. Les sévérités sont **inchangées par le portage** : les trois contrôles consultatifs le restent, en promouvoir un est une décision délibérée et pas un effet de bord.
- **Nouvelles tâches** pour les gates sans équivalent local : `lint:hygiene`, `lint:lockfiles`, `lint:ci-parity`, `test:markers`, `test:frontend:coverage`, `test:e2e`, `test:alerts`, `test:backend:unit:coverage`. `lint:frontend` a récupéré les trois ratchets qui lui manquaient.
- **Deux paliers** : `task ci:fast` (aucun service requis, **~10 min** — à lancer avant un push) et `task ci` (ajoute PostgreSQL, Redis, Docker, un navigateur). Mesuré composant par composant le 2026-07-25 : lint 74 s, `test:backend:unit:coverage` **427 s** (le poste dominant), `test:markers` 17 s, `test:frontend:coverage` 48 s, `test:deploy` 27 s.
- **Neutralisation d'environnement** : les tâches de test frontend vident `NEXT_PUBLIC_API_URL`, ce qui reproduit exactement l'environnement du runner.

**La propriété est rendue structurelle, pas conventionnelle.** [`scripts/audit/check_ci_parity.py`](../../scripts/audit/check_ci_parity.py) (`task lint:ci-parity`, appelé par la CI) échoue quand une étape `run:` n'est ni un appel de tâche, ni un provisionnement de runner déclaré, et quand le workflow appelle une tâche qui n'existe pas. Falsifié : un gate inline ajouté à `ci.yml` est attrapé et nommé.

**Trois exceptions CI-only**, chacune inscrite avec sa raison dans le dictionnaire `CI_ONLY` du script — c'est la liste qu'un relecteur lit pour savoir ce qu'un run local **ne** couvre **pas** :

| Étape | Raison | Équivalent local |
|---|---|---|
| `promtool` (binaire natif) | non installé sur une machine de dev | `task test:alerts` — **même version v2.53.2**, via conteneur |
| Replay des migrations (bash, in-container) | le wrapper bash ne tourne pas sur l'hôte Windows | `task db:migrate:replay-check` (portage Python, F048) |
| Suite unitaire sur Python 3.13 (F041) | son objet **est** l'interpréteur différent | aucun, assumé |

## Consequences

- **Un gate ajouté est un gate exécutable.** L'ajouter dans le YAML est désormais un échec de build immédiat et nommé, pas une découverte trois semaines plus tard.
- **Diagnostiquer un job rouge ne demande plus de traduction** : lire l'appel `task ...` de l'étape, le rejouer.
- **Trois jobs n'avaient jamais tourné** avant cette conversion (Code Hygiene, E2E + a11y, Test Backend Integration) : ils sont verts. Le job d'intégration est même **plus strict** que son ancienne version — `LIA_REQUIRE_DB=1` transforme tout skip d'infrastructure en échec (F019) — ce qui prouve que la CI n'avait pas de skips masqués.
- **Contrats parallèles supprimés** : le seuil de couverture n'a plus qu'une source de vérité (`pyproject.toml`) ; l'expression de markers du hook pre-commit a été alignée sur celle de la tâche qu'il prétend refléter. Trois gardes verrouillent l'ensemble dans `test_task_ci_pytest_parity_guard.py` — aucune commande pytest ne réapparaît dans le workflow, le hook ne diverge pas de la tâche, aucune tâche ne lance deux fois la même collection.
- **Limite assumée** : l'iso porte sur les **commandes**, pas sur l'**environnement**. L'hôte est Windows, le runner Linux ; une divergence de shell, de casse du système de fichiers ou de permissions ne sera toujours pas attrapée en local. Le corriger demanderait d'exécuter les gates sensibles à la plateforme dans un conteneur Linux — chantier non engagé.
- **Coût** : `arduino/setup-task` s'ajoute à 7 jobs (action épinglée par SHA, quelques secondes). Le job code-hygiene installe deux wheels (`packaging`, `pyyaml`) dans un venv minimal plutôt qu'un `requirements-dev` complet — la liste est **dérivée des imports des scripts**, pas devinée, après qu'un `pyyaml` manquant a produit un `ModuleNotFoundError` vingt minutes après le début d'un build.
