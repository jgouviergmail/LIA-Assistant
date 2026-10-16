# Ajustements des interfaces — spécification pour validation

Statut : spécification approuvée ; exécution autorisée le 16 octobre 2026. Le relevé initial repose sur le checkout et une consultation sans mutation des réglages Apparence, Taille de police, Localisation et Mes raccourcis sur l'instance indiquée. Ce relevé initial n'est pas une qualification de toutes les pages déployées. Le [plan](../plans/2026-10-16-ajustements-interfaces.md) porte le périmètre d'exécution et les vérifications.

## Intention et décisions

Rendre l'application plus cohérente, compacte et lisible : alternance des fonds entre panneaux imbriqués, commandes courtes, blocs explicatifs à leur place, réemploi des présentations existantes. Chaque ligne de la matrice ci-dessous correspond à une demande utilisateur.

Deux précisions ont été confirmées par l'utilisateur pendant la préparation :

- Taille de police : conserver le titre ; masquer la valeur visible « 16 px (100 %) », le badge « Par défaut » et la note indiquée. Le curseur garde sa valeur accessible.
- Documents : vraie première page pour les PDF ; extrait explicitement identifié pour les autres formats pris en charge. Aucun moteur de conversion Office supplémentaire.

Les retraits « Comptes rendus », « Modèles » et « Réglages avancés » visent leurs blocs/raccourcis sur les pages désignées. Les écrans, modèles et paramètres correspondants restent accessibles par leur navigation habituelle. Les retraits « Pourquoi LIA pense cela ? » portent sur le bloc de provenance, pas sur les autres explications ni sur les fonctions d'édition.

Cette spécification complète la [préparation UI du 13 octobre](../plans/2026-10-13-integration-ui-utilisateur-design.md). Lorsqu'elle décrit un nouveau comportement, elle prévaut pour ce périmètre. Les anciens plans ne prouvent pas ce qui est installé : plusieurs de leurs composants existent déjà dans le code courant.

La [réanalyse transversale de l'expérience](./2026-10-16-experience-ui-review.md) ajoute des constats et recommandations sur la fiabilité, la navigation et la cohérence visuelle. L'utilisateur a accepté les compléments repris dans l'autorisation du plan ; la dissociation Effacer / Désactiver la position mémorisée reste différée.

## Règle des surfaces

La règle demandée concerne les panneaux neutres qui structurent un contenu, pas chaque div de mise en page :

| Niveau visuel | Fond | Exemple |
|---|---|---|
| Panneau principal | Le plus clair des deux fonds | Section de réglages |
| Sous-panneau | Un peu plus foncé | Bloc mains libres, réglages imbriqués |
| Panneau contenu dans ce sous-panneau | Retour au fond le plus clair | Fiche ou détail interne |
| Niveaux suivants | Même alternance | Pas de troisième gris improvisé |

Proposition technique : réutiliser les tokens `card` et `background`, dans cet ordre, au travers d'une option explicite de surface sur les primitives existantes. `bg-muted` n'est pas une convention de profondeur fiable : il est plus foncé que la carte en clair, mais plus clair en sombre. Aucun calcul automatique à partir de la profondeur DOM, ni sélecteur global visant tous les descendants.

La même relation clair → plus foncé → clair doit fonctionner en clair, sombre et noir absolu, avec les accents existants. Le fond de page noir absolu reste noir. Les états sémantiques (épinglé, sélection, erreur, avertissement) gardent leurs couleurs et leur sens ; ils priment sur la surface neutre. Les cartes métier colorées, le compagnon et l'identité publique gardent leurs conventions.

Le lot de fondation couvre l'inventaire des consommateurs des primitives dans les écrans authentifiés, puis la migration des panneaux neutres concernés. Il doit vérifier les répercussions sur Accueil, Chat et les écrans administratifs partageant ces primitives, sans y ajouter de changement fonctionnel.

Précisions de la réanalyse : alterner les panneaux réellement peints, sans ajouter un cadre à chaque wrapper ni repeindre une coque transparente. Préserver les deux couches existantes de tokens, chrome --color-* et cartes de réponse --lia-*, ainsi que la matière sombre propre à l'Accueil. Des rôles typographiques communs n'imposent pas le remplacement de tous les titres par SectionHeader : les titres Psyché demandés gardent leur taille de référence.

## Matrice de couverture

Les réglages se trouvent sous `/dashboard/settings?section=<token>`. Les chemins de composants sont relatifs à `apps/web/src/`. « L » désigne les lots du [plan d'implémentation](../plans/2026-10-16-ajustements-interfaces.md).

| ID | Surface | Résultat attendu | Propriétaire actuel | Lot |
|---|---|---|---|---|
| R00 | Application | Alternance des fonds définie ci-dessus, sans effacer les états sémantiques. | `styles/globals.css`, `components/ui/card.tsx`, `components/ui/disclosure.tsx`, `components/settings/SettingsSection.tsx` | L0 |
| R01 | `location` | Indicateur avec libellé Actif / Inactif / Erreur à droite du titre de géolocalisation ; bouton plein rouge « Effacer ». | `components/settings/LocationSettings.tsx`, `LastKnownLocationSection.tsx` | L2 |
| R02 | `theme` | Remplacer le switch OLED par une option « Noir absolu » du sélecteur principal, directement à droite de « Sombre », au-dessus du catalogue des accents. | `components/settings/DisplayModeSelector.tsx` | L3 |
| R03 | `font-size` | Conserver le titre, l'aperçu et le curseur ; masquer px/%, badge « Par défaut » et note indiquée ; conserver Réinitialiser. | `components/settings/FontSizeSettings.tsx` | L1 |
| R04 | `display-mode` | « Cartes HTML » devient « Cartes », avec cohérence du message de sélection. Les quatre formats techniques restent distincts. | `components/settings/CardsDisplaySettings.tsx` | L1 |
| R05 | `usage-preferences` | Retirer la notice sur le choix des outils lorsque le modèle ne peut pas tous les contenir. | `components/settings/UsagePreferencesSettings.tsx` | L1 |
| R06 | `my-shortcuts` | Compteur épinglé près du titre ; aide de limite séparée et lisible sous celui-ci. Les nombres proviennent du compte. | `components/settings/MyShortcutsSettings.tsx` | L2 |
| R07 | `notifications` | Retirer la notice « Les notifications te permettent de recevoir tes rappels même lorsque l'application est fermée. » | `components/settings/NotificationSettings.tsx` | L1 |
| R08 | `voice-mode` | Description incluant le choix des voix de synthèse ; panneau mains libres regroupant activation, notice PTT, confidentialité et commande d'arrêt. | `components/settings/VoiceModeSettings.tsx` | L4 |
| R09 | `avatar` | Enregistrement automatique fiable sans bouton Enregistrer. | `components/settings/AvatarSettings.tsx`, propriétaire de sauvegarde à créer | L5 |
| R10 | `generated-assets` | Fond des éléments épinglés identique aux mémoires ; retrait de la phrase de conservation par carte ; PDF en première page et autres formats en extrait identifié. | `components/settings/generated-assets/GeneratedAssetGrid.tsx`, `components/chat/GeneratedDocumentPreview.tsx`, `lib/document-preview.ts` | L6 |
| R11 | `telephony-identity` | « Retirer le numéro » en bouton rouge. | `components/settings/TelephonyIdentitySection.tsx` | L1 |
| R12 | `psyche` | Panneaux pour Comprendre / Réglages / Réinitialisations et Évolution ; titres Traits / Relation / Motivations / Auto-efficacité de même taille que Le point de LIA ; seuls les trois premiers panneaux fermés par défaut, selon la dernière consigne. | `components/settings/PsycheSettings.tsx`, `components/psyche/PsycheStateSummary.tsx`, `PsycheEfficacy.tsx`, `PsycheLLMSummary.tsx` | L7 |
| R13 | `memories` | Retirer le bloc « Pourquoi LIA pense cela ? ». | `components/settings/MemorySettings.tsx` | L8 |
| R14 | `interests` | Retirer ce même bloc imbriqué ; conserver l'explication du sujet et ses statistiques. | `components/interests/InterestExplanation.tsx` | L8 |
| R15 | `habits` | « Recalculer maintenant » devient « Recalculer ». | `components/settings/HabitsSettings.tsx` | L1 |
| R16 | `peer-connections` | Panneaux Visibilité / Bloqués / Accès aux données ; « Supprimer » ; Supprimer et Bloquer sur la même ligne. | `components/settings/PeerConnectionsSettings.tsx`, `peers/PeerConnectionCard.tsx` | L9 |
| R17 | `heartbeat` | Notifications récentes avec la même présentation que les notifications proactives d'Alertes. | `components/settings/HeartbeatSettings.tsx`, `HeartbeatHistory.tsx` | L10 |
| R18 | `scheduled-actions` | Vue de la semaine fermée par défaut. | `components/settings/ScheduledActionsSettings.tsx` | L1 |
| R19 | `journals` | Retirer le bloc « Pourquoi LIA pense cela ? ». | `components/settings/JournalsSettings.tsx` | L8 |
| R20 | `health-metrics` | « Tout supprimer » devient « Supprimer » ; conserver la distinction entre suppression globale, rythme cardiaque et pas. | `components/settings/HealthMetricsSettings.tsx` | L1 |
| R21 | `skills` | « Trouver des skills » devient « Rechercher ». | `components/settings/SkillsSettings.tsx` | L1 |
| R22 | `plugins` | « Importer depuis une URL » devient « URL » ; champ, validation et rapport d'import inchangés. | `components/settings/PluginsSettings.tsx` | L1 |
| R23 | `mcp-servers` | Badge d'état avant le nom ; informations secondaires alignées en bas, avec les commandes. | `components/settings/MCPServerCard.tsx` | L11 |
| R24 | `rag-spaces` | Cartes compactes proches des MCP ; description courte et Voir plus / Voir moins ; alignement commun des informations et actions. | `components/spaces/SpaceCard.tsx` | L12 |
| R25 | Réglages `meetings` | Retirer le bloc Comptes rendus et sa lecture réseau devenue inutile. | `components/settings/MeetingsSettings.tsx` | L1 |
| R26 | `/dashboard/relations` | Regrouper les badges à droite de l'identité, sans collision avec le favori. | `components/relations/RelationCardList.tsx` | L13 |
| R27 | Relations, détail | Actions centrées ; cadres, titres et présentations des sections cohérents avec les autres écrans ; corriger le fond de Même personne ?. | `components/relations/RelationDetailPanel.tsx`, `CollapsibleSection.tsx`, `RelationMergePanel.tsx` | L13 |
| R28 | `/dashboard/meetings` | Retirer le raccourci Modèles dans l'en-tête de liste, conserver les modèles dans les réglages. | `app/[lng]/dashboard/meetings/page.tsx` | L1 |
| R29 | `/dashboard/notifications` | Retirer le bloc Réglages avancés et ses raccourcis, conserver les sections de réglages. | `components/notifications/NotificationsHub.tsx` | L1 |
| R30 | `/dashboard/faq` | Placer Comment fonctionne LIA après Historique des versions ; conserver recherche et replis. | `components/faq/FAQContent.tsx` | L1 |

## Composition proposée

### Localisation et raccourcis

L'indicateur de géolocalisation appartient au titre « Géolocalisation », à l'intérieur de la section Localisation : le statut des coordonnées mémorisées ou de l'adresse du domicile est distinct. Actif signifie fonctionnalité activée, permission accordée et absence d'erreur ; Erreur couvre une activation empêchée/refusée ou une erreur remontée ; Inactif signifie désactivée. Un état de permission encore inconnu ne doit pas être annoncé comme Actif. Les raisons détaillées restent sous la commande.

Le statut inclut un texte ; la couleur seule ne donne pas l'information. Le switch garde son nom accessible. « Effacer » conserve d'abord son contrat existant : aujourd'hui, cette commande efface la position mémorisée en désactivant aussi sa mémorisation. Une évolution de cette conséquence est proposée plus bas, indépendamment de la retouche visuelle.

Pour les raccourcis : badge numérique à droite du titre ; sous la description, une ligne « Limite atteinte — retire-en un pour en épingler un autre. » seulement à capacité. Le compteur et cette aide constituent une seule annonce accessible. Désépingler reste possible à capacité ; aucune limite fixe de cinq n'est codée dans l'UI.

### Apparence

Quatre choix visuels dans un seul groupe : Clair, Sombre, Noir absolu, Système. Sur écran assez large, Noir absolu est immédiatement à droite de Sombre. Sur mobile, grille à deux colonnes conservant cet ordre de lecture et des noms complets. Cette position est l'interprétation proposée de « au dessus à droite de Sombre » : elle évite un contrôle détaché du sélecteur principal.

Noir absolu appelle l'opération existante `apply({mode: 'dark', oled: true})`. Sombre appelle `apply({mode: 'dark', oled: false})`. Clair et Système désactivent explicitement OLED. Le mode local reste `light | dark | system` avec son raffinement OLED ; le backend sait déjà persister la valeur unique `oled`. Ne pas ajouter un quatrième mode à next-themes ni deux écritures serveur concurrentes. Préserver l'accent, l'initialisation avant affichage et le cycle du bouton d'en-tête.

### Mode vocal

Description proposée : « Configure la transcription, le mode mains libres et les voix de synthèse de LIA. » Organisation : moteur de transcription, panneau mains libres, puis voix de synthèse. Le panneau mains libres est statique et encadré, sans repli additionnel qui désactiverait ses enfants.

Le panneau contient le switch et les trois notices demandées : push-to-talk disponible avec appui maintenu sur envoyer ; détection locale avant activation ; interruption de lecture sans envoi dans la discussion. Les phrases d'activation et d'arrêt sont celles réellement fournies pour la langue utilisée. La notice du moteur distant reste près du choix de transcription ; elle ne doit pas être confondue avec la détection locale du mot d'activation.

### Avatar : sauvegarde et retour utilisateur

Le changement de switch ou de visage du catalogue enregistre immédiatement. Un identifiant libre se valide au blur ou à Entrée, jamais caractère par caractère. Un couple valide `{enabled, face_id}` est toujours envoyé dans un PUT unique. Le serveur assure déjà sa transaction ; aucune migration n'est prévue.

La file de sauvegarde appartient au compte dans le layout dashboard, est activée paresseusement et survit aux changements de section/page SPA. Une requête en vol, puis le dernier choix complet seulement : A en cours, B puis C sélectionnés donnent A puis C. Aucun écho intermédiaire ne remplace C dans l'interface. Sur échec confirmé, restaurer la dernière configuration confirmée, afficher un état d'erreur et permettre Réessayer. Si le résultat réseau est ambigu, relire d'abord la configuration ; ne pas prétendre que le serveur a annulé son écriture. Un succès du PUT reste confirmé même si le rafraîchissement de présentation échoue ensuite. Réessayer est une action de récupération, pas un bouton Enregistrer permanent. Arrêter la file et ignorer les réponses devenues étrangères lors d'un changement de compte.

Afficher discrètement « Enregistrement… », « Enregistré » ou l'erreur. Ne pas annoncer Enregistré avant l'accusé serveur. L'aperçu de visage reste gratuit : il ne démarre aucune session d'avatar. Un rechargement complet du navigateur pendant une écriture reste une interruption possible ; aucune promesse de sauvegarde hors ligne n'est ajoutée.

### Galerie

Une carte épinglée reprend exactement le fond et la bordure des mémoires épinglées : `bg-primary/10 border-primary/25`. L'épingle conserve un état et un nom accessibles ; les échéances des fichiers temporaires et les limites du compte restent visibles.

Réutiliser `/attachments/{id}/preview` : PNG de la vraie première page pour PDF, extrait identifié pour DOCX/PPTX/XLSX et formats texte pris en charge. Aucun contenu n'est inventé ni présenté comme une page originale pour Office. Le rendu est différé jusqu'à proximité de la zone visible, borné, avec une zone stable et un repli au pictogramme. La page PDF est entière, sans rognage.

Conserver le lien existant d'ouverture de carte et ses actions indépendantes ; ne pas imbriquer le bouton/lightbox du composant chat sous son lien étiré. Réutiliser les helpers d'URL/authentification et la lecture d'extrait existants. Pas de cache persistant de documents privés, pas d'appel à un modèle, pas de conversion Office supplémentaire.

### Psyché et provenance

Comprendre, Réglages et Réinitialisations ont chacun un panneau ; Évolution garde un cadre visible. Les titres Traits de personnalité, Votre relation, Ce qui la pousse à agir et Auto-efficacité reprennent le même niveau visuel que Le point de LIA (`text-base font-semibold`), sans agrandir tous les sous-titres internes.

La dernière consigne du 16 octobre remplace « tout replier » : seuls Comprendre la psyché, Réglages de la psyché et Réinitialisations arrivent fermés. Les autres rubriques et leurs détails arrivent ouverts sur desktop comme sur mobile, y compris Le point de LIA et Évolution. Les choix d'ouverture ou de fermeture faits ensuite sont conservés pendant les rafraîchissements et changements de largeur. À la prochaine entrée dans la section, les valeurs initiales s'appliquent à nouveau.

Le point de LIA conserve sa génération automatique à la visibilité et son actualisation existantes ; son GET peut appeler un modèle et écrire des données. L'ouverture initiale demandée rétablit donc sa lecture dès l'entrée dans la section. Ne pas réintroduire de bouton Générer à partir d'un ancien plan. Le hook d'état conserve `initialize=false`. Les preuves navigateur simulent intégralement ces lectures : aucun appel provider ou mutation réelle de Psyché n'est nécessaire à la qualification visuelle.

Retirer les trois montages de ProvenanceDisclosure dans mémoires, journaux et explication d'intérêt. Conserver les actions d'édition, les explications d'intérêt, les sources conservées et les API existantes. Mettre à jour l'aide qui promettrait encore ce bouton sur ces écrans. Si la primitive frontend n'a plus aucun consommateur, la retirer avec ses tests devenus sans objet ; ne pas supprimer les contrats serveur dans cette finition UI.

### Connexions, MCP, RAG et Relations

Visibilité, Bloqués et Accès aux données sont déjà des blocs repliables : leur donner un vrai cadre suffit. Supprimer et Bloquer restent deux actions et deux confirmations distinctes. Elles partagent une ligne lorsque les libellés tiennent, avec retour naturel pour les langues longues et le texte agrandi.

MCP : déplacer le badge d'état avant le nom et regrouper les informations secondaires avec les commandes dans une zone poussée vers le bas. Le code ne contient pas de bloc ni de compteur nommé « usages » ; l'interprétation proposée vise les données existantes (URL, authentification, outils, dernière connexion, erreur). Aucun chiffre d'usage n'est inventé. En grille, le bas s'aligne par rangée ; une description développée peut agrandir sa rangée.

RAG : réduire le padding redondant, rapprocher l'en-tête du modèle MCP, aligner état/compteurs/actions. Réutiliser le comportement de description mesurée de MCP pour n'offrir Voir plus que si le texte déborde. Ce bouton ne doit jamais déclencher l'ouverture de l'espace. Préserver les protections des espaces gérés.

Relations : badges regroupés à droite et alignés à droite même s'ils passent sur une deuxième ligne ; favori dans sa zone propre. Les actions du détail sont centrées et se répartissent sur plusieurs lignes si nécessaire. Standardiser les cadres et lignes de données à partir des composants existants. Ne pas remplacer mécaniquement CollapsibleSection par Disclosure : le premier garde ses enfants montés, le second les démonte.

Le détail Relations ne possède actuellement pas de section Alertes. La demande de standardisation vise le style commun ; elle ne crée pas de famille de données. Les appels Relations ne portent pas tous les champs des Appels récents : conserver leurs données réelles, utiliser la même hiérarchie visuelle et les composants de ligne compatibles, sans fabriquer durée, coût ou résultat.

## Suggestions supplémentaires, distinctes des demandes

| Proposition | Bénéfice concret | Portée proposée |
|---|---|---|
| Un même en-tête pour titre, état, compteur et actions | Évite des badges isolés, des titres comprimés et des alignements différents selon l'écran. | Réemploi de SectionHeader ; accessoire optionnel de SettingsSection dans L0. |
| Une seule convention pour les boutons courts | Libellé visible court, nom accessible précis, cible conservée ; rouge pour une suppression. Les confirmations nomment toujours l'objet et le périmètre. | À appliquer aux boutons touchés ; pas de refonte globale de Button. |
| Chargement différé des aperçus et historiques repliés | Galerie plus légère et aucune lecture d'historique avant ouverture. | Réemploi des mécanismes actuels, pas de préchargement général. |
| Préserver l'ouverture et le focus pendant un rafraîchissement | Évite de perdre sa place, sa saisie ou une sélection après une action. | Critère de validation des écrans touchés. |
| Dissocier à terme Effacer et Désactiver la mémoire de position | Actuellement Effacer désactive aussi la collecte future ; deux intentions différentes ont le même effet. | Suggestion fonctionnelle séparée, hors implémentation tant qu'elle n'est pas acceptée. |

Les quatre premières prolongent directement la qualité demandée. La cinquième change un comportement serveur/UI existant et reste une proposition séparée. Aucune nouvelle organisation de navigation, animation décorative, bibliothèque d'interface ou télémétrie n'est nécessaire.

## Validation attendue après le go

Tests comportementaux là où le comportement change : thème, avatar, aperçus, replis/lazy reads, Voir plus, confirmations et navigation. Pour les libellés et alignements seuls, adapter les attentes existantes et vérifier le rendu ; ne pas écrire de tests qui reproduisent simplement les classes CSS.

Vérifier desktop et mobile, largeurs intermédiaires, texte agrandi, textes longs, langues française/anglaise/allemande, parité des six catalogues, clair/sombre/noir absolu et accents. Le clavier doit garder un ordre logique, le focus doit rester visible et les actions doivent rester disponibles sur écran tactile. Les tests navigateur sont hermétiques et les validations locales passent par Docker dev.

Les tests, checks statiques et captures applicatives seront produits pendant l'implémentation. La préparation ne vaut pas réussite de ces validations. Le dépôt possède un travail staged important : conserver l'index et les modifications concurrentes, relire les composants avant chaque lot, ne pas faire de reset, stash ni formatage global. Aucun commit, push ou déploiement n'est inclus dans la préparation.
