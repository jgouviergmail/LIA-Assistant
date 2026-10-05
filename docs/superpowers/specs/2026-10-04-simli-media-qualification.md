# Qualification média Simli

Relevé du 4 octobre 2026. **La perception labiale réelle reste à confirmer sur
une session réelle** : le propriétaire a signalé des mouvements identiques et
répétitifs pendant les commentaires vocaux, et aucun mouvement labial en Live
et Live direct. Le diagnostic du soir (section « Défaut labial ») a trouvé
quatre causes dans le code, chacune corrigée et couverte par un test ; le
jugement perceptif après correction appartient au propriétaire. Les essais
Android et iOS lui sont confiés.

## Audit de la documentation officielle

L'audit a confronté l'index public, les pages MDX du dépôt officiel, les contrats
OpenAPI/AsyncAPI publiés par l'API, le SDK JavaScript et les deux exemples
officiels OpenAI/ElevenLabs au code effectivement utilisé. Les textes du dépôt
ont été lus ; les vidéos intégrées ne constituent pas une preuve exécutée.

| Sujet | Contrat vérifié | Conséquence dans LIA |
|---|---|---|
| Audio d'entrée | PCM16 signé, little-endian, mono, à 16 kHz | Décodage du conteneur, conversion selon la fréquence réelle, aucun MP3/MP4 ni en-tête WAV sur le WebSocket |
| Blocs audio | La documentation du client conseille des blocs de 6 000 octets ; le SDK utilise 3 000 échantillons | Ces deux valeurs représentent le même bloc PCM16, pas un tampon de trois secondes |
| Silence | `handleSilence=true` maintient le mouvement sans audio ; le SDK conseille `false` pour `listenToMediastreamTrack()` | Une vidéo mobile seule ne prouve pas que le moteur anime la parole ; ne pas modifier ce réglage sans vérifier le parcours concerné |
| Démarrage | Le SDK récent attend une image rendue, pas uniquement `START` | La disponibilité requiert une image, une piste audio et le déverrouillage de la restitution |
| Interruption | `SKIP` supprime l'audio antérieur ; `DONE` termine la session | Une interruption de phrase ne ferme pas une session persistante |
| Lecture immédiate | Le SDK et la démonstration préfixent le premier bloc binaire avec `PLAY_IMMEDIATE` ; AsyncAPI ne décrit pas ce raccourci | Fonction vérifiée dans les sources, mais pas ajoutée comme remède supposé à un défaut labial non diagnostiqué |
| Expressivité | Les émotions documentées appartiennent à Simli Auto ; le schéma Compose actuel ne déclare pas de sélection de modèle | Aucun paramètre émotion, regard ou FPS inventé dans Compose ; aucun appel LLM supplémentaire |
| Catalogue | Un agent du compte peut référencer un visage public absent de `/faces` | Fusion de `/faces`, `/auto/agents` et du catalogue public ; noms du compte conservés et aperçu statique gratuit |
| Transport | La migration et le SDK utilisent `/compose/webrtc/p2p` ; certains textes générés mentionnent `peer_to_peer` | Chemin vérifié par le SDK et par la connexion antérieure conservé ; SFU activé |

Sources primaires : [index](https://docs.simli.com/llms.txt),
[dépôt de documentation](https://github.com/simliai/docs),
[audio](https://docs.simli.com/api-reference/audio-info),
[client personnalisé](https://docs.simli.com/api-reference/simli-webrtc),
[SDK JavaScript](https://docs.simli.com/api-reference/javascript),
[migration JavaScript](https://docs.simli.com/api-reference/javascript_upgrade_guide),
[SDK Python](https://docs.simli.com/api-reference/python),
[migration API](https://docs.simli.com/api-reference/api_migration_guide),
[émotions](https://docs.simli.com/emotions),
[OpenAPI](https://api.simli.ai/openapi.yaml),
[AsyncAPI](https://api.simli.ai/asyncapi.yaml),
[SDK source](https://github.com/simliai/simli-client),
[exemple ElevenLabs](https://github.com/simliai/create-simli-app-elevenlabs),
[exemple OpenAI](https://github.com/simliai/create-simli-app-openai).

## Vérifications exécutées

| Frontière | Résultat observé | Portée et limite |
|---|---|---|
| Backend avatars et voix | Suite ciblée complète verte | Contrats, admission, erreurs, catalogue et conteneur PCM ; appels fournisseur simulés |
| Frontend et couverture | `task test:frontend:coverage` vert | Contrats applicatifs ; aucune preuve du rendu du modèle Simli |
| Frontend statique | `task lint:frontend` vert | TypeScript, ESLint et ratchets exécutés |
| Commentaire vocal MP3, MP4/AAC et PCM/WAV | Parcours Chromium et Firefox verts avec véritable WebRTC en boucle locale | Décodage réel, PCM soumis, une sortie audible, fenêtre persistante ; vidéo de test synthétique |
| Réglages, catalogue et aperçu | Parcours Chromium, Firefox et WebKit verts aux largeurs mobile et bureau | Sélection persistée, image chargée, accessibilité et absence de session payante |
| WebKit et média synthétique | Non validé : le pair local ne fournit pas de RTP média malgré une connexion ICE établie dans l'expérience STUN | Ne pas présenter ce défaut du banc de test comme une preuve de défaut Simli ou de compatibilité iOS |
| OpenAI WebRTC | Contrat du flux emprunté testé | Capture sans deuxième lecteur ni arrêt des pistes du fournisseur |
| ElevenLabs WebRTC | Adaptateur installé et simulé avant le filtre du SDK | Sons faibles et silences conservés ; compatibilité physique à mesurer |
| PostgreSQL et Redis | Intégrations réelles isolées vertes | Transactions, persistance et concurrence ; aucune session Simli payante |
| Établissement froid | Mesure antérieure transmise : 4,4 s | Justifie la connexion persistante retenue par le propriétaire |
| Consommation pendant silence | Solde transmis avant/après la sonde : 200 puis 198 minutes | Observation de ce compte ; aucun tarif ou arrondi universel déduit |

Les journaux détaillés sont conservés dans le répertoire de travail temporaire de
qualification. Leurs résultats ne sont pas des garanties matérielles.

## Défaut labial : diagnostic du 4 octobre 2026 (soir)

Deux mécanismes devaient être distingués : restitution locale avec avatar en
attente, ou parole réellement envoyée à Simli avec rendu incorrect. Le
propriétaire a confirmé que, pendant le Live, la fenêtre affichait « Connexion
de l'avatar… » avec le bouton « Activer le son » : c'est le premier mécanisme.
Quatre causes ont été établies dans le code, chacune par un test rouge avant
correction :

| Cause | Mécanisme | Correction |
|---|---|---|
| Live : déverrouillage jamais acquis à froid | `unlocked` n'était posé que par un `unlock()` lancé pendant un geste ET avec un flux déjà présent ; un Live démarré commentaires désactivés appelle `unlock()` avant toute connexion, puis la personne parle sans cliquer. Un re-déverrouillage automatique à la première image a été essayé : vert en Chromium de test, refusé par le Chrome du propriétaire (`avatarState: connecting` avec la vidéo affichée, 05/10) | le son distant est rendu par le graphe Web Audio repris dans le geste (contexte « running »), l'élément vidéo reste muet à vie ; et le Live ne connecte son fournisseur qu'une fois l'avatar prêt, abandonné ou à la borne (`awaitAvatarReady`) |
| Live : aucune frontière de production sur ElevenLabs WS | la route était figée jusqu'à `onGenerationComplete`, émis par Gemini seul ; `agent_response` d'ElevenLabs PRÉCÈDE ses chunks audio, donc aucun EOF audio n'existe | la frontière partagée est la vidange observée (`LIVE_PCM_PRODUCTION_HOLD_MS` sans chunk, sortie vidée) ; l'EOF ou l'indice de parole d'un fournisseur ne fait que l'avancer |
| Commentaires : cadence temps réel strict | un paquet de 187,5 ms toutes les 187,5 ms ; avec un premier son distant à +290 ms (sonde), l'avance serveur n'était que ≈ 85 ms ; chaque gigue la vidait et Simli insérait des trames de silence (`handleSilence`) — bouche qui se referme au rythme des paquets | envoi immédiat sous contre-pression du socket, avance bornée (`AVATAR_PCM_LEAD_MAX_SECONDS`), comme le client de référence du fournisseur |
| Commentaires : vidange et redémarrage par phrase | un `SimliPlayout` par chunk SSE, et l'attente de la vidange distante avant la phrase suivante : ≈ 0,3 s de vidange + 0,3 s de redémarrage par phrase, visage au repos entre deux | une phrase par run ; `voice_complete` (sinon `VOICE_RUN_END_HOLD_MS`) vidange une fois |

Les tests de régression : `lib/avatars/__tests__/browser-media.late-stream.test.ts`,
`lib/voice-output/__tests__/live-player-no-eof-transport.test.ts`, les tests de
`pcm-send-queue`, `playout`, `coordinator` et `audio-queue` réécrits sur le
nouveau contrat. Ce qui reste à mesurer : la perception labiale sur une session
réelle après correction, et les essais physiques ci-dessous.

Les diagnostics de développement ajoutés enregistrent seulement :

- la destination choisie à la frontière du commentaire, `local` ou `avatar` ;
- la fréquence, le nombre de canaux et les trames du clip décodé ;
- les échantillons PCM réellement soumis et l'observation du son distant ;
- les commandes fournisseur autorisées, notamment `SPEAK` et `SILENT`.

Ni audio, ni texte parlé, ni clé, ni URL signée ne sont enregistrés. Un timeout
borné pour une phrase sonore sans retour audio est couvert par un test de
régression. Aucun changement spéculatif de modèle, de silence ou d'expressivité
n'a été utilisé pour prétendre corriger la bouche.

La clôture exige une observation de la prochaine restitution réelle et la
corrélation de ces quatre frontières. Les essais physiques doivent ensuite
mesurer la latence chaude, le décalage audio/vidéo, les phonèmes faibles, les
pauses intérieures, l'interruption, la veille et le réveil, ainsi que les sorties
Bluetooth et interruptions système. L'ADR final attend cette validation.
