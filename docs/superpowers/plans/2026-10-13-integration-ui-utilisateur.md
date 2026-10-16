# Intégration UI utilisateur — plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Intégrer les compositions retenues sur les écrans utilisateur, en conservant données, actions, droits, coûts réellement exposés et navigation de LIA.

**Architecture:** Conserver les routes, hooks, stores et primitives du produit. Porter les compositions en JSX/Tailwind avec seulement deux nouveaux génériques de présentation ; garder les transformations temporelles et les états dans leurs domaines. Isoler les adaptations de comportement (autosave, pagination locale, génération volontaire) des simples modifications de disposition.

**Tech Stack:** Next.js 16, React, TypeScript strict, Tailwind, react-i18next, primitives Radix actuelles, Vitest et Playwright hermétique. Dépendances effectives définies par les manifests/lockfiles du dépôt ; aucune dépendance nouvelle prévue.

**Spec:** [Spécification retenue](2026-10-13-integration-ui-utilisateur-design.md). Inventaires détaillés locaux : `output/ui-finition-2026-10-13/integration-preparation/{contrats-transversaux,collections-accueil,chronologies,social,validation-et-risques}.md`.

## Global Constraints

- L’Accueil est prioritaire dans le travail de composition et la revue visuelle.
- Les cinq écrans écartés du comparateur restent dans l’application ; layout, navigation, retour, deep links et flags ne sont pas copiés depuis la maquette.
- Aucun import de `output/`, bundle statique, fixture, binders DOM ou feuille `study.css` dans le produit.
- Réutiliser les tokens, polices, taille de texte, trois rendus clair/sombre/OLED et accents de LIA. Les primitives actuelles restent la base ; pas de changement global de boutons ou de palette.
- Actions principales de page en tête ; informations d’un élément avant ses actions, selon les exceptions explicites Galerie/Export/Mon dashboard. Paramètres verticaux, titres et commandes séparés sur téléphone.
- Préserver tous les champs utiles du payload et tous les handlers existants. Une collection bornée ne devient pas un historique exhaustif par changement de layout.
- Noms visibles et accessibles traduits ; parité des six locales ; focus, erreurs, annulations et refus lisibles.
- Les contrôles et réponses restent liés au compte. Rafraîchir ne démonte pas le contenu déjà reçu ; replier ne perd pas de brouillon.
- Aucun nouveau GET summary Psyché implicite : génération volontaire, pas de retry payé automatique.
- Pas de migration, nouvelle route, nouveau catalogue ou renderer lourd prévu. La convention temporelle serveur des exports est hors de cette refonte.
- Checkout avec changements concurrents : revalider les empreintes avant écriture ; préserver les hunks existants, ne pas reset/stash/reformater globalement.
- Cette préparation n’exécute pas l’intégration ; aucune publication ou mise en production n’en fait partie.

## Review Focus

1. Changement de compte et réponses différées : aucun contenu ou téléchargement A affiché/déclenché sur B. Oracles aux lots Style, Psyché, Connexions, Accueil et Exports.
2. Instant près de minuit, fuseau opposé, DST et dates nulles : bonne journée, regroupement sans disparition et estimation d’horaire explicitée. Oracles Accueil/Réunions/Appels/Exports.
3. Contrôles occupés, deux changements rapides, repli et refetch : conserver dernière intention, brouillon et focus sans succès fictif. Oracles Réglages réunions/Connexions/Style.
4. Payload incomplet, total supérieur aux lignes, liste non paginée : aucun « tout » trompeur ni double pagination. Oracles Accueil/Notifications/Galerie.
5. Preview refusée, texte long, taille de police maximale, langue DE et 320 px : document original/actions accessibles, aucun contenu utile masqué. Oracles Galerie et validation responsive de chaque lot.

## Avant le premier lot

- [ ] Lire `CLAUDE.md`, `apps/web/CLAUDE.md`, `.claude/skills/lia-design/SKILL.md` et son guide ; consulter les guides Next.js installés pertinents avant de modifier les pages.
- [ ] Comparer le checkout aux empreintes `integration-preparation/source-baseline.json` ; relire tout fichier concerné qui a changé. La référence est le travail courant, pas un worktree distant supposé équivalent.
- [ ] Ouvrir les maquettes retenues et la spécification, puis vérifier les callers des primitives modifiées. Ne pas republier un rendu de comparaison à la place d’une route réelle.
- [ ] Relever les tests et gates déjà rouges dans le contexte courant ; les distinguer des régressions du lot, sans corriger des fichiers étrangers pour rendre un bilan artificiellement vert.

## Lot 1 — Présentation partagée, sans migration globale du design system

**Créer :** `apps/web/src/components/ui/section-header.tsx`, `timeline-group.tsx` et leurs tests `__tests__/section-header.test.tsx`, `timeline-group.test.tsx`.

**Modifier :** `components/ui/disclosure.tsx`, `components/settings/SettingsSection.tsx` et leurs tests actuels. Pas de modification de `Button`, `RowActions`, `Pagination` ou `globals.css` prévue pour ce lot.

**Interfaces :** `SectionHeader` fournit titre/icône/description, niveau de titre explicite, accessoire essentiel en ligne et commandes séparées. `TimelineGroup` nomme une section sans tri/date/API. `SettingsSection.headerAccessory?:ReactNode` est facultatif. `Disclosure.summaryContent?:ReactNode` remplace uniquement son résumé, non interactif ; `icon` devient facultative, `title:string` reste requis. Le défaut lazy et les anciens callers ne changent pas.

```tsx
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface SectionHeaderProps {
  id?: string;
  title: ReactNode;
  icon: LucideIcon;
  level: 1 | 2 | 3;
  description?: ReactNode;
  accessory?: ReactNode;
  actions?: ReactNode;
  className?: string;
}
interface TimelineGroupProps {
  headingId: string;
  heading: ReactNode;
  level: 2 | 3;
  children: ReactNode;
  className?: string;
}
```

- [ ] Ajouter les oracles FR/EN : niveaux et noms du titre, description, ordre des actions, absence de contrôles imbriqués dans `summary`, clavier Entrée/Espace, défaut fermé/lazy et appel `onOpenChange`.
- [ ] Ajouter les deux wrappers JSX purs selon ces contrats ; garder les icônes décoratives et labels du caller, les commandes distinctes et le retour à la ligne.
- [ ] Ajouter les deux extensions optionnelles ; préserver ancre `settings-section-…`, `tabIndex=-1`, state d’ouverture et montage différé. Tester un caller existant sans nouvelle prop avec son contrat initial.
- [ ] Exécuter les tests/gates appropriés et comparer les sections non sélectionnées qui consomment la primitive ; revue 320 px et titre long avant d’utiliser ces slots dans les lots suivants.

## Lot 2 — Accueil, priorité visuelle

**Modifier :** `components/dashboard/TodayBriefing.tsx`, `HeroLiaCard.tsx`, `BriefingSynthesis.tsx`, `QuickAccessCompact.tsx`, `BriefingCard.tsx`, `UsageStatistics.tsx`, `ResultsSummary.tsx`, les contenus de `cards/*Card.tsx` concernés. Préserver `CardItemActions`, audio, radio et hooks.

**Créer :** `DashboardDateHeading.tsx`, `BriefingSectionDialog.tsx`. Extraire seulement les contenus réellement partagés entre aperçu et lecteur, avec props typées `variant: 'preview'|'full'`, au lieu d’un second registre de données.

**Consomme :** `useBriefing`, `useBriefingPreferences`, les payloads `types/briefing.ts`, `useUserStatistics`, `user.timezone` et langue de la route.

- [ ] Étendre `TodayBriefing.logic/layout` et les tests des cartes avec une collection reçue longue, un total supérieur au payload, champ absent et échec partiel ; conserver toutes les actions listées dans l’inventaire Accueil.
- [ ] Tester la date sur un même instant Tokyo/Los Angeles et un navigateur dans une troisième zone ; minuit, compte/langue/fuseau changé, retour de visibilité, SSR/client stable. Fuseau absent/invalide : titre traduit Accueil, pas une date de compte inventée.
- [ ] Construire le H1 depuis `formatDate`/locale active et un fuseau validé, instant testable et mise à jour légère au changement de journée ; aucune API supplémentaire.
- [ ] Redistribuer les composants actuels : Chat puis Services mobile, raccourcis avant radio, tous contenus mobiles ouverts excepté personnalisation, commandes Mon dashboard conservées après la radio. L’écoute et le repli restent des contrôles frères.
- [ ] Composer les tuiles desktop de hauteur cohérente avec des aperçus bornés ; le lecteur réutilise le payload et les handlers du même propriétaire. Annoncer « éléments reçus/affichés » si le serveur borne la liste ; préserver les liens/actions existants vers les sources.
- [ ] Réorganiser consommations Période/Total avec cycle, cumul, cache, coûts, limites et valeurs absentes intactes. Tester échec/rafraîchissement sans fermer le lecteur ni perdre son focus ; aucune seconde instance audio/radio ou mutation à l’ouverture du lecteur.
- [ ] Revue desktop/mobile, textes agrandis et compteurs, puis gates/frontend et E2E dashboard existants.

## Lot 3 — Réunions

**Modifier :** `app/[lng]/dashboard/meetings/page.tsx`, conserver `MeetingSelectionBar`, `MeetingStatusBadge`, `useMeetingList` et propriétaire de sélection/offset.

**Créer :** `components/meetings/MeetingTimelineEntry.tsx`, projection temporelle pure dans un module de ce domaine ; utiliser `TimelineGroup`.

- [ ] Étendre `app/[lng]/dashboard/meetings/__tests__/page.test.tsx`, `components/meetings/__tests__/MeetingPage.account.test.tsx` et `hooks/__tests__/useMeetings.test.ts` : `stopped_at` réel, null, timestamp invalide, titre long, état de traitement, source nullable, IDs sélectionnés, suppression partiellement refusée et page vidée.
- [ ] Projeter la page reçue en journées et plages de lecture dans le fuseau explicitement utilisé pour l’affichage. Ne pas annoncer un `client_timezone` de capture absent du DTO summary. Chaque ID reçu reste représenté une fois, ordre serveur conservé.
- [ ] Disposition desktop : début puis fin dessous, case et titre sur une ligne, texte de détail aligné au texte du titre. Mobile : horloge + début/fin, statut indépendant s’il ne tient pas, titre puis détails fermés.
- [ ] Garder le titre comme lien réel vers le CR et la case indépendante avec nom associé. Ajouter un contrôle distinct de détails locaux mobile, sans lien/case/action imbriquée dans son résumé.
- [ ] Déplacer le pager sous les groupes ; conserver origine de retour, suppression confirmée, guards account/busy et feedback par ID. Tests clavier et `meetings-back-navigation.spec.ts` avant revue de composition.

## Lot 4 — Appels récents

**Modifier :** `components/settings/TelephonyCallsSection.tsx` ; préserver `useTelephonyCalls`, `CallDecisions`, `CallDebrief`.

**Créer :** `components/telephony/CallTimelineEntry.tsx`, adaptateur pur des horaires de suivi dans ce domaine. Le `Disclosure` étendu sert de repli, pas un nouveau moteur d’accordéon.

- [ ] Étendre `TelephonyCallsSection.test.tsx` et `hooks/__tests__/useTelephonyCalls.test.ts` : actif/polling, tous les statuts/outcomes/kinds/modes/relay, informations et coût, nullable data et compte changé.
- [ ] Tester priorité `completed_at`, calcul ≈ si données exploitables, durée 0/null/invalide, timestamp invalide, clôture manquante. Nommer les horaires comme suivi/lancement/clôture ; ne pas les vendre comme début/fin audibles.
- [ ] Fournir un `summaryContent` natif non interactif avec horaires avant identité mobile, état et badges lisibles. Pas d’icône téléphone de fiche mobile ; horloge temporelle. Desktop fin sous début, statut à droite et autres informations sous le titre.
- [ ] Garder décisions, suites et coût derrière le corps lazy ; leurs boutons restent les vrais intents/handlers. Ne pas ajouter une pagination à une liste des derniers appels ni charger tout l’historique pour la frise.
- [ ] Vérifier ouverture clavier, focus des commandes, absence de global fold et présence de toutes les informations au repli/dépliage.

## Lot 5 — Notifications

**Modifier :** `components/notifications/NotificationsHub.tsx`, `HubSection.tsx` et présentation des listes spécialisées.

**Créer/modifier ciblé :** adaptateur local de pagination des routines complètes ; ne pas transformer `usePagedSection` pour les autres endpoints paginés.

- [ ] Étendre `NotificationsHub.test.tsx`, `OpenOffersList.test.tsx`, `ScheduledActionsList.test.tsx` et les tests des hooks hub/paged : familles indépendantes, volet fermé sans query, échec avant empty, refetch stable, décisions sans navigation sur refus.
- [ ] Conserver les sept types de liste et leur tri/données propres. Regrouper seulement les éléments disponibles en gardant direction, statuts, contenu purgé/retained et actions exactes.
- [ ] Placer en-tête/commandes selon `SectionHeader` et conserver la pagination existante sous chaque famille. Pas de pagination globale artificielle.
- [ ] Corriger l’adaptateur routines : une réponse du GET actuel, total local du payload et tranches de dix, remise à zéro conforme au hook. Ne pas envoyer `limit/offset` comme preuve d’une pagination que le serveur n’effectue pas. Tests avec plus d’une tranche, dernier bloc partiel et erreur/refetch.
- [ ] Revue des états conditionnels, clavier/320 px, activités/réglages et non-régression des intents ; parcours hermétique avec réponses API de vraie forme.

## Lot 6 — Formats de réponse illustrés

**Modifier :** `components/settings/CardsDisplaySettings.tsx` et tests actuels.

**Créer :** `components/settings/ResponseDisplayPreview.tsx`, props `mode: 'cards'|'html'|'html_cards'|'markdown'`, `lng: Language`, présentation pure.

- [ ] Étendre `CardsDisplaySettings.test.tsx` : quatre valeurs exactes, choix initial, no-op, persistance refusée/retry, focus, FR/EN et zéro appel dans l’aperçu.
- [ ] Garder le handler/store de préférence actuel. Composer choix desktop à côté de l’exemple ; choix puis exemple simple sur mobile. Chaque exemple est traduit et nommé comme illustratif.
- [ ] Rendre le même jeu d’exemple contrôlé en JSX dans les quatre compositions, sans HTML externe, iframe, vrai bouton factice ou requête fournisseur.
- [ ] Garder descriptions existantes et application aux futures réponses ; ne pas promettre les mêmes données littérales dans toutes les réponses ni modifier le thème clair/sombre.

## Lot 7 — Aperçus documentaires dans la galerie conservée

**Modifier :** `components/settings/generated-assets/GeneratedAssetGrid.tsx`, extraction minimale de `components/chat/GeneratedDocumentPreview.tsx`.

**Créer :** `components/documents/DocumentSourcePreview.tsx`, noyau partagé, props dérivées des contrats actuels avec variante passive `gallery`. Réutiliser `lib/document-preview.ts` et URL helpers.

- [ ] Étendre `GeneratedAssetsSettings.test.tsx`, `GeneratedDocumentPreview.test.tsx`, `.names.test.tsx` et `generated-assets-gallery.spec.ts` : vrai PNG PDF mocké, extraits Office/texte, MIME inconnu, refus/expiration/erreur et overlay d’action indépendant.
- [ ] Remplacer seulement la vignette documentaire éligible ; images/captures/bookmarks, grille, filtres, durée, sélection, metadata et actions de production restent identiques.
- [ ] Extraire le noyau de rendu/lecture existant ; variante Galerie sans bouton Lightbox imbriqué dans le lien étiré. « Première page » uniquement PDF ; « Extrait » Office/texte. Pas d’import PDF.js ou autre renderer.
- [ ] Chargement visible/lazy, bornes existantes, annulation d’extrait en quittant l’onglet/compte, fallback stable avec accès à l’original. Ne pas déclencher toutes les previews d’un onglet caché ni un retry automatique en boucle.
- [ ] Comparer carte avant/après à mêmes dimensions : seule vignette document modifiée. Garder la régression des formats chat ; rejouer les tests serveur preview uniquement si le moteur serveur est modifié, ce qui n’est pas prévu.

## Lot 8 — Style de LIA

**Modifier :** `components/settings/PersonalitySettings.tsx`, sa suite, et seulement si reproduit le risque ciblé du `stores/personalityStore.ts`.

- [ ] Étendre tests de composant/hook/store avec catalogues 0/1/nombreux, défaut/null, descriptions longues, sélection refusée et réponse différée A→B. Vérifier synchronisation header↔réglages.
- [ ] Composer scène courante et catalogue dynamique depuis le DTO. Retirer contrôles redondants, conserver le choix directement accessible, état selected/focus sans liseret, animations existantes facultatives/reduced motion.
- [ ] Garder le contrôle focalisé pendant updating avec garde de double submit. Conserver données pendant refreshing et vrai retry au premier échec.
- [ ] Reproduire d’abord l’application d’une ancienne réponse après changement de compte ; corriger seulement ce chemin avec garde propriétaire/génération si confirmé. Rerelecture Psyché passive, nullable et liée au compte, sans créer un état pour la présentation.
- [ ] Vérifier le catalogue absent sans persona inventée et l’effet réel de sélection ; aucune administration ou modification des avatars du header.

## Lot 9 — Psyché, état lisible et point permanent sans facture implicite

**Modifier :** `components/settings/PsycheSettings.tsx`, `components/psyche/PsycheLLMSummary.tsx`, `PsycheStateSummary.tsx`, `PsycheHistory.tsx` pour leur présentation.

**Créer :** `hooks/usePsycheSummary.ts`, hook de commande borné lié au compte, sans effet de génération ; tests dédiés. `PsycheStatePanels.tsx` seulement si l’extraction des panneaux évite de grossir le composant.

```ts
interface PsycheSummaryCommand {
  summary: string | null;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error: Error | null;
  generate: () => Promise<boolean>;
  clear: () => void;
}
// usePsycheSummary({ lng, canGenerate }) produit ce contrat.
// generate est l’unique chemin du GET existant ; clear reste local.
```

- [ ] Étendre `PsycheSettings`, `PsycheLLMSummary`, `PsycheHistory` et `usePsyche.application` : état null/disabled/loading, quatre périodes/catégories, métriques et émotions réellement disponibles, resets attestés et erreurs.
- [ ] Ajouter oracles du nouveau hook : zéro GET au montage/OFF-ON/SSE/resize, un GET par commande, double clic gardé, erreur sans retry automatique, ancien texte durant refresh, abort/unmount, langue/compte changé et clear après reset sans génération.
- [ ] Placer switch en `SettingsSection.headerAccessory`, puis Comprendre/Réglages/Réinitialisations en lignes séparées. Garder confirmations soft/full, sliders au commit et callbacks actuels.
- [ ] Rendre Le point de LIA permanent avant humeur. Premier état explicite non généré, commande en haut ; ensuite contenu réel/Actualiser. Afficher le chargement/échec sans supprimer un texte reçu ; aucune donnée de coût/date ajoutée depuis la fixture.
- [ ] Restyler instruments depuis le vrai état, OCEAN réel et les quatre branches Recharts existantes. Une table/lecture mobile utilise la même projection que son graphique ; aucun tronquage arbitraire d’émotions ni série fictive.
- [ ] Garder les historiques différés et le store numérique SSE existant ; ne pas utiliser un refresh d’état ou une animation comme déclencheur LLM. Parcours hermétique Psyché avec request-count, refus/retry, reset et clavier.

## Lot 10 — Connexions LIA

**Modifier :** `components/settings/PeerConnectionsSettings.tsx`, `peers/PeerConnectionCard.tsx`, `PeerDiscoveryBlock.tsx`, `PeerRequestsBlock.tsx`, `PeerVisibilityCard.tsx`, `PeerBlocksBlock.tsx`, `PeerAccessLogBlock.tsx`.

- [ ] Conserver et étendre les suites peers/component/hook et `peer-connections.spec.ts` : flags off sans query, demande entrante/sortante, masquage email, droits de partage, refus neutre, confirmation annulée, refetch pendant saisie et compte obsolète.
- [ ] Composer visibilité/blocages/journal en trois replis verticaux ; recherche toujours montée juste avant demandes/connexions. Conserver brouillons et résultats dans leur parent, pas dans un repli nouvellement démonté.
- [ ] Composer la fiche repliable puis reçu/envoyé en deux colonnes égales desktop, reçu d’abord dans le DOM ; pile mobile. Reçu n’a aucun contrôle d’édition ; envoyé conserve vrais Select/Switch/ids et descriptions de consentement.
- [ ] Préserver confirmations de retrait/blocage, callbacks et `PeerActionResult`; distinguer mutation attestée et rerelecture pas encore terminée. Pas de succès supposé ni toast révélant un compte caché.
- [ ] Vérifier nom/adresse longs, état busy avec focus, recherche/contextes après fermeture/réouverture, liens de réglages et intégralité des champs utiles du journal.

## Lot 11 — Réglages réunions et vraie auto-application

**Modifier :** `components/settings/MeetingsSettings.tsx`, branchement limité dans `app/[lng]/dashboard/layout.tsx`, et composition de `MeetingTemplateLibrary/Manager` si requise, sans perdre leurs formulaires/actions.

**Créer :** `components/meetings/MeetingPreferenceSaveProvider.tsx` et son consumer `hooks/useMeetingPreferenceAutosave.ts`. Le propriétaire de file est au layout dashboard, lié au compte, et demeure monté lorsqu’une autre section/page s’ouvre. Le précédent est `MeetingRecorderProvider` ; une file placée seulement dans `MeetingsSettings` perdrait ses écritures en attente au démontage par `SettingsPane`.

**Interface :** contexte exposant préférences confirmées, brouillon, état pending/erreur et commandes `activate()`, `apply(patch: Partial<MeetingPreferencesUpdate>)`, `retry()`. La file assemble le PUT complet actuel ; aucune nouvelle shape serveur. `useMeetingPreferences(enabled)` existe déjà : garder `enabled=false` avant première consultation, une seule lecture et un seul `save` sous le provider activé. Aucun appel de préférence sur toutes les pages avant activation, aucun état de file dans localStorage.

- [ ] Étendre `MeetingsSettings.test.tsx`, `useMeetingPreferences.application.test.tsx`, `useMeetingTemplateAndPreferences.test.ts`, les suites TemplateLibrary/Manager/Form/Editor avec tous les droits, catégories, quotas et types de champs existants.
- [ ] Caractériser deux modifications pendant un PUT retardé puis échec : dernier brouillon doit subsister, prochain PUT doit reprendre tous les champs actuels, aucun toast tardif ni ancienne réponse écrasant la valeur récente.
- [ ] Implémenter file d’écriture sérialisée par compte : dernier DTO confirmé, changements/brouillon/version récente, un PUT actif, prochain envoi après succès si une intention plus récente existe. En échec, conserver draft et erreur avec retry ; pas de boucle de retry silencieuse. Réactivation/repli ne remet pas une ancienne version en file.
- [ ] Select/Switch valides appliqués immédiatement ; conservation audio validée à blur/commit, pas chaque chiffre. La file continue au même compte après navigation SPA hors du réglage ; un changement de compte/drop du provider abandonne les intentions non envoyées et ignore les réponses/toasts obsolètes. État pending visible dans le réglage, erreur propriétaire signalée par le feedback existant ; pas de nouvelle confirmation de navigation.
- [ ] Tester deux changements suivis immédiatement d’un départ vers Accueil puis retour : second PUT attesté, dernière intention conservée ; vérifier que le branchement ne remonte ni recorder ni radio. Une fermeture/reload complet avant acquittement serveur ne constitue pas une garantie de persistance offline : ne pas présenter le brouillon pending comme enregistré.
- [ ] Réorganiser titre, lien direct avec total réel, audio sous email, bibliothèques privées/intégrées distinctes. Supprimer Save seulement après construction/test de ce contrat ; les créations/éditions de modèles gardent leur validation.
- [ ] Revue de toutes les actions conditionnelles du modèle et des récents ; test fermeture/réouverture en vol, sortie du réglage, retry et retours réels.

## Lot 12 — Export consommation

**Modifier :** `components/settings/ConsumptionExportSection.tsx`, suites actuelles et présentation user uniquement. Le composant partagé ne doit pas casser son caller administrateur.

**Créer :** `hooks/useConsumptionExport.ts` pour la commande de téléchargement si nécessaire à la garde compte/abort/nettoyage ; consommer `apiClient.getResponse` et les chemins existants.

- [ ] Étendre les tests de dates/autocomplete/composant et un test du helper : cinq types exacts, BOM/filename attendu, champ invalid/ordre des bornes, réponse vide valide, 401/403/réseau/timeout, absence de header, click échoué, URL révoquée et compte changé avant réponse.
- [ ] Composer registre, bouton Télécharger à droite du titre desktop, description directement dessous ; mobile description pleine largeur et commande avec icône. Labels Du/Au et wrappers Input bornés sur leur ligne ; presets restent complets même s’ils doivent revenir à la ligne dans une langue longue.
- [ ] Préserver dates civiles `YYYY-MM-DD`, chaînes vides de Tout et params/API existants. Ne pas ajouter `timezone` ni modifier l’intervalle serveur en silence. Aucune sélection `user_id` en mode utilisateur.
- [ ] Remplacer seulement le transport manuel par le client partagé, garder nom du fichier et une raison d’erreur traduite ; garde busy/double départ, annulation/réponse obsolète, cleanup de l’ancre/blob en finally. Pas de téléchargement obsolète déclenché après connexion sur un autre compte.
- [ ] Vérifier visuellement le caller admin inchangé et ses tests de non-régression, sans lui appliquer la composition utilisateur ; conventions temporelles serveur restantes documentées comme chantier distinct.

## Clôture de chaque lot et du chantier

- [ ] Revue substance/forme : champs, actions, loading/empty/error/refus, focus, données nombreuses, source nullable, compte et vie des requêtes. Ne pas traiter le succès d’une fixture comme preuve de comportement live.
- [ ] Passer les gates Taskfile adaptés : `lint:frontend`, `lint:i18n`, `test:frontend`, puis `test:frontend:coverage` pour comportements affectés. `lint` pour les changements transversaux ; tsc host propre si requis.
- [ ] Passer les parcours hermétiques sur les routes Next.js ; `task test:e2e` et la matrice navigateur selon l’impact. Runtime dans le workflow Docker, API/LLM/fournisseurs interceptés et zéro requête externe non maîtrisée.
- [ ] Revue visuelle clair/sombre/OLED, tous écrans à 320/390 et desktop, formats intermédiaires, DE et texte agrandi. Vérifier les accents des assemblages nouveaux avec le garde de contraste actuel.
- [ ] Publier le bilan exact des commandes, sorties, compteurs, warnings et limites, ainsi que les captures de l’application. Les preuves des maquettes restent distinctes.
- [ ] Examiner le diff limité au chantier. Une publication ultérieure autorisée nécessite ses gates, dont `task ci:fast` ; aucun déploiement n’est prévu par ce plan.

## État de la préparation

Les cases de travail restent ouvertes parce que l’implémentation n’a pas commencé. La préparation a confronté les écrans aux sources et défini des lots et oracles ; elle n’a pas exécuté les tests applicatifs. Les inventaires locaux donnent les références `fichier:ligne`, les DTO et endpoints de chaque domaine. Reprendre les décisions documentées ci-dessus lors de l’exécution ; ne pas recopier les comportements illustratifs du comparateur.
