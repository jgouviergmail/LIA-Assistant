# Plan d'actions — révision de l'audit V14 (22/10/2026)

> **Pour l'exécution :** une action à la fois, avec son prompt, selon `superpowers:executing-plans`, strictement inline (aucun sous-agent). Chaque prompt est autonome : il porte ses preuves, son cycle analyse → preuve rouge → correction minimale → preuve verte, ses portes et ses contraintes.

**Sources.** Révision : `docs/audit/AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14-revision.html` (7,8/10 ; 26 constats ouverts, dont 4 majeurs). Plan de la session lia-a7 : `docs/superpowers/plans/2026-10-22-audit-v14-remediation.md`, complété par son message de 10:16 UTC (AC-028, AC-029 et AC-031 ajoutés à sa vague, séquence consolidée en 10 étapes), puis par les décisions du propriétaire du 22/10, relayées par lia-a7 et vérifiées dans sa transcription (section 4).

**État de référence.** HEAD `3c6795d4b`, aucun fichier suivi modifié à 10:15 UTC. Les 124 sources de la révision et les 170 preuves citées par ce plan ont été revérifiées sur cet état, chacune par son texte attendu.

**Erratum de la révision (corrigé le 22/10).** AC-033 attribuait l'échec de l'oracle de croissance CPU (V14 T03) à l'oracle des aplatisseurs. C'est celui de la compaction (`apps/api/tests/unit/agents/services/test_compaction_provenance.py:432-453`), qui mesure un seul appel par taille. La révision a été régénérée (fiche AC-033 et journal de révision) ; note globale et sous-notes inchangées.

**Ce que ce plan ajoute à la révision.** Deux preuves nouvelles, intégrées aux prompts :

- **AC-029.** Le verrou OAuth ne protège qu'une porte de rafraîchissement sur quatre : `_refresh_oauth_token` a quatre appelants et seul celui du client est sous verrou. `get_connector_credentials` rafraîchit sans verrou (`apps/api/src/domains/connectors/service.py:744-751`), et c'est par lui que passent tous les outils OAuth ; le job de rafraîchissement anticipé aussi (`apps/api/src/infrastructure/scheduler/token_refresh.py:204`, signalé par lia-a7). L'écriture des nouveaux identifiants n'est pas conditionnée (`service.py:1440-1442`). Rendre le seul verrou Redis propriétaire laisserait donc la course entière sur les trois autres portes.
- **AC-028.** Le chemin des grants OAuth tient un `SELECT … FOR UPDATE` pendant l'appel au fournisseur (`apps/api/src/domains/connectors/oauth_grant_runtime.py:98-111`), jusqu'à environ 36 s par défaut. C'est un choix d'ADR-302 qu'ADR-304, postérieure, interdit. Un `lock_timeout` ferait échouer le second lecteur : la correction est de retirer cette transaction dans AC-029, pas de relever la borne. AC-029 passe donc avant AC-028 (constat affiné avec lia-a7).

## 1. Méthode de classement

- **Valeur V = G + R**, de 1 à 5. G, gravité du constat : majeur 3, modéré 2, mineur 1. R, exposition : 2 = incident observé ou état durable faux ; 1 = défaut plausible en production, coût récurrent ou porte sur le point de rougir ; 0 = hygiène.
- **Charge J** : médiane estimée en jours-personne, analyse, correction, tests et portes compris.
- **Impact I**, rayon du changement de 1 à 5 : 1 tests, CI ou documentation ; 2 configuration ou un module, sans changement visible ; 3 comportement d'un domaine ou d'un chemin partagé ; 4 transverse ou migration ; 5 architecture.
- **ROI = V / J.** Tri : ROI décroissant, puis charge croissante, puis impact croissant, puis priorité (P1 d'abord), puis identifiant.
- **Lots** : actions regroupées par surface commune (mêmes fichiers, mêmes portes, même relecture). ROI du lot = ΣV / ΣJ, charge = ΣJ, impact = I maximal de ses actions ; même tri.
- **Lecture.** Le rang ROI n'est pas un ordre de dépendance. Les deux majeurs à rayon contenu (AC-028, AC-003) ont un ROI de 2,00 et 1,67 : leur lot vient après trois lots de garde-fous plus rentables, qui touchent d'autres fichiers et peuvent avancer en parallèle. Si une seule session travaille et que le risque prime, la séquence de lia-a7 reste compatible avec ce plan : AC-031, puis AC-029 avant AC-028 (porte unique retenue le 22/10), puis AC-003.

## 2. Lots classés

34 actions en 9 lots, environ 67 jours-personne au total, dont 26,5 j pour les pilotes de dette structurelle.

| Rang | Lot | Actions | ΣV | ΣJ | ROI | I max | Session lia-a7 |
|---|---|---|---|---|---|---|---|
| L1 | Garde-fous du banc, de la CI et du typage | AC-012a, AC-033a, AC-033b, AC-030a, AC-037, AC-033c | 12 | 3,5 j | 3,43 | 2 | couvert 6 |
| L2 | Hygiène de build et d'exécution | AC-027, AC-008, AC-035, AC-036 | 7 | 2,8 j | 2,50 | 2 | couvert 4 |
| L3 | Registre et documentation exacte | AC-032, AC-031, AC-039a | 6 | 2,5 j | 2,40 | 1 | couvert 3 |
| L4 | Défauts majeurs et fiabilité d'exécution | AC-007, AC-028, AC-003, AC-029 | 16 | 10 j | 1,60 | 3 | couvert 4 |
| L5 | Observabilité qui dit vrai | AC-006, AC-004 | 7 | 4,5 j | 1,56 | 2 | couvert 2 |
| L6 | Discussions proactives : coût et croissance bornés | AC-034a, AC-023, AC-034b | 5 | 3,75 j | 1,33 | 3 | couvert 2, complément 1 |
| L7 | Assurance mesurée | AC-021, AC-014, AC-030b | 6 | 6,25 j | 0,96 | 1 | couvert 3 |
| L8 | Propriété des traitements RAG | AC-005, AC-002 | 7 | 7,5 j | 0,93 | 4 | exclu 2 |
| L9 | Dette structurelle et gouvernance documentaire, par pilotes | AC-011a, AC-038, AC-013, AC-012b, AC-010, AC-011b, AC-039b | 14 | 26,5 j | 0,53 | 4 | couvert 2, différé 3, complément 2 |

## 3. Classement global des actions

| Rang | Action | Titre | V | J | I | ROI | Prio. | Lot | Session lia-a7 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | L1.1 AC-012a | Retirer les 6 exemptions MyPy mortes et les 12 « # type: ignore » inutilisés | 2 | 0,25 j | 1 | 8,00 | P2 | L1 | Couvert |
| 2 | L1.2 AC-033a | Bornes temporelles du harnais : faulthandler_timeout et timeout-minutes | 2 | 0,25 j | 1 | 8,00 | P2 | L1 | Couvert |
| 3 | L2.1 AC-027 | Écarter les bundles de capture du contexte Docker de production | 2 | 0,4 j | 1 | 5,00 | P2 | L2 | Couvert |
| 4 | L1.3 AC-033b | Faire exécuter les deux tests qui s'ignorent avec les réglages par défaut | 2 | 0,5 j | 1 | 4,00 | P2 | L1 | Couvert |
| 5 | L4.1 AC-007 | Joindre les tâches annulées avant de fermer leurs ressources | 3 | 1 j | 2 | 3,00 | P1 | L4 | Couvert |
| 6 | L1.4 AC-030a | Porte de couverture du diff | 3 | 1 j | 2 | 3,00 | P1 | L1 | Couvert |
| 7 | L3.1 AC-032 | Réaligner la documentation des seuils et doctrines de test | 2 | 0,75 j | 1 | 2,67 | P2 | L3 | Couvert |
| 8 | L2.2 AC-008 | Fermer les clients Hue créés pour un test de connexion | 1 | 0,4 j | 2 | 2,50 | P2 | L2 | Couvert |
| 9 | L3.2 AC-031 | Registre des constats lisible par machine, avec âge et échéances | 3 | 1,25 j | 1 | 2,40 | P1 | L3 | Couvert |
| 10 | L6.1 AC-034a | Mesurer la croissance des tables d'exécution des discussions proactives | 1 | 0,5 j | 1 | 2,00 | P3 | L6 | Couvert |
| 11 | L1.5 AC-037 | Cliquet décroissant des assertions doubles « as unknown as » | 1 | 0,5 j | 1 | 2,00 | P3 | L1 | Couvert |
| 12 | L3.3 AC-039a | Cliquet de langue sur les documents vivants | 1 | 0,5 j | 1 | 2,00 | P3 | L3 | Couvert |
| 13 | L7.1 AC-021 | Prouver la clôture des oracles E2E par un rejeu contrôlé | 2 | 1 j | 1 | 2,00 | P2 | L7 | Couvert |
| 14 | L1.6 AC-033c | Rendre fiable l'oracle de croissance CPU de la compaction | 2 | 1 j | 1 | 2,00 | P2 | L1 | Couvert |
| 15 | L2.3 AC-035 | Sortir les E/S disque bloquantes des fonctions async et outiller la règle | 2 | 1 j | 2 | 2,00 | P3 | L2 | Couvert |
| 16 | L2.4 AC-036 | Parité des gabarits d'environnement avec les défauts du code | 2 | 1 j | 2 | 2,00 | P3 | L2 | Couvert |
| 17 | L5.1 AC-006 | Résoudre chaque panneau vers un producteur réel et trancher les règles dormantes | 3 | 1,5 j | 2 | 2,00 | P2 | L5 | Couvert |
| 18 | L4.2 AC-028 | Borner côté PostgreSQL l'attente de verrou et les transactions inactives | 5 | 2,5 j | 3 | 2,00 | P1 | L4 | Couvert |
| 19 | L6.2 AC-023 | Borner la recompilation payante d'une règle sémantiquement refusée | 3 | 1,75 j | 2 | 1,71 | P2 | L6 | Couvert |
| 20 | L4.3 AC-003 | Ne déduire aucun état « livré » de l'absence d'exception | 5 | 3 j | 3 | 1,67 | P1 | L4 | Couvert |
| 21 | L5.2 AC-004 | Composer Alertmanager selon les canaux et rendre les routes spécialisées atteignables | 4 | 3 j | 2 | 1,33 | P1 | L5 | Couvert |
| 22 | L8.1 AC-005 | Donner un propriétaire au verrou global de réindexation | 3 | 2,5 j | 3 | 1,20 | P1 | L8 | Exclu |
| 23 | L9.1 AC-011a | Sortir de users le modèle de lecture d'administration (pilote de couplage) | 3 | 2,5 j | 3 | 1,20 | P2 | L9 | Différé |
| 24 | L9.2 AC-038 | Ramener CLAUDE.md à des règles et des pointeurs | 2 | 2 j | 3 | 1,00 | P3 | L9 | Complément |
| 25 | L4.4 AC-029 | Un seul point de rafraîchissement OAuth, sérialisé et clôturé | 3 | 3,5 j | 3 | 0,86 | P1 | L4 | Couvert |
| 26 | L7.2 AC-014 | Réintégrer dans la couverture les primitives d'interface comportementales (pilote) | 1 | 1,25 j | 1 | 0,80 | P2 | L7 | Couvert |
| 27 | L9.3 AC-013 | Réduire un point chaud React Hooks et complexité (pilote) | 2 | 2,5 j | 3 | 0,80 | P2 | L9 | Couvert |
| 28 | L8.2 AC-002 | Fencer de bout en bout les traitements de documents RAG téléversés | 4 | 5 j | 4 | 0,80 | P1 | L8 | Exclu |
| 29 | L7.3 AC-030b | Rétablir la marge de couverture backend par les domaines sous le plancher | 3 | 4 j | 1 | 0,75 | P1 | L7 | Couvert |
| 30 | L6.3 AC-034b | Décider et outiller la rétention des tables d'exécution des discussions | 1 | 1,5 j | 3 | 0,67 | P3 | L6 | Complément |
| 31 | L9.4 AC-012b | Résorber les diagnostics MyPy neutralisés d'une frontière à fort impact | 2 | 3 j | 2 | 0,67 | P2 | L9 | Couvert |
| 32 | L9.5 AC-010 | Réduire un point chaud d'orchestration backend (pilote) | 2 | 3,5 j | 4 | 0,57 | P2 | L9 | Différé |
| 33 | L9.6 AC-011b | Défaire les couples réciproques d'agents par des ports | 2 | 8 j | 4 | 0,25 | P2 | L9 | Différé |
| 34 | L9.7 AC-039b | Traduire les points d'entrée de la documentation | 1 | 5 j | 2 | 0,20 | P3 | L9 | Complément |

## 4. Session lia-a7 : couverture, compléments et décisions

| Statut | Sens | Actions |
|---|---|---|
| Couvert | dans sa vague, avec un périmètre au moins égal | AC-012a (L1.1), AC-033a (L1.2), AC-027 (L2.1), AC-033b (L1.3), AC-007 (L4.1), AC-030a (L1.4), AC-032 (L3.1), AC-008 (L2.2), AC-031 (L3.2), AC-034a (L6.1), AC-037 (L1.5), AC-039a (L3.3), AC-021 (L7.1), AC-033c (L1.6), AC-035 (L2.3), AC-036 (L2.4), AC-006 (L5.1), AC-028 (L4.2), AC-023 (L6.2), AC-003 (L4.3), AC-004 (L5.2), AC-029 (L4.4), AC-014 (L7.2), AC-013 (L9.3), AC-030b (L7.3), AC-012b (L9.4) |
| Différé | dans son plan, hors de sa séquence actuelle | AC-011a (L9.1), AC-010 (L9.5), AC-011b (L9.6) |
| Exclu | écarté par décision du propriétaire | AC-005 (L8.1), AC-002 (L8.2) |
| Complément | absent de son plan | AC-038 (L9.2), AC-034b (L6.3), AC-039b (L9.7) |

**Compléments proposés le 22/10 et retenus par le propriétaire** : 11 actions, 11,5 j au total, toutes intégrées à la vague de lia-a7 (8 par Q9, 3 par arbitrage).

| Action | ROI | J | I | Retenue par | Pourquoi |
|---|---|---|---|---|---|
| AC-033a (L1.2) | 8,00 | 0,25 j | 1 | Q9 | rend diagnostiquables les blocages qu'A11 doit expliquer ; aucune borne permanente aujourd'hui |
| AC-033b (L1.3) | 4,00 | 0,5 j | 1 | Q9 | deux comportements jamais vérifiés, alors que la suite est verte |
| AC-030a (L1.4) | 3,00 | 1 j | 2 | Q9 | transforme sa contrainte « autant de tests que de code » en porte mécanique, marge à 0,66 point |
| AC-032 (L3.1) | 2,67 | 0,75 j | 1 | Q9 | même lot documentaire qu'AC-031 ; doctrine de couverture écrite une fois |
| AC-034a (L6.1) | 2,00 | 0,5 j | 1 | Q9 | mesure avant de décider une rétention |
| AC-037 (L1.5) | 2,00 | 0,5 j | 1 | Q9 | arrête la croissance d'une règle de CLAUDE.md non outillée |
| AC-039a (L3.3) | 2,00 | 0,5 j | 1 | arbitrage | arrête la croissance du corpus hors règle ; politique arrêtée le 22/10 |
| AC-035 (L2.3) | 2,00 | 1 j | 2 | arbitrage | sort les lectures audio de la boucle d'événements ; règle de CLAUDE.md non outillée |
| AC-036 (L2.4) | 2,00 | 1 j | 2 | arbitrage | une installation partie de l'exemple désactive huit fonctions, sans recours depuis le panneau d'administration |
| AC-006 (L5.1) | 2,00 | 1,5 j | 2 | Q9 | mêmes fichiers et mêmes portes qu'A07 ; 4 panneaux vides et une faille latente du garde de couverture |
| AC-030b (L7.3) | 0,75 | 4 j | 1 | Q9 | seule voie pour remonter la marge de couverture à 2 points pendant la vague |

**Restent hors de la vague de lia-a7** : AC-005 (exclu), AC-011a (différé), AC-038 (complément), AC-002 (exclu), AC-034b (complément), AC-010 (différé), AC-011b (différé), AC-039b (complément).

**Décisions du propriétaire (22/10)**, relayées par lia-a7 et vérifiées dans sa transcription :

- **Q5 (AC-003)** : un SSE seul n'est pas une livraison durable.
- **Q6 (AC-031)** : un P1 échu déclenche un avertissement en CI et l'échec de `release:check`, sauf report daté et motivé.
- **Q7 (AC-028)** : mesure en production en lecture seule — non tranchée.
- **Q8 (AC-029)** : porte unique de rafraîchissement sur `run_single_flight` et `run_shared_flight`, écriture conditionnée au chiffré lu, amendement d'ADR-302 ; AC-029 passe avant AC-028. Sept précautions d'implémentation, vérifiées le 22/10, sont intégrées au prompt L4.4 : sondage de l'attente, durée du claim, session de la fabrique partagée, transitions d'ADR-302, rafraîchissement manuel, chemin Hue Remote, métriques du tableau 10.
- **Q9** : ajout d'AC-033a, AC-033b, AC-030a, AC-032, AC-006, AC-034a, AC-037 et AC-030b.
- **AC-035** : inclus ; correction des 15 sites, puis activation de Ruff ASYNC2.
- **AC-036** : priorité base de données > .env > constantes ; les 8 fonctions à true dans `.env.example` et `.env.prod.example` ; `BACKGROUND_RUNS_ENABLED` retirée de `.env.min.prod.example` ; analytique à false.
- **AC-039a** : amendement pragmatique de la règle de langue (anglais pour tout nouveau document, liste française figée et décroissante, exemptions pour les cartes, les plans datés et les rapports d'audit).
- **Processus pytest orphelins** : ne pas les arrêter pendant le déploiement en cours.

**Points échangés avec lia-a7 (22/10), tous vérifiés dans le code :**

- **AC-029** : quatre portes, une seule sous verrou, dont le job anticipé `token_refresh.py:204` signalé par lia-a7 ; écriture non conditionnée (`service.py:1440-1442`) ; chemin des grants en transaction pendant l'appel au fournisseur (choix d'ADR-302, contraire à ADR-304). Résolu par Q8.
- **AC-028** : la borne ne doit pas absorber le chemin des grants (ni borne relevée ni `SET LOCAL` large). Relevé de lia-a7 : des transactions inactives jusqu'à 53,5 s en dev (07/10), à expliquer avant de fixer la borne.
- **A12** : son énoncé vise déjà le bon test (compaction) ; c'est la révision qui a été corrigée.
- **AC-035** : 15 sites ASYNC2 ; l'unique ASYNC110 (`provider_capacity.py:126-127`) est un sondage Redis inter-processus légitime.
- **AC-036** : gabarits identiques sur les 9 interrupteurs ; `.env.min.prod.example` se contredit (l.28 contre l.143) ; un plafond `env_flag` à false bloque même le panneau d'administration (`feature_switches/registry.py:543-563`).
- **AC-037** : les 108 assertions doubles des tests frontend = 107 sous `__tests__` + 1 dans `apps/web/src/app/api/rag-upload/[spaceId]/route.test.ts`.
- **AC-039** : `README.md`, `docs/GETTING_STARTED.md` et `CONTRIBUTING.md` sont en anglais ; `docs/INDEX.md`, `docs/ARCHITECTURE.md`, `GUIDE_TESTING.md` et `GUIDE_DEVELOPPEMENT.md` sont en français.

## 5. Lots et prompts

### L1 — Garde-fous du banc, de la CI et du typage

Tests, CI et configuration de typage ; aucun comportement produit modifié. Rend le banc diagnostiquable avant les lots qui changent du comportement.

ROI du lot 3,43 · ΣV 12 · ΣJ 3,5 j · I max 2.

#### L1.1 — AC-012a · Retirer les 6 exemptions MyPy mortes et les 12 « # type: ignore » inutilisés

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G2 + R0) | 0,25 j | 1 | 8,00 | P2 | Couvert — A14a (séquence n° 6) |

**Dépendances :** Précède AC-012b.

**Preuves :** `apps/api/pyproject.toml:171`, `apps/api/pyproject.toml:198`, `apps/api/pyproject.toml:206`, `apps/api/pyproject.toml:210`, `scripts/audit/measure_mypy_debt.py:116`

```text
Rôle : ingénieur Python senior, typage strict (MyPy).

Contexte (constat AC-012 de la révision de l'audit V14) : six couples (module, code) neutralisés dans apps/api/pyproject.toml ne se déclenchent plus : no-untyped-def sur agents.nodes.* (l.171), operator sur agents.tools.* (l.198), union-attr sur graphs.base_agent_builder (l.206), arg-type, var-annotated et call-overload sur services.hitl.* (l.210). Douze « # type: ignore » sont inutilisés. Le cliquet scripts/audit/measure_mypy_debt.py (l.116) refuse les nouveaux couples mais ne signale pas ceux devenus inutiles : la dette morte reste gelée et masque les régressions futures de ces modules.

Étape 1 — Analyse : exécute MyPy avec la configuration canonique (celle de task lint:backend). Pour chacun des six couples, retire-le seul dans une copie de configuration hors dépôt et confirme 0 diagnostic ; liste les ignores inutilisés (warn_unused_ignores) avec fichier:ligne. Un couple qui produit encore un diagnostic reste en place et est signalé.

Étape 2 — Preuve rouge : un test du cliquet montre qu'un couple devenu inutile n'est aujourd'hui pas détecté.

Étape 3 — Correction : retire les couples confirmés morts, sans toucher aux autres codes des mêmes motifs, et les ignores inutilisés ; abaisse la baseline de dette MyPy par l'outil prévu ; fais signaler par le cliquet tout couple devenu inutile, selon la convention des autres cliquets shrink-only du dépôt.

Étape 4 — Vérification : MyPy canonique, task lint:mypy-debt, task lint:backend, task test:backend:unit:fast. Publie le nombre de diagnostics de la sonde sans exemptions avant et après : il ne doit augmenter nulle part.

Spécifique : aucun changement de code applicatif ; aucun Any, cast ou nouvel ignore. Si l'hôte et Docker divergent sur un ignore (piège décrit dans CLAUDE.md), aligne par override de module, jamais par ignore.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L1.2 — AC-033a · Bornes temporelles du harnais : faulthandler_timeout et timeout-minutes

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 0,25 j | 1 | 8,00 | P2 | Couvert — ajouté le 22/10 (Q9) ; complète le watchdog ponctuel d'A11 |

**Preuves :** `apps/api/pyproject.toml:241-245`, `.github/workflows/ci.yml:169-171`

```text
Rôle : ingénieur outillage de tests et CI.

Contexte (constat AC-033) : aucun délai n'existe au niveau du harnais. [tool.pytest.ini_options] (apps/api/pyproject.toml:241-245) ne fixe ni faulthandler_timeout ni pytest-timeout ; les jobs de .github/workflows/ci.yml (par exemple « Test Backend », l.169-171) n'ont pas de timeout-minutes, donc un test bloqué tient le runner jusqu'à la limite de la plateforme (360 min) sans laisser de pile. Constaté : deux processus pytest lancés le 20/10 vivaient encore le 22/10 ; deux relances massives de l'audit V14 ont stagné sans diagnostic possible.

Étape 1 — Analyse : mesure la durée des jobs CI récents (lecture seule : gh run list, gh run view) et les tests les plus longs en local (--durations=30 sur la sélection CI). Vérifie la compatibilité avec xdist, la couverture et Windows : faulthandler_timeout est natif dans pytest ; pytest-timeout exige la méthode « thread » sous Windows.

Étape 2 — Preuve rouge : un test jetable (hors dépôt, ou supprimé ensuite) qui dort au-delà de la borne visée bloque aujourd'hui sans imprimer de pile.

Étape 3 — Correction : (1) faulthandler_timeout dans la configuration pytest backend, au moins 3 fois le test le plus long mesuré ; il imprime les piles sans tuer le test. (2) timeout-minutes sur chaque job de ci.yml, environ 2 fois sa durée médiane mesurée, en propriété de job uniquement : la CI orchestre, le Taskfile implémente (ADR-151). (3) En option, après mesure seulement : pytest-timeout en dépendance de dev (manifeste puis task deps:lock, manifeste et lockfiles ensemble), avec une borne par test généreuse et documentée.

Étape 4 — Vérification : le test jetable imprime sa pile dans la borne (et, avec pytest-timeout, est interrompu) ; task test:backend:unit:fast et task test:markers verts, durée inchangée ; task lint vert, dont lint:ci-parity.

Spécifique : ne tue aucun processus existant ; liste les PID orphelins éventuels pour décision du propriétaire.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L1.3 — AC-033b · Faire exécuter les deux tests qui s'ignorent avec les réglages par défaut

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 0,5 j | 1 | 4,00 | P2 | Couvert — ajouté le 22/10 (Q9) |

**Preuves :** `apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_compute_step_timeout.py:57-62`, `apps/api/src/core/constants.py:1851-1856`, `apps/api/tests/unit/domains/telephony/test_wiring.py:24-28`

```text
Rôle : ingénieur de tests backend.

Contexte (constat AC-033) : deux tests unitaires sont verts sans jamais rien vérifier avec les réglages par défaut. (a) apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_compute_step_timeout.py:57-62 s'ignore quand le plancher égale le plafond, or les défauts du code valent 300/300 (apps/api/src/core/constants.py:1851-1856). (b) apps/api/tests/unit/domains/telephony/test_wiring.py:24-28 s'ignore quand la téléphonie est désactivée, ce qui est le défaut.

Étape 1 — Analyse : lis chaque test et le comportement qu'il protège ; confirme les deux skips avec -rs sous les réglages par défaut ; identifie la surcharge locale minimale qui crée l'état testé (plancher inférieur au plafond ; téléphonie activée sur une application construite pour le test).

Étape 2 — Preuve rouge : avec la surcharge, une mutation temporaire du comportement protégé (annulée ensuite) fait échouer chaque test ; sans surcharge, ils sont ignorés.

Étape 3 — Correction : remplace la dépendance aux réglages globaux par des surcharges locales explicites (monkeypatch des settings ou fixture dédiée), supprime les skips conditionnels et dérive les valeurs des settings au lieu de les coder en dur (règle de CLAUDE.md sur les seuils dans les tests).

Étape 4 — Vérification : tests ciblés avec -rs (0 skip), task test:backend:unit:fast, task test:markers.

Spécifique : aucune modification du code de production ; uniquement des valeurs factices pour la téléphonie, sans réseau.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L1.4 — AC-030a · Porte de couverture du diff

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 1 j | 2 | 3,00 | P1 | Couvert — ajouté le 22/10 (Q9) ; rend mécanique sa contrainte de revue |

**Dépendances :** Coordonner avec AC-032 (même guide).

**Preuves :** `Taskfile.yml:1294-1298`, `apps/api/pyproject.toml:245`, `docs/guides/GUIDE_TESTING.md:2093-2095`, `CLAUDE.md:509`

```text
Rôle : ingénieur qualité et CI.

Contexte (constat AC-030) : le plancher de couverture backend est global (78 %, apps/api/pyproject.toml:245 ; le commentaire de Taskfile.yml:1294-1298 cite une mesure de 80,36 % au 04/10). Le 22/10, la commande canonique mesurait 78,66 % : 0,66 point de marge contre les 2 points qu'exige la doctrine du cliquet (CLAUDE.md l.509 ; docs/guides/GUIDE_TESTING.md:2093-2095). Les domaines récents sont sous le plancher : sms 53,6 %, proactive_discussions 70,2 %, infrastructure/proactive 67,9 %, conversations 44,1 %. Un plancher global dilue le code nouveau ; rien n'exige de couverture sur les lignes modifiées.

Étape 1 — Analyse : choisis l'outil (diff-cover sur le XML que produit déjà task test:backend:unit:coverage, ou un script sur coverage json et la liste des fichiers modifiés) ; définis la base de comparaison en CI (merge-base avec main) et en local. Rejoue la porte, en lecture seule, sur les 10 derniers commits de main : combien auraient échoué, et pourquoi.

Étape 2 — Preuve rouge : une modification jetable et non testée d'apps/api/src passe aujourd'hui toutes les portes.

Étape 3 — Correction : une tâche Taskfile (par exemple test:backend:diff-coverage) qui exige au moins le plancher global sur les lignes modifiées d'apps/api/src ; appelée par ci:fast et par un step de ci.yml qui ne fait qu'appeler la tâche (ADR-151, lint:ci-parity vert) ; documentée dans GUIDE_TESTING par renvoi à la source, sans restater la valeur (règle doc_facts).

Étape 4 — Vérification : la modification jetable échoue, sa version testée passe ; tâche verte sur l'arbre courant ; task lint.

Spécifique : en local, obtiens la liste des fichiers modifiés sans écrire l'index (plomberie, GIT_OPTIONAL_LOCKS=0) ; une nouvelle dépendance de dev passe par le manifeste et task deps:lock ; le plancher global ne change pas ici.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L1.5 — AC-037 · Cliquet décroissant des assertions doubles « as unknown as »

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 0,5 j | 1 | 2,00 | P3 | Couvert — ajouté le 22/10 (Q9) |

**Preuves :** `CLAUDE.md:521`, `Taskfile.yml:1156`, `apps/web/src/components/chat/__tests__/ChatMessageList.test.tsx:123`, `apps/web/src/lib/sse-handlers/handlers.ts:1057`

```text
Rôle : ingénieur frontend TypeScript, outillage de qualité.

Contexte (constat AC-037) : CLAUDE.md (l.521) interdit les doubles assertions dans le code de test. On compte 108 « as unknown as » dans les tests frontend (ex. apps/web/src/components/chat/__tests__/ChatMessageList.test.tsx:123), 4 en E2E et 8 en production, dont des charges SSE non validées (apps/web/src/lib/sse-handlers/handlers.ts:1057). Aucun cliquet ne les compte, alors que les cliquets frontend existants sont câblés dans task lint:frontend (Taskfile.yml:1156).

Étape 1 — Analyse : recompte par fichier avec l'AST TypeScript (pas une regex : ni commentaires ni chaînes), en séparant tests unitaires, E2E et production ; classe les 8 cas de production (validation absente ou simple contournement de type), sans les corriger.

Étape 2 — Preuve rouge : l'ajout jetable d'une assertion double dans un test passe aujourd'hui task lint:frontend.

Étape 3 — Correction : un script de cliquet calqué sur apps/web/scripts/check-react-hooks-ratchet.mjs (baseline JSON par fichier, échec sur toute hausse ou tout nouveau fichier, mise à jour seulement à la baisse), appelé par task lint:frontend.

Étape 4 — Vérification : la preuve rouge échoue désormais ; task lint:frontend et task test:frontend verts ; baseline égale au recensement de l'étape 1.

Spécifique : aucune réécriture massive des tests ici ; les 8 cas de production sont livrés comme liste à traiter.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L1.6 — AC-033c · Rendre fiable l'oracle de croissance CPU de la compaction

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 1 j | 1 | 2,00 | P2 | Couvert — A12 (séquence n° 8) ; son énoncé vise déjà le bon test, la révision a été corrigée (erratum) |

**Preuves :** `apps/api/tests/unit/agents/services/test_compaction_provenance.py:442-453`, `apps/api/tests/unit/agents/services/test_compaction_provenance.py:452`, `apps/api/tests/unit/domains/agents/display/test_flatteners_are_linear.py:59`

```text
Rôle : ingénieur de tests, mesure de performance.

Contexte (constat AC-033, erratum de la révision du 22/10) : la commande canonique task test:backend:unit:coverage a échoué au V14 (T03) sur l'oracle test_a_long_url_tail_is_trimmed_with_linear_cpu_growth de apps/api/tests/unit/agents/services/test_compaction_provenance.py:432-453. Il chronomètre un seul appel par taille (16k puis 64k caractères) avec time.thread_time() et un plancher de 5 ms au dénominateur (l.452). Sous Windows, l'horloge avance par paliers de 15,625 ms : le petit appel vaut souvent 0, d'où les ratios [18,75 ; 18,75 ; 2], de médiane 18,75 > 8. Mesurée par lots de 64 appels, la croissance vaut environ 4 avec et sans traceur (V14 P08) : aucun défaut quadratique n'est démontré. L'oracle des aplatisseurs mesure déjà par lots (apps/api/tests/unit/domains/agents/display/test_flatteners_are_linear.py:59, CPU_BATCH_CALLS = 16).

Étape 1 — Analyse : reproduis sous la commande canonique (couverture, Windows) et sans couverture ; mesure la résolution d'horloge, le coût du traceur et la dispersion sur 10 répétitions ; cherche les autres oracles du dépôt qui chronomètrent un seul appel (time.thread_time, perf_counter dans tests/).

Étape 2 — Preuve rouge : sous couverture Windows, l'oracle actuel échoue sans défaut ; une implémentation volontairement quadratique doit rester détectée par l'oracle corrigé.

Étape 3 — Correction : mesure par lots déjà éprouvée (ou répétition adaptative jusqu'à un temps CPU total mesurable), sans relever le facteur de croissance admis, le plafond absolu ni un délai ; factorise l'aide de mesure si les deux oracles la partagent.

Étape 4 — Vérification : l'oracle passe 10 fois sur 10 sous couverture Windows et sans couverture, et échoue sur la variante quadratique témoin ; task test:backend:unit:coverage complète ; task test:backend:unit:fast.

Spécifique : si l'oracle s'avère sain dans l'état courant, ne le réécris pas : documente la mesure.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L2 — Hygiène de build et d'exécution

Contexte Docker, clients temporaires, E/S bloquantes, gabarits d'environnement : corrections locales, sans changement fonctionnel visible.

ROI du lot 2,50 · ΣV 7 · ΣJ 2,8 j · I max 2.

#### L2.1 — AC-027 · Écarter les bundles de capture du contexte Docker de production

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 0,4 j | 1 | 5,00 | P2 | Couvert — A03 (séquence n° 6) |

**Preuves :** `.dockerignore:12-16`, `scripts/capture_public_screenshots.ps1:7`, `apps/web/Dockerfile.prod:36`

```text
Rôle : ingénieur build et conteneurs.

Contexte (constat AC-027) : l'outil scripts/capture_public_screenshots.ps1 (l.7) écrit par défaut dans .next-public-screenshots ; le .dockerignore racine (l.12-16) n'exclut que .next et .next-e2e*. Un bundle de 6,6 Go présent dans l'arbre entre donc dans le contexte du builder web (apps/web/Dockerfile.prod:36). La même classe d'erreur a déjà été corrigée pour .next-e2e* (commentaire du fichier) : la liste énumère des variantes au lieu de la famille.

Étape 1 — Analyse : inventorie toutes les sorties générées .next* (scripts, tâches, configurations) et vérifie qu'aucun fichier source suivi n'appartient à la famille ; mesure la taille du contexte transféré actuel (build sans cache vers une cible jetable, sans pousser d'image).

Étape 2 — Preuve rouge : un répertoire sentinelle .next-sentinel-xyz contenant un fichier témoin entre aujourd'hui dans le contexte (cible BuildKit de diagnostic qui liste le contexte, ou --progress=plain).

Étape 3 — Correction : exclure la famille générée .next*, avec des exceptions explicites si un fichier source requis en fait partie, et un commentaire qui nomme la règle de famille.

Étape 4 — Vérification : la sentinelle n'entre plus, alors que sources, public et patches entrent ; le Dockerfile de production construit sur une copie figée de l'arbre ; taille du contexte avant et après.

Spécifique : ne supprime aucun bundle existant ni artefact utilisateur ; ne démarre ni ne pousse l'image.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L2.2 — AC-008 · Fermer les clients Hue créés pour un test de connexion

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 0,4 j | 2 | 2,50 | P2 | Couvert — A04 (séquence n° 6) |

**Preuves :** `apps/api/src/domains/connectors/service.py:881-887`, `apps/api/src/domains/connectors/router.py:1845-1848`, `apps/api/src/domains/connectors/clients/philips_hue_client.py:273`

```text
Rôle : ingénieur Python async, gestion des ressources.

Contexte (constat AC-008) : le service d'activation locale (apps/api/src/domains/connectors/service.py:881-887) et la route de test de connexion (apps/api/src/domains/connectors/router.py:1845-1848) construisent chacun un PhilipsHueClient temporaire sans le fermer, alors que le client expose close() (apps/api/src/domains/connectors/clients/philips_hue_client.py:273) et que les chemins d'outils l'utilisent. Règle de CLAUDE.md : chaque client a un propriétaire qui le ferme sur sa propre boucle.

Étape 1 — Analyse : confirme que ces deux sites possèdent leur client (aucun partage) et recense tout autre constructeur temporaire de client dans le domaine connectors.

Étape 2 — Preuve rouge : un test avec transport simulé compte 0 fermeture sur succès, échec et annulation.

Étape 3 — Correction : un seul motif de propriété (async with si le client le supporte, sinon try/finally) sur chaque site ; aucun client partagé fermé.

Étape 4 — Vérification : exactement une fermeture sur succès, exception et annulation ; aucune ResourceWarning ni sortie stderr après le résumé de task test:backend:unit:fast ; task lint:backend.

Spécifique : transports Hue entièrement simulés ; réponses et erreurs fonctionnelles inchangées.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L2.3 — AC-035 · Sortir les E/S disque bloquantes des fonctions async et outiller la règle

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 1 j | 2 | 2,00 | P3 | Couvert — inclus le 22/10 : 15 sites, puis activation d'ASYNC2 |

**Preuves :** `apps/api/src/domains/voice/stt/elevenlabs_stt.py:197`, `apps/api/src/domains/voice/stt/openai_stt.py:102`, `apps/api/src/domains/voice/stt/fishaudio_stt.py:138`, `apps/api/src/domains/account_export/publication.py:42-49`, `CLAUDE.md:610`, `apps/api/pyproject.toml:63-70`, `apps/api/src/domains/voice/provider_capacity.py:126-127`

```text
Rôle : ingénieur Python async.

Contexte (constat AC-035, précisé le 22/10) : CLAUDE.md (l.610) interdit tout appel synchrone réseau ou disque lourd sur un chemin async, mais la sélection Ruff (apps/api/pyproject.toml:63-70 : E, W, F, I, B, C4, UP) ne l'outille pas. ruff --select ASYNC2 (appels bloquants dans une fonction async) signale 15 sites, 12 ASYNC240 et 3 ASYNC230, dont trois envois de fichiers audio aux fournisseurs STT par un open() synchrone dont httpx lit les blocs dans la boucle d'événements (apps/api/src/domains/voice/stt/elevenlabs_stt.py:197, openai_stt.py:102, fishaudio_stt.py:138) et des opérations de chemin (exists, replace, unlink) dans des fonctions async (ex. apps/api/src/domains/account_export/publication.py:42-49). Hors périmètre : le seul site ASYNC110 (apps/api/src/domains/voice/provider_capacity.py:126-127) est légitime — il interroge en boucle une allocation Redis partagée entre processus, qu'un asyncio.Event ne peut pas remplacer — et ASYNC109 ne produit que 26 signalements stylistiques.

Étape 1 — Analyse : ruff --select ASYNC2 sur apps/api/src ; classe chaque site (bloquant réel sur la boucle ou chemin froid), avec la taille typique des fichiers concernés.

Étape 2 — Preuve rouge : pour un envoi STT, un test montre que la lecture du fichier s'exécute dans le thread de la boucle (instrumentation de l'ouverture), avec un transport httpx simulé.

Étape 3 — Correction : lecture des octets audio hors de la boucle (asyncio.to_thread, comme domains/skills/executor.py) ou flux asynchrone, sans changer la requête envoyée ; opérations de chemin via asyncio.to_thread ; une fois les 15 sites corrigés, famille ASYNC2 activée dans Ruff sans baseline ni noqa ; ASYNC110 et ASYNC109 restent inactives.

Étape 4 — Vérification : Ruff vert avec la règle active ; requêtes STT identiques octet pour octet (transport simulé) ; task lint:backend ; task test:backend:unit:fast.

Spécifique : aucun appel réel aux fournisseurs STT.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L2.4 — AC-036 · Parité des gabarits d'environnement avec les défauts du code

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 1 j | 2 | 2,00 | P3 | Couvert — décisions du propriétaire du 22/10 |

**Dépendances :** Mêmes fichiers qu'AC-028 (.env.example, .env.prod.example).

**Décision du propriétaire :** Tranchée le 22/10 : les 8 fonctions à true dans .env.example et .env.prod.example, BACKGROUND_RUNS_ENABLED retirée de .env.min.prod.example, PRODUCT_ANALYTICS_ENABLED à false dans les gabarits.

**Preuves :** `.env.example:1850`, `apps/api/src/core/constants.py:1851-1853`, `.env.example:2341`, `apps/api/src/core/config/habits.py:53-55`, `.env.example:2517`, `scripts/audit/check_code_hygiene.py:304-316`, `.env.min.prod.example:28`, `.env.min.prod.example:143`, `apps/api/src/core/config/product.py:30-33`, `apps/api/src/domains/feature_switches/registry.py:543-563`

```text
Rôle : ingénieur configuration.

Contexte (constat AC-036) : sur 1 324 clés comparées, 50 valeurs de .env.example diffèrent du défaut du code (hors valeurs de substitution), dont 9 interrupteurs inversés : HABITS_ENABLED, OPEN_LOOPS_ENABLED, BACKGROUND_RUNS_ENABLED, ACCOUNT_EXPORT_ENABLED, INITIATIVE_REACT_ENABLED, RECURRENCE_SUGGESTION_ENABLED, HEARTBEAT_DEPARTURE_ENABLED et HABITS_TICK_SCORING_ENABLED sont à false dans l'exemple et vrais dans le code (ex. .env.example:2341 contre apps/api/src/core/config/habits.py:53-55) ; PRODUCT_ANALYTICS_ENABLED est l'inverse (.env.example:2517). Exemples numériques : SUBAGENT_TOOL_TIMEOUT_SECONDS 180 contre 300, EMAILS_BODY_MAX_LENGTH 500 contre 20 000 (.env.example:1850 ; apps/api/src/core/constants.py:1851-1853). Le contrôle d'hygiène (scripts/audit/check_code_hygiene.py:304-316) ne vérifie que la présence des clés. Une installation partie de l'exemple désactive donc huit fonctions sans le savoir. Précisions vérifiées le 22/10 : .env.example et .env.prod.example sont identiques sur ces 9 interrupteurs ; .env.min.prod.example ne déclare que BACKGROUND_RUNS_ENABLED=false (l.143) alors que l'en-tête de sa section annonce « optional — safe default applies if omitted » (l.28) ; la description de product_analytics_enabled (apps/api/src/core/config/product.py:30-33) dit « Off by default: enabling is an explicit deployment decision », décision que les deux gabarits prennent à la place de l'installateur.

Décisions du propriétaire (22/10) : la priorité est base de données > .env > constantes, donc un gabarit écrit au niveau .env et sa valeur écrase la constante ; sur un plafond de capacité (env_flag, par exemple HABITS_ENABLED ou OPEN_LOOPS_ENABLED), false interdit même au panneau d'administration de réactiver la fonction (apps/api/src/domains/feature_switches/registry.py:543-563). Les 8 fonctions passent à true dans .env.example et .env.prod.example ; la ligne BACKGROUND_RUNS_ENABLED est retirée de .env.min.prod.example ; PRODUCT_ANALYTICS_ENABLED passe à false dans les gabarits ; les gabarits du démonstrateur sont déjà conformes (HABITS et OPEN_LOOPS à true, les 7 autres clés absentes). Règle de parité : un gabarit reprend la valeur du code, omet la clé, ou signale son écart par « # differs from default: <motif> ».

Étape 1 — Analyse : recalcule la comparaison clé par clé depuis les classes Settings (défaut effectif, default_factory compris) pour les gabarits suivis (.env.example, .env.prod.example, .env.min.prod.example, .env.demo-instance.example, .env.demo-instance.prod.example) ; classe chaque écart restant (volontaire avec motif, oubli, valeur de développement).

Étape 2 — Preuve rouge : un garde de parité échoue aujourd'hui sur les 50 écarts non annotés.

Étape 3 — Correction : garde de parité dans lint:hygiene, qui exige l'égalité ou une annotation explicite « # differs from default: <motif> » sur la ligne ; aligne les oublis, annote les écarts volontaires, applique les décisions du propriétaire sur les interrupteurs.

Étape 4 — Vérification : task lint:hygiene et task lint verts ; liste finale des écarts annotés.

Spécifique : ne touche que les gabarits suivis, jamais un fichier .env réel ; ne change aucun défaut du code ; à sérialiser avec AC-028, qui ajoute des clés aux mêmes gabarits.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L3 — Registre et documentation exacte

Le registre qui suit toute la vague, une seule doctrine de couverture écrite, la langue outillée.

ROI du lot 2,40 · ΣV 6 · ΣJ 2,5 j · I max 1.

#### L3.1 — AC-032 · Réaligner la documentation des seuils et doctrines de test

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 0,75 j | 1 | 2,67 | P2 | Couvert — ajouté le 22/10 (Q9), avec AC-031 |

**Dépendances :** Coordonner avec AC-030a (même guide).

**Preuves :** `docs/guides/GUIDE_TESTING.md:3060`, `apps/web/vitest.config.mts:415-418`, `docs/guides/GUIDE_TESTING.md:2097-2126`, `apps/api/pyproject.toml:243-244`, `Taskfile.yml:1295-1297`, `docs/guides/GUIDE_TESTING.md:3-4`

```text
Rôle : rédacteur technique, outillage documentaire.

Contexte (constat AC-032) : docs/guides/GUIDE_TESTING.md annonce un « plancher global courant » frontend de 64/58/58/65 (l.3060) alors que apps/web/vitest.config.mts:415-418 applique 85/80/83/87 ; son historique backend (l.2097-2126) s'arrête à « le plancher reste à 67 % » alors que le plancher vaut 78 ; son en-tête (l.3-4) date la mise à jour du 2026-03-08 pour un contenu daté jusqu'au 30/08. Trois doctrines se contredisent : « +2 points par release » (apps/api/pyproject.toml:243-244), relèvement seulement avec au moins 2 points de marge (GUIDE_TESTING, CLAUDE.md), et un commentaire de Taskfile.yml:1295-1297 qui affirme une marge de 2 points devenue fausse. scripts/audit/doc_facts.py rapporte 0 dérive parce que ces énoncés sont hors de ses motifs.

Étape 1 — Analyse : recense dans les documents vivants chaque énoncé d'un seuil de couverture (backend, frontend global et par glob) et chaque formulation de la doctrine du cliquet ; pour chacun, la source de vérité.

Étape 2 — Preuve rouge : un fait doc_facts ajouté pour le plancher frontend échoue aujourd'hui sur GUIDE_TESTING.md.

Étape 3 — Correction : remplace les valeurs restatées par des renvois à la source ou enregistre-les dans doc_facts (task docs:fix-facts pour la réparation mécanique) ; déplace l'historique dans une section explicitement historique ; une seule formulation de la doctrine (celle de CLAUDE.md), citée ailleurs par renvoi ; corrige les commentaires faux de pyproject.toml et de Taskfile.yml ; en-têtes datés exacts ou supprimés.

Étape 4 — Vérification : task lint:docs vert (et task lint:docs:preview si des fichiers sont déplacés) ; doc_facts couvre les planchers backend et frontend.

Spécifique : ne modifie aucun seuil. Langue : CLAUDE.md impose l'anglais ; si le guide reste français en attendant la décision AC-039, ne traduis pas ici et signale-le.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L3.2 — AC-031 · Registre des constats lisible par machine, avec âge et échéances

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 1,25 j | 1 | 2,40 | P1 | Couvert — séquence n° 1 : docs/audit/findings_register.json, AC-040 pour le sujet V14 d'AC-014, AC-022 et AC-026 « unpublished » |

**Décision du propriétaire :** Tranchée le 22/10 (Q6) : avertissement en CI et échec de release:check, sauf report daté et motivé.

**Preuves :** `docs/audit/AUDIT_PROTOCOL.md:40`, `docs/audit/AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html:267`, `docs/audit/AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html:356`, `docs/audit/AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html:441`

```text
Rôle : ingénieur outillage qualité.

Contexte (constat AC-031) : le protocole (docs/audit/AUDIT_PROTOCOL.md:40 et §4.3) exige un registre des constats reporté de cycle en cycle ; il n'existe que dans des rapports HTML successifs. Conséquences : AC-002, AC-003 et AC-004, classés « P0 — avant prochain déploiement sensible » le 02/08 (rapport V13, docs/audit/AUDIT_CODEBASE_2026-08-02_CONSOLIDE_V13.html l.267, 356, 441), étaient encore ouverts le 22/10 après 86 tags ; le V14 a omis AC-006 et réutilisé l'identifiant AC-014 pour un autre sujet. La révision du V14 publie une table de continuité V13 → V14 → révision pour AC-001 à AC-039 : c'est la base de départ.

Étape 1 — Analyse : extrais de chaque rapport, du V11 à la révision, les identifiants AC, titres, niveaux et statuts ; repère collisions et trous (AC-014 réutilisé ; AC-022 et AC-026 jamais publiés) ; vérifie le format des titres d'un rapport à l'autre avant d'écrire le garde.

Étape 2 — Preuve rouge : un garde qui confronte les identifiants des rapports au registre échoue aujourd'hui (aucun registre).

Étape 3 — Correction : docs/audit/findings_register.json (bibliothèque standard uniquement) : identifiant stable, alias, titre, niveau, priorité, effort, horizon, statut, date d'ouverture, échéance dérivée de l'horizon, apparitions par rapport, clôture (date et preuve : chemin, ADR, commit ou identifiant d'exécution, jamais un numéro de ligne). Garde unitaire : unicité des identifiants et alias, preuve obligatoire pour un constat clos, tout identifiant présent dans un rapport existe au registre ; un P1 échu déclenche un avertissement en CI et l'échec de release:check, sauf report daté et motivé (décision du propriétaire du 22/10).

Étape 4 — Vérification : garde vert sur le registre initial, rouge sur un doublon et sur un clos sans preuve ; task lint:docs ; task test:markers ; task test:backend:unit:fast.

Spécifique : la sécurité reste hors registre ; aucun détail exploitable.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L3.3 — AC-039a · Cliquet de langue sur les documents vivants

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 0,5 j | 1 | 2,00 | P3 | Couvert — amendement pragmatique décidé le 22/10 |

**Décision du propriétaire :** Tranchée le 22/10 : amendement pragmatique de la règle de langue (détail dans le prompt).

**Preuves :** `CLAUDE.md:1018`, `docs/ARCHITECTURE.md:1-3`, `docs/INDEX.md:1`, `docs/guides/GUIDE_TESTING.md:1`

```text
Rôle : ingénieur outillage documentaire.

Contexte (constat AC-039) : CLAUDE.md (l.1018) exige une documentation en anglais ; sur 833 documents Markdown suivis (hors docs/audit), 284 sont majoritairement en français, dont des points d'entrée (docs/INDEX.md, docs/ARCHITECTURE.md, docs/guides/GUIDE_TESTING.md, docs/guides/GUIDE_DEVELOPPEMENT.md) et 17 des 30 guides, alors que README.md, docs/GETTING_STARTED.md et CONTRIBUTING.md sont en anglais. Les cartes vivantes sont françaises par décision explicite ; les plans datés de docs/superpowers/ sont historiques. Aucun outil ne mesure la langue : le corpus français croît sans signal.

Décision du propriétaire (22/10) : amendement pragmatique de la règle — anglais pour tout nouveau document ; liste des documents français figée, qui ne peut que diminuer ; exemptions : cartes vivantes, plans datés (docs/superpowers/) et rapports d'audit (docs/audit/) ; règle écrite en 2 à 4 lignes dans CLAUDE.md.

Étape 1 — Analyse : choisis un détecteur déterministe et léger (proportion de mots-outils français et anglais hors blocs de code), calibré sur un échantillon étiqueté de 40 documents ; mesure les faux positifs ; périmètre = documents Markdown suivis, hors cartes vivantes, plans datés et rapports d'audit.

Étape 2 — Preuve rouge : la création jetable d'un nouveau document en français passe aujourd'hui task lint:docs.

Étape 3 — Correction : cliquet shrink-only (liste figée des documents majoritairement français, échec sur tout nouveau document français hors exemptions, liste qui ne peut que diminuer), câblé dans task lint:docs ; règle amendée en 2 à 4 lignes dans CLAUDE.md, puis task docs:sync-agents (AGENTS.md est généré, jamais édité à la main).

Étape 4 — Vérification : preuve rouge refusée ; task lint:docs vert, miroir AGENTS.md compris ; liste figée égale au recensement.

Spécifique : aucune traduction dans cette action.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L4 — Défauts majeurs et fiabilité d'exécution

Les deux majeurs à rayon contenu (AC-028, AC-003) et deux défauts de propriété (AC-007, AC-029). Le comportement change sur des chemins partagés : chaque action exige sa preuve rouge et sa revue.

ROI du lot 1,60 · ΣV 16 · ΣJ 10 j · I max 3.

#### L4.1 — AC-007 · Joindre les tâches annulées avant de fermer leurs ressources

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 1 j | 2 | 3,00 | P1 | Couvert — A05 (séquence n° 6) |

**Preuves :** `apps/api/src/infrastructure/async_utils.py:120`, `apps/api/src/infrastructure/async_utils.py:162-164`, `apps/api/src/infrastructure/startup/shutdown.py:136-141`, `CLAUDE.md:529`

```text
Rôle : ingénieur Python asyncio, cycle de vie applicatif.

Contexte (constat AC-007) : après son délai, wait_all_background_tasks (apps/api/src/infrastructure/async_utils.py:120, 162-164) appelle cancel() sur les tâches en attente puis retourne sans les joindre ; le shutdown (apps/api/src/infrastructure/startup/shutdown.py:136-141) enchaîne ensuite la fermeture du leader, des clients et des pools. cancel() est une demande, pas une jointure : une sonde à événements du V14 a observé une tâche encore pending et son finally inachevé au retour. Règle de CLAUDE.md (l.529) : chaque tâche, client et pool a un propriétaire et est fermé ou attendu sur sa boucle avant la fermeture.

Étape 1 — Analyse : recense les appelants de wait_all_background_tasks et l'ordre exact des fermetures du shutdown ; identifie les tâches qui peuvent ignorer l'annulation.

Étape 2 — Preuve rouge : tests asyncio.Event, sans sleep arbitraire, avec un finally lent, une tâche qui lève et une tâche qui ignore l'annulation : aujourd'hui au moins une est encore pending au retour.

Étape 3 — Correction : phase de jointure bornée après l'annulation (asyncio.wait sur les tâches annulées, borne issue des settings) ; politique observable pour une tâche récalcitrante (log structuré, et métrique si une métrique de shutdown existe déjà) ; le tout avant toute fermeture de ressource.

Étape 4 — Vérification : aucune tâche pending au retour ; aucun avertissement de ressource ni sortie stderr après le résumé de task test:backend:unit:fast (xdist) et de task test:backend:unit:coverage (séquentiel), comme l'exige CLAUDE.md pour l'exécution en arrière-plan ; task lint:backend.

Spécifique : ne change pas l'ordre des autres étapes du shutdown sans le justifier.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L4.2 — AC-028 · Borner côté PostgreSQL l'attente de verrou et les transactions inactives

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 5 (G3 + R2) | 2,5 j | 3 | 2,00 | P1 | Couvert — séquence n° 3, après AC-029 (décision du 22/10) |

**Dépendances :** Après AC-029, qui retire la transaction ouverte du chemin des grants. Mêmes gabarits .env qu'AC-036.

**Décision du propriétaire :** Mesure en production en lecture seule (Q7) : non tranchée au 22/10.

**Preuves :** `apps/api/src/infrastructure/database/session.py:68-82`, `apps/api/src/infrastructure/database/errors.py:52-53`, `apps/api/tests/integration/test_workboard_screen_handover_lock_order.py:1-11`, `apps/api/src/domains/workboard/assignment_notifications.py:89`, `apps/api/src/domains/connectors/api_key_use.py:48`, `apps/api/src/domains/llm_config/jev_admin.py:97`, `apps/api/src/domains/connectors/oauth_grant_runtime.py:98-111`, `docs/architecture/ADR-304-No-Transaction-Across-A-Network-Call.md:1`

```text
Rôle : ingénieur PostgreSQL et SQLAlchemy async, fiabilité.

Contexte (constat AC-028, majeur) : aucun lock_timeout, idle_in_transaction_session_timeout ni statement_timeout global n'est posé, ni dans Compose, ni dans l'initialisation SQL, ni sur le moteur applicatif (apps/api/src/infrastructure/database/session.py:68-82 : ni connect_args ni server_settings). Seuls deux SET LOCAL lock_timeout ponctuels existent (apps/api/src/domains/connectors/api_key_use.py:48 ; apps/api/src/domains/llm_config/jev_admin.py:97). Le test apps/api/tests/integration/test_workboard_screen_handover_lock_order.py:1-11 documente un blocage de production du 21/10 : un cycle d'attente entre deux connexions, que PostgreSQL ne détecte pas, a figé toutes les écritures d'un compte. Le chemin est corrigé, pas la classe, alors que apps/api/src/infrastructure/database/errors.py:52-53 classe déjà 55P03 et 57014. Relevé en dev le 22/10 (PostgreSQL 16.15) : ces délais valent tous 0.

Point d'attention : apps/api/src/domains/connectors/oauth_grant_runtime.py:98-111 tient aujourd'hui un SELECT … FOR UPDATE pendant l'appel au point de jeton, soit une transaction ouverte pendant un appel réseau, ce qu'interdit ADR-304 (docs/architecture/ADR-304-No-Transaction-Across-A-Network-Call.md). Un lock_timeout ferait échouer le second lecteur du même grant au lieu de lui rendre le jeton frais. La correction est de retirer cette transaction (AC-029, à mener avant), jamais de relever la borne ni de poser un SET LOCAL large pour l'absorber. Un relevé du 22/10 signale aussi en dev des transactions inactives de plus de 30 s (53,5 s au maximum le 07/10), sans lien établi avec les grants : à expliquer avant de fixer la borne.

Étape 1 — Analyse : inventorie les moteurs et pools (moteur SQLAlchemy applicatif, pools psycopg du checkpointer et du Store LangGraph, moteur Alembic) ; recense toute détention longue d'un verrou de ligne ou consultatif et toute transaction ouverte pendant une attente (chacune est un défaut ADR-304 à corriger, pas une borne à accommoder) ; mesure en dev pg_stat_activity et pg_locks pendant des parcours représentatifs (tour de chat, routines, ingestion RAG, Workboard, SMS) : durée maximale des transactions inactives et des attentes de verrou. Une mesure en production n'est faite qu'en lecture seule et avec l'accord explicite du propriétaire.

Étape 2 — Preuve rouge (PostgreSQL jetable) : cycle inter-connexions reproduit (A tient une ligne FOR UPDATE puis attend B ; B attend la même ligne) — aujourd'hui B bloque ; une transaction laissée inactive n'est jamais terminée.

Étape 3 — Correction : une seule fonction calcule les server_settings du moteur applicatif à partir de deux réglages .env (0 = désactivé), avec des défauts issus de la mesure et supérieurs à la plus longue détention légitime mesurée ; Alembic et la maintenance exclus ; SET LOCAL existants prioritaires ; erreurs 55P03, 57014 et 25P03 classées et comptées au niveau du moteur (événement handle_error, pas seulement BaseRepository) ; panneau et alerte câblés.

Étape 4 — Vérification : le cycle échoue en 55P03 dans la borne ; la transaction inactive est terminée dans la borne et le pool se rétablit ; SET LOCAL garde la priorité ; après AC-029, deux lecteurs concurrents du même grant OAuth réussissent tous deux ; Alembic sans borne ; garde de couverture des métriques vert ; task test:backend:integration, task db:migrate:replay-check, task test:backend:unit:fast, task lint.

Spécifique : gabarits suivis mis à jour (.env.example, .env.prod.example, .env.min.prod.example si nécessaire, .env.demo-instance.example et .env.demo-instance.prod.example) ; les fichiers .env réels, démonstrateur compris, sont signalés au propriétaire, jamais modifiés ; documentation par amendement d'ADR-304.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L4.3 — AC-003 · Ne déduire aucun état « livré » de l'absence d'exception

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 5 (G3 + R2) | 3 j | 3 | 1,67 | P1 | Couvert — A06 + A06b (séquence n° 4), 5 sites et garde AST |

**Décision du propriétaire :** Tranchée le 22/10 (Q5) : un SSE seul n'est pas une livraison durable.

**Preuves :** `apps/api/src/infrastructure/proactive/notification.py:371-441`, `apps/api/src/infrastructure/proactive/notification.py:443-447`, `apps/api/src/domains/telephony/reapers.py:110-128`, `apps/api/src/domains/telephony/return_synthesis.py:469-497`, `apps/api/src/infrastructure/scheduler/phone_relay_runner.py:205-221`, `apps/api/src/infrastructure/scheduler/peer_message_delivery.py:385-419`, `apps/api/src/domains/diagnostics/notifications.py:117-132`, `CLAUDE.md:676`

```text
Rôle : ingénieur backend senior, fiabilité des effets durables.

Contexte (constat AC-003, majeur) : NotificationDispatcher.dispatch (apps/api/src/infrastructure/proactive/notification.py:371-441) intercepte l'échec de chaque canal (archive, FCM, SSE, canaux externes) puis calcule success sans lever (l.443-447). Cinq appelants ignorent ce résultat et écrivent ensuite un état durable : le reaper téléphonique (apps/api/src/domains/telephony/reapers.py:110-128), la synthèse de retour d'appel (apps/api/src/domains/telephony/return_synthesis.py:469-497), le relais de repli téléphonique (apps/api/src/infrastructure/scheduler/phone_relay_runner.py:205-221), la livraison entre pairs, qui marque le message livré puis annonce « livré » à l'expéditeur (apps/api/src/infrastructure/scheduler/peer_message_delivery.py:385-419), et la notification d'incident d'autodiagnostic, qui compte un envoi et marque l'incident notifié (apps/api/src/domains/diagnostics/notifications.py:117-132). Règle de CLAUDE.md (l.676) : l'absence d'exception n'est pas une preuve de livraison.

Étape 1 — Analyse : pour chaque site, l'état écrit, sa reprise possible, l'idempotence et ce que voit la personne ; recense tout autre appelant de dispatch qui écrit un état. Politique de succès partiel décidée par le propriétaire le 22/10 : un SSE seul n'est pas une livraison durable ; une notification est livrée si elle est archivée, ou si au moins un push ou un canal externe a réussi. Précise-la par type d'appelant.

Étape 2 — Preuve rouge : pour chaque site, un NotificationResult en échec conduit aujourd'hui à un état livré ou notifié.

Étape 3 — Correction : une porte unique pour les appelants durables (résultat typé obligatoire, ou variante qui lève sur échec), appliquée aux 5 sites ; l'échec est enregistré pour reprise ; garde AST qui refuse d'ignorer le résultat de dispatch avant une écriture d'état (mark_*).

Étape 4 — Vérification : pour chaque site, échec → aucun état livré et reprise possible ; succès partiel conforme à la politique ; la garde échoue sur un site fictif ; tests téléphonie, pairs et diagnostic ; task test:backend:unit:fast ; task lint.

Spécifique : aucun message réel ; aucune refonte des canaux.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L4.4 — AC-029 · Un seul point de rafraîchissement OAuth, sérialisé et clôturé

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 3,5 j | 3 | 0,86 | P1 | Couvert — séquence n° 5, avancée avant AC-028 ; porte unique retenue le 22/10 (single_flight + shared_flight) |

**Dépendances :** Avant AC-028.

**Décision du propriétaire :** Tranchée le 22/10 (Q8, retenue sans objection du propriétaire) : porte unique sur run_single_flight et run_shared_flight, écriture conditionnée au chiffré lu, amendement d'ADR-302.

**Preuves :** `apps/api/src/infrastructure/locks/oauth_lock.py:89-93`, `apps/api/src/infrastructure/locks/oauth_lock.py:178`, `apps/api/src/infrastructure/locks/oauth_lock.py:214`, `apps/api/src/core/constants.py:1683`, `apps/api/src/core/constants.py:1636`, `apps/api/src/domains/connectors/service.py:1342-1355`, `apps/api/src/domains/connectors/clients/base_oauth_client.py:413-418`, `CLAUDE.md:674`, `apps/api/src/domains/connectors/clients/base_oauth_client.py:476`, `apps/api/src/domains/connectors/service.py:744-751`, `apps/api/src/domains/agents/tools/base.py:388`, `apps/api/src/infrastructure/scheduler/heartbeat_wake_sweep.py:178`, `apps/api/src/domains/connectors/service.py:347-352`, `apps/api/src/domains/connectors/router.py:369`, `apps/api/src/infrastructure/scheduler/token_refresh.py:204`, `apps/api/src/domains/connectors/service.py:1440-1442`, `apps/api/src/domains/connectors/service.py:1402-1403`, `apps/api/src/domains/connectors/oauth_grant_runtime.py:98-111`, `apps/api/src/domains/connectors/oauth_grant_runtime.py:58-73`, `apps/api/src/core/config/connectors.py:364-371`, `docs/architecture/ADR-302-OAuth-Grant-Par-Compte-Et-Consentement-Groupe.md:44-46`, `docs/architecture/ADR-304-No-Transaction-Across-A-Network-Call.md:1`, `apps/api/src/infrastructure/utils/single_flight.py:92`, `apps/api/src/infrastructure/utils/shared_flight.py:84`, `apps/api/src/infrastructure/utils/shared_flight.py:63-66`, `apps/api/src/infrastructure/utils/shared_flight.py:191-208`, `apps/api/src/domains/connectors/clients/philips_hue_client.py:288-345`, `apps/api/src/domains/connectors/service.py:1211`, `apps/api/src/infrastructure/observability/metrics.py:117-143`, `infrastructure/observability/grafana/dashboards/10-oauth-connectors-mcp.json:500-546`, `infrastructure/observability/grafana/dashboards/10-oauth-connectors-mcp.json:1817-1822`

```text
Rôle : ingénieur backend senior, concurrence et intégrations OAuth.

Contexte (constat AC-029, complété le 22/10) :

(1) Le verrou Redis OAuthLock (apps/api/src/infrastructure/locks/oauth_lock.py:89-93) est posé avec la valeur constante « locked » et un TTL de 10 s (apps/api/src/core/constants.py:1683), puis libéré par un DELETE inconditionnel (l.178 ; force_release l.214). La section qu'il protège (apps/api/src/domains/connectors/clients/base_oauth_client.py:413-418, puis apps/api/src/domains/connectors/service.py:1342-1355) peut durer environ 36 s : 3 tentatives de http_timeout_oauth (10 s, apps/api/src/core/constants.py:1636, réglable jusqu'à 60 s) et des attentes de 2 puis 4 s. Un même réglage sert d'attente d'acquisition et de durée de bail.

(2) Ce verrou ne couvre qu'une porte sur quatre : _refresh_oauth_token a quatre appelants et seul celui du client est sous OAuthLock (apps/api/src/domains/connectors/clients/base_oauth_client.py:476). Les trois autres rafraîchissent sans verrou : ConnectorService.get_connector_credentials dès que le jeton approche de l'expiration (service.py:744-751), porte de chaque outil OAuth (apps/api/src/domains/agents/tools/base.py:388) et des balayages (ex. apps/api/src/infrastructure/scheduler/heartbeat_wake_sweep.py:178) ; refresh_connector_credentials (service.py:347-352, route apps/api/src/domains/connectors/router.py:369) ; et le job de rafraîchissement anticipé (apps/api/src/infrastructure/scheduler/token_refresh.py:204).

(3) L'écriture des nouveaux identifiants est inconditionnelle (service.py:1440-1442) : un rafraîchissement retardataire peut écraser un plus récent. Or CLAUDE.md (l.674) exige un jeton propriétaire et, là où un écrivain périmé peut valider, un jeton de clôture monotone. Sur invalid_grant, le connecteur passe en ERROR (service.py:1402-1403) : si un fournisseur invalide l'ancien jeton de rafraîchissement à la rotation, deux rafraîchissements concurrents peuvent imposer une reconnexion à la personne.

(4) Le chemin des grants (apps/api/src/domains/connectors/oauth_grant_runtime.py:98-111) sérialise par SELECT … FOR UPDATE puis relecture, mais garde cette transaction ouverte pendant l'appel au point de jeton (_post_refresh, l.58-73 ; http_timeout_oauth réglable jusqu'à 60 s, apps/api/src/core/config/connectors.py:364-371). C'est le choix d'ADR-302 (docs/architecture/ADR-302-OAuth-Grant-Par-Compte-Et-Consentement-Groupe.md:44-46), contraire à ADR-304, postérieure, qui interdit toute transaction ouverte pendant un appel réseau : ce n'est pas un modèle, c'est une seconde instance du défaut.

Décision du propriétaire (22/10) : une porte unique de rafraîchissement pour les quatre portes héritées et le chemin des grants, construite sur run_single_flight (apps/api/src/infrastructure/utils/single_flight.py:92 : un seul rafraîchissement par worker pour des appelants simultanés) et run_shared_flight (apps/api/src/infrastructure/utils/shared_flight.py:84 : un claim Redis par jeton entre workers, attente bornée, puis relecture de la base). Relecture des identifiants sous claim, rafraîchissement seulement s'il reste nécessaire ; appel au point de jeton hors de toute transaction ; écriture conditionnée par le chiffré lu avant l'appel, qui sert de jeton de clôture (une écriture périmée modifie 0 ligne) ; propagation d'une rotation aux connecteurs liés sous la même condition ; invalid_grant revérifié par relecture avant tout passage en ERROR ; si Redis est en panne, le rafraîchissement continue sans claim, la condition d'écriture gardant la cohérence ; amendement d'ADR-302.

Précautions d'implémentation (vérifiées le 22/10) : (a) run_shared_flight sonde read_shared toutes les 20 ms (shared_flight.py:191-208) : read_shared ne lit pas PostgreSQL à chaque passage — l'écriture publie un marqueur de version dans Redis et la base n'est relue qu'une fois ce marqueur vu, chaque lecture sur une session courte (ADR-304). (b) Le bail par défaut (CLAIM_TTL_SECONDS = 30, shared_flight.py:63) est inférieur au pire cas de la section (environ 36 s à 10 s de délai, jusqu'à environ 186 s à 60 s) : passer claim_ttl_s calculé depuis les réglages, et un budget d'attente choisi en sachant qu'un attendant dont le budget expire refait le rafraîchissement — sûr grâce à l'écriture conditionnée, mais coûteux. (c) run_single_flight exécute la fabrique dans le contexte du premier appelant : elle ouvre sa propre session courte, jamais celle de l'appelant, que son annulation fermerait sous le travail partagé. (d) Sans verrou de ligne pendant l'appel, une activation, une désactivation ou une révocation peut s'intercaler (ADR-302, amendement du 2026-10-15 ; ConnectorService._lock_activation, service.py:1211) : l'écriture finale est conditionnée au chiffré ET à un état toujours actif, et verrouille le grant puis ses connecteurs dans l'ordre stable d'ADR-302, en une transaction courte qui propage la rotation. (e) Le rafraîchissement manuel (refresh_connector_credentials) rejoint un rafraîchissement en cours au lieu de le contourner : le résultat en vol est un jeton neuf, pas un cache périmé. (f) Un cinquième chemin existe : Hue Remote (apps/api/src/domains/connectors/clients/philips_hue_client.py:288-345) rafraîchit par un POST direct, sans verrou, et écrit ses HueBridgeCredentials sans condition : l'inclure dans la porte unique avec son format propre, ou l'exclure par une décision écrite. (g) Les cinq séries d'OAuthLock (apps/api/src/infrastructure/observability/metrics.py:117-143) alimentent cinq panneaux du tableau 10 (infrastructure/observability/grafana/dashboards/10-oauth-connectors-mcp.json, lignes 500, 541, 546, 1817 et 1822 ; aucune règle Prometheus ne les lit) : les remplacer par des issues de rafraîchissement (réclamé, rejoint, attendu, repli, écriture perdue, invalid_grant revérifié) câblées au même tableau, garde de couverture des métriques et garde inverse verts.

Étape 1 — Analyse : cartographie les quatre portes héritées et les appelants du chemin des grants ; mesure en dev, en lecture, la part des connecteurs encore sur le chemin hérité (sans oauth_grant_id) ; relis les contrats de run_single_flight et run_shared_flight (fabrique, clé d'identité complète, attente bornée, repli sur le calcul en cas d'échec — ADR-271) et vérifie qu'ils couvrent chaque porte sans exception.

Étape 2 — Preuve rouge : deux lecteurs concurrents sur une porte sans verrou appellent deux fois le point de jeton (transport simulé) ; avec le verrou actuel, A expire, B acquiert et la sortie de A libère B ; une écriture retardataire écrase la plus récente ; sur le chemin des grants, pg_stat_activity montre une transaction ouverte pendant un appel au fournisseur ralenti ; un invalid_grant reçu après la rotation faite par un autre worker met le connecteur en ERROR.

Étape 3 — Correction : une seule fonction de rafraîchissement, appelée par les quatre portes et par le chemin des grants, applique cette décision ; suppression de force_release et is_locked s'ils n'ont toujours aucun appelant ; préfixe de la famille de clés oauth_lock inchangé (ADR-260) ; ADR-302 amendée.

Étape 4 — Vérification : un seul appel au point de jeton pour N lecteurs concurrents, toutes portes confondues ; la sortie tardive de A ne libère pas B ; l'écriture retardataire modifie 0 ligne et la relecture rend le jeton le plus récent ; aucune transaction ouverte pendant l'appel (test d'intégration sur PostgreSQL jetable) ; un invalid_grant après une rotation concurrente ne met pas le connecteur en ERROR ; Redis indisponible : le rafraîchissement aboutit et une seule écriture l'emporte ; métriques existantes conservées ou remplacées sur le tableau 10 ; task test:backend:unit:fast ; tests d'intégration ciblés sur PostgreSQL et Redis jetables (deux workers, une révocation concurrente, Redis coupé) ; task lint:backend et task lint:observability. Propose ensuite au propriétaire une preuve d'exécution sur Docker dev (expiration forcée sur un connecteur Google et un connecteur Microsoft d'un compte de preuve), à ne mener qu'avec son accord.

Spécifique : aucun appel réel à Google ni à Microsoft sans cet accord ; à mener avant AC-028, dont la borne de verrou n'a alors plus à absorber le chemin des grants.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L5 — Observabilité qui dit vrai

Tableaux et alertes qui se résolvent vers des producteurs réels et des destinataires prouvés.

ROI du lot 1,56 · ΣV 7 · ΣJ 4,5 j · I max 2.

#### L5.1 — AC-006 · Résoudre chaque panneau vers un producteur réel et trancher les règles dormantes

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 1,5 j | 2 | 2,00 | P2 | Couvert — ajouté le 22/10 (Q9), avec A07 |

**Décision du propriétaire :** Activer, amender ou retirer alerts-product.yml.

**Preuves :** `infrastructure/observability/grafana/dashboards/26-product-value.json:373`, `infrastructure/observability/grafana/dashboards/26-product-value.json:418`, `infrastructure/observability/grafana/dashboards/14-registry-checkpoints.json:808`, `infrastructure/observability/grafana/dashboards/14-registry-checkpoints.json:855`, `infrastructure/observability/scripts/audit_2026_04/orphans_analysis.py:67`, `scripts/observability/validate_observability.py:126-152`, `infrastructure/observability/prometheus/alerts-product.yml:1-8`, `scripts/audit/measure_metric_coverage.py:117`, `CLAUDE.md:795`

```text
Rôle : ingénieur observabilité (Prometheus, Grafana).

Contexte (constat AC-006, rouvert par la révision) : quatre panneaux interrogent des métriques qu'aucun code ne produit : « Cost per useful outcome (7d) » et « Time to useful outcome (p50, 7d) » du tableau 26 (infrastructure/observability/grafana/dashboards/26-product-value.json:373, 418 ; product_outcome_cost_eur_*, product_outcome_duration_seconds_bucket), « Search Rate » et « Search Duration P95 » du tableau 14 (14-registry-checkpoints.json:808, 855 ; memory_hybrid_search_*), famille déjà signalée orpheline en avril (infrastructure/observability/scripts/audit_2026_04/orphans_analysis.py:67). Le validateur (scripts/observability/validate_observability.py:126-152) ne contrôle que la structure. Le garde de couverture des métriques ne vérifie que le sens code → panneau et lit 11 fichiers de règles, dont 7 que prometheus.yml ne charge pas (scripts/audit/measure_metric_coverage.py:117) : une métrique « couverte » par une règle jamais chargée passe. alerts-product.yml (l.1-8, 4 alertes) n'est pas monté, alors que son activation était prévue après 4 semaines de base à compter du 29/07. Règle de CLAUDE.md (l.795) : chaque requête de tableau doit se résoudre vers un producteur réel, une règle d'enregistrement ou une source documentée.

Étape 1 — Analyse : extrais les séries de toutes les expressions PromQL des tableaux (LogQL, mots-clés et commentaires écartés) et résous chacune vers un producteur du code, une règle d'enregistrement chargée ou un exportateur déclaré ; pour les 4 séries orphelines, décide produire ou retirer (historique Git en lecture) ; prépare la décision du propriétaire sur alerts-product.yml (activer, amender ou retirer, avec la base mesurée si elle existe).

Étape 2 — Preuve rouge : un panneau fictif sans producteur passe aujourd'hui lint:observability ; une métrique référencée seulement par une règle non chargée passe le garde de couverture.

Étape 3 — Correction : garde inverse panneau → producteur | règle chargée | exportateur déclaré, testé en Python et câblé dans task lint:observability ; les 4 panneaux corrigés ou retirés ; garde de couverture limité aux fichiers listés par prometheus.yml ; décision écrite sur alerts-product.yml (ADR concernée ou runbook).

Étape 4 — Vérification : preuves rouges refusées ; task lint:observability, task test:alerts et garde de couverture des métriques verts. Une métrique qui deviendrait aveugle se câble ; la baseline ne se relève jamais.

Spécifique : aucun Grafana ni Prometheus de production ; validation hermétique.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L5.2 — AC-004 · Composer Alertmanager selon les canaux et rendre les routes spécialisées atteignables

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 4 (G3 + R1) | 3 j | 2 | 1,33 | P1 | Couvert — A07a puis A07b (séquence n° 7), deux gabarits, anti-doublon, 6 alertes réelles |

**Décision du propriétaire :** Politique de diffusion des routes spécialisées.

**Preuves :** `infrastructure/observability/alertmanager/docker-entrypoint.sh:86-96`, `infrastructure/observability/alertmanager/alertmanager.yml.template:16-17`, `infrastructure/observability/alertmanager/alertmanager.yml.template:58-77`, `infrastructure/observability/alertmanager/alertmanager.yml.template:84-133`, `infrastructure/observability/alertmanager/alertmanager.yml.template:237`, `infrastructure/observability/alertmanager/alertmanager.yml.template:256`, `infrastructure/observability/alertmanager/alertmanager-email-only.yml.template:26-66`, `infrastructure/observability/prometheus/prometheus.yml:29-33`, `infrastructure/observability/prometheus/alerts-core.yml:41`, `infrastructure/observability/prometheus/alerts-core.yml:317`, `infrastructure/observability/alertmanager/docker-entrypoint.sh:79-80`

```text
Rôle : ingénieur observabilité, Alertmanager.

Contexte (constat AC-004, majeur). Composition : le gabarit complet est choisi dès que Slack critique OU PagerDuty est renseigné (infrastructure/observability/alertmanager/docker-entrypoint.sh:79-96), alors qu'il référence sans condition la clé PagerDuty et les webhooks Slack warning et sécurité qu'il annonce optionnels (alertmanager.yml.template:16-17, 84-133, 237, 256). La matrice du V14 a montré l'échec de validation de SMTP+PagerDuty, SMTP+Slack et Slack critique seul : Alertmanager refuse alors sa configuration. Routage : dans les deux gabarits (alertmanager.yml.template:58-77 ; alertmanager-email-only.yml.template:26-66), les deux premières routes filtrent severity critical puis warning sans continue ; or les 32 alertes chargées (infrastructure/observability/prometheus/prometheus.yml:29-33 → alerts-core.yml) portent toutes critical (13) ou warning (19). Les routes spécialisées sont donc inatteignables, y compris en mode SMTP seul, le défaut. Six alertes réelles sont concernées : DatabaseDown, RedisDown, SSELatencyP95High, RedisConnectionPoolExhaustion, LLMCallsWithoutUsage, EmbeddingOperationsFailing (ex. alerts-core.yml:41, 317). La route finance (.*(Budget|Cost).*) n'a aucun producteur chargé.

Étape 1 — Analyse : fais décider par le propriétaire la politique de diffusion (route spécialisée exclusive, ou en plus de la générique) ; inventorie les canaux et leurs combinaisons valides.

Étape 2 — Preuve rouge : matrice hermétique amtool check-config sur aucun canal, SMTP, SMTP+PagerDuty, SMTP+Slack, Slack critique seul, tous canaux, valeurs partielles ; amtool config routes test sur les 6 alertes dans les deux modes : échecs actuels.

Étape 3 — Correction : configuration rendue par fragments, un par canal renseigné ; routes spécialisées placées avant les génériques, ou continue: true selon la politique, sans doublon de notification ; route finance retirée ou dotée d'un producteur, décision écrite ; tâche Taskfile hermétique pour la matrice, appelée par la CI (ADR-151).

Étape 4 — Vérification : check-config vert sur toute la matrice ; chaque alerte réelle atteint le récepteur décidé ; task test:alerts, task lint:observability, task lint (dont ci-parity).

Spécifique : aucun webhook, courriel ni page réels ; valeurs synthétiques.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L6 — Discussions proactives : coût et croissance bornés

Même domaine (ADR-358 à ADR-360) : appel payant répété, croissance non mesurée, rétention non décidée.

ROI du lot 1,33 · ΣV 5 · ΣJ 3,75 j · I max 3.

#### L6.1 — AC-034a · Mesurer la croissance des tables d'exécution des discussions proactives

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 0,5 j | 1 | 2,00 | P3 | Couvert — ajouté le 22/10 (Q9) |

**Preuves :** `apps/api/src/domains/proactive_discussions/models.py:96`, `apps/api/src/domains/proactive_discussions/models.py:185`, `apps/api/src/domains/proactive_discussions/finance_models.py:59`, `apps/api/src/domains/agents/effects/volume.py:43-47`, `apps/api/src/infrastructure/observability/lifetime_metrics.py:247-253`

```text
Rôle : ingénieur backend, observabilité.

Contexte (constat AC-034) : discussion_runs, discussion_openings, discussion_outbox (apps/api/src/domains/proactive_discussions/models.py:96, 185), discussion_spend_reservations et discussion_budget_buckets (finance_models.py:59) ne sont purgées qu'avec le compte. Les jauges de volume (lia_ledger_rows, lia_ledger_bytes) ne couvrent que les tables de registre (apps/api/src/domains/agents/effects/volume.py:43-47 ; apps/api/src/infrastructure/observability/lifetime_metrics.py:247-253) : la croissance de ces tables est invisible.

Étape 1 — Analyse : comment volume.py mesure ses tables (estimation ou comptage, coût de la requête, fréquence) ; volumes actuels en dev ; la mesure peut-elle s'étendre par une déclaration de tables plutôt que par une seconde liste ?

Étape 2 — Preuve rouge : un test montre que ces cinq tables ne sont pas mesurées.

Étape 3 — Correction : étendre la déclaration des tables mesurées (une seule liste) avec un label de table borné ; panneau dans le tableau de bord existant ; alerte de croissance seulement si un seuil est défendable, sinon décision écrite.

Étape 4 — Vérification : jauges exposées en test ; garde de couverture des métriques vert (panneau câblé, « or vector(0) » si nécessaire) ; task lint:observability ; task test:backend:unit:fast.

Spécifique : coût de mesure borné (estimation pg_class si le comptage exact coûte, comme pour les registres) ; la rétention relève d'AC-034b.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L6.2 — AC-023 · Borner la recompilation payante d'une règle sémantiquement refusée

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 1,75 j | 2 | 1,71 | P2 | Couvert — A16 (séquence n° 8) |

**Preuves :** `apps/api/src/infrastructure/proactive/discussion_runner.py:211-220`, `apps/api/src/domains/proactive_discussions/rule_controls.py:73-75`, `apps/api/src/domains/proactive_discussions/backoff.py:23-56`, `apps/api/src/infrastructure/proactive/discussion_runner.py:681-690`

```text
Rôle : ingénieur backend, coûts LLM et ordonnancement.

Contexte (constat AC-023) : la compilation des contrôles de lecture d'une discussion proactive n'est mise en cache qu'après restricted_sources (apps/api/src/infrastructure/proactive/discussion_runner.py:211-220). Une citation inexacte lève un ValueError avant l'enregistrement du cache (apps/api/src/domains/proactive_discussions/rule_controls.py:73-75) ; retry_deadline (apps/api/src/domains/proactive_discussions/backoff.py:23-56) ne reconnaît que les refus 429/503 et rend None, d'où un règlement « failed » sans retry_after (discussion_runner.py:681-690). Le tick suivant recompile les mêmes entrées et paie un nouvel appel au modèle, à chaque tick.

Étape 1 — Analyse : trace le cycle complet (compilation, cache, règlement, tick suivant) ; recense les autres refus sémantiques du même chemin ; propose la politique — cache négatif clé par rule_cache_signature, ou recul borné — invalidée quand les contrôles, les sources ou la version du prompt changent ; décision du propriétaire si la durée relève du métier.

Étape 2 — Preuve rouge : deux ticks identiques sur une compilation refusée appellent deux fois le modèle (modèle simulé).

Étape 3 — Correction : refus typé, distinct d'une erreur transitoire, et état négatif clé par la signature des entrées, avec la même propriété de claim et les mêmes budgets ; aucun run refusé publié.

Étape 4 — Vérification : deux ticks identiques → un seul appel ; entrée modifiée → recompilation ; erreur transitoire toujours reprise selon retry_deadline ; tests de répétition, expiration, annulation et concurrence ; task test:backend:unit:fast ; task lint:backend.

Spécifique : aucun modèle payant ; budgets inchangés.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L6.3 — AC-034b · Décider et outiller la rétention des tables d'exécution des discussions

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 1,5 j | 3 | 0,67 | P3 | Complément — décision du propriétaire |

**Dépendances :** Après AC-034a (mesurer avant de purger).

**Décision du propriétaire :** Rétention par table.

**Preuves :** `apps/api/src/domains/proactive_discussions/models.py:96`, `apps/api/src/domains/proactive_discussions/models.py:185`, `apps/api/src/domains/proactive_discussions/finance_models.py:59`

```text
Rôle : ingénieur backend, persistance.

Contexte (constat AC-034) : les cinq tables d'exécution des discussions proactives (discussion_runs, discussion_openings, discussion_outbox, discussion_spend_reservations, discussion_budget_buckets ; apps/api/src/domains/proactive_discussions/models.py:96, 185 ; finance_models.py:59) ne sont supprimées qu'avec le compte, contrairement au contexte dérivé qui expire. Aucune décision de rétention n'est écrite (ADR-358).

Étape 1 — Analyse : pour chaque table, qui la lit et jusqu'à quand (affichage, budgets glissants, registres, export du compte, preuve d'une action au registre des effets) ; propose une rétention par table (par exemple outbox livré, réservations réglées) ou une conservation justifiée ; fais valider par le propriétaire avant tout code.

Étape 2 — Preuve rouge : une ligne éligible à la purge selon la décision subsiste après le passage de maintenance.

Étape 3 — Correction : purge par lots bornés, sur le leader, avec jitter (règle des jobs périodiques), qui ne supprime rien dans le doute ni aucune ligne encore lue par un budget glissant ou un registre ; métrique des lignes purgées, câblée.

Étape 4 — Vérification : tests sur PostgreSQL jetable (lignes éligibles purgées, non éligibles conservées, deux workers concurrents, reprise après interruption) ; task test:backend:integration ciblé ; task lint.

Spécifique : décision écrite en amendement d'ADR-358 ; aucune migration destructive sans validation.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L7 — Assurance mesurée

Clôture prouvée des E2E, dénominateur de couverture honnête, marge backend rétablie.

ROI du lot 0,96 · ΣV 6 · ΣJ 6,25 j · I max 1.

#### L7.1 — AC-021 · Prouver la clôture des oracles E2E par un rejeu contrôlé

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 1 j | 1 | 2,00 | P2 | Couvert — A10 (séquence n° 10) |

**Preuves :** `apps/web/e2e/playwright.config.ts:47`, `apps/web/e2e/playwright.config.ts:65`

```text
Rôle : ingénieur de tests E2E (Playwright).

Contexte : AC-021 (oracles E2E réalignés sur les interactions décidées) est présumé clos par la révision : onze fichiers E2E (dix spécifications et une fixture) ont été réalignés, et le dernier passage complet observé d'une session concurrente (691 cas, 2 workers, aucune relance) a écrit « passed ». La révision n'a ni rejoué la suite ni disposé du journal complet ; la configuration autorise des relances (apps/web/e2e/playwright.config.ts:47, 65).

Étape 1 — Analyse : liste les spécifications touchées par AC-021, AC-024 et AC-025 ; vérifie qu'aucune assertion utile n'a été retirée ou affaiblie (lecture des diffs d'oracles).

Étape 2 — Rejeu : task test:e2e sur un build de production frais, 0 relance, médias natifs compris ; puis 3 rejeux des spécifications touchées pour mesurer l'instabilité.

Étape 3 — Correction : uniquement si un échec est reproduit, en distinguant défaut produit, fixture, banc et instabilité ; jamais par retrait d'une assertion utile.

Étape 4 — Vérification : comptes exacts (passés, échoués, ignorés, rejoués), sans additionner les rejeux comme des tests distincts ; clôture inscrite au registre (AC-031) avec sa preuve.

Spécifique : backend entièrement simulé (suite hermétique) ; aucun fournisseur réel.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L7.2 — AC-014 · Réintégrer dans la couverture les primitives d'interface comportementales (pilote)

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 1,25 j | 1 | 0,80 | P2 | Couvert — A13, AC-040 dans son registre (séquence n° 9) |

**Preuves :** `apps/web/vitest.config.mts:49-62`, `apps/web/src/components/ui/dialog.tsx:37-46`, `apps/web/src/components/ui/dialog.tsx:64-70`

```text
Rôle : ingénieur frontend React, tests.

Contexte (constat AC-014 du V14, AC-040 dans le registre proposé) : quatorze primitives sont exclues de la couverture (apps/web/vitest.config.mts:49-62) au motif qu'elles n'auraient ni branche ni interaction propre ; apps/web/src/components/ui/dialog.tsx contient pourtant une détection de combobox ouverte et un gestionnaire d'Échap qui la préserve (l.37-46), ainsi que la traduction et le retour de focus (l.64-70).

Étape 1 — Analyse : classe chaque exclusion selon sa logique réelle (re-export trivial ou comportement) ; choisis un premier ensemble cohérent de fichiers comportementaux.

Étape 2 — Preuve rouge : une fois ces fichiers réintégrés, la couverture de leurs branches est aujourd'hui insuffisante (mesure par fichier).

Étape 3 — Correction : tests comportementaux d'abord (clavier, noms traduits, focus, désactivation et erreur, transitions), puis réintégration dans le dénominateur ; motif vérifiable pour chaque exclusion restante ; garde qui refuse l'ajout de logique (branche, gestionnaire) dans un fichier exclu.

Étape 4 — Vérification : task test:frontend:coverage (environnement neutralisé), numérateurs et dénominateurs avant et après ; seuils inchangés ou relevés ; task lint:frontend.

Spécifique : ni snapshot ni assertion CSS comme oracle unique ; un pilote ne déclare pas toutes les exclusions résolues.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L7.3 — AC-030b · Rétablir la marge de couverture backend par les domaines sous le plancher

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 4 j | 1 | 0,75 | P1 | Couvert — ajouté le 22/10 (Q9) |

**Dépendances :** Après AC-030a (la porte empêche une nouvelle érosion pendant le rattrapage).

**Preuves :** `Taskfile.yml:1294-1298`, `apps/api/pyproject.toml:245`, `docs/guides/GUIDE_TESTING.md:2124-2126`, `CLAUDE.md:509`

```text
Rôle : ingénieur de tests backend, priorisation par le risque.

Contexte (constat AC-030) : couverture backend de 78,66 % le 22/10 pour un plancher de 78 % (apps/api/pyproject.toml:245), soit 0,66 point de marge contre les 2 exigés (CLAUDE.md l.509 ; docs/guides/GUIDE_TESTING.md:2124-2126). Domaines sous le plancher : sms 53,6 %, proactive_discussions 70,2 %, infrastructure/proactive 67,9 %, conversations 44,1 %.

Étape 1 — Analyse : remesure par domaine avec la commande canonique (task test:backend:unit:coverage) ; dans chaque domaine faible, classe les lignes non couvertes par risque métier (transitions persistantes, chemins d'erreur, reprise, concurrence, quotas) plutôt que par volume.

Étape 2 — Tests : tests comportementaux des chemins à risque (unitaires, et intégration sur PostgreSQL jetable quand la sémantique SQL compte), sans tests creux ni mocks qui contournent la frontière testée.

Étape 3 — Si un test révèle un défaut produit : arrête, documente, et traite-le comme une action distincte.

Étape 4 — Vérification : marge d'au moins 2 points mesurée par la commande canonique ; sms et proactive_discussions au moins au plancher ; task test:backend:unit:fast ; task test:markers.

Spécifique : aucun plancher modifié ici. Un relèvement ultérieur garde au moins 2 points de marge et relève de la décision du propriétaire.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L8 — Propriété des traitements RAG

Exclu de la vague lia-a7 par décision du propriétaire. À replanifier : AC-002 est le plus ancien majeur ouvert (02/08).

ROI du lot 0,93 · ΣV 7 · ΣJ 7,5 j · I max 4.

#### L8.1 — AC-005 · Donner un propriétaire au verrou global de réindexation

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 2,5 j | 3 | 1,20 | P1 | Exclu — A08, lot 4 écarté par le propriétaire |

**Preuves :** `apps/api/src/domains/rag_spaces/reindex.py:343-348`, `apps/api/src/domains/rag_spaces/reindex.py:366-367`, `apps/api/src/domains/rag_spaces/reindex.py:452-461`, `apps/api/src/domains/rag_spaces/reindex.py:551-552`, `apps/api/src/infrastructure/locks/redis_claim.py:87`, `apps/api/src/infrastructure/locks/redis_claim.py:126`, `CLAUDE.md:674`

```text
Rôle : ingénieur backend, concurrence distribuée (Redis).

Contexte (constat AC-005) : le drapeau global de réindexation RAG est acquis par SET NX avec la valeur constante « 1 » (apps/api/src/domains/rag_spaces/reindex.py:343-348) ; le renouvellement fait un EXPIRE inconditionnel (l.366-367) et trois chemins font un DELETE inconditionnel (l.452-461, 551-552). Après expiration et reprise, un ancien drain peut prolonger ou supprimer le drapeau du nouveau. Les primitives propriétaires existent (apps/api/src/infrastructure/locks/redis_claim.py:87-126 : try_claim, refresh_claim, release_claim, held_claim). Règle de CLAUDE.md (l.674).

Étape 1 — Analyse : cartographie acquisition, renouvellement, progression et libération ; identifie les effets à arrêter quand le claim est perdu ; vérifie l'intention transactionnelle de réindexation (une maintenance prévue sur changement de dimension ne doit pas disparaître).

Étape 2 — Preuve rouge (Redis jetable, deux acteurs) : A expire, B reprend ; le renouvellement puis l'arrêt tardifs de A touchent le drapeau de B.

Étape 3 — Correction : redis_claim avec un jeton unique par exécution ; renouvellement, progression et libération conditionnés ; arrêt des effets sur ClaimLost avant le document suivant ; échec Redis et annulation bornés ; la génération servie reste en place jusqu'à la bascule (règle RAG de CLAUDE.md).

Étape 4 — Vérification : le scénario rouge ne touche plus B ; tests d'annulation et de reprise ; suites RAG ciblées ; task test:backend:unit:fast ; task lint:backend.

Spécifique : famille de clés inchangée ou déclarée (ADR-260) ; aucun fournisseur d'embedding réel.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L8.2 — AC-002 · Fencer de bout en bout les traitements de documents RAG téléversés

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 4 (G3 + R1) | 5 j | 4 | 0,80 | P1 | Exclu — A09, lot 4 écarté par le propriétaire |

**Décision du propriétaire :** Réintégrer le lot RAG dans une vague (exclu jusqu'ici) ; migration éventuelle.

**Preuves :** `apps/api/src/domains/rag_spaces/source_document_lease.py:19-22`, `apps/api/src/domains/rag_spaces/source_document_lease.py:24-39`, `apps/api/src/domains/rag_spaces/processing.py:648-651`, `apps/api/src/domains/rag_spaces/processing.py:700-706`, `apps/api/src/domains/rag_spaces/processing.py:718-737`, `apps/api/src/domains/rag_spaces/processing.py:785-791`, `apps/api/src/domains/rag_spaces/jobs_repository.py:125-131`, `apps/api/src/domains/rag_spaces/jobs_repository.py:104-114`

```text
Rôle : ingénieur backend senior, persistance concurrente (PostgreSQL).

Contexte (constat AC-002, majeur, ouvert depuis le 02/08) : pour un document téléversé, aucune source native n'est active : require_source_document sort immédiatement (apps/api/src/domains/rag_spaces/source_document_lease.py:19-39) et ne contrôle ni propriétaire ni bail. Le booléen de heartbeat_document est ignoré avant chaque lot d'embedding (apps/api/src/domains/rag_spaces/processing.py:648-651) ; l'échange des chunks n'est précédé d'aucune vérification du claim (l.700-706) ; le succès écrit READY et efface worker_id par une mise à jour sur la seule clé primaire (l.718-737) ; l'échec appelle fail_or_retry_document, dont l'UPDATE ne filtre que sur id (apps/api/src/domains/rag_spaces/jobs_repository.py:125-131). Le chemin natif (Drive, Gmail) applique déjà le bon motif : SELECT … FOR UPDATE conditionné par worker_id et lease_expires_at > clock_timestamp() (jobs_repository.py:104-114). Une sonde à deux sessions (V14 P02) a montré qu'un échec tardif de A remet PENDING et efface le propriétaire B.

Étape 1 — Analyse : cartographie chaque mutation du chemin upload (heartbeat, échange des chunks, succès, échec ou retry, reaper) et la transaction qui l'écrit ; présente le schéma de solution (réutilisation du motif natif), ses risques et s'il exige une migration ; fais valider avant tout code si une migration ou un contrat public change.

Étape 2 — Preuve rouge (PostgreSQL jetable, deux sessions) : A réclame, son bail expire, B reprend ; le succès puis l'échec tardifs de A modifient l'état et les chunks de B.

Étape 3 — Correction : chaque mutation conditionnée par worker_id et un bail non expiré, vérifiés sous verrou dans la transaction qui écrit ; heartbeat refusé → arrêt immédiat (SourceLeaseLost) avant tout appel d'embedding ou écriture ; échange des chunks et règlement d'état atomiques ; aucune session ouverte pendant un appel au fournisseur (ADR-304).

Étape 4 — Vérification : les actions tardives de A modifient 0 ligne et laissent les chunks de B intacts ; annulation, crash après effet et reprise par le reaper couverts ; suites RAG, intégration et agents impactées ; task test:backend:unit:fast ; task lint.

Spécifique : aucun fournisseur réel ; aucune baseline relevée.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

### L9 — Dette structurelle et gouvernance documentaire, par pilotes

Programmes longs : un pilote mesuré par lot, jamais un chantier global.

ROI du lot 0,53 · ΣV 14 · ΣJ 26,5 j · I max 4.

#### L9.1 — AC-011a · Sortir de users le modèle de lecture d'administration (pilote de couplage)

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 3 (G2 + R1) | 2,5 j | 3 | 1,20 | P2 | Différé — A18 (lot 7), pilote recommandé |

**Note :** Levier mesuré : jusqu'à 7 couples réciproques en une extraction.

**Preuves :** `apps/api/src/domains/users/repository.py:516-523`, `CLAUDE.md:527`, `scripts/audit/measure_coupling.py:157`

```text
Rôle : architecte backend (DDD), couplage.

Contexte (constat AC-011) : 22 couples réciproques à l'exécution sur 59 domaines (28 tous imports confondus, contre 25 au V13) ; 11 passent par users. La liste d'administration des utilisateurs importe localement les modèles de 7 domaines « pour éviter les dépendances circulaires » (apps/api/src/domains/users/repository.py:516-523 : interests, memories, rag_spaces, scheduled_actions, skills, usage_limits, user_mcp), le contournement que CLAUDE.md interdit (l.527 : un import local qui cache une arête).

Étape 1 — Analyse : mesure le graphe avant (scripts/audit/measure_coupling.py, l.157) ; identifie les consommateurs de cette liste et les arêtes que son déplacement supprimerait ; choisis l'hôte (module de composition ou de reporting hors users, ou un port) sans créer de module « shared » fourre-tout.

Étape 2 — Preuve : un test de caractérisation fige la réponse actuelle de la liste d'administration (contenu, tri, pagination, total exact).

Étape 3 — Correction : déplace le modèle de lecture ; supprime les imports locaux ; abaisse la baseline des cycles seulement après mesure.

Étape 4 — Vérification : couples à l'exécution en baisse (avant et après), aucune arête déplacée ailleurs, aucun import local nouveau ; tests des domaines touchés ; task test:backend:unit:fast ; task lint (cliquets de couplage et de taille).

Spécifique : comportement de l'API d'administration inchangé.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.2 — AC-038 · Ramener CLAUDE.md à des règles et des pointeurs

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G1 + R1) | 2 j | 3 | 1,00 | P3 | Complément — décision du propriétaire |

**Décision du propriétaire :** Format cible de la section des pointeurs.

**Preuves :** `CLAUDE.md:1164`, `CLAUDE.md:1171`

```text
Rôle : rédacteur technique, gouvernance des instructions d'agents.

Contexte (constat AC-038) : CLAUDE.md compte environ 272 Ko et 1 274 lignes ; la section « Useful Documentation Pointers » (à partir de la l.1164) en occupe 57 %, avec des puces de plus de 12 000 caractères qui racontent des ADR entiers (ex. l.1171). AGENTS.md en est le miroir généré. Chaque session d'agent charge ce texte : coût de contexte et dilution des règles.

Étape 1 — Analyse : pour chaque puce de la section, l'ADR ou le document technique qui porte déjà la narration ; ce qui manque ailleurs et doit être déplacé, jamais perdu ; propose un format (une ligne par entrée : sujet — ADR — document) et des limites de longueur ; fais valider par le propriétaire.

Étape 2 — Preuve rouge : un garde de longueur par puce et par section échoue aujourd'hui.

Étape 3 — Correction : narration déplacée dans les ADR ou docs/technical (amendements datés), pointeurs réduits à une ligne ; garde de longueur dans task lint:docs ; miroir régénéré par task docs:sync-agents.

Étape 4 — Vérification : task lint:docs vert (doc_facts, agents_mirror, doc_maps) ; aucune règle des sections Systemic Rules et Key Patterns modifiée ; taille avant et après.

Spécifique : AGENTS.md ne s'édite jamais à la main.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.3 — AC-013 · Réduire un point chaud React Hooks et complexité (pilote)

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G2 + R0) | 2,5 j | 3 | 0,80 | P2 | Couvert — A15 (séquence n° 9) |

**Preuves :** `apps/web/.cc-baseline.json:15`, `apps/web/scripts/check-react-hooks-ratchet.mjs:28`, `apps/web/scripts/check-cc-ratchet.mjs:27`

```text
Rôle : ingénieur frontend React senior.

Contexte (constat AC-013) : 30 écarts React Hooks sur 25 fichiers et 39 violations de complexité sur 38 fichiers, maximum 46 dans ChatMessage.tsx (apps/web/.cc-baseline.json:15). Les cliquets passent (apps/web/scripts/check-react-hooks-ratchet.mjs:28 ; check-cc-ratchet.mjs:27) : la dette est gelée, pas réduite.

Étape 1 — Analyse : choisis un point chaud (par exemple ChatMessage.tsx) ; cartographie ses effets, ses dépendances et ses règles pures ; liste les scénarios à risque (montage et démontage, changement de compte, réponses tardives, annulation).

Étape 2 — Preuve : tests de caractérisation de ces scénarios avant toute extraction.

Étape 3 — Correction : extraction de règles pures et de cycles d'effets cohésifs (hooks dédiés) ; suppression des exemptions du fichier ; aucune règle désactivée.

Étape 4 — Vérification : complexité du fichier et totale, avant et après (pas de déplacement de dette) ; baselines abaissées seulement après réduction ; task lint:frontend, task test:frontend, task test:frontend:coverage ; E2E impactés.

Spécifique : interface, i18n et API inchangées.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.4 — AC-012b · Résorber les diagnostics MyPy neutralisés d'une frontière à fort impact

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G2 + R0) | 3 j | 2 | 0,67 | P2 | Couvert — A14b (conversations.service, séquence n° 9) |

**Dépendances :** Après AC-012a.

**Preuves :** `scripts/audit/measure_mypy_debt.py:116`

```text
Rôle : ingénieur Python senior, typage strict.

Contexte (constat AC-012) : 89 couples (module, code) neutralisés couvrent 489 fichiers ; sans les seuls disabled_error_code, MyPy signale 859 diagnostics sur 144 fichiers (arg-type 268, assignment 132, return-value 108, no-any-return 97, attr-defined 77). Les 6 couples morts relèvent d'AC-012a ; le cliquet est scripts/audit/measure_mypy_debt.py (l.116).

Étape 1 — Analyse : sonde sans exemptions sur le module choisi (par exemple conversations.service) ; classe les diagnostics (défaut réel, annotation manquante, Any propagé).

Étape 2 — Preuve : tout diagnostic qui révèle un défaut réel reçoit d'abord un test rouge.

Étape 3 — Correction : types corrigés à la source (ni cast, ni Any, ni ignore) ; couples devenus inutiles retirés ; baseline abaissée.

Étape 4 — Vérification : diagnostics de la sonde avant et après, globaux et du module (aucun déplacement) ; task lint:mypy-debt ; task lint:backend ; suites du module.

Spécifique : ne refactorise pas un domaine entier pour un diagnostic local.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.5 — AC-010 · Réduire un point chaud d'orchestration backend (pilote)

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G2 + R0) | 3,5 j | 4 | 0,57 | P2 | Différé — A17 (lot 7) |

**Preuves :** `apps/api/src/domains/agents/api/service.py:421`, `apps/api/src/infrastructure/startup/schedulers.py:89`, `apps/api/src/domains/agents/services/memory_extractor.py:215`, `apps/api/src/domains/agents/api/router.py:345`, `apps/api/src/domains/agents/nodes/planner_node_v3.py:78`, `apps/api/src/domains/agents/services/query_analyzer_service.py:750`

```text
Rôle : ingénieur backend senior, refactorisation sûre.

Contexte (constat AC-010) : 263 fonctions à CC ≥ 15 (maximum 77) et 170 fonctions de plus de 100 SLOC ; les queues se concentrent dans _stream_with_new_services (apps/api/src/domains/agents/api/service.py:421 ; 719 SLOC, CC 66), init_scheduler (apps/api/src/infrastructure/startup/schedulers.py:89), extract_memories_background (apps/api/src/domains/agents/services/memory_extractor.py:215 ; CC 74), stream_chat (apps/api/src/domains/agents/api/router.py:345), planner_node_v3 (apps/api/src/domains/agents/nodes/planner_node_v3.py:78 ; CC 77) et analyze_full (apps/api/src/domains/agents/services/query_analyzer_service.py:750 ; CC 75). Tendance favorable depuis le V13.

Étape 1 — Analyse : choisis UN point chaud (le plus souvent modifié selon l'historique, en lecture) ; cartographie ses décisions et l'ordre de ses effets.

Étape 2 — Preuve : tests de caractérisation (sorties et ordre des effets) avant extraction.

Étape 3 — Correction : extraction de décisions pures ou d'une machine d'états cohésive ; aucun déplacement de complexité vers un autre fichier sans baisse totale.

Étape 4 — Vérification : scripts/audit/measure_cc.py et measure_sloc.py avant et après (fonction, fichier, total) ; plafonds abaissés seulement après réduction ; suites du périmètre, agents, modes xdist et séquentiel ; task lint.

Spécifique : un seul point chaud par lot ; contrats inchangés.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.6 — AC-011b · Défaire les couples réciproques d'agents par des ports

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 2 (G2 + R0) | 8 j | 4 | 0,25 | P2 | Différé — A18 (programme) |

**Dépendances :** Après AC-011a.

**Preuves :** `CLAUDE.md:527`, `scripts/audit/measure_coupling.py:157`

```text
Rôle : architecte backend.

Contexte (constat AC-011) : 9 des 22 couples réciproques à l'exécution passent par agents. Après le pilote AC-011a (users), traiter agents par ports (Protocol), injection ou événements, jamais par import local (CLAUDE.md l.527). Mesure : scripts/audit/measure_coupling.py (l.157).

Étape 1 — Analyse : liste les 9 couples, la direction de dépendance légitime de chacun et le mécanisme le moins invasif ; ordonne-les par gain (couples supprimés) sur risque.

Étape 2 — Preuve : caractérisation des comportements qui traversent chaque arête choisie.

Étape 3 — Correction : un couple par lot ; dépendance inversée par un port déclaré côté consommateur.

Étape 4 — Vérification : couples avant et après, aucun import local, baselines abaissées après mesure ; suites des deux domaines ; task lint.

Spécifique : pas de module « shared » monolithique.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

#### L9.7 — AC-039b · Traduire les points d'entrée de la documentation

| V | J | I | ROI | Priorité | Session lia-a7 |
|---|---|---|---|---|---|
| 1 (G1 + R0) | 5 j | 2 | 0,20 | P3 | Complément — après AC-039a |

**Dépendances :** Après AC-039a.

**Décision du propriétaire :** Non exigée par la politique du 22/10 (liste française figée, qui ne peut que diminuer) : à planifier si le propriétaire le souhaite.

**Preuves :** `CLAUDE.md:1018`, `docs/ARCHITECTURE.md:1-3`, `docs/INDEX.md:1`, `docs/guides/GUIDE_TESTING.md:1`

```text
Rôle : rédacteur technique bilingue.

Contexte (constat AC-039) : 284 des 833 documents Markdown suivis (hors docs/audit) sont majoritairement en français, dont docs/INDEX.md, docs/ARCHITECTURE.md, docs/guides/GUIDE_TESTING.md et docs/guides/GUIDE_DEVELOPPEMENT.md, alors que CLAUDE.md (l.1018) exige l'anglais ; README.md, docs/GETTING_STARTED.md et CONTRIBUTING.md sont déjà en anglais.

Étape 1 — Analyse : selon la politique décidée (AC-039a), liste les points d'entrée à traduire en premier (documents les plus liés, guides de contribution) ; vérifie les ancres et les liens entrants.

Étape 2 — Correction : traduction fidèle, sans perte ni réécriture du fond ; ancres stables ou liens entrants mis à jour.

Étape 3 — Vérification : task lint:docs vert (liens, faits, orphelins) ; baseline du cliquet de langue abaissée.

Spécifique : les cartes vivantes restent françaises (décision explicite) ; aucune traduction automatique non relue.

Contraintes communes — Lis d'abord CLAUDE.md (et apps/web/CLAUDE.md pour le frontend) et applique ses règles systémiques. La sécurité est hors périmètre : ne modifie ni ne réévalue aucun mécanisme de sécurité. Aucune opération Git en écriture (add, commit, stash, checkout, reset, restore) : l'utilisateur les gère ; pour lire, uniquement des commandes de plomberie préfixées de GIT_OPTIONAL_LOCKS=0. Travail inline, sans sous-agent, dans D:\Developpement\LIA. L'arbre est partagé avec d'autres sessions : ne touche que ton périmètre et ne réécris aucun changement que tu n'as pas fait. Aucun seuil abaissé, aucune baseline relevée, aucune exemption ajoutée. Aucun fournisseur réel, aucun appel payant, aucun déploiement. Tests d'intégration sur l'hôte contre PostgreSQL et Redis jetables (testcontainers, --no-cov), jamais dans le conteneur lia-api-dev. Si l'analyse infirme le constat, arrête-toi et rapporte la preuve au lieu de corriger. Rapport final : cause racine prouvée, fichiers modifiés, commandes exactes et codes de sortie, comptes de tests (passés, échoués, ignorés), avertissements, limites et ce qui reste non prouvé.
```

## 6. Définition de terminé, commune à toutes les actions

- Un rapport d'analyse précède tout code : preuves, cause racine, option retenue. L'action s'arrête si le constat est infirmé.
- Chaque comportement corrigé a sa preuve rouge puis verte ; un garde-fou ajouté échoue sur son cas témoin.
- Portes : `task lint`, plus la suite du rayon (unitaires backend rapides, frontend, intégration jetable, E2E hermétique selon le cas) ; `task ci:fast` avant de proposer un commit.
- Aucun seuil abaissé ni baseline relevée ; toute baisse de dette est mesurée avant et après.
- L'entrée du registre des constats (AC-031) reçoit son statut et sa preuve (chemin, commit ou exécution).
- Revue adversariale du diff ; documentation et ADR mis à jour quand le comportement change.

## 7. Limites

- Les charges sont des estimations fondées sur les preuves de la révision, non des mesures ; G, R et I relèvent du jugement, explicité en section 1.
- Le risque de reconnexion forcée d'AC-029 dépend de la politique de rotation du fournisseur ; la part des connecteurs encore sur le chemin hérité n'a pas été mesurée.
- Aucune mesure en production ; la sécurité est exclue. Tant que Q7 reste ouverte, la borne d'AC-028 se calibre sur les seuls parcours de dev.
- Les numéros de ligne valent pour l'état de référence : une action menée après d'autres relocalise ses lignes par le texte qu'elles citent.
