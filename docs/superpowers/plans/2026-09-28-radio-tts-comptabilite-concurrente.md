# Comptabilité concurrente radio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empêcher la perte et le double enregistrement des unités lorsque plusieurs tâches partagent TrackingContext, en conservant les contrats de transaction, d’archive et de budget existants.

**Architecture:** Un verrou par instance sérialise les écritures. Chaque écriture utilise un snapshot immuable des préfixes de toutes les listes et du delta de messages. Les lecteurs continuent de voir les données en attente ; le succès retire uniquement le préfixe enregistré et le publie une fois dans les collecteurs.

**Tech Stack:** Python/asyncio, NamedTuple existants, dataclass immuable, SQLAlchemy AsyncSession, PostgreSQL et pytest.

**Spec:** [Conception et contraintes communes](../specs/2026-09-28-radio-tts-correctifs-cibles-design.md).

**Statut : conception uniquement. Aucun correctif ni nouveau test n’est développé.**

## Global Constraints

- Même formule de coût et mêmes unités, mêmes statistiques et budgets, aucune migration.
- Inclure LLM, Google API, images, TTS et messages ; les appels Google en cache restent non facturables.
- Un échec d’écriture ne casse pas le chat ; CancelledError conserve sa sémantique.
- Une AsyncSession n’est jamais utilisée simultanément par plusieurs tâches.
- Le propriétaire d’une session externe garde son commit/rollback. Le tracker n’acquiert pas cette responsabilité.
- Aucune identité durable d’opération, reprise après crash ou garantie exactement une fois sur résultat DB inconnu n’est introduite.
- service.py doit rétrécir par extraction du contrat et de l’agrégation de lot, sans déplacer des dépendances cycliques.

## Review Focus

1. Ajout d’unités après capture et avant commit : elles restent en attente, puis se retrouvent dans toutes les vues après le prochain commit — C1/C2/C3.
2. commit concurrent avec commit ou sortie du contexte : aucune écriture simultanée et aucun delta en double — C1/C2.
3. Échec ou annulation avant confirmation, puis reprise : lot intact, rollback réel, aucun doublon d’archive — C2/C3/C4.
4. Message ou famille de consommation arrivant pendant le flush, même si absente du snapshot initial : pas de disparition — C2/C3.
5. Session externe, collecteurs partagés par run_id et lecture d’archive pendant le flush : préserver les responsabilités et les vues — C3/C4.

---

## Contrats actuels à conserver

| Point | Contrat observé |
|---|---|
| commit et __aexit__ | Utilisent pending_families ; enregistrement best effort ; sorties normales, exceptionnelles et annulations couvertes |
| record_node_tokens / increment_message_count | Asynchrones, utilisent le verrou court _lock |
| record_google_api_call / record_image_generation_call / record_tts_call | Synchrones, ajoutent aux listes ; les rendre asynchrones casserait leurs appelants |
| get_summary | Résumé des données encore en attente, pas total cumulatif déjà enregistré |
| Archives TTS et debug | Collecteurs du run + données encore en attente, permettant un accès après commit |
| Persistance | Logs détaillés puis résumé incrémental, registre de budget instance et statistiques utilisateur |
| Session interne | Tracker déclenche la confirmation de sa transaction |
| Session externe | Tracker écrit dans la transaction fournie ; le propriétaire la confirme ou l’annule |

AccountedProducer.produce et produce_flash appellent tous deux tracker.commit dans leur finally. Un même tracker est construit dans session_parts. Ne pas corriger ce défaut avec un verrou uniquement dans AccountedProducer : l’arrivée de nouvelles unités pendant une écriture resterait non protégée et d’autres consommateurs partageraient encore le défaut.

## Décision technique : préfixe immuable, sans vidage anticipé

1. Attendre un nouveau verrou _persist_lock propre au tracker.
2. Recalculer pending_families après acquisition, même si l’appelant l’avait déjà lu.
3. Copier les listes dans des tuples, sans await entre leur capture et le début de l’écriture. Les données restent dans les listes d’origine.
4. Écrire exclusivement à partir du lot capturé : logs détaillés, résumé, budget instance, statistiques, compteurs de diagnostic.
5. Après confirmation, acquitter le lot sans await : publier ses éléments dans les collecteurs et supprimer exactement les préfixes correspondants.
6. Les éléments ajoutés entre-temps restent dans les listes et seront capturés par un prochain commit.
7. Si l’écriture échoue avant confirmation, ne rien retirer ni publier. Aucun code de restauration ou fusion n’est nécessaire.

Il faut les deux mécanismes : le verrou seul n’empêche pas les producteurs synchrones d’ajouter des éléments pendant la requête SQL ; le snapshot seul n’empêche pas deux commits de capturer le même préfixe.

Le verrou _lock de collecte reste court. Ne pas le conserver pendant des I/O et ne pas rendre les appels de collecte dépendants de la durée PostgreSQL. La garantie visée porte sur les tâches de la boucle propriétaire du tracker ; ce plan n’introduit pas de partage d’un même tracker entre plusieurs boucles.

### Forme du lot à créer

Dans le futur module tracking_batch.py :

```python
@dataclass(frozen=True, slots=True)
class TrackingBatch:
    node_records: tuple[TokenUsageRecord, ...]
    google_api_records: tuple[GoogleApiRecord, ...]
    image_generation_records: tuple[ImageGenerationRecord, ...]
    tts_records: tuple[TTSUsageRecord, ...]
    message_count: int

    def summary(self) -> dict[str, int | float]:
        """Même agrégation et mêmes clés que le get_summary actuel."""
```

Le module importe les formes depuis tracking_records.py et les noms de champs depuis core.field_names. Il n’importe ni service.py, ni les repositories, ni les collecteurs globaux.

Dans TrackingContext, interfaces privées proposées :

```python
def _snapshot_pending(self) -> TrackingBatch:
    """Copie synchrone des préfixes et du delta de messages."""

def _acknowledge_batch(self, batch: TrackingBatch) -> None:
    """Publication et retrait synchrones du lot confirmé, jamais un clear global."""

async def _do_persist(
    self, db: AsyncSession, *, batch: TrackingBatch, commit: bool
) -> None:
    """Écrit ce lot seulement ; acquitte après le succès au sens du mode choisi."""
```

Ces signatures décrivent le contrat futur. Conserver _persist_to_database comme porte sérialisée commune à commit et __aexit__. Aucun appelant de production ne doit appeler _do_persist directement.

### Compteur de messages

Le booléen _message_count_committed peut avaler un message ajouté pendant un flush qui avait capturé zéro message. Le remplacer par _committed_message_count, un entier initialisé à zéro.

Le delta à capturer vaut _message_count - _committed_message_count. À l’acquittement, incrémenter le compteur confirmé de batch.message_count. _message_count reste le total du contexte pour les lecteurs qui le présentent ainsi. Aucun nouveau comptage de messages n’est introduit à l’antenne.

### Confirmation, échec et annulation

| Situation | Acquittement mémoire | Transaction et comportement |
|---|---|---|
| Session interne, commit DB retourné avec succès | Immédiatement, sans await avant publication/retrait | Les données du lot sont confirmées |
| Échec certain avant succès du commit interne | Aucun | Le contexte DB annule/ferme ; le lot reste en attente |
| Annulation en attendant _persist_lock | Aucun lot capturé | Aucune écriture supplémentaire |
| Annulation avant l’envoi du commit | Aucun | Prouver le rollback avec PostgreSQL, pas avec un mock de close |
| Succès des écritures en session externe | Acquittement selon le contrat existant d’acceptation dans la transaction appelante | Ne pas appeler commit ou rollback à la place du propriétaire |
| Rollback ultérieur du propriétaire externe | Pas de rejeu autonome | Le propriétaire gère l’échec ; ne pas promettre que ce tracker peut être réutilisé pour rejouer sa transaction |
| Réponse perdue pendant commit ou mort du processus | Résultat potentiellement inconnu | Hors garantie du correctif ; aucune affirmation exactement une fois |

Placer l’acquittement immédiatement après le retour du commit et avant les logs/fermetures susceptibles d’échouer. Ne pas déplacer cette étape après un nouvel await de nettoyage : cela créerait une fenêtre de commit confirmé mais de lot encore rejouable.

Le wrapper DB actuel reste responsable de son cycle de vie ; ne pas profiter de cette correction pour remplacer les helpers de session ou refondre la composition des transactions. Une panne de nettoyage après acquittement ne doit pas remettre le lot en attente.

L’acquittement ne contient ni journalisation ni éviction de collecteurs : ces opérations viennent après la publication et le retrait de tous les préfixes. Une erreur de diagnostic après confirmation ne doit pas laisser un lot déjà publié disponible pour un nouveau commit. Le mécanisme existant de limite du nombre de runs reste actif après cette séquence.

## Task C1 — caractériser les courses par les portes publiques

**Files:**

- Create test: apps/api/tests/unit/domains/chat/test_tracking_context_concurrency.py.
- Reuse: tests/unit/domains/chat/test_tracking_context_exit.py et test_tracking_context_instance_budget.py.

**Interfaces:** Le test appelle commit et __aexit__. Des asyncio.Event suspendent le repository après capture des valeurs persistées ; les méthodes de collecte restent réelles, leurs services de prix sont remplacés par des valeurs locales connues.

- [ ] Préparer des records typés pour chaque famille, avec identités de run uniques et nettoyage des collecteurs en finally.
- [ ] Test ajout : enregistrer 100 caractères, démarrer commit, bloquer l’écriture, enregistrer 200, libérer, puis vérifier 100 persistés et 200 encore en attente. Après un second commit, total 300 et aucune attente.
- [ ] Test deux commits : lancer deux commit sur les mêmes 100 caractères ; vérifier le maximum d’écritures actives égal à un et le total enregistré égal à 100.
- [ ] Test commit + __aexit__ : même oracle, contexte correctement réinitialisé.
- [ ] Paramétrer l’ajout pendant écriture pour LLM, Google, images et TTS ; couvrir aussi une famille vide au départ qui reçoit un nouvel élément.
- [ ] Ajouter un cas de message incrémenté pendant l’écriture d’un lot qui n’en avait pas, puis un cas de second message après un premier lot confirmé.
- [ ] Exécuter ces tests sur le code actuel et conserver les défauts reproduits. Utiliser des barrières, pas des sleeps destinés à « provoquer la course ».

Chronologie normative du premier test :

```text
record(100) -> commit A capture -> repository suspendu
record(200) -> repository libéré -> commit A terminé
assert deltas == [100] et pending == 200
commit B -> assert deltas == [100, 200] et pending == 0
```

Le test doit aussi vérifier l’archive à chacun de ces instants : total visible 300 avant et après la fin du premier flush, puis 300 après le second, jamais 100 ni 400.

## Task C2 — lot immuable et sérialisation

**Files:**

- Create: apps/api/src/domains/chat/tracking_batch.py.
- Modify: apps/api/src/domains/chat/service.py.
- Create test: apps/api/tests/unit/domains/chat/test_tracking_batch.py.
- Modify test: apps/api/tests/unit/domains/chat/test_tracking_context_exit.py.
- Modify test: apps/api/tests/unit/domains/chat/test_tracking_context_instance_budget.py.

**Interfaces:** Les formes et méthodes définies ci-dessus. Les méthodes publiques et la forme de leurs résultats restent inchangées.

- [ ] Extraire l’agrégation actuelle dans TrackingBatch.summary sans changer ses formules, conversions numériques, clés ou traitement du cache Google.
- [ ] Tester une somme mixte avec plusieurs lignes LLM, unités Google supérieures à un, images multiples et TTS facturé en caractères ou tokens déjà valorisés. Un élément ajouté à une liste d’origine après capture ne change pas le résumé du lot.
- [ ] Faire déléguer get_summary à un snapshot de ses données en attente ; préserver son contrat et ses informations de diagnostic utiles.
- [ ] Ajouter _persist_lock distinct de _lock, puis le recontrôle de pending_families sous ce verrou dans _persist_to_database.
- [ ] Passer le même batch à toutes les étapes SQL de _do_persist. Retirer tout accès aux listes mutables dans cette séquence d’écriture et dans les diagnostics qui prétendent décrire ce lot.
- [ ] Remplacer le booléen des messages par le compteur confirmé et adapter uniquement ses lecteurs identifiés.
- [ ] Ajouter _acknowledge_batch : collecteurs et copies historiques reçoivent batch, _total_committed_records augmente du nombre de nœuds du lot, puis chaque liste perd exactement son préfixe ; aucun await dans cette méthode.
- [ ] Acquitter après succès selon la table ci-dessus. Sur exception, laisser les listes et collecteurs tels qu’ils étaient avant cet acquittement.
- [ ] Transformer le test qui simule get_summary puis appelle _do_persist directement : lui fournir de vrais records et observer l’ordre résumé → budget → commit. Le nouveau test ne doit pas contourner le snapshot qu’il valide.
- [ ] Maintenir le guard AST couvrant toutes les familles dans pending_families ; étendre la vérification aux listes lues par _snapshot_pending et _acknowledge_batch. Ajouter les tests comportementaux de chaque famille, pas seulement le guard.
- [ ] Vérifier la baisse réelle de la taille logique de service.py et l’absence de nouveau cycle ou d’override MyPy.

À l’acquittement, la règle est celle-ci pour chaque famille, avec la liste et le tuple correspondants :

```python
del self._tts_records[: len(batch.tts_records)]
```

Ce retrait vient après publication du même tuple dans le collecteur, au sein de la même séquence synchrone. Ne pas retirer par égalité ou par ensemble : deux appels légitimes peuvent porter exactement les mêmes valeurs.

## Task C3 — archives, échecs et sorties

**Files:**

- Extend: apps/api/tests/unit/domains/chat/test_tracking_context_concurrency.py.
- Extend: apps/api/tests/unit/domains/chat/test_tts_usage_record.py.
- Extend: apps/api/tests/unit/domains/chat/test_tracking_context_exit.py.
- Reuse: apps/api/tests/unit/domains/radio/test_adapters.py.

**Interfaces:** get_summary, get_tts_usage_for_archive, get_llm_calls_breakdown, get_google_api_calls_breakdown et get_image_generation_calls_breakdown conservent leurs résultats métier.

- [ ] Lire les archives pendant l’écriture suspendue, après le premier succès et après le second : mêmes totaux cumulés ; les nouveaux records ne doivent pas être publiés prématurément dans les collecteurs.
- [ ] Injecter un échec connu avant commit après capture, ajouter des unités entre-temps et réessayer après rollback : aucun élément perdu et aucun collecteur rempli avant succès.
- [ ] Vérifier l’absence de doubles copies locales et globales après deux commits vides successifs.
- [ ] Vérifier les appels Google exclusivement en cache : pas de dépense ni de persistance forcée. Mélangés à un lot facturable, ils conservent leur visibilité de diagnostic actuelle.
- [ ] Annuler une tâche qui attend le verrou ; l’autre flush se termine, aucun nouveau snapshot n’est écrit par la tâche annulée.
- [ ] Annuler pendant une écriture simulée avant commit : données encore en attente, lock libéré, nouvelle tentative possible après résolution connue de la transaction.
- [ ] Préserver le contrat __aexit__ sur exception/annulation et auto_commit=False, ainsi que la gestion actuelle du ContextVar. Tout task créé pour protéger une écriture doit être détenu et attendu ; ne pas ajouter un fire-and-forget.
- [ ] Vérifier que AccountedProducer continue de déposer la consommation sur réussite, erreur de production et flash ; ne pas ajouter de verrou radio redondant.
- [ ] Vérifier deux trackers distincts du même run_id avec des ensembles disjoints : total de leurs collecteurs correct et aucun dédoublonnage fondé sur les valeurs des records.

## Task C4 — preuve PostgreSQL des transactions

**Files:**

- Create test: apps/api/tests/integration/domains/chat/test_tracking_context_concurrency_db.py.
- Reuse regression: apps/api/tests/integration/domains/chat/test_run_ledger_tts_db.py.
- Reuse regression: apps/api/tests/integration/domains/google_api/test_tts_export_db.py.

**Interfaces:** Vrais ChatRepository, statistiques et registre de budget. Les barrières peuvent entourer une méthode pour contrôler l’interleaving, mais son SQL réel est exécuté.

La fixture async_session du projet utilise une transaction englobante et des savepoints. Ne pas partager cette même AsyncSession entre opérations concurrentes pour fabriquer la preuve. Pour le scénario session interne, utiliser une petite factory de sessions du moteur de test, avec un propriétaire réellement visible de ses connexions, puis nettoyage explicite des seules données de test. Une session externe est testée séparément sous contrôle de sa tâche propriétaire.

- [ ] Refuser une adresse de base non déclarée comme cible de test ; utiliser les fixtures test_database_url/async_engine du projet et un identifiant de run unique.
- [ ] Exécuter deux commits concurrents du même tracker sur de vraies transactions ; vérifier une seule consommation dans MessageTokenSummary, UserStatistics et le registre d’instance, ainsi que le bon nombre de logs détaillés des familles concernées.
- [ ] Rejouer ajout 100 + 200 avec interruption contrôlée après capture. Après les deux commits, retrouver 300 dans le résumé et l’archive, et le coût correspondant dans les agrégats concernés.
- [ ] Injecter une erreur certaine avant le commit : toutes les écritures de la transaction ciblée sont annulées. Retirer l’injection et réessayer : un seul total final.
- [ ] Tester une annulation avant envoi du commit et inspecter la DB depuis une session indépendante après fermeture : aucune écriture partielle du lot annulé.
- [ ] Session externe : commit du tracker écrit sans confirmer la transaction du propriétaire ; un rollback du propriétaire laisse zéro donnée persistée. Ne pas réutiliser implicitement le tracker consommé pour rejouer une transaction externe annulée.
- [ ] Session externe, succès du propriétaire : une seule consommation finale ; le tracker n’a ni confirmé ni annulé d’autres changements métier de cette transaction.
- [ ] Deux trackers, deux sessions DB, même run_id, données disjointes : l’UPSERT cumule les deltas. Le verrou par instance ne doit pas devenir un verrou global de la radio.
- [ ] Nettoyer les données de test et collecteurs même si une assertion échoue. Aucun DDL ni purge générale dans les cas de test.

Pour le registre quotidien global, isoler la cible ou mesurer un delta sous une exécution séquentielle dédiée : ne pas attribuer au scénario testé les dépenses d’un autre test concurrent.

## Vérifications de la réalisation

Depuis apps/api, après création des fichiers :

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/domains/chat/test_tracking_batch.py tests/unit/domains/chat/test_tracking_context_concurrency.py tests/unit/domains/chat/test_tracking_context_exit.py tests/unit/domains/chat/test_tracking_context_instance_budget.py tests/unit/domains/chat/test_tts_usage_record.py tests/unit/domains/chat/test_tracking_context_started_offset.py tests/unit/domains/chat/test_tracking_context_call_type.py tests/unit/domains/radio/test_adapters.py --no-cov -q
.venv/Scripts/python.exe -m pytest tests/integration/domains/chat/test_tracking_context_concurrency_db.py tests/integration/domains/chat/test_run_ledger_tts_db.py tests/integration/domains/google_api/test_tts_export_db.py --no-cov -q
```

Les tests d’intégration exigent le préflight et l’environnement hermétique du projet. Les suites rapides avec xdist et la couverture séquentielle font partie de la qualification : l’annulation et les collecteurs partagés ne doivent produire aucun warning de tâche, coroutine ou transport.

## Livraison, observation et limites

Changement indépendant des lots A et B, sans migration ni retraitement historique. Les commentaires affirmant une idempotence générale grâce à un clear doivent décrire la nouvelle garantie de concurrence et ses limites.

Observer les erreurs de persistance existantes et vérifier, sur une session contrôlée, la concordance entre unités collectées, résumés et budget. Ne pas corriger automatiquement l’historique : le défaut reproduit ne démontre pas quels enregistrements historiques seraient erronés.

Un retour au commit antérieur ne nécessite pas de conversion de données ; il réintroduit cependant le défaut concurrent. Un arrêt de déploiement qui tue un processus au milieu d’un commit reste hors garantie de ce correctif local. Une exigence de reprise exactement une fois après résultat incertain constituerait un nouveau projet de registre durable.
