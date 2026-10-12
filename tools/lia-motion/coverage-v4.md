# LIA V5 — périmètre éditorial et limites visuelles

Révision des sources du 12 octobre 2026. Le nom de ce fichier est conservé pour la compatibilité des commandes et archives ; son contenu décrit V5. Ce rapport distingue l’attribution d’une fonctionnalité, la vue retenue, les données de démonstration et l’exécution réelle. Il ne mesure pas les médias encodés.

La livraison V4 antérieure comprenait un film de 120 secondes, une coupe de 65 secondes et 23 focus. Sa qualification technique locale a réussi avant cette révision. Ses rapports et sa revue appartiennent à cette construction : ils ne qualifient pas les nouveaux écrans, la piste ou les exports V5.

## Les autorités

- [chapters-data.ts](../../apps/web/src/components/landing/editorial/chapters-data.ts), `REQUIRED_FEATURE_KEYS` : inventaire canonique du produit.
- [presentation-plan.ts](src/presentation-plan.ts) : révision, chapitres, coupe landing explicite, focus, clés, sujets complémentaires et propriétaires éditoriaux.
- [Root.tsx](src/Root.tsx) et [PresentationFilm.tsx](src/PresentationFilm.tsx) : compositions actives et choix des détails effectivement montés.
- [FeatureScreens.tsx](src/FeatureScreens.tsx), `FEATURE_SCREEN_METADATA` : composant source de chaque interface reconstituée, capture de référence, famille fonctionnelle et limites.
- [manifest.json](public/capture-v2/manifest.json), [provenance.json](public/capture-v2/provenance.json) et [mobile.provenance.json](public/capture-v4/mobile.provenance.json) : origine des captures natives.

Une métadonnée d’écran ne signifie pas que la vue est montée dans un film. Une clé dans le plan ne signifie pas que le texte associé est lisible dans le rendu. Ces deux vérifications relèvent des images et du visionnage à effectuer ensuite.

## Ce qui est construit

Le plan principal comporte seize chapitres et dure 150 secondes ; la coupe landing comporte douze chapitres et dure 65 secondes. Le plan comprend vingt-neuf focus. Les frontières proches des pulsations peuvent déplacer une coupe de 0,45 seconde au maximum, sans changer la durée totale. La landing inclut désormais avatars, modes d’affichage et notification ; mémoire/Relations, voix/appels, cercle et administration sont développés dans le principal et les focus.

L’inventaire canonique conserve 63 clés. Les vingt-deux focus propriétaires les attribuent une fois chacune, sans omission ou doublon. Le principal annonce 48 clés ; quinze restent complémentaires. Sept focus non propriétaires — Simli et six nouveaux traitements — développent des sujets existants ou supplémentaires, sans ajouter de clé au canon. `editorialTopics` distingue modes d’affichage, notifications, planning, registre et vues d’administration de `features`.

**63 clés attribuées, 48 annoncées au principal et 29 focus ne signifient pas 63 fonctionnalités individuellement démontrées ou 29 clips validés.** Les quarante-cinq figures correspondant au plan — seize chapitres et vingt-neuf focus — servent à examiner la construction, sans certifier d’exécution fournisseur.

## Nature des vues

Les écrans desktop du film sont des reconstructions animables de l’UX/UI existante : composants, libellés, styles et captures ont servi de référence. Ce ne sont pas des sessions interactives de l’application dans le rendu Remotion. Les données sont fictives et les contrôles n’écrivent pas de préférence ou de compte.

Les catégories du code sont à lire ainsi :

| Métadonnée | Ce qu’elle documente | Ce qu’elle ne certifie pas |
|---|---|---|
| `native-demo-ui` | Interface existante, avec référence de tournage native et données contrôlées | Exécution réelle pendant le montage, résultat fournisseur ou compte privé |
| `source-ui-demo` | Vue reconstituée depuis le JSX, les styles et des fixtures existantes | Correspondance pixel vérifiée par une capture spécifique ou fonctionnement fournisseur |
| `configuration` | Champs et options du réglage natif | Connexion effective, sauvegarde, invocation ou session |

La vue mobile finale est une capture native de 390 × 844. BIP y est masqué par la préférence de visibilité réelle ; aucun pixel n’a été retouché. Elle prouve la disposition web responsive enregistrée avec des SSE fictifs. Elle ne montre pas une application Android/iOS sur appareil physique, une livraison push ou une synchronisation entre deux clients.

BIP reste le guide extérieur à l’écran. Lumo est le personnage masculin natif `lumen`, distinct d’« Esprit de LIA » (`spirit`). Les avatars utilisent les fonctions natives de visage avec des changements de contexte scénarisés. Cela ne certifie ni inférence émotionnelle en direct ni parole fournisseur jouée par un visage.

Les nouvelles vues d’affichage, notification, Relations centralisées, planning, registre et administration viennent du code courant, avec fixtures explicites. Elles ne disposent pas, du seul fait de cette révision, d’une nouvelle capture runtime ou d’une mesure de plateforme. Le centre des notifications distingue les rappels à venir de leur déclenchement : le produit supprime un rappel lorsqu’il se déclenche ; le film ne crée pas un historique natif de rappels livrés qui n’existe pas.

## La partition éditoriale complète

Les propriétaires initiaux sont conservés. Les vues mentionnées décrivent la sélection du plan et les contrats de montage ; le rendu et sa revue doivent confirmer leur présence effective. « Annoncé » désigne une famille dans le texte ou son rattachement éditorial, sans parcours visuel complet.

| Focus propriétaire | Clés attribuées | Vue sélectionnée et portée actuelle |
|---|---|---|
| `focus-conversation` | `natural_language`, `multi_agent`, `rich_responses`, `attachments`, `computed_answers`, `browser_control` | Conversation V3, sources et divergence de dates. La navigation pilotée, une exécution multi-agent et un calcul réel ne sont pas montrés ; leurs clés restent un rattachement éditorial. |
| `focus-avatars` | `personalities`, `psyche`, `mood_face`, `themes` | Lumo masculin et autres avatars natifs animés avec contextes scénarisés. La Psyché appartient à la vue du focus mémoire ; aucun changement de thème ou inférence émotionnelle réelle démontré. |
| `focus-memory` | `memory`, `bookmarks`, `self_knowledge` | Liste de mémoires et Psyché reconstituées. Ni la galerie des réponses conservées ni une interrogation de ses capacités ne sont montrées comme parcours distinct. |
| `focus-relations` | `personal_crm` | Fiche de Morgan centralisant identité, coordonnées, contexte, engagements et sections des fournisseurs présents dans l’UI. Échanges, e-mails, appels et rendez-vous sont des fixtures, sans récupération actuelle de comptes. |
| `focus-peers` | `peers`, `peer_shares`, `peer_safety` | Connexion fictive et deux sens de partage. Aucun relais entre deux comptes ou droit effectivement accordé/révoqué. |
| `focus-radio` | `briefing`, `personal_radio` | Briefing puis programme Radio, transcription et sources. La capture native antérieure a exercé lecture/pause avec un WAV silencieux ; aucune émission vocale réellement produite pour le film. |
| `focus-routines` | `reminders_scheduling`, `conditional_routines` | Action planifiée et formulaire de condition fictive. Aucun run automatique exécuté. |
| `focus-proactive` | `proactive`, `proactive_wake`, `proactive_moments`, `interests` | Plage/sources du heartbeat et condition. Pas de notification ou réveil réellement déclenché ; les intérêts sont une source nommée, sans cycle d’apprentissage montré. |
| `focus-habits` | `habits`, `habits_lifecycle` | Habitudes et contrôles reconstitués avec données fictives. Apprentissage volontaire, désactivé par défaut ; pas de promotion ou pause persistée pendant le film. |
| `focus-workboard` | `workboard`, `workboard_delegation` | Tableau et détail du ticket attribué à LIA ; échanges, dernière exécution et coûts fictifs. Aucun ticket réellement traité. |
| `focus-voice` | `voice_mode`, `live_voice` | Réglages vocal et Live. Aucun microphone, audio synthétisé, WebRTC ou session fournisseur. |
| `focus-phone` | `telephony`, `telephony_callback` | Historique et débrief d’appel fictifs. L’identité et le rappel vers ton numéro sont annoncés/qualifiés ; aucune vérification ou numérotation réelle. |
| `focus-meetings` | `meetings`, `meeting_templates` | Compte rendu prêt et transcription fictive. Pas d’enregistrement, transcription fournisseur ou reformatage réel dans le film. |
| `focus-knowledge` | `rag_spaces`, `mail_label_spaces` | Espace Atlas, sources Drive/Gmail et zone d’import. Aucune indexation, synchronisation ou recherche fournisseur exécutée. |
| `focus-creation` | `generated_files`, `document_generation`, `image_generation`, `excalidraw`, `email_share` | Galerie avec PDF de fixtures et réglages image. Excalidraw reste annoncé : aucun schéma ou éditeur montré. Aucun fichier produit par LIA, image générée ou partage e-mail réellement effectué. |
| `focus-extensions` | `skills`, `plugins`, `mcp`, `mcp_apps`, `sub_agents` | Galerie Skills, import de plugin et configuration MCP. Pas de mini-app externe active ou recherche déléguée. Une vue de capacité sous-agents existe dans `FeatureScreens.tsx` ; elle n’est pas sélectionnée par ce focus courant. |
| `focus-connected-services` | `connected_services`, `web_intelligence`, `environment`, `smart_home` | Catalogue de connecteurs. Pas d’OAuth, recherche/itinéraire exécuté ou commande Hue ; météo/air/pollens sont rattachés au scénario, sans parcours complet de chaque donnée. |
| `focus-health` | `health_metrics` | Mesures et courbes fictives par période, avec absences de données conservées. Vue descriptive ; aucune mesure privée reçue ou analyse médicale produite. |
| `focus-journals` | `journals` | Observation de journal fictive, source/confiance et contrôles. Pas de génération ou consolidation exécutée. |
| `focus-control` | `control`, `usage_limits`, `privacy` | Carte d’accord, résultat fictif, coût de recherche de démonstration et plafonds de l’instance. Les accès/données sont qualifiés dans le texte ; export/effacement non exercés. |
| `focus-mobile` | `chat_sync`, `multichannel`, `native_apps`, `responsive`, `languages`, `simplicity` | Capture web mobile native et préférences. Aucun parcours d’app native, Telegram, push, traduction complète ou synchronisation entre clients. |
| `focus-admin` | `devops_cli` | Utilisateurs et catalogue des prix LLM dans leurs vues administrateur natives, remplaçant les seuls quotas de V4. Le propriétaire éditorial DevOps est conservé, sans console CLI, commande ou diagnostic réellement exécuté. |

Le complément `focus-speaking-avatar` présente les réglages Simli expérimentaux, déconnectés. Il reprend la famille avatar/voix/Live sans être propriétaire d’une clé. Aucun visage Simli animé ou flux fournisseur n’est montré. Connecteur personnel, crédits possibles pendant le silence et qualification fournisseur/appareils restent explicitement mentionnés.

## Les sept traitements complémentaires

Ces lignes ne deviennent pas des propriétaires supplémentaires. Les sujets sans clé canonique restent dans `editorialTopics`, séparément des clés ci-dessous.

| Focus complémentaire | Clés rattachées, sans propriété | Vue et qualification |
|---|---|---|
| `focus-speaking-avatar` | `mood_face`, `voice_mode`, `live_voice` | Réglages Simli expérimentaux déconnectés. Aucun visage parlant ou flux fournisseur ; connexion et crédits personnels. |
| `focus-display` | `rich_responses`, `simplicity` | Quatre modes réels : cards, html, html_cards et markdown. Sélecteur natif et description active, sans préférence sauvegardée ou réponse réellement reformatée. Aucun mode bulles inventé. |
| `focus-notifications` | `reminders_scheduling` | Rappel à venir et notification scénarisée selon les composants natifs. Aucun SSE, push ou rappel réellement livré ; pas de faux historique natif. |
| `focus-planning` | `reminders_scheduling` | Timeline des actions planifiées, horaires, récurrences et numéros de routine. Fixtures, sans déclenchement ou modification persistée. |
| `focus-registry` | `control`, `usage_limits` | Registre des actions et journal des effets, route actions, états et repères fictifs. Aucun historique réel d’exécution attribué au tournage. |
| `focus-llm-config` | — | Configuration LLM par usage et paramètres natifs, réservée à l’administration. Aucun modèle, routage ou paramètre sauvegardé ; aucun fournisseur invoqué. |
| `focus-platform` | — | Vue native de diagnostics/santé de plateforme avec états fictifs. Aucune sonde, mesure actuelle ou opération DevOps exécutée. |

## Les limites à garder dans la fiche de livraison

Les interfaces d’image, Live, voix, MCP, plugin et connecteurs montrent des réglages. Le montage ne doit pas transformer une commande de réglage en preuve de service connecté. Une génération ou un appel fictif ne devient pas réel parce qu’un contrôle ou un statut porte son nom.

Utilisateurs, prix, routages LLM et états de santé sont des fixtures de montage, jamais les valeurs actuelles d’une instance. Le catalogue de prix montré ne constitue pas une mesure de facturation fournisseur.

La bande musicale fait exception au périmètre des interfaces fictives : trois prises sur mesure ont réellement été créées avec Google Lyria 3.5, chacune sur correction explicitement demandée par l’utilisateur, sans retry automatique. La prise active est « LIA — ElectroFunk » ; sa [provenance](public/audio/v5/lia-electrofunk-generation.json) conserve le MP3 source et les empreintes du travail. Les deux prises antérieures et leurs records restent historiques. Le tarif publié est 0,08 USD par prise, soit 0,24 USD au total ; aucune facture n’est déclarée vérifiée. Cette création sonore ne certifie aucune exécution fournisseur d’une fonctionnalité LIA dans les écrans. Les conditions Gemini API s’appliquent, sans CC BY ni exclusivité revendiquée.

L’audit optionnel d’instrumentation a soumis une demande, reçue en HTTP 400, sans retry et sans conclusion exploitable. Les instruments exclus dans le prompt ne sont donc pas déclarés absents sur la foi de cet audit. Aucun nouvel appel d’audit n’est effectué par les contrôles documentaires.

Les PDF `synthese-atlas-demo.pdf` et `compte-rendu-demo.pdf` ont été créés localement avec ReportLab pour les fixtures de tournage. Leur présence dans la galerie n’est pas une génération LIA ou fournisseur. Aucun résultat d’image ou schéma inventé n’a été ajouté pour masquer cette limite.

Le coût `0,001800 €` repris près du résultat appartient à la réponse de recherche de démonstration, avec ses IN/OUT/CACHE/consultation fictifs. Ce n’est pas le prix mesuré d’une confirmation, d’un envoi ou d’une requête actuelle. La vue de plafonds utilise également des chiffres fictifs.

Excalidraw et DevOps CLI gardent un propriétaire éditorial. Une configuration MCP de diagrammes ne montre pas Excalidraw ; la vue native de diagnostics plateforme ne devient pas une exécution DevOps CLI. Aucune commande ou sonde réelle n’est attribuée au montage.

La capture native de référence provient d’un build isolé existant. Sa correspondance aux composants du dépôt est documentée ; son SHA de compilation exact n’est pas établi. Les API et fournisseurs ont été bloqués. La reconstitution actuelle est confrontée au code courant, puis devra être examinée sur les figures et la lecture continue.

## Statut de qualification

Le générateur [presentation-report.mjs](scripts/presentation-report.mjs), appelé par `motion:check`, conserve les noms compatibles `presentation-coverage.json` et `screenplay-v4.json`. La génération du contenu vient de `PRESENTATION_REVISION`. Il contrôle le canon et ce tableau, calcule les durées depuis le plan et conserve qualifications et empreintes des sources, CSS, captures, ressources natives et musique. Il n’impose pas un nombre constant de focus et ne calcule pas un nombre de fonctionnalités visuellement validées.

Le scénario JSON fournit les coupes à 30 et 25 images/s depuis les pulsations mesurées. Les timings du principal à 25 images/s correspondent à la composition de master ; les tables à 25 images/s de la landing et des focus sont des aides de montage dérivées, sans composition ou clip déclaré rendu. Le générateur ne lance ni navigateur, ni encodage, ni mesure de média, ni fournisseur.

La qualification V4 reste une preuve historique. Une livraison V5 doit porter cette génération et correspondre aux nouveaux octets empaquetés. Aucun succès d’encodage, niveau sonore, poster final, lecture complète ou validation esthétique V5 n’est déduit du présent rapport de sources.

Après génération, `verify-delivery.mjs` doit mesurer les fichiers réellement empaquetés : schémas natifs de manifeste/beat, empreintes, dimensions, codecs, durées et son encodé. La revue des figures et la lecture continue contrôlent BIP unique, textes, tenues, projections, raccords et qualifications. L’écoute humaine complète et l’acceptation du diffuseur restent distinctes.

Les sources, ressources, licences, rapports et exports réellement livrés doivent rester associés à leur version. Le détail des commandes de reconstruction et de packaging est dans le [README](README.md).
