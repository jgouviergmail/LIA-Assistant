# Ajustements des interfaces — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task, according to the user's instructions. No implementation before the user's go. Steps use checkbox syntax for tracking.

**Goal:** Appliquer les ajustements d'interface recensés, avec des surfaces cohérentes et les comportements existants préservés ou explicitement adaptés.

Autorisation reçue le 16 octobre 2026 : exécuter la demande initiale et les suggestions acceptées, dont protection mobile, persistance fiable, contexte de navigation, états erreur/vide, densité, commandes en attente et vocabulaire. La dissociation Effacer / Désactiver la mémoire de position reste différée. Le développement ne comprend ni publication Git ni déploiement.

**Architecture:** Réutiliser Card, Disclosure, SettingsSection, SectionHeader, NotificationHistoryItem et les helpers de preview existants. Les seuls nouveaux propriétaires identifiés sont la sauvegarde d'avatar liée au compte et, si nécessaire, une description réutilisable pour MCP/RAG. Aucune migration ou nouvelle dépendance prévue.

**Tech Stack:** Next.js, React, TypeScript, Tailwind, react-i18next, Vitest, Playwright ; API existante pour les préférences et aperçus.

**Spec:** [Spécification et matrice R00–R30](../specs/2026-10-16-ajustements-interfaces-design.md).

## État d'exécution du 16 octobre 2026

Les ajustements R00–R30 et les axes complémentaires acceptés sont implémentés. La revue indépendante a notamment fait renforcer la réconciliation des sauvegardes d'avatar, le statut de géolocalisation, l'emprise des commandes de BIP et les reprises après erreur. Une seconde lecture n'a relevé aucun défaut restant sur ces points.

La suite frontend complète avec couverture a réussi après les derniers correctifs : 1 061 fichiers, 13 076 tests, tous les seuils globaux et ciblés conservés. Couverture : statements 87,75 %, branches 81,93 %, fonctions 85,56 %, lignes 89,28 %. ESLint, TypeScript sans compilation incrémentale, parité des six langues, contrôles globaux d'accessibilité/hooks/complexité et audit documentaire passent ; les violations historiques admises par les ratchets ne sont pas augmentées. Les dernières consignes sur les replis Psyché et le badge des Journaux sont également vérifiées par les 131 tests de la famille Psyché et les 27 tests Journaux.

La qualification navigateur dans Docker utilise les API simulées et le garde réseau existant. Les parcours mobiles à 360 pixels, le texte doublé, le retour au rail et la sauvegarde automatique sont validés. Les oracles Psyché suivent la dernière consigne : rubrique du point ouverte à l'entrée, lectures initiales simulées et fermetures ultérieures conservées. Les 627 cas uniques de l'inventaire Chromium ont tous réussi, sans cas ignoré ni non exécuté. Ce bilan consolide les lots et les rejeux des cas affectés après correction ; il ne décrit pas un unique lancement intégral sans reprise.

Captures de la version locale : [mobile, recherche dégagée](../../assets/ui-analysis-2026-10-16/settings-mobile-360-after.png) et [texte doublé](../../assets/ui-analysis-2026-10-16/settings-mobile-360-text-200-after.png). La [capture initiale](../../assets/ui-analysis-2026-10-16/settings-mobile-360.jpg) reste le relevé avant correction.

La [capture française finale de Psyché](../../assets/ui-analysis-2026-10-16/psyche-final-fr-1440.png) montre le panneau principal et les trois premières rubriques fermées, avec les observations suivantes ouvertes. Les vues mobiles à texte doublé montrent les [traits de personnalité](../../assets/ui-analysis-2026-10-16/psyche-traits-text-200-fr-360.png) et les [statistiques de relation](../../assets/ui-analysis-2026-10-16/psyche-text-200-fr-360.png), sans couper leurs libellés. Les données de ces preuves sont fictives.

Dans les [Journaux à texte doublé](../../assets/ui-analysis-2026-10-16/journals-text-200-fr-360.png), le badge conversation garde son icône et son texte ensemble ; les catégories laissent leurs mots entiers et leurs compteurs visibles. Les [Mémoires dans les mêmes conditions](../../assets/ui-analysis-2026-10-16/memories-categories-text-200-fr-360.png) servent de référence et n'ont pas nécessité de correction supplémentaire.

Le contrôle élargi a exposé une frontière serveur/client des styles de bouton : les variantes sont désormais dans un module pur partagé, tandis que le bouton interactif conserve ses protections d'attente. La reprise d'avatar garde aussi son bouton et son focus pendant la requête, puis rend le focus à un contrôle du formulaire si nécessaire. Le refus de rafraîchissement de compte n'efface plus les préférences langue/fuseau confirmées.

Un signalement complémentaire de disparition du fond mobile a été retiré par l'utilisateur. Les deux contrôles Chromium/WebKit après un vrai défilement de 1 200 px passent ; aucune correction de fond n'est revendiquée.

La file d'avatar survit aux navigations internes. Un rechargement complet ou la fermeture de l'onglet pendant une requête ne garantit pas son achèvement ; l'écran relit la configuration à son retour. Effacer garde son contrat existant de désactivation de la mémorisation future. Aucun appel payant de validation, aucune publication Git et aucun déploiement ne font partie de cette exécution.

### Retours visuels complémentaires

La seconde passe traite les sept captures fournies par l'utilisateur. La profondeur dépend du parent réellement peint : un conteneur de mise en page transparent ne constitue pas un niveau. Card et Disclosure définissent le fond du niveau et le fond attendu de leurs champs ; Input, Select, Textarea et les boutons secondaires lisent ce repère. Les overlays réinitialisent ce repère selon leur propre surface. Les couleurs d'état, de sélection et d'épinglage restent sémantiques.

- Mode vocal, Radio, génération d'images, réponses conservées et santé : alternance rétablie jusque dans les options, notices, sélecteurs, extraits et statistiques.
- Psyché et Connexions : panneau principal opaque rétabli, puis panneaux et éléments imbriqués alternés. Le titre de relation et son badge peuvent se répartir sur plusieurs lignes sur mobile avec texte agrandi.
- Journaux : catégories présentées comme les Mémoires, avec en-tête, compteur et entrées encadrées ; le bloc Détails reprend le niveau suivant.
- Mémoires, intérêts, habitudes, réunions, relations, espaces, connecteurs, téléphonie et administration : vérification des parents peints et correction des profondeurs incohérentes rencontrées, y compris les extraits de confirmation et l'export administrateur.
- Alertes : dates, planifications et métadonnées déjà colorées des listes en gras ; application au composant d'historique partagé avec les notifications proactives.

La preuve navigateur dédiée passe sur huit écrans en clair desktop, sombre desktop et noir absolu à 360 pixels avec texte agrandi : 24 cas, avec mesure des couleurs calculées, de l'opacité et de l'alternance en luminance sur trois ou quatre niveaux. Les API sont toutes simulées, les requêtes non prévues restent refusées. La relecture indépendante a ensuite corrigé cinq compositions supplémentaires ; les suites comportementales concernées passent, sans ajouter de tests qui recopient simplement les classes CSS.

Dernière consigne reçue pendant la qualification : Psyché s'ouvre maintenant entièrement sauf Comprendre la psyché, Réglages de la psyché et Réinitialisations. Les choix ultérieurs de fermeture sont préservés ; le résumé et l'historique retrouvent leurs lectures initiales habituelles, entièrement simulées dans les tests. Le résumé garde une lecture par ouverture, avec le cache serveur existant. La capture complémentaire des Journaux a aussi conduit à empêcher la compression du badge de source : icône et texte restent ensemble, tandis que l'en-tête répartit le titre et les badges sur plusieurs lignes lorsque nécessaire. Les 131 tests de la famille Psyché et les 27 tests Journaux passent.

La relecture visuelle à texte doublé a exposé deux limites que la seule absence de défilement horizontal ne détectait pas : les mots des statistiques Psyché se coupaient, et le bouton Niveau des Journaux dépassait son panneau. Deux cas navigateur ont reproduit ces défauts avant correction. Les anneaux et les lignes de traits s'adaptent maintenant au texte ; le regroupement des Journaux peut occuper deux lignes et ses boutons gardent une hauteur suffisante. Les 158 tests des deux domaines passent après ces changements. La qualification navigateur vérifie les huit libellés de statistiques, le texte des valeurs et les limites des boutons à l'intérieur de leur panneau.

Une dernière lecture de la capture a fait corriger les en-têtes de catégories des Journaux : Observations et Apprentissages étaient comprimés par l'icône et le compteur, bien que les mots tiennent dans le panneau. Le cas navigateur reproduit leur coupure avant correction, puis vérifie les mots entiers et leur contenance dans le bouton ; les sept catégories des Mémoires passent aussi ce contrôle sans modification produit. Les trois variantes Journal et les 27 tests du composant passent après correction.

Le contrôle global a également signalé des clés absentes dans les ajouts récents du catalogue public. Les 204 chaînes manquantes ont été ajoutées dans les six langues sans modifier les valeurs existantes ni les cartes présentes. Une couleur de texte trop atténuée dans l'une de ces scènes reprend le jeton de texte secondaire à pleine intensité. Les 22 tests de contenu public et d'opacité, la parité i18n et le format des six catalogues passent ; aucun seuil n'a été abaissé.

### Renommages complémentaires des réglages

Demande complémentaire reçue pendant la validation : appliquer les noms suivants au menu et au titre de chaque page correspondante, actualiser les références de la FAQ et de la documentation courante, puis réindexer le corpus FAQ local une fois les mises à jour terminées.

| Ancien libellé | Nouveau libellé français |
|---|---|
| Administration des personnalités | Admin. perso. |
| Administration des skills systèmes | Admin. skills systèmes |
| Administration des RAG système | Admin. RAG système |
| Administration des connecteurs | Admin. connecteurs |
| Export de mes consommations | Export conso. |
| Exporter mes données | Export données |
| Espace de connaissances (RAG) | Espaces de connaissances |
| Compétences LIA (skills) | Compétences |
| Notifications proactives | Notifications |
| Téléphonie Mon identité | Mon téléphone |
| Génération d'images IA | Génération d'images |
| Mode Live | Mode vocal live |
| Journaux personnels | Journal de LIA |
| Raccourcis du chat | Raccourcis |
| Mes raccourcis | Mes favoris |
| Avatar parlant (bêta) | Avatar parlant |
| Mes Connecteurs | Mes connecteurs |
| Réseau du bac à sable | Autorisations skills |

Les dix-huit clés de titre existantes alimentent déjà le menu, la recherche et le titre des sections. Les jetons de liens profonds et les contrats restent stables. Les six langues reprennent les nouveaux noms ; les termes techniques, les historiques de versions et les noms d'applications tierces conservent leur sens.

- [ ] Mettre à jour les dix-huit titres et les références courantes dans la FAQ, avec parité des six langues.
- [ ] Actualiser les instructions de navigation dans la documentation et dans `docs/knowledge`, source du corpus RAG FAQ.
- [ ] Requalifier les tests existants de recherche, de réglages et de FAQ ; adapter les trois noms accessibles littéraux des parcours navigateur concernés.
- [ ] Réindexer une fois le corpus FAQ local avec `task db:seed:system-rag`, puis vérifier le hash et les éléments indexés. La FAQ web et l'index RAG ont des sources distinctes ; la seule modification des textes web ne réindexe pas les documents.

### Défaut graphique découvert pendant la qualification

Le parcours réel Smiley a exposé une perte prématurée de son contexte WebGL lors du rejeu d'effet StrictMode. La trace navigateur montre le canvas encore connecté avec un contexte perdu et sans programme GPU actif ; une régression unitaire conservant l'état de perte reproduit également ce cas. Le binding détruit désormais ses ressources immédiatement, mais réserve la perte forcée du contexte au retrait réel du canvas. Les remplacements de variante ou de taille et le démontage conservent leur libération des ressources. La revue indépendante ne relève pas de défaut restant sur ce correctif ; les 90 suites Eyes, soit 1 196 tests, passent, ainsi que les huit tests du binding final. Le rejeu GPU réel garde son assertion d'origine.

Le même parcours a ensuite révélé un défaut de placement : une coordonnée préférée légèrement hors de la marge de sécurité pouvait faire choisir le bord opposé, même sans obstacle. Le solveur borne maintenant cette coordonnée avant de chercher les positions libres, sans modifier la position enregistrée. Trois nouvelles régressions reproduisent les cas gauche, haut et viewport décalé ; les quatre suites de placement et widget, soit 99 tests, passent. Le contrôle de complexité conserve son baseline et le parcours de regard garde ses seuils.

La qualification native utilise `scripts/browser/run-native-media.sh`, avec une sortie audio virtuelle et un serveur STUN local vérifiés avant les tests. Le serveur web de preuve et le navigateur partagent un réseau Docker privé fonctionnel. Les quatre parcours Live initialement en échec passent dans cet environnement ; aucun correctif de transport vocal n'a été nécessaire. Le canal HMR local de développement reste ouvert dans un puits local sans transfert : sa fermeture provoquait des rechargements automatiques sous horloge simulée. Les quatorze tests d'isolation vérifient encore le refus des transports API non simulés, des tunnels CONNECT et des autres WebSockets.

Les oracles de géométrie suivent la présentation demandée : absence de Modèles, taille tactile du bouton d'enregistrement et liste sans chevauchement. Le démarrage des Réunions reste borné à deux lectures par défaut ; `E2E_NEXT_DEV=1` distingue explicitement les deux montages rejoués par StrictMode dans le serveur de développement utilisé ici. Les interactions de présentation continuent d'exiger zéro lecture supplémentaire. Le test de regard conserve ses seuils et un générateur déterministe variable, car une constante globale empêchait la délégation clavier de React ; les deux sérialisations CSS acceptées décrivent exactement le même cercle centré.

## Global Constraints

- Go reçu pour la demande et les suggestions acceptées ; aucune publication ou mise en production incluse.
- Taille de police : conserver le titre ; masquer px/%, badge Par défaut et note ; conserver valeur accessible du curseur.
- Aperçus : vraie première page PDF ; extrait identifié pour les autres formats pris en charge ; aucun nouveau moteur Office.
- Alternance des panneaux : fond principal le plus clair, fond imbriqué plus foncé, puis retour au premier ; tous les rendus existants.
- Préserver API, droits, confirmations, coûts, conservation, préférences et contrôles d'espace géré ; aucun modèle appelé pour la décoration.
- Parité en/fr/de/es/it/zh ; noms accessibles traduits ; évolution partagée du Button autorisée pour garder libellé, dimensions et focus pendant l'attente ; aucune copie des composants de maquette.
- Préserver intégralement le travail concurrent staged ; ne pas modifier AGENTS.md ; pas de livraison Git ou déploiement implicite.
- Réutiliser l'implémentation actuelle, pas les cases décochées des plans du 13 octobre ; pas de tests CSS miroirs pour une retouche simple.

## Review Focus

1. Changements de compte ou de section pendant une sauvegarde : le choix courant ne reçoit jamais la réponse d'un autre compte ; l'avatar survit à la navigation SPA.
2. Replis, refetch et changement de largeur : conserver choix d'ouverture, saisie et focus ; appliquer les ouvertures initiales propres à chaque rubrique, dont la dernière consigne Psyché.
3. Coût caché : le résumé Psyché se lit une fois par ouverture, avec le cache serveur existant ; une preview ne lance ni modèle ni session avatar.
4. Contenu hostile/indisponible : preview bornée, document privé/expiré, erreur réseau et carte toujours ouvrable avec repli visuel.
5. Textes longs, grand texte et clavier : les badges, commandes et Voir plus restent accessibles ; aucun clic enfant n'ouvre accidentellement une carte.

Chaque risque est attaché à ses lots ci-dessous. Les identifiants Rxx renvoient aux critères d'acceptation de la spécification.

La [réanalyse transversale](../specs/2026-10-16-experience-ui-review.md) précise les frontières de L0 et les améliorations supplémentaires. Le go couvre notamment l'évolution de Button, la préservation des brouillons de réunions et la restitution du contexte de navigation.

## Exécution et points d'entrée

Commencer par L0. Traiter ensuite les écrans un par un, en réutilisant les modifications communes une seule fois. L1 regroupe le travail mécanique pour sa lecture, mais chaque écran y constitue un sous-lot vérifiable séparément. Un écran n'est annoncé terminé qu'après ses checks et sa revue. Aucun arrêt d'approbation supplémentaire n'est déduit de ce plan ; l'utilisateur conserve son contrôle sur le go et toute consigne ultérieure.

Les chemins ci-dessous sont relatifs à la racine du dépôt. Les tests nommés existent déjà sauf mention « créer ». Dans tous les lots, mettre à jour les six catalogues si les clés ou valeurs visibles changent. Les traductions ne doivent pas modifier des usages hors périmètre d'une clé commune.

### L0 — Fondations et inventaire des surfaces (R00)

**Fichiers :** apps/web/src/components/ui/card.tsx ; ui/disclosure.tsx ; settings/SettingsSection.tsx ; ui/section-header.tsx ; styles/globals.css seulement si un alias est nécessaire. Tests : settings/__tests__/SettingsSection.test.tsx, styles/__tests__/design-contrast.guard.test.ts et tests existants des primitives.

**Interfaces :** ajouter `surface?: 'primary' | 'nested'` à Card et Disclosure, défaut primary inchangé ; primary utilise card, nested utilise background. Les composants sémantiques gardent priorité. Ajouter `headerAccessory?: ReactNode` à SettingsSection avec zone de titre réductible et retour adapté au mobile ; titre et ancre DOM existants conservés. Réutiliser SectionHeader existant, sans le recréer.

- [x] Inventorier les Card, Disclosure et conteneurs neutres significatifs des écrans authentifiés avec `rg -n 'bg-card|bg-muted|bg-background|<Card|<Disclosure' apps/web/src/components apps/web/src/app`. Classer les panneaux par niveau sémantique et les exceptions colorées ; ne pas remplacer globalement les résultats.
- [x] Ajouter les oracles utiles : contraste texte/focus sur les deux surfaces et états colorés, noms accessibles FR/EN du titre/accessoire ; conserver les tests d'ancre/focus de SettingsSection.
- [x] Implémenter les options de présentation puis migrer les panneaux neutres inventoriés écran par écran. Un wrapper flex n'ajoute aucun niveau ; le troisième panneau revient explicitement à primary.
- [x] Mesurer le rendu calculé des surfaces, pas seulement les noms de classes : clair/sombre/OLED, accents, étroit/large. Vérifier aussi les consommateurs partagés Accueil/Chat/admin et les états épinglés.

### L1 — Retouches de texte, retraits et défauts simples

**Fichiers :** les propriétaires R03–R05, R07, R11, R15, R18, R20–R22 et R25/R28–R30 de la matrice ; apps/web/locales/{en,fr,de,es,it,zh}/translation.json.

**Interfaces :** aucun nouveau contrat réseau. Garder les noms techniques de display_mode et la valeur accessible du curseur. Un retrait de bloc entraîne le retrait de ses seules lectures et imports sans consommateur.

- [x] R03 : retirer l'affichage visuel px/% et le badge, garder `aria-valuetext`, bornes, aperçu et Réinitialiser ; retirer l'InfoBox ciblée. Adapter FontSizeSettings.test.tsx sans retirer les oracles de rollback, clavier et limites.
- [x] R04/R05/R07 : labels Cartes, notice de sélection d'outils et notice notifications. Adapter les attentes visibles existantes ; vérifier que la description de section ne réintroduit pas le texte supprimé.
- [x] R11/R15/R20/R21/R22 : bouton numéro rouge, Recalculer, Supprimer, Rechercher et URL. Garder les handlers et les différents périmètres de suppression ; le champ URL et son ouverture actuelle restent en place.
- [x] R18 : retirer `defaultOpen` du Disclosure de la semaine. Adapter ScheduledActionsSettings.test.tsx : fermé au montage, ouverture volontaire conservée pendant polling, focus inchangé.
- [x] R25 : retirer RecentMeetings, son hook, sa limite et ses imports devenus sans usage de MeetingsSettings.tsx. Adapter son test : réglages et modèles présents, pas de requête de liste des CR depuis ce panneau.
- [x] R28 : retirer uniquement l'action Modèles de la liste Réunions. Adapter app/[lng]/dashboard/meetings/__tests__/page.test.tsx et page.application.test.tsx : commandes vides valides si recorder indisponible, accès aux réunions intact. Le second utilise Modèles comme cible de focus ; choisir un contrôle pérenne sans perdre l'oracle « une nouvelle tentative ne vole pas le focus ».
- [x] R29 : retirer le Disclosure Réglages avancés de NotificationsHub, ses liens et imports inutiles ; garder Activité conditionnelle. Adapter notifications/__tests__/NotificationsHub.test.tsx, conserver lazy reads et décisions.
- [x] R30 : inverser les blocs changelog/intro de FAQContent ; vérifier ordre de titres, fermeture initiale indépendante et masquage lors de la recherche dans ses tests existants.
- [x] Pour chaque sous-lot, vérifier traduction et rendu concernés avant de passer au suivant ; aucune nouvelle suite de test dédiée à un simple renommage.

### L2 — Localisation et raccourcis (R01, R06)

**Fichiers :** apps/web/src/components/settings/LocationSettings.tsx ; LastKnownLocationSection.tsx ; MyShortcutsSettings.tsx ; tests de même nom sous __tests__/.

**Interfaces :** consommation de SettingsSection.headerAccessory pour le compteur de raccourcis ; état de géolocalisation dérivé de isEnabled/permission/geoError, pas de la permission seule. Aucun changement d'opt-in.

- [x] Ajouter cas Actif, Inactif, refus/erreur, permission inconnue et indisponibilité ; vérifier switch nommé et raison d'erreur conservée.
- [x] Placer le statut à droite du titre de géolocalisation et rendre Effacer plein rouge avec handler actuel. Vérifier qu'il reste une seule commande d'effacement.
- [x] Intégrer compteur et aide de limite sans concaténation visuelle, sur une seule live region. Préserver maxCount serveur et les tests capacité atteinte → retrait possible → nouvel ajout.
- [x] Vérifier clavier, texte agrandi et grand compteur ; ne pas écrire « 5 / 5 » en dur.

### L3 — Noir absolu dans le choix d'apparence (R02)

**Fichiers :** apps/web/src/components/settings/DisplayModeSelector.tsx ; hooks/useThemeMode.ts et lib/theme-mode.ts seulement si nécessaire ; tests DisplayModeSelector, useThemeMode, theme-mode, theme-toggle et theme-init-script.

**Interfaces :** groupe de quatre options visuelles projetant sur l'opération existante apply ; aucune nouvelle valeur de mode next-themes et aucune migration.

- [x] Faire évoluer les tests du sélecteur : quatre choix, Noir absolu utilisable depuis Clair/Système, .dark et data-oled ensemble ; sortie vers Sombre/Clair/Système enlève OLED ; clavier cohérent.
- [x] Remplacer switch et notice OLED séparés par le choix Noir absolu, à droite de Sombre au-dessus des accents ; ordre responsive conforme à la spécification.
- [x] Vérifier rafale de choix, compte changé, échec et hydratation avec les tests existants du seam. Conserver une écriture coalescée de préférence et le cycle d'en-tête.

### L4 — Bloc vocal et descriptions (R08)

**Fichiers :** apps/web/src/components/settings/VoiceModeSettings.tsx ; __tests__/VoiceModeSettings.test.tsx ; catalogues.

**Interfaces :** aucune nouvelle API ou souscription. Le bloc mains libres reste monté ; les notices réutilisent wakeWordCopy.

- [x] Regrouper le switch et les notices PTT/confidentialité/arrêt dans un panneau nested ; les sélecteurs de voix sont distincts et la description les annonce.
- [x] Adapter les tests de contenu/localisation : langue réelle de phrase/arrêt, STT distant distinct de la détection locale, pas de nouvelle activation micro au rendu.
- [x] Vérifier lisibilité et ordre clavier sur mobile ; pas de nouvelle couche de repli.

### L5 — Sauvegarde automatique de l'avatar (R09)

**Fichiers :** apps/web/src/components/settings/AvatarSettings.tsx ; apps/web/src/components/avatars/AvatarPreferenceSaveProvider.tsx, qui exporte également useAvatarPreferenceSave ; raccord dans app/[lng]/dashboard/layout.tsx. Tests du provider à travers AvatarSettings.test.tsx ; e2e/smoke/settings-speaking-avatar.spec.ts et settings-avatar-autosave-recovery.spec.ts.

**Interfaces livrées :** la préférence reprend enabled/face_id d'AvatarConfig. `useAvatarPreferenceSave()` expose change, initialize, retry (Promise de confirmation), confirmed/desired et les indicateurs saving/failed/saved. Le provider lié à user.id héberge file et transport ; montage paresseux des lectures, aucune requête globale additionnelle. PUT /avatars/settings inchangé ; validation UUID/visage activé conservée.

- [x] Écrire les tests comportementaux avant le remplacement : switch/select → PUT ; saisie libre invalide → aucun PUT ; blur/Entrée valide → un PUT ; A en vol puis B/C → envois A/C, pas B ; aucun écho A sur l'affichage C.
- [x] Tester échec → retour au dernier snapshot confirmé + erreur/Réessayer ; réponse perdue/ambiguë → relire la configuration avant de revendiquer sa valeur ; compte changé → queue abandonnée et réponse ignorée. Un PUT confirmé reste un succès même si refreshUser ou la relecture de présentation échoue ensuite : ne pas rejouer une mutation réussie pour réparer un rafraîchissement.
- [x] Tester navigation SPA immédiate hors réglages → sauvegarde terminée, retour → dernière valeur ; aucun état Enregistré anticipé ; aucun /avatars/sessions ou mint depuis l'aperçu.
- [x] Implémenter le propriétaire de file et les messages accessibles ; garder contrôles focusables ; raccorder révision avatar et refreshUser sans écraser un choix plus récent. Retirer le bouton Enregistrer seulement après ces preuves.
- [x] Rejouer le parcours hermétique, avec latence et erreur, dans Docker dev. Documenter la limite du rechargement complet en cours d'écriture.

### L6 — Galerie et aperçus (R10)

**Fichiers :** apps/web/src/components/settings/generated-assets/GeneratedAssetGrid.tsx ; lib/generated-assets/display.ts ; lib/document-preview.ts ; components/chat/GeneratedDocumentPreview.tsx comme référence. Extraire un affichage d'extrait commun si réemploi nécessaire, sans transporter le bouton/lightbox du chat dans le lien étiré de galerie. Tests : GeneratedAssetsSettings.test.tsx, GeneratedDocumentPreview.test.tsx, GeneratedDocumentPreview.names.test.tsx ; e2e/smoke/generated-assets-gallery.spec.ts.

**Interfaces :** `isKept(asset)` reste l'autorité expires_at === null ; `documentPreviewUrl` et `fetchDocumentPreview` existants ; endpoint preview inchangé. Aucun cache privé persistant, conversion Office ou nouveau modèle.

- [x] Adapter les oracles épinglé/temporaire, retirer la seule kept_line ; vérifier conservation/plafonds et échéances.
- [x] Ajouter cas PDF image réelle, extrait Office/texte identifié, échec/expiration → pictogramme sans casser ouverture et téléchargement ; aucun chargement hors viewport, abort/compte changé si lecture d'extrait.
- [x] Mettre en place les aperçus bornés, dimensions stables, PDF entier et actions indépendantes ; ne pas imbriquer des contrôles interactifs dans le lien de carte.
- [x] Rejouer galerie et lien avec clavier/mobile ; réutiliser les tests backend tests/unit/domains/attachments/test_document_preview.py si une modification du contrat de lecture s'avère nécessaire, sans modifier les limites pour la présentation.

### L7 — Panneaux Psyché et replis (R12)

**Fichiers :** apps/web/src/components/settings/PsycheSettings.tsx ; components/psyche/PsycheStateSummary.tsx ; PsycheEfficacy.tsx ; PsycheLLMSummary.tsx ; tests correspondants et e2e/smoke/psyche-settings.spec.ts.

**Interfaces :** réutiliser PsychePanel et ses options de cadre ; les trois premières rubriques fermées, les suivantes ouvertes selon la dernière consigne, sans branche de largeur. Le résumé reçoit isOpen depuis son panneau contrôlé. Préserver les contrats auto-efficacité récemment ajoutés.

- [x] Tests : Comprendre/Réglages/Réinitialisations fermés au premier montage, autres rubriques ouvertes desktop/mobile ; resize/refetch ne réimpose pas les ouvertures ; état et contrôles disponibles sans mutation d'initialisation.
- [x] Test hermétique : résumé ouvert à l'entrée → lecture initiale simulée unique, StrictMode inclus ; fermeture puis réouverture contrôlées et rafraîchissement explicite conservés. Ne jamais exécuter ce GET réel pour une vérification esthétique.
- [x] Encadrer Comprendre/Réglages/Réinitialisations/Évolution ; rendre Le point repliable ; aligner les quatre titres demandés sur text-base font-semibold sans étendre cette taille aux sous-domaines internes.
- [x] Vérifier confirmations de reset, erreurs, compte changé, valeurs inconnues et historique différé avec les tests actuels ; conserver initialize=false pour l'état.

### L8 — Retrait ciblé de la provenance (R13, R14, R19)

**Fichiers :** apps/web/src/components/settings/MemorySettings.tsx ; JournalsSettings.tsx ; components/interests/InterestExplanation.tsx ; components/provenance/ProvenanceDisclosure.tsx seulement pour retrait si inutilisé ; aide/catalogues annonçant l'accès retiré.

**Interfaces :** aucune suppression d'API ou de données. Conserver l'explication externe d'intérêt et toutes les commandes d'édition.

- [x] Retirer les trois montages ; vérifier par recherche l'absence d'autres consommateurs avant tout nettoyage de primitive.
- [x] Adapter les tests MemorySettings, JournalsSettings, InterestsSettings et InterestExplanation : bloc ciblé absent, éditer toujours disponible, explication/coefficients d'intérêt présents. Aucun appel provenance à l'ouverture de ces cartes.
- [x] Corriger l'aide décrivant ce bouton et vérifier six langues ; conserver les explications non ciblées.

### L9 — Connexions (R16)

**Fichiers :** apps/web/src/components/settings/PeerConnectionsSettings.tsx ; peers/PeerConnectionCard.tsx ; peers/__tests__/PeerConnectionsSettings.test.tsx et PeerConnectionCard.test.tsx ; e2e/smoke/peer-connections-settings.spec.ts.

**Interfaces :** les trois Disclosure existent déjà ; restaurer cadre et surface au lieu de recréer leur état. Libellé visible Supprimer ; nom accessible et confirmations restent précis.

- [x] Présenter les trois commandes comme des panneaux nested, gardés fermés initialement ; aligner Supprimer/Bloquer sur une ligne avec retour pour textes longs.
- [x] Vérifier suppression vs blocage, sérialisation, échec/retry, saisie et focus conservés pendant refetch ; ne pas remplacer loading du premier chargement par un démontage à chaque mutation.

### L10 — Historique proactif (R17)

**Fichiers :** apps/web/src/components/settings/HeartbeatSettings.tsx ; HeartbeatHistory.tsx et NotificationHistoryList.tsx seulement si correction nécessaire ; tests HeartbeatSettings/HeartbeatHistory ; e2e/smoke/settings-heartbeat.spec.ts.

**Interfaces :** passer `presentation="timeline"` à HeartbeatHistory, exactement comme Alertes. Garder la lecture activée seulement quand historyOpen.

- [x] Réutiliser cette variante ; vérifier ordre, texte, sources, verdicts et compteurs conservés avec les fixtures existantes.
- [x] Vérifier zéro lecture avant ouverture, erreur différente de vide et pagination propre à la famille ; aucune requête d'historique additionnelle.

### L11 — Cartes MCP (R23)

**Fichiers :** apps/web/src/components/settings/MCPServerCard.tsx ; __tests__/MCPServersSettings.test.tsx ; comportement ServerDescription actuel comme source de réemploi.

**Interfaces :** DTO UserMCPServer inchangé. `ServerFacts` rejoint le conteneur poussé en bas avec les actions. Badge d'état avant le nom, provenance plugin distincte.

- [x] Modifier l'en-tête et ancrer faits + commandes en bas ; noms longs, erreur présente/absente et descriptions développées doivent rester lisibles.
- [x] Vérifier OAuth, switch, Voir plus, actions et clavier existants ; comparer les positions basses dans une rangée de cartes de contenus différents. Aucun compteur d'usage créé.

### L12 — Cartes RAG compactes (R24)

**Fichiers :** apps/web/src/components/spaces/SpaceCard.tsx ; components/settings/MCPServerCard.tsx si extraction ; créer components/ui/expandable-description.tsx seulement pour le réemploi effectif. Tests SpaceCard.test.tsx et MCPServersSettings.test.tsx.

**Interfaces :** `ExpandableDescription({text, className?})` avec chaînes résolues dans la locale active ; extraction depuis ServerDescription, même détection d'overflow, ResizeObserver nettoyé. API RAG et actions inchangées.

- [x] Tests Voir plus absent si texte court, présent si débordement, développement/réduction, recalcul après resize/langue ; clic/Entrée sur ce bouton ne navigue pas vers l'espace et le lien carte reste fonctionnel.
- [x] Réduire padding et en-tête, aligner métadonnées/actions en bas ; autoriser le développement réel sans hauteur fixe qui tronque le texte.
- [x] Conserver activation, compteur/taille, actions et protection des espaces gérés. Revalider MCP si description extraite ; nom accessible direct FR/EN et parité six langues.

### L13 — Relations (R26, R27)

**Fichiers :** apps/web/src/components/relations/RelationCardList.tsx ; RelationDetailPanel.tsx ; CollapsibleSection.tsx ; RelationMergePanel.tsx ; RelationProviderSections.tsx si présentations internes concernées. Tests de même nom et relation-switch.simulation.test.tsx ; e2e/smoke/relations-crm.spec.ts et relations-mobile-overflow.spec.ts.

**Interfaces :** standardiser la présentation sans fusionner les DTO des appels/notifications. CollapsibleSection garde enfants montés, panneau adressable, bouton d'actualisation frère du toggle. Les liens d'action restent des brouillons de chat, jamais des envois.

- [x] Regrouper les badges à droite sans collision favori, centrer les actions du détail, utiliser la surface attendue pour Même personne ? et les sections internes.
- [x] Réutiliser les présentations de lignes/badges compatibles ; conserver la richesse réellement fournie par chaque section et les mentions de liste bornée.
- [x] Vérifier mobile/texte long, clavier, compte/relation changé, sélection et brouillon conservés après repli/refetch ; fusion/séparation et retour du focus restent sûrs.

## Commandes de validation après implémentation

Les résultats de l'exécution sont présentés en tête de ce document. Le task complet test:frontend neutralise les variables publiques mais ne relaie pas de filtre CLI. Pour une exécution ciblée, utiliser un processus PowerShell dédié depuis apps/web, par exemple `$env:NEXT_PUBLIC_API_URL=''; $env:NEXT_PUBLIC_PRODUCT_TELEMETRY=''; pnpm exec vitest run src/components/settings/__tests__/AvatarSettings.test.tsx`. Remplacer le chemin par les fichiers existants du lot. Les variables sont alors limitées à ce processus PowerShell et à ses enfants.

- [x] Exécuter les tests comportementaux ciblés de chaque lot ; relever succès, échecs, avertissements et limites.
- [x] Passer le gate complet `task lint:frontend`, la parité `task lint:i18n` et la suite frontend complète avec couverture (variables publiques neutralisées comme le Taskfile) ; aucun seuil/baseline abaissé.
- [x] Passer `task lint:docs:preview` et le contrôle de miroir si des documents/instructions sont touchés.
- [x] Rejouer les scénarios Playwright concernés avec API/SSE interceptées. Cibler le web Docker avec E2E_MANAGED_SERVER=0 ; le garde réseau exige HTTP et refuse les tunnels CONNECT, donc le runtime de preuve isolé utilise l'adresse interne Docker http://127.0.0.1:3001 avec son propre cache. Ne pas lancer de serveur Next host en parallèle.
- [x] Faire la validation visuelle dans Docker dev : mobile, desktop, largeurs intermédiaires, texte agrandi, polices, langues longues, clair/sombre/OLED. Le lot partagé L0 requiert aussi le paquet E2E hermétique complet lorsque les changements affectent le layout global.
- [x] Revue à froid : oubli de ligne Rxx, coût caché, champs perdus, contrôles imbriqués, état occupé/focus, erreur/retry, changement de compte, préservation des saisies et modifications concurrentes. Corriger avant d'annoncer le lot terminé.

Un futur push nécessite `task ci:fast` et les hooks réels, mais ni commit ni push ne sont autorisés par la seule préparation. Aucun déploiement n'est prévu par ce document.
