# WAV Gemini dans la radio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supprimer l’encodage MP3 intermédiaire du chemin Gemini radio tout en conservant le MP3 final, les voix, les paramètres, les pauses et la consommation fournisseur.

**Architecture:** Le point de composition radio demande à la factory le format WAV déjà disponible. Le client valide les WAV PCM sans conversion ; un format non lisible par wave passe par un décodage de contrôle avec ffmpeg. Les bytes d’origine sont conservés. L’assembleur mesure ces fichiers et effectue l’unique encodage MP3. Les autres consommateurs gardent le défaut de la factory.

**Tech Stack:** Python, httpx MockTransport, pytest, wave/struct de la bibliothèque standard, ffmpeg/ffprobe existants.

**Spec:** [Conception et contraintes communes](../specs/2026-09-28-radio-tts-correctifs-cibles-design.md).

**Statut : préparation uniquement. Aucun changement de format n’a été appliqué.**

## Global Constraints

- Même fournisseur, modèle, voix, texte et contrôles vocaux réellement transmis.
- Même API radio, même segment MP3 final et mêmes règles de pauses.
- Aucune modification du comportement de la factory pour les consommateurs qui ne demandent pas le WAV.
- Pas de nouvel encodage avec perte, cache, politique de retry, volume Docker ou réglage administrateur.
- Les unités input/output retournées par Gemini sont conservées ; la politique actuelle d’usage manquant reste inchangée.
- Aucune génération payante pour les tests ; véritable mixage local obligatoire.

## Review Focus

1. Réponse PCM brute plutôt que WAV : même fréquence et mêmes échantillons après enveloppement — B2.
2. Fichiers WAV plus gros : nettoyage sur tous les chemins et absence de copie persistante supplémentaire — B2/B3.
3. Durée MP3 avec padding : comparer les offsets aux sources WAV réelles, pas aux durées d’un ancien MP3 intermédiaire — B3.
4. Audio fournisseur corrompu : le refus reste une erreur TTS récupérable ; mix final en erreur après audio validé : consommation conservée et aucun nouvel appel fournisseur — B2/B3.
5. Usage direct hors radio et autres fournisseurs : format nominal conservé ; client toujours fermé — B1/B2.

---

## Parcours actuel et changement exact

Le parcours actuel est : réponse Gemini WAV/PCM → éventuel enveloppement WAV → transcode MP3 → fichier de ligne MP3 → décodage/mixage → MP3 final.

Le parcours prévu est : réponse Gemini WAV/PCM → éventuel enveloppement WAV → fichier de ligne WAV → décodage/mixage → MP3 final.

La factory supporte déjà cette sélection dans get_tts_client_sync, puis _instantiate_client. Dans le point de composition session_parts, l’appel futur sera :

```python
client = get_tts_client_sync(
    config,
    strict=True,
    records_tokens=True,
    gemini_output="wav",
)
```

La factory ignore ce paramètre pour les autres fournisseurs. Ne pas changer son défaut global. production.py construit déjà le suffixe du fichier à partir de client.audio_format ; le mixer accepte les formats que ffprobe peut lire. Aucun changement des schémas de session, du codec Redis ou du lecteur n’est nécessaire.

### Conserver la validation qui se trouvait dans le transcode

Une bascule de factory seule est insuffisante : un WAV corrompu actuellement refusé par le transcode déclenche provider_invalid_response et peut être remplacé par la tentative suivante. Sans validation avant retour, il produirait MIX_FAILED, donc l’abandon du segment. Cette différence doit être couverte avant toute activation.

Créer dans un module voice/gemini_audio.py une fonction privée au domaine, appelée dans la branche de sortie WAV :

```python
async def validate_audio_for_mix(audio: bytes, *, timeout_s: float) -> None:
    """Valide un WAV PCM en mémoire, sinon vérifie son décodage par ffmpeg."""
```

Algorithme retenu :

1. Ouvrir les bytes avec wave.open sur BytesIO. Pour un PCM compris par wave, lire les frames et vérifier fréquence/canaux/largeur positifs, nombre de frames positif et longueur exacte des samples annoncés. Réserver la voie sans ffmpeg au PCM mono 16 bits à GEMINI_TTS_SAMPLE_RATE, format produit par l’enveloppement nominal existant et qualifié par B3. Une structure lisible par wave ne prouve pas à elle seule la compatibilité de n’importe quelle combinaison de paramètres avec ffmpeg. Les autres paramètres passent au contrôle de décodage ; ils ne sont pas rejetés ni rééchantillonnés.
2. Si cette validation réussit, terminer. Le client retourne les bytes originaux à l’identique. Aucune synthèse ni conversion locale supplémentaire.
3. Si wave ne sait pas lire le conteneur, si sa structure ne permet pas cette validation ou si ses paramètres sortent du chemin qualifié ci-dessus, appeler le transcode existant avec output_format="f32le" et args=["-codec:a", "pcm_f32le"]. Cette sortie brute sert uniquement à prouver que le contenu est décodable ; elle n’est ni stockée ni rendue. Ne jamais parser le texte d’une wave.Error pour décider si le conteneur est légitime. Accepter une sortie non vide dont la longueur est un multiple de quatre octets, puis conserver les bytes source. Le mixer sait déjà décoder ces mêmes formats via ffmpeg.
4. Si le contrôle ne produit aucun sample complet, ou si ffmpeg échoue, lever FfmpegError et garder son wrapping en TTS provider_invalid_response récupérable, comme le chemin actuel. Le module client reste responsable du comptage et du wrapping ; le helper audio ne dépend pas du ledger.
5. Après succès seulement, retourner le même SynthesisResult et les mêmes unités que la réponse. Aucun changement de formule ou de prix.

Le contrôle utilise l’entrée et la sortie par pipe de transcode, avec le timeout et l’annulation existants. Aucun nouveau helper media public ou accès à son _run privé n’est nécessaire. Le WAV float de compatibilité doit être accepté et conservé byte à byte après un décodage réel de contrôle ; le test prouve aussi qu’un fichier refusé par ffmpeg reste une erreur avant le mix.

La voie de compatibilité peut encore rencontrer une erreur locale susceptible d’être réessayée selon le contrat antérieur. Ce plan élimine ce risque de conversion sur la voie PCM nominale qualifiée ; il ne prétend pas corriger tous les échecs locaux de tous les formats. La part réelle des réponses empruntant chaque voie n’est pas mesurée. Aucun gain de processus ou de latence n’est annoncé sur la voie de compatibilité.

Dans _voice_line, synthesize_billed retourne l’usage, ledger.record_tts_call l’enregistre, puis les octets sont écrits. L’échec ultérieur du mix conserve donc déjà ces unités en mémoire pour AccountedProducer.commit. Ce plan préserve ce chemin ; la correction des races du commit relève du plan C.

## Task B1 — sélection à la composition de la radio

**Files:**

- Modify: apps/api/src/domains/radio/adapters.py, session_parts.
- Modify tests: apps/api/tests/unit/domains/radio/test_adapters.py.
- Modify tests: apps/api/tests/unit/domains/voice/test_tts_factory.py.

**Interfaces:** get_tts_client_sync conserve sa signature. Le seul nouvel argument transmis par la radio est gemini_output="wav". Aucun nouveau type.

- [ ] Étendre le test du constructeur radio pour capturer la configuration et les arguments strict, records_tokens, gemini_output.
- [ ] Modifier le double existant dans TestTheSessionParts : il doit accepter cet argument nommé explicitement, sans un **kwargs qui masquerait une faute de frappe.
- [ ] Tester la construction effective du client Gemini par la vraie factory : son audio_format vaut wav avec l’argument et mp3 sans argument. Utiliser les clés factices de la fixture existante.
- [ ] Tester les autres familles configurées avec gemini_output="wav" : leurs formats restent ceux de leur configuration, aucune substitution de fournisseur.
- [ ] Exécuter ces tests avant modification pour voir échouer le branchement radio attendu.
- [ ] Ajouter l’argument dans session_parts et un commentaire indiquant que la radio possède déjà l’encodeur final.
- [ ] Relancer les tests, dont la fermeture du client lorsque _cards_of échoue.

Oracles principaux :

```python
assert captured_options == {
    "strict": True,
    "records_tokens": True,
    "gemini_output": "wav",
}
assert radio_gemini_client.audio_format == "wav"
assert default_gemini_client.audio_format == "mp3"
```

captured_options est alimenté par le double typé de construction ; radio_gemini_client et default_gemini_client sont produits par la vraie factory avec la configuration de test et fermés dans un finally.

## Task B2 — consommation et erreurs avec le vrai client simulé au transport

**Files:**

- Modify tests: apps/api/tests/unit/domains/voice/test_gemini_tts_client.py.
- Create test: apps/api/tests/unit/domains/radio/test_gemini_wav_production.py.
- Create: apps/api/src/domains/voice/gemini_audio.py.
- Modify: apps/api/src/domains/voice/gemini_tts_client.py, branche WAV uniquement.
- Read only: infrastructure/media/ffmpeg.py, billing.py et domains/radio/production.py.

**Interfaces:** GeminiTTSClient.synthesize_with_usage retourne le même SynthesisResult. Les tests radio injectent ce client réel derrière un MockTransport et un ledger de test enregistrant des appels typés.

Dans cette suite unitaire, les cas de compatibilité contrôlent le résultat ou l’échec du helper transcode avec un double explicite ; ils ne lancent pas de processus. Les fixtures de conteneurs sont déterministes. La capacité réelle de décodage et de mixage se prouve en B3, où aucun helper ffmpeg n’est simulé.

- [ ] Construire un véritable petit WAV mono 16 bits dans la fixture. Ne pas utiliser les octets RIFF factices existants pour un test de format.
- [ ] Remplacer le WAV factice partagé du test client par un vrai petit WAV généré en mémoire, afin que les tests existants respectent le contrat renforcé.
- [ ] Écrire d’abord la séquence réponse WAV corrompue, puis WAV valide ; le transport doit être appelé deux fois et la production doit réussir. Cette caractérisation interdit de déplacer silencieusement l’erreur vers MIX_FAILED.
- [ ] Implémenter validate_audio_for_mix selon l’algorithme défini, puis brancher uniquement la sortie WAV du client. Garder la sortie MP3 hors radio inchangée.
- [ ] Faire répondre le transport avec ce WAV et un usage connu ; vérifier l’égalité byte à byte avant mix ainsi que characters/input_tokens/output_tokens.
- [ ] Faire répondre le transport avec PCM brut et mime_type audio/L16;codec=pcm;rate=24000, puis avec une autre fréquence déjà supportée ; vérifier les samples via wave.open.
- [ ] Remplacer transcode dans le module Gemini par une fonction qui échoue si elle est appelée : un client radio en WAV doit réussir sans la toucher.
- [ ] Pour le même oracle sans conversion, faire également échouer transcode au point d’import du nouveau helper gemini_audio : aucun contournement ne doit appeler ffmpeg sur un PCM WAV valide.
- [ ] Tester une source tronquée, un conteneur vide, un en-tête invalide et un WAV non PCM valide produit par ffmpeg : les trois premières conservent la récupération existante lorsque le décodeur les refuse ; la dernière passe par le contrôle de décodage et reste exploitable. Une source partiellement décodable par ffmpeg suit le comportement préexistant, elle n’est pas rejetée arbitrairement par un test plus strict.
- [ ] Comparer les corps HTTP émis par un client WAV et un client MP3 à configuration identique : ils sont identiques. Pour le second, simuler seulement le transcode local ; cette vérification ne porte pas sur la qualité acoustique.
- [ ] Faire traverser une production valide avec ce client et un mixeur contrôlé : chaque ligne réussie enregistre exactement une consommation aux unités du résultat, les chemins intermédiaires finissent par .wav.
- [ ] Faire échouer le mixeur après réception des lignes : résultat MIX_FAILED, aucune nouvelle requête fournisseur, unités déjà reçues présentes et tous les fichiers de lignes supprimés.
- [ ] Annuler pendant la synthèse ou l’assemblage : aucun fichier de ligne abandonné ni processus appartenant au test encore actif ; la fermeture du client est effectuée.
- [ ] Tester les usages absents avec les attentes actuelles du projet. Ne pas transformer une estimation existante en zéro facturé et ne pas modifier sa formule ici.

La fixture de script est un véritable script accepté par le vérificateur radio avec des faits/références locaux. Elle peut s’appuyer sur les formes de test_production.py, mais ne doit pas importer son module avec ses fixtures autouse ni désactiver le validateur par défaut.

## Task B3 — qualification acoustique locale et image API

**Files:**

- Create test: apps/api/tests/integration/domains/radio/test_gemini_wav_mix.py.
- Reuse: apps/api/src/domains/radio/audio.py et apps/api/src/infrastructure/media/ffmpeg.py.
- Document the accepted result: complément à la décision audio de docs/architecture/ADR-324-A-Personal-Radio-A-Grid-Decides-Models-Only-Write.md.

**Interfaces:** assemble_segment lit les fichiers réellement retournés par GeminiTTSClient avec transport simulé. run_ffmpeg et probe_duration ne sont pas remplacés.

- [ ] Déclarer le marqueur integration et vérifier son exécution dans la suite CI existante ; l’absence de ffmpeg/ffprobe doit faire échouer cette qualification, pas la sauter silencieusement.
- [ ] Générer par bibliothèque standard trois signaux mono de durées connues, avec fréquences distinctes pour identifier leur ordre. Leur amplitude reste sous la saturation et chaque signal porte des bords adoucis pour ne pas introduire de clic de fixture.
- [ ] Mélanger une source WAV et une réponse PCM enveloppée, sur deux parties éditoriales, via le vrai assembleur.
- [ ] Faire aussi traverser une source WAV float nécessitant la voie de compatibilité, avec le vrai décodage de contrôle ; mêmes bytes avant mix, même codec final et aucun MP3 intermédiaire.
- [ ] Ajouter un PCM valide à une autre fréquence acceptée par le client : il suit le contrôle de compatibilité et conserve fréquence et samples avant mix. Ce test interdit de transformer la restriction du chemin rapide en restriction des formats acceptés.
- [ ] Sonder le résultat : codec MP3, mono, fréquence et débit conformes à MixParams. Le fichier partiel n’existe plus après publication.
- [ ] Vérifier les offsets déclarés à partir des durées exactes des samples source et des pauses de MixParams. Ne pas calculer l’oracle en appelant plan_segment.
- [ ] Décoder le MP3 final en PCM et retrouver les fenêtres des trois signaux : ordre correct, silence entre lignes/parties, aucune disparition de ligne. Mesurer les transitions avec une fenêtre de 10 ms et une tolérance justifiée par les trames du codec ; ne pas élargir la tolérance pour absorber une erreur de pause.
- [ ] Comparer la durée totale au cumul source + pauses ; tenir compte explicitement du padding MP3. Pour un candidat dépassant la borne de quelques trames, analyser le padding et le graphe au lieu d’augmenter arbitrairement un epsilon.
- [ ] Vérifier l’absence de saturation numérique et le maintien du filtre de normalisation ; effectuer une écoute locale courte du résultat si une fixture de parole réutilisable existe. Les signaux seuls ne prouvent pas la perception d’une voix humaine.
- [ ] Rejouer le cas audio dans l’image API de production construite à partir du candidat, qui déclare ffmpeg. Aucun changement des Dockerfiles n’est attendu.
- [ ] Inscrire les résultats réellement mesurés dans le complément documentaire, sans inventer de pourcentage d’économie.

La comparaison avec l’ancien double encodage est utile pour expliquer les différences de padding et de niveau, mais l’objectif est de conserver le signal source et la sortie produit. Exiger une égalité binaire entre deux MP3 empêcherait précisément de supprimer un encodage avec perte.

## Ressources et risques bornés

Un PCM mono 16 bits à 24 kHz représente environ 48 kB/s, contre environ 8 kB/s pour un MP3 à 64 kbit/s, hors en-têtes. L’augmentation concerne les intermédiaires d’une production, déjà supprimés en finally ; aucune durée de rétention supplémentaire n’est introduite. Mesurer les tailles des fixtures et confirmer le nettoyage sur succès, échec et annulation.

Le premier bénéfice garanti par les tests est la disparition de l’encodage MP3 intermédiaire ; sur la voie WAV PCM validée, aucun processus de conversion intermédiaire ne subsiste. Le mix final reste susceptible d’échouer ; ce lot n’en promet pas la reprise automatique. Une corruption refusée par le décodeur doit conserver son traitement récupérable avant le mix, pas devenir un abandon de segment.

## Vérifications de la réalisation

Depuis apps/api, après création des fichiers :

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/domains/voice/test_gemini_tts_client.py tests/unit/domains/voice/test_tts_factory.py tests/unit/domains/radio/test_adapters.py tests/unit/domains/radio/test_gemini_wav_production.py tests/unit/domains/radio/test_production.py tests/unit/domains/radio/test_audio_plan.py --no-cov -q
.venv/Scripts/python.exe -m pytest tests/integration/domains/radio/test_gemini_wav_mix.py --no-cov -q
```

Appliquer ensuite les portes communes. Pour le test d’intégration, utiliser l’environnement hermétique prévu par le dépôt ; les fixtures d’intégration peuvent initialiser des services même si le cas audio n’effectue aucune requête SQL métier.

## Livraison et retour arrière

Livrer indépendamment. Les nouvelles sessions prennent la composition du candidat ; ne pas remplacer un client au milieu d’une production existante. Le retour à la version précédente rétablit l’argument par défaut pour les sessions suivantes. Les segments MP3 déjà publiés restent valides.

Critères de refus : paramètres HTTP modifiés, consommation différente à réponse identique, format final modifié, mauvais offsets, fichiers non nettoyés, ou échec dans l’image de production. Aucun changement de voix ou de modèle n’est un moyen de contourner un tel échec.
