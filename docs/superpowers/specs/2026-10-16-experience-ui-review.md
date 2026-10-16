# Réanalyse de l'expérience et de la cohérence des interfaces

Analyse du 16 octobre 2026, en complément de la [spécification des ajustements](./2026-10-16-ajustements-interfaces-design.md) et de son [plan](../plans/2026-10-16-ajustements-interfaces.md). Ce document conserve le relevé effectué avant développement. L'utilisateur a depuis donné son go pour les demandes et les huit axes complémentaires repris dans le plan ; la dissociation Effacer / Désactiver reste différée. Les constats ci-dessous décrivent l'état observé lors de la préparation.

## Diagnostic

LIA possède déjà les principaux éléments d'un système de présentation : couleurs, champs, boutons, lignes d'actions, barres de commandes, états vides, timelines et conventions d'accessibilité. Le principal axe de progrès est de rendre leur utilisation cohérente d'un écran à l'autre, jusque pendant les enregistrements, les erreurs et les retours de navigation.

La qualité perçue dépend ici de trois choses liées : lire rapidement, savoir où agir et pouvoir se fier au résultat affiché. Réduire les espacements ou raccourcir les textes aide, mais ne suffit pas si un retour de fiche efface la recherche ou si une erreur de chargement ressemble à une liste vide.

L'identité de LIA — compagnon, personnalité, accents et environnement visuel — peut être conservée. Le travail recommandé porte sur la place qu'elle laisse à la tâche en cours, la hiérarchie des informations et la stabilité des interactions.

## Ce qui a été vérifié

- Lecture du checkout courant, y compris les composants partagés et les écrans concernés ; prise en compte des modifications staged déjà présentes.
- Consultation du hub des réglages dans Chrome, en français, sans modifier les contrôles du compte : largeurs de 1440 et 360 pixels CSS. La taille de texte observée est celle du compte consulté ; elle n'a pas été modifiée.
- Mesures DOM des commandes, du champ de recherche et du compagnon ; capture du cas mobile. Le navigateur a ensuite retrouvé sa taille normale et les onglets d'analyse ont été fermés.
- Vérification des références W3C utiles aux cibles tactiles et au contraste. Les mesures de géométrie ne constituent pas une certification d'accessibilité.

Trois niveaux de preuve sont distingués : **observé** dans le navigateur ; **établi dans le code** pour une structure ou une branche de rendu ; **scénario à reproduire** pour un effet d'interaction ou une panne qui n'a pas été déclenchée. Aucun score de qualité global, audit WCAG complet, test applicatif, build, appel de modèle ou déploiement n'a été réalisé.

## Priorités recommandées

P1 signifie « à traiter tôt pour la confiance, l'accès ou la continuité de la tâche », P2 « cohérence et efficacité », P3 « évolution facultative ». Ces priorités UX ne sont pas des niveaux d'incident de production. Petit / moyen qualifie l'étendue relative, pas une estimation horaire.

| Référence | Amélioration | Priorité | Étendue | Lien avec la préparation initiale |
|---|---|---|---|---|
| A01 | Protéger les champs et commandes des flottants sur mobile | P1 | Moyenne, locale | Proposition complémentaire aux contrôles de compagnon existants |
| A02 | Préserver brouillon et dernière valeur réellement enregistrée | P1 | Moyenne | Précise l'avatar ; extension distincte pour les autres préférences et réunions |
| A03 | Garder identité et focus d'une commande pendant l'attente | P1 | Moyenne, partagée | Lot supplémentaire à décider ; ne pas modifier Button globalement au détour d'un renommage |
| A04 | Distinguer erreur, vide confirmé, données anciennes et total inconnu | P1 | Petite à moyenne | Extension ciblée des états de listes |
| A05 | Retrouver recherche, filtres, position et focus après un détail | P1 | Moyenne | Complément fonctionnel Relations/Réglages |
| A06 | Donner un nom de champ aux sélecteurs composés | P1 | Petite | Complément accessible, dont génération d'images |
| A07 | Fiabiliser les replis et la recherche d'aide | P1 | Moyenne | Complète le déplacement demandé dans la FAQ |
| A08 | Adapter les zones fixes aux bandeaux déjà mesurés | P1 | Petite, ciblée | Complément au rail des réglages |
| A09 | Uniformiser les rôles visuels sans multiplier les cadres | P2 | Petite à moyenne | Précision de L0 et des panneaux demandés |
| A10 | Assouplir badges, noms et descriptions avec le grand texte | P2 | Petite à moyenne | Précision de MCP/RAG/Relations |
| A11 | Choisir carte, liste ou timeline selon le contenu | P2 | Petite | Précision des présentations demandées |
| A12 | Rendre les retours de sauvegarde et les erreurs plus sobres et utiles | P2 | Petite à moyenne | Complète l'autosave et les commandes |
| A13 | Clarifier le vocabulaire et les repères de navigation | P2 | Petite | Proposition éditoriale, routes et destinations conservées |
| A14 | Augmenter le confort tactile sans dilater tout le desktop | P2 | Petite | Complément responsive aux contrôles touchés |
| A15 | Harmoniser recherche, périmètres et retour aux pages de liste | P2 | Petite à moyenne | Complément Relations/Réunions |
| A16 | Réduire la concurrence visuelle des aides et de la décoration | P3 | Petite à moyenne | Choix visuel facultatif à montrer avant adoption |

## A01 — Une place sûre pour les éléments flottants

**Observation réelle.** Sur le hub des réglages à 360 × 800, le compagnon sélectionné recouvre une partie du champ de recherche. Le champ mesure environ 313 × 36 ; son intersection avec la boîte du compagnon mesure environ 162 × 36. Le point central de cette intersection est reçu par le groupe du compagnon, et non par le champ. Le débordement horizontal de page est absent : vérifier seulement le scrollWidth n'aurait pas trouvé ce problème.

[Capture de l'observation mobile](../../assets/ui-analysis-2026-10-16/settings-mobile-360.jpg).

Ce résultat concerne la taille, la position et le personnage du compte consulté, après passage desktop → mobile. Il ne prouve pas que toutes les configurations se recouvrent. Le compagnon concerné est EyesWidget/SpiritCompanion ; ce n'est pas la fenêtre vidéo AvatarWindow.

Le code possède déjà un évitement dans [useEyesAvoidance](../../../apps/web/src/components/eyes/useEyesAvoidance.ts), mais [EyesWidget](../../../apps/web/src/components/eyes/EyesWidget.tsx), autour de la ligne 118, ne l'active que pour son placement par défaut sur la surface chat. Ce n'est donc pas une protection générale des formulaires dans le dashboard. Le dock de raccourcis garantit surtout sa présence dans le viewport.

**Recommandation.** Protéger en priorité la recherche, le champ actif, les commandes principales et les commandes d'arrêt. Sur petit écran, proposer une présence compacte lorsque le placement développé ne laisse plus de place sûre. Le déplacement et le déploiement manuel restent possibles. La correction doit rester locale aux propriétaires existants ; inutile de créer un gestionnaire général de toutes les superpositions.

Ne pas écraser durablement une position personnalisée pour résoudre un manque de place temporaire. Prévoir une position d'affichage contrainte ou un repli temporaire, puis restituer le choix quand l'espace revient. Vérifier aussi clavier virtuel, paysage, grand texte, dock déployé et capture/radio actives.

## A02 — Séparer ce qui est choisi, envoyé et confirmé

**Établi dans le code.** Langue et Fuseau modifient leur sélection locale avant le PATCH ; leurs traitements d'erreur ne rétablissent pas cette sélection. Dans [MeetingsSettings](../../../apps/web/src/components/settings/MeetingsSettings.tsx), autour des lignes 139–147, la réponse d'enregistrement vide le brouillon sans comparer sa révision à celle envoyée. Les champs restent éditables pendant cet envoi. Le repli Paramétrages utilise Disclosure, dont la fermeture démonte le formulaire qui possède ce brouillon.

**Scénarios à reproduire.** Un PATCH refusé laisse-t-il le nouveau choix visuellement sélectionné ? Une modification B faite pendant l'envoi de A disparaît-elle à sa réponse ? Fermer puis rouvrir Paramétrages efface-t-il les modifications non envoyées ? Ces mécanismes sont identifiés, sans reproduction de panne dans cette analyse.

**Recommandation.** Deux contrats simples :

- Préférence isolée : sauvegarde automatique, état En cours / Enregistré / Erreur, valeur confirmée distincte du choix souhaité.
- Formulaire cohérent : brouillon explicite, état Modifications non enregistrées, sauvegarde d'un instantané et conservation des éditions postérieures.

La fermeture d'un panneau n'est pas une instruction d'abandon. Porter le brouillon au-dessus du repli si le contenu peut être démonté. Un changement de compte doit isoler toutes ces valeurs. Une écriture confirmée reste réussie même si un refresh secondaire échoue ; une réponse réseau perdue demande une relecture avant de déclarer une annulation.

Appliquer ce contrat à l'avatar déjà demandé ; traiter les autres préférences et le formulaire réunions comme propositions supplémentaires. Ne pas convertir tous les formulaires à l'autosave.

## A03 — Pendant l'attente, la commande doit rester reconnaissable

**Établi dans le code.** [Button](../../../apps/web/src/components/ui/button.tsx), lignes 98–105, impose disabled avec isLoading et remplace les enfants par le spinner et un loadingText facultatif. Sans loadingText, le libellé visible disparaît. [RowActions](../../../apps/web/src/components/ui/row-actions.tsx), SectionToolbar et [Pagination](../../../apps/web/src/components/ui/pagination.tsx) désactivent aussi les commandes en attente. Des écrans récents préservent au contraire leur cible focusable. Les tests actuels de certaines primitives affirment la désactivation : c'est un contrat à faire évoluer, pas un détail CSS à changer sans revue.

**Recommandation.** Conserver le libellé, la largeur et le nom de l'action ; ajouter un petit indicateur d'attente sans remplacer toute son identité. Distinguer une action structurellement impossible d'une action temporairement en cours. Lorsque le contrôle garde le focus, utiliser une indisponibilité annoncée et une garde synchrone du handler contre les doubles soumissions, ou définir explicitement son prochain point de focus.

Le choix devra couvrir les boutons natifs et les composants rendus avec asChild ; un simple remplacement automatique de disabled par aria-disabled serait incomplet. Les contrôles Arrêter/Annuler d'un média ou traitement doivent garder leur rôle propre. Le déplacement effectif du focus reste à vérifier au navigateur.

## A04 — Un échec ne doit pas ressembler à une absence de données

**Établi dans le code.** [usePlugins](../../../apps/web/src/hooks/usePlugins.ts) expose error/refetch mais fournit aussi une liste vide si la donnée n'existe pas. [PluginsSettings](../../../apps/web/src/components/settings/PluginsSettings.tsx), autour de la ligne 311, ne consomme pas cette erreur et peut afficher « Aucun plugin installé » après un échec initial. Skills et OpenLoops possèdent déjà des retours d'erreur et une nouvelle tentative.

Le hub Alertes a une autre nuance : [useHubCounts](../../../apps/web/src/hooks/useHubCounts.ts) ne publie pas l'état d'erreur de ses compteurs ; « — » ne distingue pas chargement et décompte indisponible. Ce n'est pas un zéro.

**Recommandation.** Même lecture partout : premier chargement ; données ; vide après succès ; aucun résultat de filtre ; erreur initiale ; actualisation échouée avec données antérieures conservées. Une liste connue ne disparaît pas pendant son actualisation. Une erreur initiale propose Réessayer ; une erreur de refresh précise que les données visibles n'ont pas été actualisées.

Préserver les compteurs propres à chaque famille. Un historique reçu, des décisions en attente et des actions futures ne deviennent pas un seul compteur de non-lus. Ne pas ajouter de requête de total pour afficher un badge décoratif.

## A05 — Le retour doit retrouver la tâche commencée

**Établi dans le code.** La page Relations remplace la liste par le détail ; [RelationCardList](../../../apps/web/src/components/relations/RelationCardList.tsx), vers la ligne 334, possède les états de recherche/tri/filtres du composant démonté. Le retour recrée ces états. Dans [la page des réglages](../../../apps/web/src/app/[lng]/dashboard/settings/page.tsx), ouvrir et fermer une section scrolle à zéro ; la restauration de l'élément choisi dans le rail n'est pas prévue.

**Recommandation.** Pour Relations, garder recherche, tri et filtres dans le propriétaire de page, avec la carte et la position de départ. Au retour, retrouver cette carte, ou une voisine logique si elle n'existe plus. Pour les réglages mobile, retrouver le bouton et la position du rail ; à l'ouverture, donner le focus au titre du panneau puisque la liste d'origine devient cachée. Le desktop conserve son comportement qui laisse le focus dans le rail lorsque c'est pertinent.

Pas de stockage durable des noms recherchés ni de changement de deep link requis. Le bénéfice est direct : consulter plusieurs fiches ou régler plusieurs sections sans recommencer le même trajet.

## A06 — Un champ se nomme par sa question

**Établi dans le code.** Qualité, Taille et Format de [ImageGenerationSettings](../../../apps/web/src/components/settings/ImageGenerationSettings.tsx) sont des paragraphes voisins de leurs SelectTrigger, sans liaison explicite. Un contrôle qui annonce seulement sa valeur ne dit pas nécessairement quelle question il pose. Input/FieldFrame possède déjà un contrat de label, erreur et description.

**Recommandation.** Relier les sélecteurs à leur label et à leur aide ; vérifier leurs noms par rôle dans au moins FR/EN. Réutiliser les primitives de champ existantes sans imposer un wrapper inadapté à Radix. Généraliser l'oracle de nom accessible aux Switch et Select composés lors des modifications d'écran.

## A07 — La FAQ doit aider avant de présenter le produit

Le réordonnancement demandé — Historique puis Comment fonctionne LIA — reste prévu. La recherche et les catégories répondant à une question concrète doivent rester faciles à atteindre avant ces contenus éditoriaux.

**Établi dans le code.** Les boutons de repli de ces deux blocs dans [FAQContent](../../../apps/web/src/components/faq/FAQContent.tsx), vers 420 et 492, n'exposent pas aria-expanded/aria-controls. Les résultats utilisent un defaultValue d'accordéon dérivé de la recherche ; un defaultValue ne constitue pas une synchronisation des ouvertures à chaque nouvelle requête. Le cas où une réponse trouvée reste repliée est à reproduire.

**Recommandation.** Donner aux deux boutons leur état accessible. Piloter les ouvertures pendant la recherche et annoncer le nombre de réponses trouvées ; restituer l'état de lecture hors recherche. Tester deux recherches successives dans une même catégorie puis effacement. Ne pas forcer l'ouverture permanente de toute l'aide.

## A08 — Les zones fixes doivent partager les mêmes mesures

**Établi dans le code.** Le rail des réglages utilise top-20 et une hauteur disponible fixe. Le recorder publie déjà --meeting-banner-h ; la radio publie --radio-banner-h et se place sous le recorder. Ces valeurs ne sont pas reprises par le rail.

**Recommandation.** Utiliser ces mesures existantes pour son décalage et sa hauteur disponible, avec valeur nulle en l'absence de bandeau. Rejouer scroll + recherche ouverte + capture/radio, zoom et paysage. Le recouvrement effectif n'a pas été déclenché pendant cette analyse, qui n'a démarré aucun enregistrement ou lecteur.

Sources : [page Réglages](../../../apps/web/src/app/[lng]/dashboard/settings/page.tsx), [MeetingRecorderProvider](../../../apps/web/src/components/meetings/MeetingRecorderProvider.tsx), [RadioBanner](../../../apps/web/src/components/radio/RadioBanner.tsx).

## A09 — Une grammaire visuelle commune, avec peu de niveaux

La règle demandée de fonds alternés est conservée. Elle s'applique aux panneaux réellement peints ; une coque transparente, une rangée flex et chaque champ n'ont pas à recevoir une boîte supplémentaire. Un cadre principal peut contenir des lignes séparées sans encadrer chaque ligne.

Le chrome utilise --color-* et les cartes de réponse V3 --lia-* ; ces deux couches ont leurs propres réglages OLED. L'Accueil possède aussi sa matière de carte sombre approuvée. Ne pas fusionner ces palettes pour régler une incohérence locale. Le décor AppCosmos actuel est volontaire et distinct de ces matières opaques.

Proposition de rôles : titre de page ; titre de panneau ; sous-titre de groupe ; texte courant ; métadonnée. Les noms de tokens ne suffisent pas à les identifier : text-base et --lia-text-base n'ont pas la même taille de référence. SectionHeader impose text-lg hors H1 : l'utiliser partout ferait notamment dépasser les 16 px demandés pour les titres Psyché.

Pour les objets comparables MCP/RAG/galerie/Relations, aligner progressivement les rayons sur le token de carte existant ; les champs et petites lignes gardent une géométrie plus serrée. Préserver l'espacement nécessaire aux cibles et aux erreurs avant de chercher à gagner quelques pixels.

Sources : [globals.css](../../../apps/web/src/styles/globals.css), [lia-components.css](../../../apps/web/src/styles/lia-components.css), [SectionHeader](../../../apps/web/src/components/ui/section-header.tsx), [Card](../../../apps/web/src/components/ui/card.tsx).

## A10 — Texte long : nom lisible, état court, détail développable

Les noms identifient des personnes, fichiers ou serveurs ; une troncature à une seule ligne peut les rendre indiscernables sur téléphone. Un attribut title ne fournit pas à lui seul une consultation tactile fiable. Les descriptions MCP possèdent déjà une détection de débordement utile à RAG.

**Recommandation.** Deux lignes possibles pour l'identité ; états courts ; description bornée avec Voir plus seulement si nécessaire. Les [badges](../../../apps/web/src/components/ui/badge.tsx) gardent actuellement une hauteur fixe tandis que la taille du texte varie : vérifier leurs libellés sur plusieurs lignes et permettre une hauteur naturelle là où ils se replient. Un objectif ou une phrase n'est pas un badge de statut.

État, compteur et action restent visuellement distincts. Un badge informatif n'a pas besoin d'un hover évoquant un bouton. Les couleurs suivent le statut réel, y compris inconnu et désactivé ; ne pas fabriquer un vert de succès à partir d'un simple total.

## A11 — Trois formats de lecture suffisent

| Contenu | Forme recommandée | Point à préserver |
|---|---|---|
| Objet identifiable et manipulable : serveur, espace, fichier, relation | Carte | Identité d'abord ; état lisible ; commandes regroupées |
| Données d'un même objet : contact, options, faits secondaires | Lignes ou groupes simples | Alignement label/valeur ; pas de carte par information |
| Événements successifs : appels, notifications, réunions passées | Liste chronologique / timeline | Date, état, contenu et actions dans un ordre stable |

Aligner le bas des cartes MCP/RAG par rangée, sans imposer une grande hauteur minimale à toutes les cartes. Le développement d'une description peut agrandir sa rangée. Les appels Relations gardent leur DTO plus court ; même langage visuel ne signifie pas mêmes champs inventés.

La timeline Heartbeat demandée affiche aussi le texte intégral. C'est un gain de lisibilité, avec une incidence possible sur la hauteur : conserver les bornes de lecture et la pagination, plutôt que couper arbitrairement le contenu.

## A12 — Moins de toasts, un résultat plus clair

**Établi dans le code.** Langue et Fuseau émettent chacun plusieurs notifications après un changement ; le Toaster peut développer plusieurs messages simultanés. Certaines erreurs de préférence ne donnent qu'un message générique. Les confirmations de suppression existent déjà, mais leur fermeture peut précéder l'appel qui échoue ensuite.

**Recommandation.** Préférence simple : état discret à proximité ; commande explicite ou import : retour de résultat ; erreur bloquante : message local persistant et possibilité de reprise. Une information durable appartient à une aide de champ plutôt qu'à un second toast. Ne pas annoncer deux fois le même événement par toast et live region.

Après une confirmation, garder un résultat retrouvable : le périmètre, l'opération en cours puis son succès ou son échec. Un traitement court peut finir dans le dialogue ; un traitement plus long peut continuer dans la liste avec retour persistant. Ne pas ajouter une deuxième confirmation, ni prétendre que le clic de confirmation vaut exécution réussie.

Sources : [LanguageSettings](../../../apps/web/src/components/settings/LanguageSettings.tsx), [TimezoneSelector](../../../apps/web/src/components/settings/TimezoneSelector.tsx), [Toaster](../../../apps/web/src/components/ui/toaster.tsx), [useConfirm](../../../apps/web/src/components/ui/use-confirm.tsx).

## A13 — Un vocabulaire stable et des destinations reconnaissables

La navigation française affiche Réglages tandis que le titre de page est Paramètres ; Alertes mène à un titre Notifications. Ces mots ne bloquent pas la compréhension, mais ajoutent un effort inutile d'association.

**Proposition éditoriale.** Réglages pour la destination et son H1 ; Alertes pour le hub ; Notifications push pour le mécanisme de réception sur l'appareil. Conserver les distinctions utiles entre Mode vocal, Live, Style de LIA et Avatar parlant. Leurs descriptions doivent expliquer leur fonction respective avant d'exposer des détails techniques. Les noms internes et les routes ne changent pas.

Entre les largeurs desktop compactes, les destinations sont des icônes seules. Sur mobile, le menu est visuellement identifié par LIA ; son nom accessible dit déjà Menu. Ajouter un indice de menu visible au logo et identifier la destination courante lorsque les libellés sont masqués est une amélioration bornée. Ne pas ajouter un second système de navigation ou une barre persistante supplémentaire.

## A14 — Une densité adaptée au moyen de pointage

**Mesuré dans la configuration consultée.** À 1440 px, les premières lignes du rail mesurent 32 px de haut. À 360 px, elles restent à 32 px ; les commandes visibles de l'en-tête ont une boîte d'environ 36 × 44. La page ne déborde pas horizontalement. Ce constat n'établit pas à lui seul une non-conformité.

**Recommandation produit.** Conserver la densité desktop ; viser une zone d'activation confortable autour des commandes importantes sur tactile, et environ 44 px de hauteur pour les lignes de navigation mobile. Agrandir la zone des petites croix sans grossir nécessairement le pictogramme. Autoriser le nom du réglage à tenir sur deux lignes.

Précision normative : le minimum WCAG 2.2 AA est de 24 × 24 pixels CSS, avec exceptions et règles d'espacement ; 44 × 44 correspond au critère renforcé AAA. Ici, 44 est un objectif de confort proposé, pas une obligation AA attribuée à tort. Sources : [W3C — Target size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [W3C — Target size enhanced](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html).

De même, séparation subtile entre fonds et contraste du texte sont deux questions différentes. Tester le texte sur le fond réellement composé, avec transparences et états. Le [critère de contraste du texte](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) ne fixe pas une obligation générale de fort contraste entre deux panneaux neutres décoratifs.

## A15 — Une recherche et un historique de navigation prévisibles

Relations recherche actuellement avec lowercase/includes, alors que Réglages et FAQ normalisent déjà accents et apostrophes. Son filtre porte sur le jeu reçu, pas sur une recherche serveur de toutes les relations ; la limite n'est expliquée qu'en bas. Une liste filtrée vide n'offre pas de retour direct au jeu complet.

**Recommandation.** Réutiliser la normalisation existante, proposer Effacer les filtres, conserver le champ visible tant qu'un filtre est actif et rapprocher la mention « dans les fiches chargées ». Séparer total serveur, éléments chargés et résultats du filtre.

Réunions conserve l'origine du retour mais pas un contrat explicite de page consultée. Vérifier le trajet page suivante → détail → retour, puis conserver une page validée si nécessaire, en réutilisant le clamp existant après suppression. Ne pas restaurer silencieusement une sélection de suppression multiple.

Pour les dates et montants, réutiliser les formateurs existants ; relever séparément les affichages qui s'appuient encore sur la langue implicite du navigateur, comme la date de dernière position. Le fuseau d'une occurrence et celui d'un instant de suivi ne sont pas interchangeables. Une correction de fuseau ou de devise ne doit pas se glisser dans un changement de mise en forme.

## A16 — Conserver la présence de LIA avec des zones de lecture calmes

AppCosmos et le compagnon sont des choix visuels actuels à préserver. Leur présence ne doit pas rendre la lecture ou l'identification des commandes plus difficile. La capture mobile montre aussi pourquoi une grille d'évaluation doit porter sur la page entière, avec ses flottants, et non sur la carte de réglage isolée.

**Proposition facultative.** Garder les matières de contenu opaques ; laisser le décor autour. Comparer, sur le même écran, l'existant et une intensité décorative plus discrète dans les zones de consultation longue. Réutiliser reduced motion et les mécanismes d'animation existants. Ne pas ajouter un nouveau mode de thème ou une préférence d'animation sans bénéfice observé.

Pour l'aide, conserver une phrase utile près d'un choix complexe et déplacer les explications longues dans leurs groupes pertinents. Les limites, prix et conséquences d'une suppression doivent rester visibles au moment de décider. La simplification n'est pas un motif pour les retirer.

## Ordre de travail à proposer lorsque le développement sera autorisé

1. Vérifier les scénarios de perte de brouillon, faux vide et réponses tardives ; prendre les garanties existantes comme référence.
2. Corriger l'accès aux commandes : collision mobile démontrée, noms des champs, retours de focus et zones fixes.
3. Réaliser la règle des surfaces et les ajustements déjà demandés, écran par écran.
4. Étendre les conventions de retours d'état et de navigation retenues, dans des lots explicitement choisis.
5. Montrer les choix purement visuels facultatifs avant de les adopter.

Les consommateurs des primitives sont inventoriés avant une évolution partagée. Les tests de comportement suivent les risques : échec initial puis reprise, A envoyé/B édité, repli avec brouillon, retour liste/détail, compte changé, nom par rôle, double activation, petit écran/zoom/texte long. Le scénario de collision dispose déjà d'une preuve ; les autres effets dynamiques seront qualifiés hermétiquement dans Docker dev, pas en provoquant des mutations sur l'instance consultée.

## Périmètre documentaire

Cette réanalyse affine la règle des surfaces et la grille de qualité, mais ne change pas les décisions confirmées : titre Taille de police conservé, valeur px/% masquée ; PDF en vraie page 1, autres formats en extraits identifiés ; retrait ciblé des blocs demandés ; aucun nouveau moteur Office ou compteur d'usage MCP inventé. Les nouvelles propositions Axx ne sont pas encore des développements autorisés.
