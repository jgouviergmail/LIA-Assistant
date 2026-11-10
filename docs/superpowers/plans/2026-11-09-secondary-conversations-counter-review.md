# Discussions annexes — contre-revue des trois arbitrages

Date : 2026-11-09. Statut : **conception révisée, sans code métier**. Travail strictement inline. Ce document complète l'[analyse](2026-11-09-secondary-conversations-analysis.md) et le [plan TDD](2026-11-09-secondary-conversations-plan.md), corrigés avec les mêmes décisions.

## 1. Décisions après vérification

| Point contesté | Décision révisée | Motif et limite |
|---|---|---|
| Changer l'identité runtime au reset | **Conservé, avec périmètre réduit et protection des écritures.** L'UUID de la discussion reste stable ; seul l'état de travail change d'identité. | Permet de servir un état neuf pendant le nettoyage de l'ancien. La rotation seule ne garantit pas son effacement physique. |
| Une génération par compte et 100 annexes | **Une exécution du graphe par compte conservée comme choix explicite de cette version ; plafond de 100 annexes retiré.** | Le premier choix évite d'ajouter du parallélisme payant aux historiques multiples. Il n'était pas une garantie générale du code actuel. Aucun besoin ni mesure ne justifie le second. |
| Nettoyage distribué | **Contrat précisé : admission durable, transition SQL unique, écritures clôturées, nettoyage idempotent suivi jusqu'à résultat explicite.** | Un TTL Redis, un `done` SSE, un timeout d'attente ou une absence d'exception ne prouvent pas l'arrêt des producteurs ni la purge. |

Le dossier ne prétend pas garantir l'absence absolue de bugs futurs. Il retire les faux acquis et donne des oracles vérifiables pour les courses identifiées. L'activation est interdite tant qu'un test critique de ces contrats échoue ou reste sans preuve.

## 2. Identité : alternatives éprouvées et frontière minimale

### 2.1 Ce qui a réellement été essayé

Les sondes utilisent le LangGraph et le saver PostgreSQL installés dans le venv, un petit graphe sans modèle et une base jetable.

| Option | Observation | Conclusion |
|---|---|---|
| Garder le thread et seulement appeler `adelete_thread` | R02 : un `aput` tardif recrée un checkpoint sous ce même thread. | Insuffisant sans clôture des écritures. Une purge échouée peut aussi laisser l'ancien état lisible. |
| Utiliser librement `checkpoint_ns` comme révision du graphe racine | R01 : `aget_state` refuse `revision1` avec `Subgraph revision1 not found`. Le graphe interprète ce namespace comme un sous-graphe. | Ce n'est pas un remplacement natif transparent. Détourner une clé interne ou adapter les méthodes de lecture/écriture serait une autre intégration à maintenir. |
| Conserver le thread avec une clôture transactionnelle, puis attendre la purge | Faisable en principe, mais impose de rendre la discussion indisponible tant que l'ancien état n'est pas effectivement purgé. | Alternative valable si ce compromis est accepté ; ce n'est pas celui retenu pour les pannes de stockage. |
| UUID runtime distinct, clôture transactionnelle des écritures et nettoyage repris | R03 : le nouveau graphe ne relit pas l'ancien état. R19–R23 : les API natives peuvent écrire sur une connexion liée à la transaction de contrôle. | Retenu : disponibilité du nouveau contexte, provenance stable, et protection de l'ancien stockage sont trois responsabilités distinctes. |

Sources propriétaires : [saver instrumenté](../../../apps/api/src/domains/conversations/instrumented_checkpointer.py), [factory](../../../apps/api/src/domains/conversations/checkpointer.py), [orchestration](../../../apps/api/src/domains/agents/services/orchestration/service.py). Le contrôle du namespace a aussi été lu dans `_subgraph_for_namespace` du LangGraph installé ; les trois tables et les écritures natives dans son `checkpoint/postgres/aio.py`. Aucun fichier de bibliothèque n'a été modifié.

### 2.2 Une identité par responsabilité

| Identité | Lecteurs/writers concernés | Invariant |
|---|---|---|
| Compte | Préférences, consentements, apprentissages, plafonds, authentification | Inchangée ; aucune duplication par annexe. |
| Discussion métier | Routes publiques, messages, fichiers produits, décisions, coûts, provenance | UUID stable ; `agent_decisions.thread_id` conserve ce sens métier malgré son nom. |
| Runtime | Checkpoints, namespaces des contextes d'outils, interruptions, buffers de cartes temporaires | Nouveau UUID au reset seulement ; initialement égal à l'UUID historique, donc pas de déplacement massif des checkpoints. |
| Run | Comptabilité et effets d'une exécution, admission, reprise | Le même run reste le même travail payé, même si sa source disparaît. |
| Session fournisseur | Identifiants Live/téléphonie distants | Jamais utilisés comme UUID LIA. |

Le recensement AST ciblant les appels `.get("thread_id")`, `.get("__parent_thread_id")` et `conversation_uuid(...)` a trouvé **40 sites dans 24 modules** sur le snapshot. Ce chiffre est le périmètre de cette recherche, pas un total certifié de tous les accès possibles : les subscripts, builders, variables propagées, namespaces et voies synchrones doivent également être couverts par la garde du lot 0.

Cas à traiter par paires : producteur/consommateur des captures navigateur, files temporaires d'images/documents, contextes des sous-boucles et `derive_sub_agent_context`. Renommer seulement le paramètre du producteur peut rendre une carte introuvable. Le registre des identités autorisées distingue explicitement plomberie et provenance ; aucune substitution globale de `thread_id`.

Un thread de sous-agent peut porter un nom technique non UUID. Sa référence de runtime parent est donc transmise explicitement, jamais reconstruite en découpant son nom. Tout namespace/thread enfant réellement persisté est enregistré parmi les cibles de son runtime parent ; le retrait purge cet inventaire exact. Un sous-agent sans checkpointer ne devient pas artificiellement persistant.

### 2.3 Empêcher la réécriture physique, sans transaction autour du LLM

Le saver actuel délègue ses écritures sans vérifier de génération applicative. La proposition ajoute une **porte de persistance runtime**, appelée pour les checkpoints ET les écritures intermédiaires, pas seulement pour `aput`.

Contrat transactionnel : prendre une connexion du pool existant ; ouvrir une transaction courte ; verrouiller la ligne de conversation en `FOR SHARE` et vérifier son runtime courant ; exécuter l'écriture native sur **cette même connexion** ; commit et restitution. Le reset prend un verrou incompatible avant de changer le runtime. Il n'y a aucun appel fournisseur dans cette transaction.

- Écriture gagnante : elle finit avant la transition, puis sa donnée appartient à la purge de l'ancien runtime.
- Reset gagnant : l'ancien runtime est refusé avant toute écriture. Un contrôle fait sur une autre connexion ou avant le wait ne satisfait pas ce contrat.
- Les méthodes natives de sérialisation, blobs, pending writes et suppression restent utilisées. Pas de trigger ajouté aux tables du fournisseur, ni de fork de son SQL.
- La porte reçoit une référence immuable ; aucun état de requête sur le singleton. Les pools, le fonctionnement concurrent et les métriques du saver actuel restent couverts. Un refus de génération retirée est typé et clôt le producteur ; il ne déclenche pas un retry de modèle.

Les contextes d'outils sont concernés aussi. Les writers actuels de `context/manager.py` et `calendar_tools.py` écrivent les namespaces `(compte, runtime, "context", domaine)`. Leurs lecteurs utilisent des clés et recherches par namespace ; ces données de travail n'ont pas besoin d'une recherche sémantique globale. Le lot 2 rend leur `index=False` explicite et utilise la même transaction de validation pour leur batch natif. **Ne pas entourer le Store sémantique global d'une transaction** : son implémentation peut appeler `aembed_documents` pendant un batch. Les namespaces indépendants, notamment le heartbeat, gardent leur propre politique.

R23 prouve cette composition sur un Store non indexé, pas sur tous ses usages. L'adaptateur final doit posséder et fermer toute tâche de batching qu'il crée ; la sonde a explicitement annulé et attendu celle du Store. Les écritures synchrones et les batches mixtes ne peuvent contourner la classification des namespaces. Une garde et un test de compatibilité de la bibliothèque verrouillent cette frontière avant activation.

## 3. Concurrence et volume : décision assumée, sans quota inventé

### 3.1 Ce que le verrou actuel garantit réellement

[Le broker](../../../apps/api/src/infrastructure/streaming/run_stream_broker.py) utilise une clé par conversation. R04 confirme que deux UUID différents peuvent l'acquérir simultanément. [La route](../../../apps/api/src/domains/agents/api/router.py) n'utilise ce registre que dans le chemin background activé et après résolution d'une conversation existante. Le premier message peut ne pas passer par cette acquisition. Le heartbeat sait reprendre une clé expirée et continue à réessayer sur erreur Redis.

Il était donc incorrect de présenter « un tour par compte » comme une garantie générale déjà acquise. Les tests actuels prouvent des contrats du broker, pas cette garantie.

### 3.2 Choix retenu pour cette évolution

La fonctionnalité ouvre plusieurs historiques, sans ajouter un nouveau mode de générations parallèles : **au plus une exécution active du graphe par compte**, quels que soient la discussion, le worker et la porte d'entrée. La personne peut consulter/préparer une autre discussion ; une nouvelle génération indique où LIA travaille déjà. Une attente HITL libère l'exécution après suspension effective, tout en conservant sa carte et son contexte propres.

Ce choix limite le changement de comportement et le nombre de courses payantes à qualifier. Il ne constitue ni une nécessité mathématique, ni une garantie de plafond monétaire strict, ni un verrou sur tous les jobs : notifications simplement archivées, extractions différées et traitements indépendants gardent leur fonctionnement. Les runners autonomes de graphe appliquent leur contrat existant d'occupation/report ; aucun report, abandon ou succès n'est inventé silencieusement. Un test par producteur est obligatoire.

L'admission devient durable dans PostgreSQL, avec une ligne d'exécution par run et un index unique partiel par compte sur les phases qui occupent encore l'exécution. R09 éprouve le mécanisme d'unicité partielle, pas le modèle final. Redis reste le transport et l'indicateur de présence, sans décider à lui seul qu'une discussion peut être détruite. La création/résolution du premier fil précède toujours cette admission.

Le parallélisme entre annexes nécessiterait une qualification supplémentaire des fusions d'apprentissages, du débit fournisseurs, de la capacité instance et de l'admission des dépenses. Il est volontairement hors du périmètre proposé ; il n'est pas dissimulé dans un paramètre magique.

### 3.3 Aucun plafond de nombre d'annexes

Le plafond de 100 est **retiré**, ainsi que ses scénarios de quota et sa configuration. Une liste paginée, ses requêtes indexées et le rate limit de création protègent le service. Une page contient au plus la limite publiée ; cette limite n'est pas un maximum de discussions autorisées. Tester un ensemble dépassant plusieurs pages, sans charger ses messages ni checkpoints et avec un total exact.

Les réglages de page proposés restent des paramètres techniques publiés par l'API. Créer une annexe vide ne consomme aucun token. Aucun plafond commercial ou quota de stockage nouveau n'est déduit du besoin.

Le reçu de création minimal (compte, request_id, empreinte, UUID résultat) est conservé pendant la vie du compte, même si l'annexe est retirée : une requête retardée répond alors « cible retirée » et ne la recrée pas. Le reçu ne conserve pas le texte du titre et disparaît avec le compte. La rétention des reçus de création est distincte de celle des opérations de purge terminées.

## 4. Cycle de vie : protocole exécutable et limites de responsabilité

### 4.1 Deux défauts supplémentaires constatés

| Source actuelle | Preuve | Conséquence pour le plan |
|---|---|---|
| [Pièces jointes](../../../apps/api/src/domains/attachments/service.py), `delete_all_for_user`, commit interne | R05 exécute le corps actuel extrait par AST avec une vraie connexion : le rollback extérieur ne retire plus une écriture faite avant ce helper. | Le lifecycle ne peut pas réutiliser ce helper à l'intérieur de sa phase atomique. Les repositories y flushent sans commit ; les suppressions de fichiers viennent après. |
| [Tâches différées](../../../apps/api/src/infrastructure/async_utils.py), `await_run_id_tasks` | R17 : après timeout, le helper retourne avec une tâche vivante, déjà retirée de l'index par run. | `done` et cette valeur de retour ne prouvent pas le drainage. La supervision doit garder les tâches vivantes identifiables et distinguer fin d'affichage, arrêt du graphe et fin des extractions. |

### 4.2 États, acteurs et propriété

Proposition de deux modèles cohérents dans le domaine conversations, sans moteur générique de jobs :

| Enregistrement | Champs essentiels et transitions |
|---|---|
| Activité/exécution | Compte, discussion, runtime, révision, nature `graph`/`live`, run ou session, token propriétaire et identité de supervision. `running → draining → closed` ; `running/draining → recovering` si l'arrêt est inconnu. `running` commence à la réservation, avant tout fournisseur. Les phases non closes occupent la cible. L'unicité compte de génération filtre `graph` ; une réservation `live` protège sa cible, veille comprise, et n'empêche pas sa délégation d'admettre un graphe. Une pause HITL close l'exécution, pas la question. |
| Opération lifecycle | Compte technique, discussion, `operation_id`, empreinte canonique de type/cible/révision, ancien runtime, nouvelle révision éventuelle, manifeste sans contenu, phases explicites. `pending → running → succeeded`, ou `running → retry_wait/needs_attention`, puis reprise. |

Le lease d'un nettoyeur porte token, échéance et fence monotone. Le run applicatif ne devient pas libre par la seule expiration de son heartbeat : on réclame sa récupération, on arrête/joint le propriétaire ou on établit sa mort, puis on clôture. Un résultat externe inconnu reste inconnu dans le registre ; aucune génération n'est relancée pour le deviner. Un opérateur peut devoir traiter un état `recovering`, visible et alerté.

La pause SSE et l'attente humaine ne conservent aucune connexion. Une perte Redis ne retire pas l'admission SQL. Une erreur d'accès à cette autorité refuse un nouveau démarrage ; un heartbeat Redis isolé peut être réparé par le même propriétaire après vérification SQL. Il ne peut créer une deuxième admission ni réarmer un runtime retiré.

Les opérations qui prennent plusieurs verrous suivent un ordre unique : verrou propriétaire puis ligne utilisateur si requise pour consentement/effacement ; conversations dans l'ordre UUID ; fichiers dans l'ordre UUID ; enregistrements d'opération. Un writer de checkpoint ne prend que sa conversation et ne remonte jamais ensuite vers l'utilisateur. Un nettoyeur ne garde pas son verrou de claim pendant une I/O. Les chemins existants d'effacement et consentement doivent être confrontés à cet ordre en TDD, pas simplement renommés.

Le démarrage Live réserve sa cible durablement sous cette même autorité AVANT la création de session fournisseur. Sinon un reset pourrait se glisser entre « aucune session Redis » et l'ouverture effective. Le record Redis garde les détails de transport ; la réservation SQL porte la liaison et le droit de retrait, sans dupliquer les préférences ou les échanges vocaux. Une ouverture refusée libère après compensation explicite ; une ouverture de résultat inconnu reste en récupération. La clôture/relay achevée libère la réservation ; la veille ne le fait pas. Les deux ordres start/reset sont obligatoires dans T23.

### 4.3 Transition SQL, un seul commit

1. Authentifier sans conserver de session autour d'un flux. Chercher d'abord l'opération de ce propriétaire : même empreinte → retourner son résultat, même identifiant avec une autre empreinte → conflit. Cette lecture précède le refus de révision périmée lors d'un replay légitime.
2. Sous l'autorité propriétaire et le verrou de conversation, relire rôle, révision, activité durable et session Live, veille comprise. Refuser Principale au delete. Refuser une cible dont le graphe ou le relais vocal n'est pas arrêté ; un bouton « arrêter » ne vaut pas accusé d'arrêt. Une attente HITL inactive est abandonnée explicitement, sans action.
3. Enregistrer l'opération et son manifeste exact ; incrémenter la révision ; choisir un nouveau runtime au reset ou retirer la discussion au delete ; retirer les messages et les usages visés, détacher les provenances selon leurs FK, remettre à zéro les compteurs de vue. Conserver dépenses et registres.
4. Enregistrer les intentions de nettoyage des uploads orphelins, le signal après commit et l'audit. **Un seul commit appartient au service lifecycle.** Aucun appel de helper qui committe, aucune suppression filesystem, aucun appel réseau avant ce commit.

Après commit, le reset peut afficher/utiliser son nouvel état de travail pendant que l'opération termine la purge de l'ancien. La réponse distingue `logical_applied` du statut terminal de nettoyage. Le delete retire la ligne après cette acceptation durable ; une erreur de nettoyage ultérieure ne fait pas réapparaître l'annexe. Une erreur avant commit laisse la vue et les données intactes.

Les alias `/me` restent des alias de Principale. Leur ancienne réponse `success` n'est émise qu'après le résultat complet ; à la borne d'attente, une erreur typée expose l'identifiant d'opération et le fait qu'une réconciliation est nécessaire. Aucun retry HTTP aveugle. Le nouveau client utilise directement l'opération idempotente et son endpoint d'état.

Les requêtes nouvelles de chat/HITL/upload/Live portent aussi la révision affichée. Une requête préparée avant reset mais reçue après ne doit pas être admise dans le nouveau contexte par une résolution opportuniste. L'absence de cible/révision reste le contrat historique Principale ; elle n'est pas le contrat du nouveau client ciblé.

### 4.4 Écritures tardives : les portes doivent toutes fermer

| Famille | Règle après retrait de la génération |
|---|---|
| Checkpoint et pending writes | Validation et écriture natives dans la même transaction, section 2.3. L'ancienne identité ne peut réapparaître après purge. |
| Store de travail | Même clôture SQL pour les namespaces runtime déclarés, sans embeddings sous verrou. Pas de purge du Store compte par motif partiel. |
| Archives, sources de cartes, extractions | Vérifier source/révision et consentement dans la transaction qui écrit, avec verrou compatible avec l'ordre commun. Le booléen calculé avant l'appel modèle ne vaut rien après son retour. |
| Clés Redis runtime | Écritures par la porte déclarée, avec propriétaire/génération ; fermer l'autorisation du runtime et purger atomiquement ses membres. L'absence d'autorisation refuse l'écriture ; un vieux producteur ne la recrée pas. Tout renouvellement dépend de son admission durable encore valide. |
| Buffers locaux/front | Identité runtime et génération de vue, invalidation et abandon des callbacks tardifs. Aucun buffer global de tokens ou carte partagé entre vues. |
| Uploads en vol | Identité de fichier et chemin temporaires possédés dès admission ; validation de cible avant publication. Si refus tardif, le fichier temporaire devient une cible de nettoyage suivie, jamais un orphelin oublié. |
| Travail déjà payé | Facturer et clore le registre selon le résultat réel, même si l'archive est refusée. Pas de remise à zéro des quotas, de replay du fournisseur ni de fausse annulation d'un effet déjà parti. |

Les six familles d'extraction gardent leurs politiques propres. Le helper commun de consentement déclare actuellement mémoire/journal/psyché ; sa variante de révision sert aussi aux sources sans ce consentement. Ne pas inventer six valeurs déjà supportées par cet enum. Une mémoire validée avant la transition reste acquise ; une nouvelle extraction issue de la source retirée est refusée.

Une notification indépendante mérite un contrat distinct : `CurrentPrimaryPublication` résout Principale à l'archivage ; `PinnedRunPublication` conserve la discussion et la révision du run. Une nouvelle notification peut donc arriver après un reset de Principale ; ce n'est pas une résurrection. Une ancienne réponse de modèle ne peut pas se faire passer pour cette notification afin de contourner la garde.

### 4.5 Nettoyage et clôture

Le manifeste est immuable : anciens runtimes, namespaces exacts, familles et membres Redis déclarés, identifiants/chemins des uploads dont la transition vers suppression a été acquise. Un worker ne recalculera jamais « le runtime courant à supprimer ». Les noms de fichiers ne sont jamais réutilisés pour une autre génération.

Chaque phase réclame son travail, ferme sa transaction, exécute son I/O, puis persiste le résultat conditionné par token/fence. Une disparition constatée vaut succès idempotent ; un timeout sans résultat ou un refus filesystem reste en attente. Un crash après `unlink` mais avant enregistrement se récupère par la constatation d'absence. Un propriétaire périmé ne marque rien terminé et n'enchaîne pas de nouvelle phase.

La clôture exige : toutes les phases requises explicitement terminées, clôtures d'écritures effectives, absence de producteur encore autorisé pour les cibles retirées. La fin du flux ou une durée arbitraire n'est pas cet oracle. Les nettoyages locaux peuvent être réessayés ; les actions fournisseurs n'appartiennent pas à ce runner.

La rétention bornée commence **après succès** pour le tombstone et les clés d'idempotence. Une opération incomplète ne disparaît pas à son échéance : elle reste réparable et alertée. Une suppression du compte ne doit pas la supprimer en cascade. Après expiration de la preuve de dédoublonnage, une ancienne requête destructive conserve sa `expected_revision` périmée et ne peut effacer le nouveau contenu.

### 4.6 Pièces jointes et ressources conservées

Le lien d'usage fichier/discussion ne remplace pas la provenance. Lors du dernier retrait, verrouiller le fichier puis vérifier les usages et passer atomiquement à `deleting`. Si un attachement a gagné, le fichier reste ; si le retrait a gagné, le nouvel attachement est refusé. R15/R16 observent ces deux ordres sur deux connexions PostgreSQL avec `pg_blocking_pids`, sans déduire une course d'un simple `sleep`.

Un upload partagé conserve sa politique actuelle d'expiration ; un lien ne transforme pas un upload en fichier gardé. Fichiers générés/gardés, souvenirs déjà extraits et objets métier créés gardent leur politique. Les nettoyeurs utilisent des chemins exacts sous la racine contrôlée ; aucun retrait du dossier complet du compte dans un reset de discussion.

## 5. Preuves produites pour cette contre-revue

Artefacts locaux : `output/analysis/secondary-conversations-20261109/review_probes.py`, `review-probes.json`, `identity-call-sites.json`. Le rapport inclut le hash du script et les versions réellement exécutées ; ce ne sont pas des changements des dépendances du dépôt.

Environnement observé : Python 3.14.7, LangGraph 1.2.14, checkpoint-postgres 3.1.3, psycopg 3.3.4, client Redis 8.0.1. PostgreSQL/pgvector et Redis proviennent d'images locales résolues en identifiants immuables, deux conteneurs `--rm` sans volumes applicatifs, ports publiés sur loopback seulement. Chaque exécution SQL crée un schéma synthétique dans `review_analysis`. Aucun appel modèle ni donnée applicative.

Les deux conteneurs de sondes ont été arrêtés et retirés après vérification de leur label d'appartenance ; les services applicatifs n'ont pas été arrêtés. Le script et les résultats restent disponibles dans le workspace pour la reprise en TDD.

Commande exécutée depuis la racine, sur les ports des conteneurs de cette session :

```powershell
apps/api/.venv/Scripts/python.exe output/analysis/secondary-conversations-20261109/review_probes.py --pg-port 45370 --redis-port 29903
```

**Résultat : exit 0, 23 sondes passées.** Aucun avertissement ou erreur de ressource dans la sortie. Ce sont des expériences de conception sur de vraies dépendances et des protocoles réduits, **pas 23 tests d'intégration de la future application**.

| Sondes | Oracle observé |
|---|---|
| R01–R03 | Namespace racine refusé ; résurrection possible sous le même ID ; nouvelle identité isolée, ancien état encore à purger. |
| R04 | Verrou actuel par conversation, deux discussions admissibles ; libération par ancien token refusée. |
| R05 | Le commit interne actuel du helper fichiers traverse la transaction appelante. |
| R06–R07 | Écriture d'apprentissage périmée refusée ; coût conservé ; apprentissage validé auparavant conservé. |
| R08–R10 | Admission et reset sérialisés ; unicité compte atomique ; ancien token/revision refusé ; replay de même opération sans second reset. |
| R11–R12 | Rollback transition/intention ; takeover du nettoyage avec fence, ancienne clôture refusée. |
| R13–R16 | Crash après unlink repris ; fichier partagé conservé ; deux ordres réels de la course attachement/retrait. |
| R17–R18 | Helper d'attente retourne avec enfant vivant ; refus filesystem ne peut donner un succès terminal. |
| R19–R22 | Écriture native antérieure bloque le reset ; ancienne génération refusée ; round-trip blobs/pending writes ; rollback extérieur effectif sur le saver lié à la connexion. |
| R23 | Écriture/lecture native du Store de travail non indexé ; ancienne génération refusée après retrait et purge. |

Complément sur les contrats actuels, depuis `apps/api` :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/streaming/test_active_run_lease.py tests/unit/infrastructure/streaming/test_active_run_visibility.py tests/unit/infrastructure/test_async_utils_shutdown_join.py tests/unit/infrastructure/test_async_utils_settled_or_raise.py tests/unit/infrastructure/test_async_utils_background_failure.py tests/unit/domains/attachments/test_service.py -q --no-cov -p no:cacheprovider -o faulthandler_timeout=60
```

**Exit 0, 33 passed, 1,03 s** mesurées par pytest. Logs WARNING attendus pour perte de lease, timeout de shutdown, run absent et PDF invalide ; aucun avertissement pytest ou erreur après résumé. Le test de shutdown n'est pas une preuve que le helper différent `await_run_id_tasks` draine ses enfants : R17 démontre précisément cette distinction.

## 6. Portes de sortie ajoutées au plan

Les scénarios T33–T40 de l'analyse étendent les lots 0, 2–6 et 10–11 : compatibilité saver/Store et clôtures atomiques, vraie admission durable, commit imbriqué, drainage incomplet, publication principale indépendante, erreurs physiques, idempotence et volume sans plafond arbitraire. Les fixtures fautives doivent échouer avant correction.

Pour le protocole distribué complet, qualifier au minimum deux workers, vrai PostgreSQL/Redis/Store, redémarrage et arrêt brutal, ancienne tâche suspendue puis reprise, et panne entre chaque commit/phase. Mesurer `pg_stat_activity` pendant un appel modèle simulé lent : aucune transaction de cette évolution ne doit attendre le fournisseur. Les probes SQL ne remplacent pas ce test d'intégration.

L'UI, les migrations complètes, les coûts réels et les parcours multi-discussions restent à qualifier au développement. Le dossier est maintenant suffisamment précis pour commencer ce TDD ; l'affirmation « aucune régression » reste conditionnée à ses preuves sur l'implémentation finale.
