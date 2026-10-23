# LIA Audit V14 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Analyse et décisions inline ; déléguer uniquement les opérations mécaniques indépendantes si les instructions applicables l'autorisent.

**Goal:** Résorber les défauts démontrés en maximisant le bénéfice par effort et en minimisant le rayon de régression, sans transformer une remise en qualité en refonte générale.

**Architecture:** Conserver les contrats et les primitives existantes. Une action = une correction cohérente, ses tests et sa preuve de clôture. Séparer résultats durables, propriété des ressources, assurance et dette structurelle ; ne pas mélanger leurs changements dans un même lot technique.

**Tech Stack:** FastAPI/Python, SQLAlchemy/PostgreSQL, Redis, LangGraph, Next.js/React/TypeScript, Vitest, Playwright, Docker, Prometheus/Alertmanager et Task.

**Spec:** Demande de plan d'actions du 22 octobre 2026 et [rapport technique V14](../../audit/AUDIT_CODEBASE_2026-10-22_CONSOLIDE_V14.html). Le rapport est une référence datée, pas une preuve automatique de l'état futur du workspace.

## Global Constraints

- Planification uniquement dans cette livraison : aucun correctif produit ni changement du rapport V14 n'est effectué.
- La sécurité reste strictement exclue ; ne pas modifier ni réévaluer ses mécanismes à l'occasion des corrections.
- « Impact minimal » signifie **faible rayon de modification et faible risque de régression**, pas faible bénéfice fonctionnel.
- Lire `CLAUDE.md`, les instructions du périmètre et les commandes réelles du `Taskfile.yml` avant toute intervention. `AGENTS.md` est généré, jamais édité directement.
- Préserver les modifications concurrentes, stagées ou non. Ne pas exiger de commit ; aucune opération Git, publication ou déploiement n'est autorisée par ces prompts.
- Aucun fournisseur payant réel, aucune donnée ou base de production/démo ; intégrations sur cibles jetables explicitement désignées et E2E hermétiques.
- Ne pas relever les seuils, augmenter les baselines, ajouter de suppression de diagnostic ou supprimer un oracle pour obtenir du vert. Ne pas exécuter `task test:backend:exhaustive`.
- Analyse avant modification : vérifier la cause actuelle, rechercher les contre-preuves et reproduire. Si le défaut est déjà corrigé, qualifier et clôturer **sans réimplémenter**.
- Après analyse, corriger seulement si la solution reste dans le contrat établi. Si une décision métier, une migration risquée ou une évolution d'interface publique est nécessaire, présenter les options et obtenir l'accord avant cette partie.
- Les commentaires, docstrings et documentations techniques ajoutés au produit restent en anglais. Ce document opérationnel et ses prompts sont en français pour leur destinataire.
- Fournir commandes, environnement, versions utiles, pass/fail/skip, avertissements et limites ; « interrompu » ou « non exécuté » ne signifie jamais « passé ».

## Review Focus

1. Un résultat négatif retourné, sans exception, ne doit pas devenir un succès durable — A06.
2. Un ancien propriétaire ne doit plus renouveler, libérer, terminer ni remplacer les données de son successeur — A08/A09.
3. Un `cancel()` n'est pas la fin d'une tâche ; un client partagé n'est pas une ressource à fermer par son emprunteur — A04/A05.
4. Une UI rafraîchie après fermeture du dialogue ne doit ni perdre le focus ni reprendre celui que la personne a déplacé — A02.
5. Une fixture/oracle corrigé doit toujours contrôler le résultat métier, les requêtes et les erreurs ; une hausse de couverture doit inclure le bon dénominateur — A10/A13/A19.

---

## 1. Base de décision et limites du classement

Référence : V14, 24 périmètres, 16 chantiers ouverts à sa borne de capture, 3 majeurs. Le plan couvre ces 16 IDs et ajoute trois actions de qualification, **sans inventer trois défauts produit supplémentaires**.

Une vérification statique complémentaire le 22 octobre à 10 h 41, heure de Paris, a comparé les 89 sources citées : 86 empreintes identiques, 3 différentes. Les changements portent sur `fr/translation.json`, `SmsErasure.tsx` et `sms-archive.spec.ts`.

- **AC-025 : correction visible à requalifier.** Le mot-clé complet « Administration des utilisateurs » est désormais présent dans l'entrée française. Aucun nouveau passage de suite n'est affirmé dans ce plan.
- **AC-024 : correction visible à requalifier.** La collecte des cibles de retour n'est plus limitée au type `message`. Le cas de suppression groupée doit encore être vérifié dynamiquement.
- **AC-026 : déjà clôturé dans V14**, donc volontairement absent du backlog.
- **AC-021 : partiellement repris.** Trois nœuds courants étaient verts dans V14 ; le fichier home-layout avait évolué sans rejeu. Les autres modifications et tous les échecs résiduels doivent être réconciliés, pas corrigés aveuglément depuis un ancien journal.

Le ROI ci-dessous est un **bénéfice technique attendu**, pas un retour financier mesuré : ni fréquence d'incident, ni économie monétaire, ni gain de note ne sont inventés. Les charges sont des jours-personne incluant analyse, code et validation ciblée ; elles ne sont pas des engagements de délai et n'incluent pas toutes les attentes de CI.

L'ordre applique : clôture sans recodage → correction locale → défaut majeur à correction contenue → concurrence durable → assurance complète → dette ciblée → refonte structurelle. L'urgence d'un défaut majeur prime un score de confort : **amorcer l'analyse AC-002 dès la première vague**, sans attendre la fin des travaux de dette. Si son exposition opérationnelle est avérée, avancer son traitement ; ne pas désactiver une fonction sans accord.

### Lots classés et ordre des actions

| Rang | Lot | Actions, dans l'ordre | ROI attendu | Charge indicative | Rayon / risque de changement |
|---|---|---|---|---|---|
| 1 | Valider les correctifs déjà présents | A01 AC-025 ; A02 AC-024 | Très élevé : éviter de recoder et clôturer deux défauts d'usage | 0,5–1 j ; correction résiduelle en supplément seulement si démontrée | Nul pour la validation ; local si un résidu est confirmé |
| 2 | Petites corrections de ressources et de build | A03 AC-027 ; A04 AC-008 ; A05 AC-007 | Très élevé à élevé | 1,25–4,5 j | Faible, sauf arrêt asynchrone : moyen |
| 3 | Défauts majeurs à correction contenue | A06 AC-003 ; A07 AC-004 | Très élevé en fiabilité opérationnelle | 4–10 j | Faible à moyen, sans refonte de domaine |
| 4 | Propriété des traitements RAG | A08 AC-005 ; A09 AC-002 | Élevé ; intégrité des traitements et prévention du travail répété | 7–15 j | Moyen à élevé ; analyse et tests de concurrence indispensables |
| 5 | Rétablir une assurance réellement exploitable | A10 AC-021 ; A11 banc courant ; A12 oracle CPU ; A13 AC-014 | Élevé, transversal ; pas un gain fonctionnel direct | 3,5–10,5 j | Très faible à faible côté produit ; attention aux oracles |
| 6 | Réduire la dette par petits lots | A14 AC-012 ; A15 AC-013 ; A16 AC-023 | Ciblé, dépend du hotspot choisi | 4–10 j pour les premiers lots | Faible à moyen ; ne clôture pas toute la dette MyPy/Hooks |
| 7 | Réduire les gros points centraux et le couplage | A17 AC-010 ; A18 AC-011 | À démontrer localement, moins favorable à court terme | Pilotes de 2–5 j chacun ; programme complet non chiffré | Élevé si réalisé globalement : rester sur une frontière par lot |

**A19 est une barrière de qualification transversale**, à exécuter après chaque vague significative, pas un prétexte pour attendre la disparition de toute dette structurelle. Ne pas additionner ses coûts complets à chaque petite action.

Les lots sont des unités de pilotage, pas des patchs monolithiques. Chaque action garde son propre cycle analyse → preuve rouge → correction minimale → preuve verte → revue. Si le budget immédiat est réduit : A01, A03 et A04 constituent les premières petites interventions ; engager ensuite A06/A07 et l'analyse A09, plutôt qu'une réécriture du planner.

## 2. Critères de passage communs

- [ ] **Avant :** relecture des producteurs/consommateurs, périmètre exact, état initial reproduit et contre-vérification ; distinguer source inchangée et preuve d'exécution courante.
- [ ] **Tests :** écrire ou compléter une caractérisation qui échoue pour la bonne raison ; conserver les cas déjà couverts et les assertions métier.
- [ ] **Correction :** modifier le propriétaire du contrat, pas ses symptômes ; aucune refonte opportuniste.
- [ ] **Après :** suite ciblée, gates applicables, résultats exacts et absence de fuite/tâche pendante/warning tardif ; mesurer avant/après lorsque l'action concerne une mesure.
- [ ] **Revue :** fichiers touchés justifiés, nouveaux comportements/choix documentés, critères d'acceptation satisfaits ; si nécessaire, rapprocher la note de l'audit uniquement après nouvelle qualification.

Gates canoniques : `task lint` pour les changements de code ; backend `task test:backend:unit:fast` et couverture séquentielle pour les changements asynchrones ; frontend `task lint:frontend`, `task test:frontend:coverage` et parcours impactés. Adapter intégration/agents/migrations/builds au rayon réel, sans remplacer une cible jetable par une base applicative. Les sélections rapides servent à itérer, pas à se substituer aux gates de fin de vague.

---

## Lot 1 — Valider et clôturer sans recoder inutilement

### A01 — Requalifier la recherche des réglages — AC-025

**Charge :** 0,25–0,5 j. **Rayon :** validation puis catalogue français seulement si nécessaire. **Sortie :** bonne destination trouvée, classement pertinent, filtres de disponibilité inchangés.

**Fichiers/tests :** `apps/web/src/lib/settings-search.ts`, `settings-sections.ts`, `apps/web/locales/fr/translation.json` ; `apps/web/src/lib/__tests__/settings-search.test.ts`, `settings-sections.test.ts`, `apps/web/src/components/settings/__tests__/SettingsSearch.test.tsx`, `apps/web/e2e/smoke/settings-search.spec.ts`.

```text
Dans D:\Developpement\LIA, traite AC-025 de l'audit V14. Lis CLAUDE.md et apps/web/CLAUDE.md. Analyse d'abord le matcher, les sections et le catalogue français actuels : le synonyme « Administration des utilisateurs » a été ajouté depuis l'audit. Ne réimplémente pas une correction déjà suffisante.

Reproduis sur les modules et traductions réels les recherches « administration des utilisateurs », « utilisateurs » et « admin. des utilisateurs ». Vérifie que admin-users est trouvé et correctement classé pour un administrateur, et que les filtres existants restent effectifs. Étends les tests du matcher et le parcours settings-search si un oracle manque.

Si le défaut subsiste, corrige seulement la cause minimale, de préférence les synonymes de l'entrée, sans rendre le matcher globalement permissif ni changer le libellé visible pour satisfaire un ancien test. Si tout passe, livre une clôture sans nouveau code produit. Vérifie i18n, lint/typecheck non incrémental et les tests ciblés dans le workflow prévu. Fournis commandes, versions, comptes et limites. Sécurité hors périmètre ; aucun Git, déploiement ou fournisseur réel ; préserver les changements concurrents et tous les seuils.
```

### A02 — Requalifier le focus des suppressions SMS — AC-024

**Charge :** 0,25–0,5 j de qualification ; si résidu confirmé, réestimer une correction locale de 0,5–2 j. **Rayon :** cycle de vie du bouton/dialogue/archive, pas API d'effacement. **Sortie :** six cas canoniques, focus logique et absence de vol de focus.

**Fichiers/tests :** `apps/web/src/components/sms/SmsErasure.tsx`, `SmsConfirmation.tsx` ; `apps/web/src/components/sms/__tests__/SmsErasure.test.tsx`, `SmsArchive.test.tsx`, `apps/web/src/components/ui/__tests__/dialog-focus-return.test.tsx`, `apps/web/e2e/smoke/sms-archive.spec.ts`.

```text
Dans D:\Developpement\LIA, analyse puis requalifie AC-024. Lis les instructions racine/frontend. SmsErasure.tsx a changé depuis V14 : les cibles de retour sont maintenant collectées pour message/sender/day. Vérifie le code actuel avant de proposer une autre mécanique.

Rejoue les six cas canoniques de suppression SMS aux largeurs 390 et 1280 px avec API contrôlée. Conserve les assertions de contenu, confirmation, requêtes et focus. Distingue le retour à la fermeture du dialogue de la disparition différée du bouton après rafraîchissement. Ajoute les cas cible conservée/supprimée, annulation/erreur, déplacement volontaire du focus, et absence de fournisseur/contexte.

Si un résidu existe, corrige le propriétaire du cycle de vie, sans temporisation arbitraire, focus global forcé ou modification de l'effacement métier. Ne reprends jamais le focus à une personne qui l'a déplacé. Si la correction actuelle suffit, clôture sans la réécrire. Exécute tests unitaires, parcours, lint/tsc et couverture applicables ; donne résultats exacts et limites moteurs/appareils. Sécurité exclue ; aucun Git, déploiement ou données réelles ; aucune suppression d'oracle ni hausse de baseline.
```

## Lot 2 — Petits changements, périmètre borné

### A03 — Alléger le contexte Docker après les captures — AC-027

**Charge :** 0,25–0,5 j. **Rayon :** exclusions de contexte, aucune logique applicative. **Gain attendu :** éviter la copie inutile d'un bundle local d'environ 6,5 Gio dans le builder ; ce n'est pas une économie runtime ou une panne de déploiement prouvée.

**Fichiers :** `.dockerignore`, `scripts/capture_public_screenshots.ps1`, `apps/web/Dockerfile.prod` ; vérifier `.gitignore` et `apps/web/.gitignore` comme contrats de sorties, pas les modifier par défaut.

```text
Dans D:\Developpement\LIA, analyse AC-027 à partir du .dockerignore racine, du Dockerfile.prod web et de DistDirectory dans capture_public_screenshots.ps1. Le build depuis un workspace ayant .next-public-screenshots peut inclure ce bundle dans son contexte/builder ; ne transforme pas ce fait en affirmation d'image runtime polluée ou de deploy:prod cassé.

Après reproduction par sentinelles BuildKit sans données privées, ajoute l'exclusion minimale des familles de sorties générées réellement maintenues. Ne supprime aucun artefact utilisateur, source, public, patch ou fixture utile. Prouve à la fois les exclusions et l'inclusion des sources/patches nécessaires. Compare la taille transférée du contexte et construis le Dockerfile de production sur une copie source figée avec faux artefact de capture. Ne démarre ni ne déploie l'image.

Livre un diff réduit, les commandes, hashes/mesures et résultats exacts. Lis les instructions du dépôt ; sécurité hors périmètre, aucune opération Git ni publication ; pas de refonte du déploiement, d'élargissement de scope ou d'affaiblissement de test. Nettoie seulement les ressources d'audit dont tu as vérifié la propriété.
```

### A04 — Fermer les deux clients Hue temporaires — AC-008

**Charge :** 0,5–2 j. **Rayon :** deux sites propriétaires du client, aucune instance partagée. **Sortie :** fermeture attendue sur succès, erreur et annulation, sans masquer l'erreur initiale.

**Fichiers/tests :** `apps/api/src/domains/connectors/service.py`, `router.py`, `clients/philips_hue_client.py` ; `apps/api/tests/unit/domains/connectors/test_active_client.py` comme contrat de fermeture, puis tests spécifiques des deux appelants.

```text
Dans D:\Developpement\LIA, analyse puis corrige AC-008. Lis les instructions et retrouve tous les constructeurs de PhilipsHueClient, son async close(self) et les propriétaires réels. Deux chemins temporaires de connexion/test dans connectors/service.py et router.py étaient sans fermeture ; ne ferme pas un client partagé ou géré par une dépendance.

Ajoute d'abord les tests des deux appelants : connexion réussie, résultat négatif, exception et annulation. Applique ensuite le contexte asynchrone existant ou un try/finally minimal, avec close attendu exactement selon son contrat et sans masquer l'erreur initiale. N'invente pas un nouveau gestionnaire global de clients.

Conserve les réponses et erreurs fonctionnelles. Tous les transports Hue restent simulés. Exécute les tests ciblés puis lint/backend et gates applicables, et recherche les ressources non fermées jusque dans les sorties après résumé. Donne fichiers, cause, comptes et limites. Sécurité exclue ; aucun pont réel, Git, changement d'environnement applicatif ou déploiement ; préserver le travail concurrent et les seuils.
```

### A05 — Joindre les tâches après annulation — AC-007

**Charge :** 0,5–2 j. **Rayon :** helper partagé de shutdown ; risque moyen malgré un petit diff. **Sortie :** nettoyage achevé avant fermeture des dépendances, ou échec borné et observable explicite.

**Fichiers/tests :** `apps/api/src/infrastructure/async_utils.py`, `startup/shutdown.py` ; `apps/api/tests/unit/infrastructure/test_async_utils_background_failure.py`, `startup/test_shutdown_order.py`.

```text
Dans D:\Developpement\LIA, analyse le contrat de wait_all_background_tasks(timeout=30.0), ses appelants et l'ordre du shutdown avant de modifier AC-007. L'audit observait cancel() puis retour alors qu'une tâche et son finally restaient inachevés. Reproduis avec asyncio.Event, pas avec une course au sleep.

Définis la phase de jointure après annulation et son budget dans le budget global existant. Teste fin normale, finally asynchrone, exception de nettoyage, annulation du shutdown et tâche refusant de terminer. Préserve CancelledError et une issue observable si le second budget expire ; ne promets pas l'arrêt d'une coroutine non coopérative. DB/Redis/clients ne doivent pas être fermés avant le drainage prévu par le contrat.

Implémente la correction minimale, sans changer tous les schedulers. Exécute tests ciblés, gardes d'ordre, unitaires rapides xdist et couverture séquentielle ; aucun pending task ou warning tardif caché. Livrer résultats et limites exacts. Lire CLAUDE.md ; sécurité exclue, aucun Git, fournisseur réel ni déploiement ; aucun seuil/timeout de test augmenté pour masquer le défaut.
```

## Lot 3 — Majeurs à rayon de correction contenu

### A06 — Ne plus déclarer livrée une notification refusée — AC-003

**Charge :** 2–5 j. **Rayon :** deux consommateurs du résultat de dispatch et état durable associé. **Sortie :** échec total retourné ≠ DELIVERED ; succès partiel et reprise explicitement définis.

**Fichiers/tests :** `apps/api/src/infrastructure/proactive/notification.py`, `domains/telephony/reapers.py`, `return_synthesis.py` ; `apps/api/tests/unit/domains/telephony/test_reapers.py`, `test_return_synthesis.py`.

```text
Dans D:\Developpement\LIA, analyse puis corrige AC-003. Lis NotificationResult et NotificationDispatcher.dispatch, les deux consommateurs telephony/reapers.py et return_synthesis.py, et le repository. Le contrat peut retourner NotificationResult.failure(error) sans lever ; les tests d'exception seuls ne couvrent pas ce cas.

Écris une régression dans chacun des deux chemins : failure retourné ne marque jamais la notification livrée et conserve une issue permettant la reprise prévue. Couvre succès, échec total, exception, succès partiel, annulation, perte de claim et crash entre effet et commit. Déduis la politique de succès partiel du contrat existant ; si elle est ambiguë, soumets la décision métier avant code. Réutilise l'identité/idempotence existante ; ne promets pas exactly-once si le transport ne le garantit pas.

Corrige les consommateurs au minimum, sans refondre les canaux. Aucun message réel. Exécute tests téléphonie/dispatch, lint et modes backend applicables ; donne transitions, commandes, pass/fail/skip et limites. Lis CLAUDE.md ; sécurité exclue ; aucun Git, déploiement ou hausse de baseline ; ne pas réécrire les changements concurrents.
```

### A07 — Composer Alertmanager selon les canaux réellement configurés — AC-004

**Charge :** 2–5 j. **Rayon :** entrypoint/templates/tests ; ne pas modifier les seuils d'alertes par opportunité. **Sortie :** configuration valide et destinataires corrects dans toutes les combinaisons annoncées.

**Fichiers/tests :** `infrastructure/observability/alertmanager/docker-entrypoint.sh`, `alertmanager.yml.template`, `docker-compose.prod.yml` en lecture du contrat ; `apps/api/tests/unit/test_alertmanager_webhook_matrix.py`.

```text
Dans D:\Developpement\LIA, traite AC-004 après analyse de l'entrypoint Alertmanager, des templates, des variables Compose et des tests de matrice existants. Distingue validité de configuration et destinataires effectifs. task test:alerts vérifie les règles Prometheus, pas à lui seul amtool ni toutes les combinaisons de receivers.

Reproduis avec l'image épinglée, sans réseau sortant : aucun canal, SMTP seul, SMTP+PagerDuty sans Slack, SMTP+Slack sans PagerDuty, Slack critique seul, tous les canaux et valeurs partielles. Compose seulement les receivers/routes configurés. Vérifie avec amtool check-config puis routes test les receivers attendus des alertes critiques finance/LLM, DB et SLO. La politique de fan-out doit être explicite ; ne corrige pas l'ordre des routes au hasard et demande arbitrage si plusieurs destinataires métier sont possibles.

Conserve le webhook applicatif et les modes valides. Ajouter un gate Task hermétique si nécessaire, workflow seulement orchestrateur. Exécute la matrice, test:alerts et lint:observability. Aucun webhook/courriel réel, Git ou déploiement ; sécurité exclue, aucun seuil abaissé. Donner configuration synthétique, commandes et résultats exacts.
```

## Lot 4 — Propriété et concurrence des traitements RAG

### A08 — Rendre le flag global de réindexation propriétaire — AC-005

**Charge :** 2–5 j. **Rayon :** contrat du run global, sa progression et son nettoyage. **Sortie :** un run A périmé ne renouvelle, ne supprime et ne solde jamais le run B.

**Fichiers/tests :** `apps/api/src/domains/rag_spaces/reindex.py`, `infrastructure/locks/redis_claim.py` ; `apps/api/tests/unit/domains/rag_spaces/test_reindex_lock_renewal.py`, `tests/unit/infrastructure/locks/test_redis_claim.py`.

```text
Dans D:\Developpement\LIA, analyse AC-005 : acquisition du flag global avec valeur constante, renouvellement, suppression, progression et tous les chemins d'arrêt/reprise. Vérifie le contrat actuel avant correction. Réutilise try_claim/refresh_claim/release_claim ou held_claim de infrastructure/locks/redis_claim.py, avec un token unique par run et arrêt sur ClaimLost ; n'ajoute pas une seconde implémentation de verrou.

Teste avec deux acteurs et Redis jetable : A expire, B reprend, puis A renouvelle, publie sa progression ou s'arrête. Aucun effet tardif de A ne doit affecter B. Couvrir un document dépassant le TTL, annulation, panne Redis et nettoyage tardif. Une comparaison de token sur le seul DELETE ne suffit pas si d'autres effets restent possibles.

Conserve les générations servies et l'intention transactionnelle de réindexation ; une maintenance prévue sur changement de dimension ne doit pas être supprimée. Diff borné, unitaires puis preuve Redis réelle, lint et suites RAG impactées. Lis CLAUDE.md ; aucun Git, fournisseur réel ou déploiement, aucune base applicative, sécurité exclue et seuils inchangés. Soumettre toute migration ou évolution publique non indispensable au contrat.
```

### A09 — Interdire les mutations d'un ancien claim documentaire — AC-002

**Charge :** 5–10 j. **Rayon :** transitions et swap transactionnel de documents ; risque élevé, à ne pas traiter comme une simple condition ajoutée à un helper.

**Fichiers/tests :** `apps/api/src/domains/rag_spaces/jobs_repository.py`, `processing.py`, `source_document_lease.py`, `reapers.py` ; `apps/api/tests/integration/domains/rag_spaces/test_jobs_repository.py`, `tests/integration/test_source_document_lease.py`.

```text
Dans D:\Developpement\LIA, analyse AC-002 avant toute écriture : claim_document(id, worker_id, lease_ttl_s), heartbeat booléen, succès, fail/retry, reaper, flux upload, contrôles natifs et transaction de remplacement des chunks. Une sonde V14 montrait qu'après reprise B, un échec tardif A remet PENDING et efface B. complete_document sans appelant n'est pas à confondre avec le chemin de succès applicatif.

Cartographie chaque mutation et la preuve de propriété qu'elle lit. Cherche la solution minimale utilisant les colonnes/claims existants ; n'impose pas une nouvelle migration par défaut. Toute identité/fencing doit empêcher le stale commit, pas seulement vérifier le bail avant un await puis écrire sans garde.

Reproduis sur PostgreSQL jetable avec deux sessions : A réclame, expire, B reprend, puis A heartbeat/réussit/échoue/swap/termine. B et ses chunks doivent rester intacts ; perte de heartbeat arrête les effets ultérieurs. Tester annulation, crash/reprise, idempotence et sources natives. Garder état et swap atomiques sans session ouverte pendant un fournisseur. Présente le schéma de solution et ses risques ; demander validation si migration/contrat public requis. Puis corriger et vérifier suites RAG, intégration, agents et modes combinés applicables. Aucun Git, fournisseur réel, baisse de seuil ou déploiement ; sécurité exclue.
```

## Lot 5 — Assurance rétablie, pas simple couleur verte

### A10 — Réconcilier les E2E avec les contrats présents — AC-021

**Charge :** 2–5 j selon le résidu réel. **Rayon produit :** nul par défaut ; un défaut produit confirmé devient une action distincte. **Sortie :** matrice des anciens échecs réconciliée et suite courante rejouée sans retries masquants.

**Fichiers :** `apps/web/e2e/a11y/axe-journeys.spec.ts` et `e2e/smoke/` : `chat-360-two-people`, `dashboard-home-layout`, `notifications`, `proactive-discussions`, `relations-crm`, `settings-capability-sharing`, `settings-rail`, `sms-alerts`, `sms-archive`, `telephony-calls-settings` (`.spec.ts`).

```text
Dans D:\Developpement\LIA, analyse AC-021 à partir de l'annexe F du rapport V14 et des sources E2E actuelles. Le run historique 691=644 pass/47 fail n'est pas le backlog actuel : plusieurs attentes ont été corrigées. Commence par une matrice cas → contrat actuel → code de preuve → statut réellement rejoué. Ne refais pas les corrections déjà présentes.

Vérifie un groupe indépendant à la fois : sélecteurs de rôle uniques, sections dashboard non repliables, draft avec bon sujet et aucun POST, panneaux Contexte/Données, import attesté par toast/fermeture/requêtes, badges SMS, icônes et fresh connectors. Pour les notifications, comparer le bord du badge au temps, pas son texte intérieur décalé par padding. Conserver reflow, axe, contenu, erreurs, requêtes et focus. Ne modifier un oracle qu'après preuve de son inadéquation ; ne masquer ni AC-024 ni AC-025.

Exécute les fichiers touchés puis la suite hermétique sur build Docker courant, 0 retry. Fournis les préconditions natives média réelles nécessaires, sans simuler PCM/videoWidth pour satisfaire l'oracle. Distingue défaut produit, fixture, banc, flake et non-conclusif. Aucun fournisseur/backend réel, Git ou déploiement ; sécurité exclue, aucune suppression d'assertion utile ni hausse de seuil. Livrer les comptes exacts, sans addition de replays comme tests uniques.
```

### A11 — Diagnostiquer les relances backend courantes non concluantes — Qualification Q1

**Charge :** 0,5–2 j de diagnostic borné ; résolution à réestimer si la cause dépasse le banc. **Statut :** pas de régression produit prouvée. **Sortie :** cause instrumentée ou limitation honnête, puis preuve des suites réellement terminées.

```text
Dans D:\Developpement\LIA, qualifie le runtime backend courant à la suite du rapport V14. Les suites complètes de référence ont des résultats connus, mais deux relances supplémentaires à 8 workers, avec dépendances tardives, ont stagné sans résumé pytest. Le diagnostic pur et 69 tests de checkpoint passaient. N'attribue pas ce blocage à la base, au réseau, au cache ou au produit sans stack/preuve.

Analyse les tâches canoniques, dépendances effectives/importées, environnement de tests, cache tokenizer, cibles PostgreSQL/Redis et consommation de ressources. Installer un watchdog/collecte de stack avant un essai borné ; commencer petit et ne lancer qu'une suite lourde à la fois pour maîtriser le banc, sans prétendre que la concurrence était la cause. Prouver la provenance du master et de chaque worker et neutraliser les fournisseurs sans modifier l'environnement applicatif.

Corrige uniquement la cause démontrée : banc si banc, produit si défaut reproduit et solution approuvée dans son périmètre. Ne pérennise pas une dépendance à .tmp-codex ni un bootstrap opaque. Rejoue les commandes CI et les modes combinés xdist/séquentiel pertinents avec cibles jetables ; jamais test:backend:exhaustive. Rapporter comptes, couverture, skips, warnings et interruptions sans inventer d'exit pytest. Aucun Git, déploiement ou fournisseur payant ; sécurité exclue et assertions/floors conservés.
```

### A12 — Qualifier l'oracle de croissance CPU sur Windows — Qualification Q2

**Charge :** 0,5–1,5 j si un défaut d'oracle est reproduit. **Statut :** une mesure canonique rouge, pas de complexité quadratique actuelle démontrée. **Sortie :** oracle sensible à une vraie régression, indépendant des petits quanta d'horloge.

```text
Dans D:\Developpement\LIA, analyse l'échec d'oracle CPU décrit en T03/P08 de V14, sans le transformer en défaut d'algorithme certain. Retrouve le test exact, le helper de compaction mesuré et les horloges. Le run couvert donnait [18.75,18.75,2], tandis que les lots de 64 appels sur entrées x4 avaient une croissance proche de x4 ; l'horloge Windows avait des paliers de 15.625 ms.

Reproduis sous le mode canonique et mesure résolution, coût du traceur, bruit et durée utile. Si l'oracle est en cause, corrige sa méthode par lots/calibration bornés, sans augmenter arbitrairement le seuil de croissance ou le timeout. Conserve l'équivalence fonctionnelle et ajoute un contrôle négatif borné montrant que la méthode détecte encore une implémentation délibérément superlinéaire. Vérifier Windows et Linux, avec/sans couverture quand applicable.

Si le test actuel est déjà sain, ne le réécris pas. Si une régression du helper est réellement prouvée, la traiter séparément après analyse. Livrer mesures brutes, répétitions, limites et commande CI inchangée ou modification de méthode précisément justifiée. Aucun Git, fournisseur réel, déploiement ni test exhaustif ; sécurité exclue ; ne pas rebaptiser un run rouge en vert par commentaire.
```

### A13 — Mesurer les primitives devenues comportementales — AC-014

**Charge :** 0,5–2 j pour la revue des exclusions et un premier ensemble cohérent. **Rayon :** tests/configuration ; comportement inchangé par défaut. **Sortie :** dénominateur honnête et branches des primitives incluses effectivement testées.

**Fichiers/tests :** `apps/web/vitest.config.mts`, `src/components/ui/{dialog,input,textarea,alert-dialog}.tsx` et suites correspondantes dans `src/components/ui/__tests__/`.

```text
Dans D:\Developpement\LIA, analyse les exclusions de primitives de vitest.config.mts signalées par AC-014. Quatorze étaient présentées comme triviales ; dialog possède notamment combobox Escape, retour de focus et i18n, et input/textarea du plumbing de champ. Un fichier déjà testé n'est pas nécessairement inclus dans la mesure.

Classe chaque exclusion actuelle selon sa logique réelle. Réintègre en premier un petit ensemble cohérent de fichiers comportementaux ; garde seulement les re-exports réellement triviaux avec justification. Ajoute avant modification du dénominateur les tests clavier, noms traduits, focus, erreur/désactivation et transitions utiles, en réutilisant les suites existantes. Ne remplace pas les assertions par des snapshots ou classes CSS.

Exécute task test:frontend:coverage via son environnement neutralisé. Publie numérateurs/dénominateurs et seuils global/glob avant/après : ils sont agrégés, pas per-file. Ne baisse pas les floors pour absorber les fichiers ajoutés et ne transfère pas leur logique hors mesure. Statique et E2E impactés selon rayon réel. Lis les instructions ; aucun Git, déploiement ou fournisseur réel, sécurité exclue. Si seul un pilote est traité, ne déclare pas toutes les exclusions résolues.
```

## Lot 6 — Dette locale en petites tranches

### A14 — Supprimer un ensemble cohérent de suppressions MyPy — AC-012

**Charge :** 1–2 j par premier micro-lot ; le chantier complet reste E4. **Rayon :** une frontière/type de diagnostic. **Sortie :** baisse de dette sans nouveau contournement, comportement inchangé.

**Fichiers/tests :** `apps/api/pyproject.toml`, `scripts/audit/measure_mypy_debt.py`, `apps/api/tests/unit/test_mypy_debt_ratchet_guard.py`, puis module choisi et ses suites.

```text
Dans D:\Developpement\LIA, traite un micro-lot AC-012 après analyse. Les 89 couples module/code et 859 diagnostics de sonde dans V14 sont une dette mesurée sous une configuration différente, pas autant de pannes produit. Rejoue la mesure actuelle et sélectionne un seul ensemble cohérent, de préférence une frontière touchée par une correction précédente.

Retire les suppressions de ce seul périmètre dans une sonde, qualifie les diagnostics et corrige les vrais contrats par types précis, génériques, TypedDict, Protocol ou stub exact. Ne pas introduire Any/cast/double assertion, ignore-errors, type: ignore ou nouvelle exemption pour déplacer le problème. Ajoute une caractérisation lorsqu'un contrat runtime serait mal couvert.

Supprime les suppressions devenues inutiles et montre les comptes avant/après, y compris le total pour déceler un déplacement. Vérifie MyPy canonique, sonde ciblée, lint:mypy-debt, lint/backend et les suites impactées. Ne refactorise pas tout un domaine pour un diagnostic local. Lire CLAUDE.md ; sécurité exclue, aucun Git, fournisseur réel ou déploiement. Livrer le résidu : un micro-lot vert ne clôture pas l'ensemble AC-012.
```

### A15 — Réduire un hotspot React Hooks/complexité — AC-013

**Charge :** 1–3 j par composant/hook ; chantier complet E4. **Rayon :** un cycle de vie/cohérence fonctionnelle, pas tous les hooks. **Sortie :** comportement conservé et dette réellement diminuée.

**Fichiers/tests :** ratchets `apps/web/scripts/check-react-hooks-ratchet.mjs`, `check-cc-ratchet.mjs` ; composant choisi. `src/hooks/useChat.ts` et `src/hooks/__tests__/useChat.test.ts` sont un exemple central, **pas une obligation de commencer par le plus risqué**.

```text
Dans D:\Developpement\LIA, analyse AC-013 et choisis un unique hotspot justifié par les sorties actuelles des ratchets. Les 30 écarts Hooks et 39 écarts de complexité de V14 sont une référence, pas des chiffres à recopier sans mesure. Préfère une zone déjà touchée et bien caractérisable à une réécriture générale de useChat.

Fige rendu, effets, abonnements et ordre des actions. Teste montage/démontage, changement d'identité/d'endpoint, réponse tardive, annulation et absence de double souscription. Corrige les dépendances en structurant le cycle de vie ; extrais des décisions pures ou un hook cohésif si nécessaire. Ne retire pas une dépendance, n'ajoute pas eslint-disable et ne mémoïse pas aveuglément pour satisfaire l'outil.

Conserve UI, i18n, API et effets métier. Montre CC/écarts avant/après sur le fichier et l'ensemble, sans déplacer la dette. Exécute tests, lint frontend/tsc propre, couverture et E2E utiles ; réduire les caps seulement après preuve. Lis les instructions racine/frontend ; sécurité exclue, aucun Git, fournisseur réel ou déploiement. Signaler clairement que le pilote ne clôture pas toute la dette.
```

### A16 — Espacer les compilations sémantiquement refusées — AC-023

**Charge :** 2–5 j. **Rayon :** signature/cache/refus du runner de discussions. **Sortie :** répétition bornée, invalidation correcte, possibilité de récupération conservée.

**Fichiers/tests :** `apps/api/src/infrastructure/proactive/discussion_runner.py`, `domains/proactive_discussions/rule_controls.py`, `repository.py` ; `apps/api/tests/unit/domains/proactive_discussions/test_rule_controls.py`, `tests/integration/domains/proactive_discussions/test_producer_flow.py`.

```text
Dans D:\Developpement\LIA, analyse AC-023 sur apply_read_controls, rule_cache_signature, RuleCache et settle_run(retry_after=...). V14 reproduisait deux compilations identiques lorsqu'une citation était refusée avant le cache. Ce refus est intentionnel : ne l'assouplis pas, et n'invente pas une économie monétaire non mesurée.

Reproduis avec compilateur simulé et distingue abstention valide, erreur fournisseur transitoire et refus sémantique. Propose le plus petit cooldown/cache négatif borné par signature compatible avec les champs existants. Conserve une chance de récupération : aucun échec probabiliste n'est figé pour toujours. Invalider sur modification pertinente des contrôles, sources ou version de prompt ; lire un délai depuis son autorité de configuration, pas un nouveau nombre dispersé.

Tester répétition, expiration, modification, succès ultérieur, annulation et concurrence ; aucun run refusé ne doit être publié. Préserver budgets et propriété du claim. Corriger seulement après analyse de la politique existante, demander arbitrage si la durée/politique est métier. Exécuter suites ciblées et gates backend applicables ; fournir nombre d'appels et transitions. Sécurité exclue ; aucun Git, modèle payant, base applicative ou déploiement, aucune hausse de seuil.
```

## Lot 7 — Refonte uniquement là où le gain est démontré

### A17 — Extraire une responsabilité d'un hotspot backend — AC-010

**Charge :** pilote de 2–5 j ; programme E5 non chiffré. **Rayon :** une responsabilité ; risque élevé si le scope devient transversal. **Sortie :** fonction/fichier plus simple et contrats/ordre des effets inchangés.

**Fichiers :** `scripts/audit/measure_sloc.py`, `measure_cc.py`, puis hotspot choisi ; `apps/api/src/domains/agents/nodes/planner_node_v3.py` est une source de référence, pas une cible automatique sans analyse.

```text
Dans D:\Developpement\LIA, analyse un pilote AC-010, sans lancer une refonte globale. Mesure SLOC logique et CC actuelles avec les instruments du dépôt, sépare données et logique, et sélectionne un hotspot dont une responsabilité cohésive peut être extraite avec un bénéfice concret. Le simple dépassement d'un compteur ne suffit pas à justifier une réécriture.

Cartographie entrées, sorties, effets, erreurs et ordre des transitions ; ajoute des caractérisations/goldens des contrats manquants. Présente l'extraction minimale et les interfaces conservées. Si elle change DSL, prompts, sémantique de plan ou API publique, demande validation avant cette partie. Extraire ensuite une décision pure ou une unité cohésive, pas un autre god-file ni un dispatch qui cache la complexité.

Comparer fonction, fichier, complexité totale et couplage avant/après ; abaisser les caps seulement après preuve. Vérifier tests du périmètre, agents, modes combinés xdist/séquentiel et statique selon le rayon. Aucun fournisseur réel ni réécriture des sorties de référence pour masquer un changement. Lire CLAUDE.md ; sécurité exclue, aucun Git, déploiement ou hausse de baseline. Livrer un pilote réversible, avec dette résiduelle explicite.
```

### A18 — Supprimer une dépendance réciproque métier injustifiée — AC-011

**Charge :** pilote de 2–5 j ; chantier complet E4. **Rayon :** deux domaines et leur composition seulement. **Sortie :** vraie réduction d'arête runtime avec contrats identiques, pas import local dissimulant le couplage.

**Fichiers :** `scripts/audit/measure_coupling.py` ; candidats cités dans V14 : `apps/api/src/domains/shared/discussion_sources.py`, `src/infrastructure/startup/registries.py`. Choisir le couple après analyse, pas par nom de fichier.

```text
Dans D:\Developpement\LIA, analyse AC-011 sur un seul couple de domaines réciproques. Rejoue measure_coupling et distingue runtime, TYPE_CHECKING, types partagés, appels métier et racine de composition. Les 22 couples de V14 ne sont pas 22 cycles concrets ni 22 crashs : ne change pas une composition légitime pour réduire un compteur.

Choisis une arête métier injustifiée, documente le sens de dépendance attendu et les contrats/consommateurs. Propose un port/Protocol, un type neutre ou une composition existante plutôt qu'un nouveau domaine fourre-tout. Si le sens métier n'est pas clair, arrête la correction et demande arbitrage. Conserver les signatures et l'ordre des effets, avec tests contractuels puis garde d'architecture bornée.

Prouve disparition de l'arête réelle, pas son déplacement dans une fonction ou un module shared monolithique. Mesure graphe avant/après, imports à froid et suites des deux domaines, puis lint et modes d'exécution nécessaires. Lis les instructions ; sécurité exclue, aucun Git, fournisseur réel ou déploiement, aucune baseline relevée. Le pilote ne clôture pas tous les couples réciproques.
```

## A19 — Qualification de fin de vague et clôture des actions — Barrière Q3

**Charge :** 0,5–2 j selon la vague, ressources et résidus ; mutualiser les suites lourdes. **Rayon produit :** nul sans défaut nouveau approuvé. **Dépendances :** actions de la vague terminées ; banc et sources identifiés.

```text
Dans D:\Developpement\LIA, qualifie la vague de remédiation terminée du plan audit-v14-remediation. Analyse d'abord les preuves et les modes d'exécution requis. N'implémente pas une nouvelle fonctionnalité et ne modifie pas rétrospectivement le rapport V14 daté. Lis les instructions et Taskfile courants ; dresse pour chaque action sources/hashes, critères, tests avant/après, changements concurrents et statut résolu/partiel/non-conclusif.

Exécute les gates canoniques proportionnés : statique transverse ; backend rapide et couverture CI, agents/intégration et modes combinés lorsque concernés ; frontend couverture via Task ; E2E hermétiques sur build courant avec préconditions média ; matrice Alertmanager ; builds/migrations jetables si leur périmètre a changé. Ne somme pas les replays comme tests uniques. Ne mélange pas une mesure sur anciens locks avec un verdict sur les nouveaux.

Documente fail/skip/désélections, warnings et interruptions. Un bug produit, une fixture, un oracle et un problème de banc ont des clôtures distinctes. Aucune hausse automatique de note ; aucune attestation globale si les P1 ou suites requises restent non qualifiés. Propose un nouveau rapport uniquement si demandé, sans publication distante. Sécurité exclue ; aucun Git, déploiement, fournisseur payant, base applicative ni tâche exhaustive. Nettoyer seulement les ressources temporaires possédées, après transfert des preuves.
```

## 3. Mesure du ROI et contrôles de fin

L'indice de triage utilisé est `P = (bénéfice + risque d'inaction) × (6 − effort)`, sur des échelles ordinales 1–5. Il sert à comparer des travaux similaires ; **ce n'est ni une rentabilité financière ni une probabilité d'incident**. Le rayon de régression est une dimension distincte. Le classement des lots arbitre ensuite les corrections déjà présentes, l'urgence des majeurs et les dépendances de qualification ; il ne prétend pas être une optimisation numérique prouvée.

| Action | Bénéfice | Risque d'inaction | Effort ordinal | P | Rayon indicatif |
|---|---:|---:|---:|---:|---|
| A01 validation recherche | 2 | 2 | 1 | 20 | Aucun code par défaut |
| A02 validation focus | 3 | 3 | 1 | 30 | Aucun code par défaut |
| A03 contexte Docker | 3 | 2 | 1 | 25 | Faible |
| A04 Hue | 3 | 3 | 2 | 24 | Faible |
| A05 shutdown | 4 | 4 | 2 | 32 | Moyen, helper partagé |
| A06 résultat de livraison | 5 | 5 | 3 | 30 | Faible à moyen |
| A07 Alertmanager | 5 | 5 | 3 | 30 | Faible à moyen |
| A08 claim reindex | 5 | 4 | 3 | 27 | Moyen à élevé |
| A09 claim documents | 5 | 5 | 4 | 20 | Élevé |
| A10 E2E | 4 | 4 | 3 | 24 | Très faible produit, élevé si oracles affaiblis |
| A11 banc backend | 4 | 3 | 2 | 28 | Très faible produit |
| A12 oracle CPU | 3 | 3 | 2 | 24 | Très faible produit |
| A13 dénominateur couverture | 3 | 3 | 2 | 24 | Faible produit |
| A14 pilote MyPy | 3 | 3 | 2 | 24 | Faible à moyen |
| A15 pilote Hooks | 3 | 3 | 2 | 24 | Moyen |
| A16 refus sémantique | 3 | 3 | 3 | 18 | Moyen |
| A17 complexité, programme complet | 3 | 3 | 5 | 6 | Élevé si global |
| A18 couplage, programme complet | 3 | 3 | 4 | 12 | Élevé si global |

Les scores des pilotes A14/A15 ne chiffrent pas la clôture totale de leurs constats ; ceux d'A17/A18 représentent le programme complet, d'où l'intérêt de sélectionner un pilote avant tout engagement. A19 est une condition de preuve, non un chantier à choisir selon son score.

### Définition de terminé

- Une cause actuelle démontrée, ou une correction antérieure requalifiée sans recodage.
- Un changement minimal et ses tests de contrat ; aucune dérive de périmètre, sémantique, threshold ou baseline.
- Critères d'acceptation satisfaits et preuves rattachées aux sources/dépendances réellement testées.
- Résidus explicites : un pilote ne devient pas une clôture globale, un test modifié ne devient pas une exécution, un build ne devient pas un déploiement.
- Choix métier et évolutions d'interface arbitrés avant exécution ; P1 non masqués par une moyenne de qualité.

### Auto-revue du plan

- [x] Les 16 IDs ouverts de V14 ont une action ; AC-026 n'est pas réintroduit.
- [x] AC-024/025 commencent par la qualification des modifications présentes.
- [x] Les trois majeurs AC-002/003/004 ont une stratégie de preuve et ne sont pas noyés dans la dette.
- [x] Les limites de banc courant et de mesure CPU ont leur propre diagnostic, sans accusation produit non démontrée.
- [x] Chaque action possède un prompt autonome analyse puis correction conditionnelle et des critères vérifiables.
- [x] Les pilotes de dette sont distingués d'une résolution totale ; les contrôles lourds sont mutualisés par vague.
- [x] Aucun correctif produit, opération Git ou déploiement n'est déclenché par la rédaction de ce plan.

Plan à valider avant mise en œuvre. Il ne constitue pas une autorisation de déploiement ni une nouvelle notation de la codebase.
