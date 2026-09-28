# Radio TTS — préparation des trois correctifs ciblés

**Statut : analyse et conception uniquement, aucun développement commencé.**

Préparé le 28 septembre 2026, sur HEAD `79a071251e387f58ea0d0b7800ddb5a749a1bf1e` et le contenu du checkout. Les modifications préexistantes de la radio dans personal.py et readers sont étrangères à ce périmètre et doivent être préservées. Recontrôler les fichiers ciblés au démarrage de la réalisation.

## Objectif

Corriger trois défauts délimités sans changer le fournisseur, le modèle, les voix, les textes, les contrôles factuels, l’expressivité ni les fonctionnalités du lecteur :

| Lot | Résultat attendu | Plan indépendant |
|---|---|---|
| A — erreurs TTS OpenAI | Une erreur est classée à partir du statut, des types SDK et des indications structurées ; une requête définitivement invalide n’est pas renvoyée par la radio | [Plan A](../plans/2026-09-28-radio-tts-erreurs-openai.md) |
| B — audio Gemini | La radio conserve le WAV reçu jusqu’au mixage final ; l’encodage MP3 intermédiaire disparaît | [Plan B](../plans/2026-09-28-radio-tts-gemini-wav.md) |
| C — comptabilité concurrente | Deux enregistrements sur le même tracker ne perdent ni ne comptent deux fois les unités arrivées pendant une écriture | [Plan C](../plans/2026-09-28-radio-tts-comptabilite-concurrente.md) |

Ces plans sont exécutables séparément. Ordre conseillé : B, puis A, puis C. Aucun ne dépend du regroupement des lignes ou d’un cache de reprise.

## Bénéfice attendu et décision d’engagement

| Lot | Effet directement vérifiable | Effet sur les appels et la facture fournisseur | Risque à qualifier |
|---|---|---|---|
| B | Suppression de l’encodage MP3 intermédiaire ; conservation des samples source | Aucun appel économisé sur un parcours nominal réussi. Une resynthèse provoquée par cet encodage peut disparaître, sans fréquence mesurée | Validation de l’audio, compatibilité des formats, offsets et ressources temporaires |
| A | Arrêt des répétitions radio après une erreur structurée permanente | Moins de requêtes dans ces scénarios seulement. Aucun gain promis sur les synthèses réussies ni sur des erreurs que le fournisseur ne facture pas | Conserver la récupération des erreurs transitoires et des indications explicites du serveur |
| C | Un lot concurrent connu est enregistré sans perte ni doublon local | Rend les coûts internes et budgets fiables ; ne réduit pas la consommation facturée par le fournisseur | Tracker partagé avec le chat, transactions externes, annulations et archives |

L’ordre B → A privilégie d’abord un travail local supprimé de façon certaine, puis la correction conditionnelle des appels inutiles. C est un correctif de fiabilité partagé à traiter séparément. Aucun de ces lots ne résout le plafond de 100 appels lorsqu’une session réalise plus de 100 synthèses distinctes utiles. Les qualifier de sûrs signifie un périmètre borné avec des critères de refus explicites ; l’absence de régression reste à démontrer par les tests prévus.

## Contraintes communes

1. Même configuration vocale effective et même texte transmis.
2. Même API radio, même segment MP3 final, mêmes règles de pauses et même calcul des offsets à partir des durées réelles.
3. Aucun changement des budgets de tentatives, du délai maximal du cooldown, de l’ordonnanceur ou du tampon de diffusion dans ces lots.
4. Les indications structurées qui distinguent une erreur récupérable d’une erreur définitive font partie du lot A ; le SDK conserve ses paramètres de retry et de timeout actuels.
5. Aucun nouveau fournisseur, modèle, service externe, appel de transcription ou dépendance.
6. Aucun changement de schéma DB, de tarif, de plafond budgétaire ou de rétention audio.
7. Les tests fournisseur sont hermétiques, sans clé réelle ni synthèse payante. Le mixage utilise de vrais fichiers audio et le véritable ffmpeg.
8. Les tests de transaction utilisent une base jetable ou la cible hermétique déclarée par le projet. Jamais la production, ni la base de développement contenant des données personnelles.
9. Conserver les ratchets. Le retrait des comparaisons sur le texte d’erreur doit réduire leur baseline ; le tracker partagé doit rétrécir par extraction d’une responsabilité cohérente.
10. Les performances et les coûts doivent être décrits à partir des effets effectivement vérifiés. Aucun pourcentage global d’économie n’est promis.

## Constats qui motivent précisément les changements

### A. L’information existe dans le SDK mais est perdue

OpenAITTSClient.synthesize classe actuellement le texte libre d’une exception avec des sous-chaînes. Il ne transporte pas son statut HTTP ni Retry-After dans TTSProviderError. La propriété transient traite alors une erreur HTTP sans statut comme récupérable.

Le SDK installé réessaie notamment HTTP 408, 409, 429 et les erreurs serveur. Il lit aussi x-should-retry et plusieurs formes de Retry-After. Une correction qui marquerait tous les 4xx comme définitifs diminuerait donc la résilience pour 409 ou une indication explicite du serveur.

Le plan A prévoit une classification typée, une indication interne facultative de retryabilité et un parseur borné des délais. Les autres adaptateurs gardent exactement leur comportement lorsqu’ils ne fournissent pas cette indication. Le compteur de requêtes du transport simulé constitue la preuve des appels évités ; une métrique de synthèse logique ne compte pas les retries internes du SDK.

### B. La capacité WAV existe déjà

La factory accepte déjà gemini_output="wav". Le client Gemini sait retourner le WAV reçu et envelopper les réponses PCM dans un conteneur WAV. La radio ne passe pas cet argument et conserve donc le défaut MP3.

Son assembleur sonde les durées des fichiers, les décode, applique les pauses et l’encodage final. Il n’a pas besoin d’un MP3 intermédiaire. Les fichiers temporaires portent déjà l’extension fournie par client.audio_format. Le changement de production principal est donc un argument explicite au point de composition de la radio.

Le test indispensable traverse factory radio → client Gemini simulé → fichier WAV réel → assembleur/ffmpeg réel → MP3 final. Un FakeMixer ou les seuls octets factices RIFF des tests existants ne prouvent pas ce résultat.

**Point découvert pendant la préparation :** la conversion MP3 actuelle valide aussi implicitement le contenu reçu. La supprimer seule ferait arriver une réponse corrompue au mix final, hors du retry TTS. Le plan B inclut donc une validation du WAV avant retour : lecture PCM valide sans conversion ; sinon décodage local de contrôle par le helper ffmpeg existant, avec la même erreur TTS récupérable en cas d’échec. Les bytes d’origine sont conservés après validation. Ce chemin de compatibilité conserve les conteneurs lisibles par ffmpeg que la bibliothèque wave ne sait pas lire. La suppression garantie du processus intermédiaire concerne la voie PCM/WAV validée ; elle n’est pas affirmée pour cette voie de compatibilité.

### C. Le tracker écrit un ensemble mutable

Le même TrackingContext appartient à une session radio. Les productions de démarrage et les flashes peuvent appeler commit simultanément, pendant que d’autres tâches ajoutent de la consommation.

La persistance lit les listes à plusieurs instants séparés par des await, puis les vide intégralement. Les deux scénarios déjà reproduits sont :

- 100 unités au départ, 200 ajoutées pendant l’écriture : 100 persistées, 0 restantes ;
- 100 unités et deux commits simultanés : deux deltas de 100.

Le défaut est démontré hors production. L’historique fournisseur et les unités enregistrées concordaient sur la session radio précédemment auditée : aucune occurrence sur cette session n’est affirmée.

**Conception retenue : verrou de persistance + copie immuable du préfixe des listes + acquittement de ce seul préfixe.** Les listes ne sont pas vidées avant l’écriture. Les archives continuent donc de voir les enregistrements en cours, et un échec avant confirmation n’exige aucune réinsertion susceptible de doubler un lot.

## Pourquoi ce périmètre reste limité

| Sujet | Décision |
|---|---|
| Regrouper des lignes TTS | Différé ; aucun changement de découpage ou d’alignement |
| Supprimer les retries du SDK | Différé ; leurs budgets et leur propriétaire restent inchangés |
| Corriger tout le cooldown | Différé ; transmettre un délai ne signifie pas supprimer le plafond actuel de l’ordonnanceur |
| Recommencer le mixage final | Différé ; le lot B supprime une conversion intermédiaire, il ne crée pas une nouvelle politique de retry local |
| Cache ou reprise après redémarrage | Différé ; aucune persistance supplémentaire |
| Tableau de bord d’optimisation | Différé ; métriques et logs existants, tests comptant les requêtes réelles |
| Garantie comptable exactement une fois après résultat DB incertain | Hors lot C ; elle nécessite une identité durable d’opération et une stratégie de réconciliation |
| Changement des transactions externes | Le propriétaire reste responsable du commit/rollback ; le plan C caractérise ce contrat sans le remplacer |

## Interfaces et fichiers principaux

| Fichier existant | Responsabilité dans le projet | Changement prévu |
|---|---|---|
| apps/api/src/domains/voice/openai_tts_client.py | Appel SDK et métriques TTS | Déléguer la classification typée, conserver les paramètres de requête |
| apps/api/src/domains/voice/exceptions.py | Contrat d’erreur partagé | Indication facultative de retryabilité, défaut inchangé |
| apps/api/src/domains/radio/adapters.py | Construction des dépendances radio | Demander explicitement le WAV à Gemini |
| apps/api/src/domains/chat/service.py | Collecte, résumé, persistence et archives | Sérialiser l’écriture et acquitter le lot exact |

Trois nouveaux modules de production sont proposés pour la réalisation : openai_tts_errors.py pour la traduction des exceptions SDK ; gemini_audio.py pour la validation avant mixage ; tracking_batch.py pour le contrat immuable et l’agrégation d’un lot. Le dernier ne dépend pas de TrackingContext : pas de cycle d’import.

## Critères d’acceptation communs

- Une erreur HTTP 400 déterministe produit un seul appel HTTP SDK, puis aucune nouvelle tentative de la radio ; les scénarios transitoires gardent leur capacité de récupération.
- Une réponse Gemini WAV est rendue à l’identique avant le mix ; le PCM conserve ses échantillons lors de l’enveloppement WAV ; aucun transcode MP3 intermédiaire n’est appelé par la radio.
- Le fichier radio servi reste un MP3 conforme aux paramètres de MixParams. Le transcript conserve l’ordre et les pauses calculées depuis les durées mesurées.
- Les scénarios comptables 100 + 200 et deux commits de 100 donnent respectivement 300 et 100 au terme des commits nécessaires, dans les agrégats, les statistiques et les archives concernés.
- Un défaut de comptabilité ne casse pas le flux conversationnel ; les données non acquittées restent disponibles pour une nouvelle tentative lorsque le résultat de la transaction est connu.
- Aucun nouveau test n’est rendu vert en simulant la frontière qu’il est censé vérifier : transport SDK pour A, processus ffmpeg pour B, PostgreSQL pour les transitions du lot C.

## Portes qualité lors de la future réalisation

Après chaque lot : suite comportementale ciblée, puis les portes imposées par CLAUDE.md pour les fichiers modifiés. Avant livraison de l’ensemble : task lint, task test:backend:unit:fast, task test:backend:unit:coverage et task ci:fast avant push. Pour C, ajouter les tests d’intégration avec PostgreSQL ; pour B, les tests avec ffmpeg/ffprobe et la validation dans l’image API de production. Ne pas lancer la suite exhaustive par défaut.

Les tests d’intégration audio et de transactions nouveaux doivent être inclus dans les jobs existants ; task test:markers vérifie qu’aucun test ne tombe entre les filtres CI. Les fixtures et les sources de coûts sont locales aux tests : aucune génération ou facturation réseau.

Une sortie positive d’un test ciblé n’est pas une qualification de livraison. Les anomalies préexistantes du checkout restent identifiées séparément et ne doivent pas être corrigées ou masquées pour élargir ce chantier.

## Effort réévalué sur ce périmètre réduit

Heures actives, conception résiduelle, code, tests ciblés et revue inclus ; hors attente et qualification commune finale.

| Lot | Optimiste | Central | Prudent | Motif principal de variation |
|---|---:|---:|---:|---|
| A — classification seulement | 4 h | 8 h | 14 h | Tests sous SDK et compatibilité de retryabilité |
| B — WAV radio et validation compatible | 5 h | 10 h | 18 h | Validation des réponses, compatibilité et assemblage ffmpeg |
| C — persistance concurrente | 12 h | 24 h | 40 h | Transactions, annulation, archives et consommateurs partagés |
| Total ciblé | 21 h | 42 h | 72 h | Trois changements indépendants |

L’enveloppe commune de qualification de livraison reste distincte (6/12/24 h actives selon les résultats des portes et l’environnement), une seule fois pour un ensemble livré. Ce sont des scénarios de travail, pas des percentiles ni un calendrier garanti.

L’estimation A est inférieure au précédent lot OpenAI, car elle exclut désormais le changement de propriétaire des retries. L’estimation C reste conservatrice : le choix du préfixe immuable simplifie la restauration, mais ne supprime pas la qualification des usages partagés.

L’estimation B augmente par rapport au simple argument de factory : conserver la récupération d’une réponse audio invalide est une exigence fonctionnelle nécessaire découverte en suivant la frontière de validation. Elle ne doit pas être omise pour tenir artificiellement le premier chiffrage.

## État de vérification de cette préparation

Effectué ici : relecture des points d’entrée et consommateurs, du SDK installé, des helpers audio, des tests existants, du mécanisme de transaction, des instructions et portes projet ; vérification des trois fichiers radio déjà modifiés avant cette préparation. ffmpeg et ffprobe sont disponibles localement et déclarés dans les Dockerfiles API.

Contrôle documentaire : liens des quatre nouveaux documents vérifiés ; la prévisualisation des audits du dépôt ne signale aucun lien cassé, chemin périmé ou document orphelin dans les documents vivants, aucune dérive des valeurs citées, et des cartes documentaires à jour. Les avertissements historiques préexistants et les chemins des futurs fichiers de ces plans ne constituent pas une validation d’implémentation.

Les reproductions et campagnes de tests de l’audit précédent sont des preuves du diagnostic existant. **Les nouveaux tests décrits dans les plans ne sont ni écrits ni exécutés. Aucun correctif n’est développé, aucun changement de production ni déploiement n’a été effectué.**
