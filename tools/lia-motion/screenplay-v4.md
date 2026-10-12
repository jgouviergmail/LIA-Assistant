# LIA — scénario et construction du film V5

Révision des sources du 12 octobre 2026, sous un nom de fichier conservé pour compatibilité. Ce document décrit V5 et sa direction éditoriale ; il ne certifie ni les nouveaux médias exportés, ni une exécution fournisseur, ni l’acceptation d’un diffuseur. Le [rapport de couverture](coverage-v4.md) distingue les interfaces retenues, les annonces et les limites visuelles.

La livraison V4 antérieure — 120 secondes, coupe de 65 secondes, 23 focus — a réussi sa qualification technique locale. Cette preuve appartient à ses sources et médias ; elle ne valide pas les ajouts ou la nouvelle musique V5. Les rapports de livraison doivent conserver leur génération.

Le fil conducteur est une journée avec le dossier Atlas : comprendre ce qui attend, préparer la revue, transformer les décisions en travail, puis confirmer avant d’agir. Les noms, documents, échanges, dates et résultats sont ceux des données de démonstration existantes. Morgan Démo et le fournisseur du dossier restent les mêmes personnes d’un écran à l’autre. Les dates du 19 et du 22 octobre sont un élément du scénario fictif.

Le plan [presentation-plan.ts](src/presentation-plan.ts) prescrit un principal de 150 secondes à 30 images/s, une coupe landing explicite de 65 secondes et vingt-neuf focus. `PRESENTATION_REVISION` distingue la révision active des noms de fichiers compatibles. Les focus reprennent les mêmes composants et gestes de montage, avec des variantes ciblées. Les repères nominaux ci-dessous peuvent être rapprochés des pulsations par [presentation-timing.ts](src/presentation-timing.ts), dans une limite de 0,45 seconde, sans changer la durée totale.

## La mise en scène

Le fond reprend la version claire de la landing : ciel, halos et motif d’attention LIA. Les écrans conservent leurs panneaux, couleurs, contrôles et hiérarchies natives. Les effets agissent sur la caméra, les échelles et des fragments réels de l’interface ; ils ne créent pas de nouveaux contrôles de produit.

BIP apparaît uniquement dans la présentation. Il regarde l’élément utile, change d’appui, accompagne un déplacement ou réagit brièvement à la résolution d’une difficulté. Son expression peut passer de l’attention à la réflexion, puis à la satisfaction. Il ne saute pas sur chaque battement et ne mime pas une parole qui n’existe pas. Les mouvements du corps et du regard précèdent légèrement l’objet qu’il désigne ; cela lui donne une intention. Les composants desktop n’intègrent plus son widget ; la [capture mobile V4](public/capture-v4/mobile.provenance.json) masque BIP par la préférence native de visibilité, sans retouche bitmap. Les captures anciennes avec un BIP interne restent des références historiques.

Le chapitre Compagnons donne une vraie place à Lumo masculin (`lumen`) et aux autres avatars natifs. Trois contextes courts font passer Lumo de l’attention à la réflexion puis à la joie ; une galerie animée termine ce temps. BIP ne devient pas un deuxième personnage interne. Les contextes sont des scènes fictives choisies pour animer les expressions natives, pas la preuve d’une détection émotionnelle ou d’une voix fournisseur.

Les textes deviennent une partie du cadre. Un titre de deux lignes au maximum porte une idée ; une phrase courte situe le cas d’usage. Le détail ne se disperse pas en puces autour de l’écran. Inter conserve l’identité de l’application, avec des poids et des tailles suffisamment différents pour rendre la hiérarchie évidente. Bleu, violet et cyan/vert de la palette LIA distinguent les blocs complets, sans colorer arbitrairement un mot par phrase.

Le sujet utilise environ les trois quarts du cadre utile. On alterne plan ample, recadrage près du détail et composition occupant toute la largeur. Les scènes avec texte à gauche et écran à droite ne deviennent pas une formule répétée : mémoire et tableau inversent les rôles, connaissances met le texte au-dessus, créations et finale utilisent la largeur. La marge de sécurité demeure constante et aucun effet ne fait passer un texte utile sous BIP.

Les effets suivent une action ou un lien : un sujet du briefing conduit à une personne ; une source conduit à son espace ; une action du compte rendu conduit à son ticket ; un résultat conduit à la galerie ; la suite du dossier conduit à une routine ; le partage ramène à l’accord. Les objets restent reconnaissables pendant le déplacement. Une transition ne remplace pas un écran par une autre page de texte.

La piste de test Lookin’ Up a été écartée. La piste active, « LIA — ElectroFunk », est la troisième création sur mesure avec Google Lyria 3.5 via Gemini API. Chaque prise réussie correspond à une correction explicitement demandée par l’utilisateur, sans retry automatique. Source active MP3 mesurée : 160,914208 secondes, stéréo 44,1 kHz / 192 kbit/s. [prepare_music_film.py](scripts/prepare_music_film.py) réutilise cette source, prépare 160 secondes continues sans boucle en PCM 24 bits / 48 kHz et met à jour [music-film.json](src/music-film.json). Le format de travail ne prétend pas améliorer le MP3. Le prompt cible 134 BPM ; les appuis suivent les pulsations mesurées, pas une cadence supposée constante. Entrée, stabilisation, lecture, sortie laissent comprendre avant le mouvement suivant ; les phrases ne clignotent pas à chaque battement. [La provenance active](public/audio/v5/lia-electrofunk-generation.json) et [les conditions](public/audio/v5/LICENSE.md) accompagnent la création, sans licence CC BY ou exclusivité de copyright revendiquée. Les sources et records des deux premières prises, « Une journée en harmonie » et « Le groove en mouvement », sont conservés. Le total publié des trois générations est 0,24 USD, sans facture vérifiée. Écoute humaine et acceptation TV restent distinctes des mesures techniques.

Le prompt de la prise active exclut saxophone, cuivres, bois et voix. L’audit optionnel d’instrumentation a reçu HTTP 400 pour sa seule demande, sans retry ; aucune conclusion utilisable ne confirme cette instrumentation. Ce scénario ne transforme pas la consigne de composition en résultat d’audit.

## Les quatre usages

| Temps | Usage | Ce que le spectateur comprend |
|---|---|---|
| 0–44 s | Commencer la journée | Compagnon et lecture s’adaptent ; briefing, rappel et fiche Relations ramènent au même rendez-vous. |
| 44–79 s | Préparer un rendez-vous | LIA rapproche les informations, rend une divergence visible, retrouve les sources et garde la trace des échanges. |
| 79–124 s | Faire avancer le dossier | Travail, livrables, planning, registre, outils et cercle prolongent la décision. |
| 124–150 s | Rester maître | L’instance se configure et se suit ; le contenu se relit avant confirmation. |

## Le découpage

| Temps | Surimpression | Image et mouvement | Temps de lecture / résultat |
|---|---|---|---|
| 0–4 s | **Ta journée. / LIA à tes côtés.** Un fil pour préparer, décider et avancer. | BIP prend présence par regard et pivot ; une demande ouvre l’histoire. | Signature lisible, action brève. |
| 4–14 s | **Une présence. / Des expressions vivantes.** Lumo et les avatars natifs accompagnent le contexte illustré. | Lumo masculin grand : attentif, réfléchit, joyeux. Après 6,5 secondes de scène, ensemble natif animé. | Le changement suit une demande, sans bouche prétendument calée sur une parole absente. |
| 14–21 s | **Le même résultat. / Ta façon de le lire.** Cartes, HTML, HTML + cartes ou Markdown : tu choisis. | Quatre boutons natifs, passage Cartes HTML vers HTML enrichi et description active du réglage. | Sélecteur lisible, sans prétendre montrer une réponse reformatée ; aucun mode bulles inventé. |
| 21–29 s | **Ta journée, / à lire ou à écouter.** Ton briefing et ta Radio, selon les sources choisies. | Briefing puis Radio avec le même dossier. | Programme et sujet demeurent reconnaissables. |
| 29–34 s | **Le rappel arrive. / Le fil reste ouvert.** La notification de démonstration ramène au rendez-vous. | Notification native reconstituée ; transition vers Morgan. | Rappel fictif explicite, sans livraison push ou SSE réelle. |
| 34–44 s | **Une personne. / Le contexte réuni.** Coordonnées, échanges, préférences et engagements au même endroit. | Fiche Relations centrale : identité, coordonnées et sections du même contact ; rapprochement vers un engagement et mémoire. | Contacts, e-mails, appels et rendez-vous gardent la même identité. |
| 44–59 s | **Des informations, / une vue claire.** Messages, documents et agenda réunis pour ton rendez-vous. | Conversation, bloc unique des trois sources, dates contradictoires. | Divergence lisible avant le départ. |
| 59–68 s | **Retrouve la décision. / Avec sa source.** Tes documents et les fils que tu choisis. | Espace de connaissances, documents et sources connectées. | Source et emplacement se lisent dans la vraie UI. |
| 68–79 s | **Parler. Puis retrouver / ce qui compte.** Voix, Live, appels et comptes rendus gardent le fil. | Compte rendu puis débrief d’appel ; réglages vocaux nommés. | Deux détails principaux ; sessions fournisseur non exercées. |
| 79–88 s | **Un dossier confié. / Un résultat suivi.** Le ticket garde échanges, décisions et résultat. | Tableau, détail Atlas, porteur et état, recadrage vers résultat. | Un ticket identifiable, jamais une exécution réelle supposée. |
| 88–98 s | **Du rendez-vous / aux livrables.** Documents, images et schémas à relire et à partager. | Galerie et aperçu du PDF local fictif. | Capacité image et Excalidraw annoncées, sans faux résultat généré. |
| 98–112 s | **Au moment / que tu choisis.** Actions planifiées, conditions et registre gardent le suivi lisible. | Planning, horaire/condition puis registre des actions du dossier. | Trois lectures séparées ; aucun déclenchement backend fabriqué. |
| 112–124 s | **Tes outils. / Votre cercle.** Compétences et assistants connectés à ton choix. | Compétence puis connexion du cercle et deux sens de partage. | Deux moments distincts, détails étendus par les focus. |
| 124–136 s | **Ton instance. / Ses réglages visibles.** Utilisateurs, prix LLM, modèles et santé de la plateforme. | Quatre vues natives : utilisateurs, tarifs, configuration LLM, santé ; données fictives. | Environ trois secondes chacune ; les focus détaillent chaque tableau ou formulaire. |
| 136–146 s | **Avant d’agir, / tu confirmes.** Contenu, destinataire et coût restent visibles. | Retour à l’accord, clic, résultat et coût fictif de recherche. | Contenu avant clic ; coût sans fausse attribution à la confirmation. |
| 146–150 s | **LIA, / à tes côtés.** Une conversation. Des outils. Tes décisions. | Passage vers la vue mobile, BIP et signature. | Pose finale stable ; un seul BIP. |

## La coupe landing de 65 secondes

La coupe courte est définie explicitement par `PRESENTATION_LANDING_CHAPTERS`, plutôt que déduite de tous les chapitres longs. Elle conserve avatars, affichage et rappel. Les parcours Relations/mémoire, voix/appels, cercle/extensions et administration restent disponibles dans le principal et les focus.

| Temps nominal | Sujet | Priorité visuelle |
|---|---|---|
| 0–3 s | Ouverture | BIP et demande |
| 3–8 s | Avatars natifs | Lumo, un changement contextuel puis ensemble |
| 8–12 s | Modes d’affichage | Cartes puis HTML, quatre choix visibles |
| 12–18 s | Briefing/Radio | Un programme, deux détails au maximum |
| 18–22 s | Notification | Un rappel lisible |
| 22–32 s | Conversation | Sources et divergence |
| 32–38 s | Connaissances | Document et source |
| 38–44 s | Tableau | Ticket et résultat |
| 44–50 s | Livrables | Galerie et aperçu |
| 50–56 s | Suivi | Planning puis registre ; conditions détaillées dans les focus |
| 56–61 s | Contrôle | Accord puis résultat |
| 61–65 s | Signature | Fil mobile et BIP |

## Refaire l’extraction des trois lignes

Le produit affiche une liste de définitions `dl.lia-kv`, composée de paires `dt` et `dd`. Dans le film, les trois lignes forment un seul objet. Il faut conserver la grille commune, l’espacement vertical, le fond et le contour du bloc, plutôt que donner trois fonds et trois ombres aux lignes.

Au départ, le bloc extrait se superpose au bloc de la réponse à la même position, dans la même perspective et à la même échelle. Sa copie interne disparaît au moment du départ. Le mouvement agrandit l’ensemble ; une ligne active ou deux dates surlignées orientent la lecture à l’intérieur du bloc. La perspective reste faible quand il faut lire.

Au retour, position, largeur et échelle sont celles du bloc original. Le mouvement se termine avant que la copie interne réapparaisse. Les autres parties de la réponse restent présentes et légèrement en retrait ; elles donnent l’origine et la destination du fragment. Aucun texte ne s’étire et aucun bord de lettre ne touche le masque.

Références de construction : [FaithfulUi.tsx](src/FaithfulUi.tsx), [ProductStory.tsx](src/ProductStory.tsx), [lia-components.css](../../apps/web/src/styles/lia-components.css) et [landing-proof-data.ts](../../apps/web/e2e/capture/landing-proof-data.ts).

## Les focus indépendants

Chaque focus possède `kind`, `variant`, titre, durée, cadrage et effet. Il reprend le même vocabulaire visuel ; son premier plan présente le besoin sans dépendre d’une scène précédente. Une narration est approfondie pendant vingt à vingt-quatre secondes. Les mêmes IDs ne rendent pas un export antérieur compatible ou qualifié V5.

| Focus | Variante | Fonctionnalités dont il porte le détail | Qualification |
|---|---|---|---|
| Conversation | `conversation` | Langage naturel, agents spécialisés, réponses enrichies, pièces jointes, calculs, navigation assistée | Outils selon l’instance ; navigation non exercée. |
| Compagnons | `avatars` | Lumo masculin et autres avatars natifs animés avec plusieurs contextes | Contextes scénarisés ; aucune inférence émotionnelle ou session vocale réelle. Psyche et thèmes gardent leur attribution éditoriale, sans nouveau parcours visuel complet. |
| Mémoire | `memory` | Mémoires, réponses conservées, connaissance des capacités | Préférences éditables ; pas d’apprentissage prétendument exécuté pendant le tournage. |
| Relations | `relations` | Informations centralisées, engagements, souvenirs et sections fournisseurs | Morgan et échanges fictifs ; aucune récupération actuelle de compte. |
| Cercle | `peers` | Relais d’assistants, partages, protection et révocation | Connexions volontaires, même instance, lecture seule choisie. |
| Briefing et Radio | `radio` | Briefing, Radio personnelle | Commandes natives exercées avec silence local ; aucune parole Radio générée. |
| Routines | `routines` | Rappels, calendrier et conditions | Interface et récurrence fictives ; pas de déclenchement fournisseur. |
| Proactivité | `proactive` | Propositions, réactions aux événements, moments de suivi, centres d’intérêt | Activation, sources et plages choisies ; pas de notification réellement déclenchée. |
| Habitudes | `habits` | Observations, progression, pause et évolution | Apprentissage volontaire, désactivé par défaut. |
| Tableau | `workboard` | Tableau de travail, délégation | Colonnes, détail et échanges natifs avec résultats fictifs. |
| Voix | `voice` | Transcription, lecture et Live | Configuration et fournisseurs nécessaires ; aucune session réelle. |
| Téléphone | `phone` | Appels pour toi et appels vers toi | Débrief fictif ; objectif confirmé pour un tiers, numéro vérifié pour toi. |
| Réunions | `meetings` | Réunion, transcription, modèles de compte rendu | Compte rendu fictif ; aucun enregistrement/transcription fournisseur exercé. |
| Connaissances | `knowledge` | Espaces, dossiers Drive et libellés Gmail | Sources et listes natives ; aucune indexation ou recherche fournisseur exécutée. |
| Créations | `creation` | Galerie, documents, images, Excalidraw, partage par e-mail | Document fictif créé localement ; capacités image/schéma annoncées, sans faux résultat. |
| Extensions | `extensions` | Skills, plugins, MCP, MCP Apps, sous-agents | Skills système et interface réelle ; outils, import et délégation externes non exercés. |
| Services | `connectors` | Comptes connectés, recherche, lieux, trajets, météo/air/pollens, Hue | Catalogue et briefing ; aucun compte réel relié ni commande de maison exécutée. |
| Santé | `health` | Pas et fréquence cardiaque par période | Vue descriptive avec données fictives ; les absences de mesures restent visibles. |
| Journaux | `journals` | Observations, sources, confiance et corrections | Journaux fictifs ; aucun travail de consolidation exécuté. |
| Contrôle | `control` | Confirmations, coûts/quotas, données/accès | Résultat fictif ; coût de recherche de démonstration, sans mesure de confirmation ; accès/données qualifiés dans le texte. |
| Mobile et canaux | `mobile` | Fil synchronisé, canaux, apps natives, responsive, langues, réglages | Capture web responsive disponible ; ne pas simuler une application native ou une notification non testée. |
| Administration | `admin` | Utilisateurs et prix LLM dans leurs vues natives | Comptes/prix fictifs, sans modification. Propriétaire DevOps conservé, sans CLI exécuté. |
| Avatar parlant | `simli` | Complément à l’avatar, la voix et le Live | Expérimental, connecteur personnel, crédits possibles pendant le silence, qualification appareils/fournisseur en cours. |
| Affichage | `display` | Cartes, HTML, HTML + cartes, Markdown | Sélecteur natif, sans réponse reformatée ou préférence sauvegardée ; pas de mode bulles inventé. |
| Notifications | `notifications` | Rappel à venir et notification | Fixture native ; aucun push/SSE livré ni faux historique de rappels déclenchés. |
| Planning | `planning` | Actions planifiées, horaires, récurrences et numéros | Aucune action réellement déclenchée ou modifiée. |
| Registre | `registry` | Actions, journal des effets, états et repères | Historique fictif, sans exécution attribuée au film. |
| Configuration LLM | `llm-config` | Usages, modèles et paramètres natifs | Administrateur ; aucun routage ou paramètre sauvegardé. |
| Plateforme | `platform` | Vue native de diagnostics/santé | États fictifs, sans sonde actuelle ou opération DevOps exécutée. |

## Couverture et sources

Le périmètre canonique vient de `REQUIRED_FEATURE_KEYS` dans [chapters-data.ts](../../apps/web/src/components/landing/editorial/chapters-data.ts). Les libellés, variantes et premiers scénarios sont confrontés à [content.ts](src/content.ts), au [README du produit](../../README.md), aux composants cités dans le plan et aux documents techniques des domaines. Le manifeste de tournage est [capture-v2/manifest.json](public/capture-v2/manifest.json) ; ses limites sont précisées dans [provenance.json](public/capture-v2/provenance.json).

Le contrôle du plan V5 conserve 63 clés canoniques. Les vingt-deux propriétaires les répartissent exactement, sans clé manquante, inconnue ou répétée. Simli et six nouveaux focus sont des compléments hors partition. Le principal déclare 48 clés autour de seize scènes. Les sujets supplémentaires sont dans `editorialTopics`, sans ajout au canon. Ces rattachements ne prouvent pas qu’une fonction est montrée, lisible ou exécutée dans le média.

Les quinze clés complémentaires du principal restent attribuées via `FOCUS_FEATURE_OWNERS`. Elles incluent langues, protection du cercle, Psyché, connaissance des capacités, journaux, intérêts, habitudes et leur évolution, rappel téléphonique vers soi, santé, navigation assistée, DevOps CLI, thèmes, environnement et maison Hue. Les quatre vues d’administration sont des sujets supplémentaires concrets, sans prétendre exécuter le CLI.

Les traitements antérieurs restent conservés pour l’historique. [PresentationFilm.tsx](src/PresentationFilm.tsx) sélectionne les vues depuis les contrats de [FeatureScreens.tsx](src/FeatureScreens.tsx). Les changements V5 concernent Lumo et les avatars, affichage, notification, Relations centrales, planning/registre et administration. La preuve de qualification V4 ne leur est pas transférée. Le [rapport de couverture](coverage-v4.md) conserve les écarts entre clés et vues, notamment Excalidraw sans éditeur et DevOps sans CLI exécuté.

Les preuves natives disponibles comprennent notamment :

- Une saisie réelle et le renderer de chat, alimentés par des SSE fictifs ; une confirmation native suivie de son résultat de démonstration, sans envoi d’e-mail.
- Relations, mémoire, espace de connaissances, réunion, tableau, briefing et réglages natifs, avec données contrôlées.
- Une interaction du skill système convertisseur qui calcule réellement une valeur locale ; les outils externes, MCP et sous-agents ne sont pas invoqués.
- Les contrôles Radio avec un fichier silencieux local ; aucune synthèse de voix, session Live ou session Simli.
- Des fichiers de démonstration locaux et leurs métadonnées ; aucune génération d’image fournisseur.
- Une vue web mobile de 390 × 844 ; elle ne prouve pas un parcours sur une application native ou un appareil physique.

Le tournage natif provient d’un build isolé existant. Sa correspondance aux composants du dépôt est documentée ; son SHA de compilation exact n’est pas établi. Les API serveur et requêtes externes ont été bloquées pendant ce tournage. Les adaptations animées sont donc vérifiées contre les composants et les captures, sans faire passer le montage pour un test fournisseur complet.

## Vérification de construction

Le plan est confronté à une seconde source, l’inventaire canonique de la landing. La construction V5 prescrit 150 s / 4 500 images pour le principal et 65 s / 1 950 images pour la landing, à 30 images/s. Le générateur contrôle la partition et conserve les sujets supplémentaires séparément. Les noms, fichiers sources et libellés des nouvelles vues ont été vérifiés dans le dépôt courant.

La revue des quarante-cinq figures correspondant au plan — seize chapitres et vingt-neuf focus — examine lisibilité en diffusion, marges, détourage, BIP unique et continuité des identités. Ce nombre décrit la prescription, pas des contrôles V5 déjà réussis. La lecture continue contrôle les tenues, raccords, cadrages et appuis musicaux ; les nouvelles scènes courtes de landing nécessitent des vues prioritaires, deux détails au maximum. Données fictives, réglages et expérimental gardent leur qualification dans le film et sa fiche de livraison.

La structure de travail est conservée : plan typé, composants natifs adaptés, horloge Remotion, variantes de focus, données fictives et provenance, musique/licence, puis exports séparés. Aucun fichier de l’application, publication, commit ou déploiement n’est requis pour cette écriture du scénario.
