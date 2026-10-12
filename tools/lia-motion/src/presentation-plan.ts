import type { FeatureKey } from './content';

/** Editorial scope is independent from the provenance of a rendered shot. */
export type FeatureScreenKind =
  | 'briefing-radio'
  | 'memory'
  | 'routines'
  | 'voice-meetings'
  | 'workboard'
  | 'knowledge'
  | 'creation'
  | 'ecosystem'
  | 'appearance'
  | 'notifications'
  | 'administration'
  | 'mobile';

export type PresentationChapterKind = FeatureScreenKind | 'avatars' | 'intro' | 'context' | 'control' | 'finale';
export type PresentationFocusKind = FeatureScreenKind | 'avatars';
export type PresentationLayout = 'left' | 'right' | 'top' | 'full';
/** A shot holds its geometry. Only its declared native focus may be enlarged. */
export type PresentationEffect = 'hold';
export type PresentationTitle = readonly [string] | readonly [string, string];
export type FeatureScreenVariant =
  | 'base' | 'conversation' | 'avatars' | 'memory' | 'relations' | 'peers'
  | 'radio' | 'routines' | 'proactive' | 'habits' | 'workboard' | 'voice'
  | 'phone' | 'meetings' | 'knowledge' | 'creation' | 'extensions'
  | 'connectors' | 'health' | 'journals' | 'control' | 'mobile' | 'admin' | 'simli'
  | 'display' | 'notifications' | 'planning' | 'registry' | 'llm-config' | 'platform';

export interface PresentationNativeShot {
  detail: string;
  /** Index in FEATURE_SCREEN_FOCUSES; no implicit or decorative camera target. */
  focusTarget?: 0 | 1;
  /** Wait for a declared modal/state to exist before its crop can appear. */
  focusFromSeconds?: number;
}

/** Each focus names an actual source UI element. Absent target = fixed full view. */
export const PRESENTATION_NATIVE_SHOTS: Readonly<Record<FeatureScreenKind, readonly PresentationNativeShot[]>> = {
  'briefing-radio': [{detail:'today',focusTarget:0},{detail:'radio',focusTarget:1}],
  memory: [{detail:'memories',focusTarget:0},{detail:'relations-central',focusTarget:0}],
  routines: [{detail:'planning'},{detail:'conditional',focusTarget:0},{detail:'registry',focusTarget:0}],
  'voice-meetings': [{detail:'meeting',focusTarget:0},{detail:'phone',focusTarget:0}],
  workboard: [{detail:'board',focusTarget:0},{detail:'ticket',focusTarget:1}],
  knowledge: [{detail:'space',focusTarget:1},{detail:'attachments',focusTarget:0}],
  creation: [{detail:'files',focusTarget:0},{detail:'images',focusTarget:0}],
  ecosystem: [{detail:'skills',focusTarget:0},{detail:'mcp',focusTarget:0},{detail:'peers',focusTarget:0}],
  appearance: [{detail:'display-cards',focusTarget:0},{detail:'display-html',focusTarget:0}],
  notifications: [{detail:'reminder',focusTarget:1}],
  administration: [{detail:'users',focusTarget:0},{detail:'llm-pricing',focusTarget:0},{detail:'llm-config',focusTarget:1},{detail:'platform-health',focusTarget:0}],
  mobile: [{detail:'pwa-mobile'},{detail:'pwa-install',focusTarget:0}],
};

export const PRESENTATION_FOCUS_SHOTS: Readonly<Partial<Record<FeatureScreenVariant, readonly PresentationNativeShot[]>>> = {
  memory:[{detail:'memories',focusTarget:0},{detail:'psyche',focusTarget:0}],
  relations:[{detail:'relations-central',focusTarget:0},{detail:'relations-central',focusTarget:1}],
  peers:[{detail:'peers',focusTarget:0}], radio:PRESENTATION_NATIVE_SHOTS['briefing-radio'],
  routines:[{detail:'scheduled',focusTarget:0},{detail:'conditional',focusTarget:0}],
  proactive:[{detail:'heartbeat',focusTarget:1},{detail:'conditional',focusTarget:0}],
  habits:[{detail:'habits',focusTarget:0}], workboard:PRESENTATION_NATIVE_SHOTS.workboard,
  voice:[{detail:'voice',focusTarget:0},{detail:'live',focusTarget:0}],
  phone:[{detail:'phone',focusTarget:0}], meetings:[{detail:'meeting',focusTarget:0},{detail:'transcript',focusTarget:0}],
  knowledge:PRESENTATION_NATIVE_SHOTS.knowledge, creation:PRESENTATION_NATIVE_SHOTS.creation,
  extensions:[{detail:'skills',focusTarget:0},{detail:'plugins',focusTarget:0},{detail:'mcp',focusTarget:0}],
  connectors:[{detail:'connectors',focusTarget:0}], health:[{detail:'health',focusTarget:0}],
  journals:[{detail:'journals',focusTarget:0}], mobile:PRESENTATION_NATIVE_SHOTS.mobile,
  admin:[{detail:'users',focusTarget:0},{detail:'llm-pricing',focusTarget:0}],
  simli:[{detail:'simli',focusTarget:0}], display:PRESENTATION_NATIVE_SHOTS.appearance,
  notifications:PRESENTATION_NATIVE_SHOTS.notifications,
  planning:[{detail:'planning'},{detail:'scheduled',focusTarget:0}],
  registry:[{detail:'registry',focusTarget:0}], 'llm-config':[{detail:'llm-config',focusTarget:0,focusFromSeconds:3.5}],
  platform:[{detail:'platform-health',focusTarget:0},{detail:'platform-health',focusTarget:1}],
};

export interface PresentationChapter {
  id: string;
  kind: PresentationChapterKind;
  durationSeconds: number;
  title: PresentationTitle;
  detail: string;
  features: readonly FeatureKey[];
  /** Additional editorial subjects; never added to the canonical key inventory. */
  editorialTopics?: readonly string[];
  layout: PresentationLayout;
  effect: PresentationEffect;
  accent: `#${string}`;
  /** Production direction, never a product UI label. */
  direction: string;
  nativeAssets: readonly string[];
  evidence: readonly string[];
  /** Only a capability-specific qualification shown when relevant. */
  note?: string;
}

export const PRESENTATION_FPS = 30;
/** Source revision is distinct from the export pipeline generation. */
export const PRESENTATION_REVISION = 'v6';
export const PRESENTATION_NOTE = 'Démonstration scénarisée · données fictives';

/** Four uses carry the film; the feature keys do not become a screen of labels. */
export const PRESENTATION_CHAPTERS: readonly PresentationChapter[] = [
  {
    id: 'a-day-with-lia', kind: 'intro', durationSeconds: 4,
    title: ['Ta journée.', 'LIA à tes côtés.'],
    detail: 'Pose ta demande. LIA retrouve les informations et prépare les actions.',
    features: ['natural_language', 'mood_face'],
    layout: 'full', effect: 'hold', accent: '#2c56c4',
    direction: 'BIP accueille avec une expression et un regard. Le champ de saisie apparaît à position fixe. Aucun avatar dans la navigation de l’écran.',
    nativeAssets: ['chat', 'avatars'],
    evidence: ['apps/web/src/components/chat/ChatInput.tsx', 'apps/web/src/components/eyes/ExpressiveEyes.tsx'],
  },
  {
    id: 'a-companion-in-context', kind: 'avatars', durationSeconds: 18,
    title: ['Des designs', '100% originaux.'],
    detail: 'Lumo masculin et tous les styles natifs, animés selon le contexte.',
    features: ['mood_face', 'personalities'],
    editorialTopics: ['native_avatar_contexts', 'lumo_masculine'],
    layout: 'left', effect: 'hold', accent: '#7c5cf6',
    direction: 'Lumo masculin natif montre les contextes illustrés, puis le catalogue complet demeure lisible dans un seul plan fixe. BIP est la mascotte unique hors écran ; aucun écran ne se déplace.',
    nativeAssets: ['avatars'],
    evidence: ['apps/web/src/components/eyes/ExpressiveEyes.tsx', 'apps/web/src/components/eyes/eye-styles.ts', 'apps/web/locales/fr/translation.json'],
    note: 'Contextes et expressions scénarisés · avatars natifs animés.',
  },
  {
    id: 'choose-how-to-read', kind: 'appearance', durationSeconds: 7,
    title: ['Le même résultat.', 'Ta façon de le lire.'],
    detail: 'Cartes, HTML, HTML + cartes ou Markdown : tu choisis.',
    features: ['rich_responses', 'simplicity'],
    editorialTopics: ['response_display_modes'],
    layout: 'right', effect: 'hold', accent: '#2c56c4',
    direction: 'Les quatre modes natifs restent visibles. Montrer d’abord Cartes HTML, puis HTML enrichi et le texte explicatif actif dans le vrai sélecteur. Les champs illustrent un choix configurable ; ne pas prétendre montrer une réponse réellement reformatée. Aucun mode « bulles » inventé.',
    nativeAssets: [], evidence: ['apps/web/src/components/settings/CardsDisplaySettings.tsx'],
  },
  {
    id: 'read-or-listen', kind: 'briefing-radio', durationSeconds: 8,
    title: ['Ta journée,', 'à lire ou à écouter.'],
    detail: 'Ton briefing et ta Radio, selon les sources choisies.',
    features: ['briefing', 'personal_radio'],
    layout: 'left', effect: 'hold', accent: '#2c56c4',
    direction: 'Briefing puis Radio en deux vues fixes. Un focus déclaré sur la synthèse ou la transcription peut apparaître sans déplacer le parent.',
    nativeAssets: ['briefing', 'radio'],
    evidence: ['apps/web/src/components/dashboard/TodayBriefing.tsx', 'apps/web/src/components/radio/RadioPage.tsx', 'apps/web/src/components/radio/RadioArticles.tsx', 'docs/technical/RADIO.md'],
  },
  {
    id: 'the-reminder-reaches-you', kind: 'notifications', durationSeconds: 5,
    title: ['Le rappel arrive.', 'Le fil reste ouvert.'],
    detail: 'La notification de démonstration ramène au rendez-vous.',
    features: ['reminders_scheduling'],
    editorialTopics: ['reminder_notification'],
    layout: 'left', effect: 'hold', accent: '#2c56c4',
    direction: 'Une notification de rappel native devient le point de passage entre le programme du matin et Relations. Son libellé et son type restent ceux du produit ; le film ne fait pas passer une fixture pour une notification effectivement livrée.',
    nativeAssets: [], evidence: ['apps/web/src/components/notifications/NotificationsHub.tsx', 'apps/web/src/components/notifications/PendingRemindersList.tsx', 'apps/web/src/hooks/useNotifications.ts'],
    note: 'Notification scénarisée · aucun rappel réellement déclenché.',
  },
  {
    id: 'keep-the-context', kind: 'memory', durationSeconds: 10,
    title: ['Une personne.', 'Le contexte réuni.'],
    detail: 'Coordonnées, échanges, préférences et engagements au même endroit.',
    features: ['memory', 'personal_crm', 'bookmarks'],
    layout: 'right', effect: 'hold', accent: '#7c5cf6',
    direction: 'Deux vues fixes : préférence mémorisée et fiche Relations centralisée. Un focus déclaré peut montrer les engagements et échanges sans déplacer les autres sections.',
    nativeAssets: ['memory', 'relations'],
    evidence: ['apps/web/src/components/settings/MemorySettings.tsx', 'apps/web/src/components/relations/RelationDetailPanel.tsx', 'apps/web/src/components/relations/RelationProviderSections.tsx', 'apps/web/src/components/relations/RelationCardList.tsx'],
  },
  {
    id: 'prepare-the-meeting', kind: 'context', durationSeconds: 13,
    title: ['Une demande.', 'Tes sources réunies.'],
    detail: 'Messages, documents et agenda réunis pour ton rendez-vous.',
    features: ['multi_agent', 'connected_services', 'rich_responses', 'attachments', 'computed_answers', 'web_intelligence'],
    layout: 'top', effect: 'hold', accent: '#2c56c4',
    direction: 'Le fil natif reste fixe. Sources puis divergence de dates reçoivent des focus déclarés ; le bloc DL est recadré comme un seul objet sans changer sa largeur ni son retour à la ligne.',
    nativeAssets: ['chat', 'dossier'],
    evidence: ['tools/lia-motion/src/FaithfulUi.tsx', 'tools/lia-motion/src/ProductStory.tsx', 'apps/web/src/styles/lia-components.css', 'apps/web/e2e/capture/landing-proof-data.ts'],
  },
  {
    id: 'find-the-decision', kind: 'knowledge', durationSeconds: 8,
    title: ['Retrouve la décision.', 'Avec sa source.'],
    detail: 'Tes documents et les fils que tu choisis.',
    features: ['rag_spaces', 'mail_label_spaces'],
    layout: 'top', effect: 'hold', accent: '#7c5cf6',
    direction: 'Espace de connaissances puis import dans deux plans fixes. Les documents ou la zone d’import sont les seuls éléments déclarés pour un focus.',
    nativeAssets: ['knowledge'],
    evidence: ['apps/web/src/app/[lng]/dashboard/spaces/[id]/page.tsx', 'apps/web/src/components/landing/editorial/chapters-data.ts'],
  },
  {
    id: 'talk-and-revisit', kind: 'voice-meetings', durationSeconds: 10,
    title: ['Parler. Puis retrouver', 'ce qui compte.'],
    detail: 'Voix, Live, appels et comptes rendus gardent le fil.',
    features: ['voice_mode', 'live_voice', 'telephony', 'meetings', 'meeting_templates'],
    layout: 'left', effect: 'hold', accent: '#2c56c4',
    direction: 'Compte rendu puis débrief d’appel en deux vues fixes. Un focus déclaré porte sur les décisions ou le débrief, sans session Live ni parole fournisseur prétendument exercée.',
    nativeAssets: ['meetings', 'voice', 'live', 'phone'],
    evidence: ['apps/web/src/components/meetings/MeetingReportView.tsx', 'apps/web/src/components/settings/VoiceModeSettings.tsx', 'apps/web/src/components/settings/LiveModeSettings.tsx', 'apps/web/src/components/settings/TelephonyCallsSection.tsx', 'docs/technical/LIVE_MODE.md', 'docs/technical/MEETINGS.md'],
    note: 'Interfaces et débrief de démonstration · aucun appel ou Live fournisseur exercé.',
  },
  {
    id: 'delegate-the-work', kind: 'workboard', durationSeconds: 8,
    title: ['Confie une tâche.', 'Retrouve son suivi.'],
    detail: 'Le ticket garde les échanges, les décisions et le résultat.',
    features: ['workboard', 'workboard_delegation'],
    layout: 'right', effect: 'hold', accent: '#2c56c4',
    direction: 'Tableau puis ticket dans deux vues fixes. Le focus est réservé au ticket détenu par LIA ou à sa dernière exécution fictive.',
    nativeAssets: ['workboard'],
    evidence: ['apps/web/src/components/workboard/WorkboardPage.tsx', 'docs/technical/WORKBOARD.md'],
  },
  {
    id: 'make-the-deliverables', kind: 'creation', durationSeconds: 9,
    title: ['Du rendez-vous', 'aux livrables.'],
    detail: 'Retrouve tes fichiers et choisis les options de génération.',
    features: ['document_generation', 'image_generation', 'excalidraw', 'generated_files', 'email_share'],
    layout: 'full', effect: 'hold', accent: '#2c56c4',
    direction: 'Galerie puis options d’image dans des vues fixes. Un aperçu de fichier existant peut être agrandi comme un extrait exact ; aucun résultat fournisseur ni schéma Excalidraw inventé.',
    nativeAssets: ['files', 'images'],
    evidence: ['apps/web/src/components/settings/GeneratedAssetsSettings.tsx', 'apps/web/src/components/settings/generated-assets/GeneratedAssetGrid.tsx', 'apps/web/src/components/settings/ImageGenerationSettings.tsx', 'apps/web/src/components/chat/GeneratedDocumentPreview.tsx', 'apps/web/src/components/landing/editorial/chapters-data.ts'],
    note: 'Fichiers de démonstration · capacités et réglages illustrés.',
  },
  {
    id: 'choose-the-moment', kind: 'routines', durationSeconds: 12,
    title: ['Au moment', 'que tu choisis.'],
    detail: 'Actions planifiées, conditions et registre gardent le suivi lisible.',
    features: ['reminders_scheduling', 'conditional_routines', 'proactive', 'proactive_wake', 'proactive_moments'],
    layout: 'left', effect: 'hold', accent: '#2c56c4',
    editorialTopics: ['planned_actions', 'action_registry'],
    direction: 'Planning complet, condition puis registre dans trois vues fixes. Seuls les éléments explicitement déclarés reçoivent un focus ; états et horaires restent fictifs.',
    nativeAssets: ['routines', 'heartbeat'],
    evidence: ['apps/web/src/components/settings/ScheduledActionsSettings.tsx', 'apps/web/src/components/settings/ScheduledActionsTimeline.tsx', 'apps/web/src/components/settings/RoutineNumberChip.tsx', 'apps/web/src/components/effects/RegistersPage.tsx', 'apps/web/src/components/effects/EffectsJournal.tsx', 'apps/web/src/components/effects/RegisterRow.tsx', 'apps/web/src/components/settings/HeartbeatSettings.tsx', 'apps/web/src/hooks/useScheduledActions.ts'],
  },
  {
    id: 'tools-and-circle', kind: 'ecosystem', durationSeconds: 10,
    title: ['Tes outils.', 'Tes connexions.'],
    detail: 'Compétences ajoutées et assistants connectés à ton choix.',
    features: ['skills', 'plugins', 'mcp', 'mcp_apps', 'sub_agents', 'peers', 'peer_shares'],
    layout: 'right', effect: 'hold', accent: '#7c5cf6',
    direction: 'Compétences, configuration MCP et connexions volontaires dans des vues fixes. Seuls les éléments natifs déclarés reçoivent un focus, sans exécution d’outil externe.',
    nativeAssets: ['skill', 'extensions', 'plugins', 'mcp', 'peers'],
    evidence: ['apps/web/src/components/chat/SkillAppWidget.tsx', 'apps/web/src/components/settings/SkillsSettings.tsx', 'apps/web/src/components/settings/PluginsSettings.tsx', 'apps/web/src/components/settings/MCPServersSettings.tsx', 'apps/web/src/components/settings/PeerConnectionsSettings.tsx'],
  },
  {
    id: 'run-your-instance', kind: 'administration', durationSeconds: 12,
    title: ['Ton instance.', 'Ses réglages visibles.'],
    detail: 'Utilisateurs, prix LLM, modèles et santé de la plateforme.',
    features: ['usage_limits'],
    editorialTopics: ['admin_users', 'llm_pricing', 'llm_configuration', 'platform_health'],
    layout: 'right', effect: 'hold', accent: '#2c56c4',
    direction: 'Quatre vues fixes : utilisateurs, tarifs, configuration et santé de plateforme. Le modal natif peut apparaître sans déplacement du cadre ; aucun réglage ni diagnostic réellement exécuté.',
    nativeAssets: [], evidence: ['apps/web/src/components/settings/AdminUsersSection.tsx', 'apps/web/src/components/settings/AdminLLMPricingSection.tsx', 'apps/web/src/components/settings/AdminLLMConfigSection.tsx', 'apps/web/src/components/settings/AdminDiagnosticsSection.tsx'],
    note: 'Administration de démonstration · données et réglages fictifs, aucune modification appliquée.',
  },
  {
    id: 'keep-the-decision', kind: 'control', durationSeconds: 10,
    title: ['Avant d’agir,', 'tu confirmes.'],
    detail: 'Contenu, destinataire et coût restent visibles.',
    features: ['control', 'usage_limits', 'privacy'],
    layout: 'top', effect: 'hold', accent: '#2c56c4',
    direction: 'Le fil natif reste fixe. Aperçu du brouillon, accord puis coût après confirmation sont des éléments de focus déclarés. Aucun envoi réel présenté comme testé.',
    nativeAssets: ['approval', 'administration'],
    evidence: ['apps/web/src/components/chat/HitlActionCard.tsx', 'apps/web/src/hooks/usePendingHitlSync.ts', 'apps/web/src/components/settings/AdminUsageLimitsSection.tsx', 'README.md'],
  },
  {
    id: 'lia-on-your-mobile', kind: 'mobile', durationSeconds: 10,
    title: ['LIA sur ton mobile.', 'Installe la PWA.'],
    detail: 'Ajoute LIA à ton écran d’accueil et retrouve tes échanges en un geste.',
    features: ['chat_sync', 'responsive'], editorialTopics: ['pwa_installation'],
    layout: 'left', effect: 'hold', accent: '#2c56c4',
    direction: 'Conversation mobile puis dashboard avec la ligne native Installer. Deux cadres fixes lisibles ; aucun zoom, déplacement du mobile ni faux dialogue système. La proposition beforeinstallprompt est illustrée, pas exercée.',
    nativeAssets: ['mobile'], evidence: ['apps/web/src/components/pwa/InstallHint.tsx', 'apps/web/src/app/[lng]/dashboard/chat/page.tsx'],
    note: 'PWA : interface native reconstituée · aucune installation ou session mobile réelle.',
  },
  {
    id: 'lia-by-your-side', kind: 'finale', durationSeconds: 4,
    title: ['LIA,', 'à tes côtés.'],
    detail: 'Une conversation. Des outils. Tes décisions.',
    features: ['chat_sync', 'multichannel', 'native_apps', 'responsive'],
    layout: 'full', effect: 'hold', accent: '#2c56c4',
    direction: 'Signature fixe avec BIP et un regard vers le spectateur. La PWA possède son propre chapitre lisible ; aucun mobile ne traverse la signature.',
    nativeAssets: ['mobile', 'chat'],
    evidence: ['apps/web/src/app/[lng]/dashboard/chat/page.tsx', 'docs/guides/GUIDE_MOBILE_ANDROID.md', 'docs/guides/GUIDE_MOBILE_IOS.md', 'README.md'],
  },
];

export const PRESENTATION_DURATION_SECONDS = PRESENTATION_CHAPTERS.reduce((sum, chapter) => sum + chapter.durationSeconds, 0);
export const PRESENTATION_DURATION_FRAMES = Math.round(PRESENTATION_DURATION_SECONDS * PRESENTATION_FPS);

/** Landing includes the PWA; durations leave readable, fixed native shots. */
export const PRESENTATION_LANDING_CHAPTERS: readonly PresentationChapter[] = [
  ['a-day-with-lia', 3], ['a-companion-in-context', 5], ['choose-how-to-read', 4],
  ['read-or-listen', 5], ['the-reminder-reaches-you', 4], ['prepare-the-meeting', 8],
  ['find-the-decision', 6], ['delegate-the-work', 5], ['make-the-deliverables', 5],
  ['choose-the-moment', 5], ['keep-the-decision', 5], ['lia-on-your-mobile', 6], ['lia-by-your-side', 4],
].map(([id, durationSeconds]) => {
  const chapter = PRESENTATION_CHAPTERS.find(item => item.id === id);
  if (!chapter) throw new Error(`Missing landing chapter ${id}`);
  return { ...chapter, durationSeconds: Number(durationSeconds) };
});
export const PRESENTATION_LANDING_DURATION_SECONDS = PRESENTATION_LANDING_CHAPTERS.reduce((sum, chapter) => sum + chapter.durationSeconds, 0);

export interface PresentationFocus {
  id: string;
  kind: PresentationFocusKind;
  variant: FeatureScreenVariant;
  durationSeconds: number;
  title: PresentationTitle;
  detail: string;
  features: readonly FeatureKey[];
  /** Additional subjects do not alter canonical feature ownership. */
  editorialTopics?: readonly string[];
  layout: PresentationLayout;
  effect: PresentationEffect;
  accent: `#${string}`;
  nativeAssets: readonly string[];
  /** Matching legacy authorship; those legacy exports are not V4-qualified. */
  legacySceneIds: readonly string[];
  availability: 'standard' | 'configured' | 'opt-in' | 'admin-only' | 'experimental';
  note?: string;
  /** True for exactly one editorial owner of each canonical feature. */
  coverageOwner: boolean;
}

const focus = (
  id: string, kind: PresentationFocusKind, variant: FeatureScreenVariant,
  title: PresentationTitle, detail: string, features: readonly FeatureKey[],
  nativeAssets: readonly string[], legacySceneIds: readonly string[],
  options: Partial<Pick<PresentationFocus, 'durationSeconds' | 'layout' | 'effect' | 'accent' | 'availability' | 'note' | 'coverageOwner' | 'editorialTopics'>> = {},
): PresentationFocus => ({
  id, kind, variant, title, detail, features, nativeAssets, legacySceneIds,
  durationSeconds: 20, layout: 'left', effect: 'hold', accent: '#2c56c4',
  availability: 'standard', coverageOwner: true, ...options,
});

/** Editable source treatments; export generation and provider proof remain separate. */
export const PRESENTATION_FOCUS_PLAN: readonly PresentationFocus[] = [
  focus('focus-conversation', 'knowledge', 'conversation', ['Une demande.', 'Les bonnes informations.'], 'Rapprocher, lire et calculer dans le même fil.', ['natural_language', 'multi_agent', 'rich_responses', 'attachments', 'computed_answers', 'browser_control'], ['chat', 'dossier', 'agents'], [], { durationSeconds: 24, availability: 'configured', note: 'Outils disponibles selon l’instance · navigation fournisseur non exercée.' }),
  focus('focus-avatars', 'avatars', 'avatars', ['Ton avatar.', 'Ses expressions.'], 'Lumo et les autres avatars natifs changent d’expression avec le contexte illustré.', ['personalities', 'psyche', 'mood_face', 'themes'], ['avatars'], ['focus-avatars'], { durationSeconds: 28, effect: 'hold', accent: '#7c5cf6', editorialTopics: ['native_avatar_contexts', 'lumo_masculine'], note: 'Expressions et contextes scénarisés · animation réduite disponible.' }),
  focus('focus-memory', 'memory', 'memory', ['Retrouve le fil.', 'Garde les repères.'], 'Préférences, réponses conservées et capacités consultables.', ['memory', 'bookmarks', 'self_knowledge'], ['memory', 'chat'], ['focus-relations'], { effect: 'hold', accent: '#7c5cf6' }),
  focus('focus-relations', 'memory', 'relations', ['Une personne.', 'Ses repères réunis.'], 'Informations, échanges, engagements et points ouverts dans la même fiche.', ['personal_crm'], ['relations'], ['focus-relations'], { durationSeconds: 22, layout: 'right', effect: 'hold', accent: '#7c5cf6' }),
  focus('focus-peers', 'ecosystem', 'peers', ['Tes assistants', 'se relaient.'], 'Des connexions volontaires et des partages révocables.', ['peers', 'peer_shares', 'peer_safety'], ['peers'], ['focus-peers'], { effect: 'hold', availability: 'opt-in', note: 'Personnes de la même instance · accès choisis en lecture seule.' }),
  focus('focus-radio', 'briefing-radio', 'radio', ['Ta journée,', 'sur ta station.'], 'Programme, sources et transcription près du lecteur.', ['briefing', 'personal_radio'], ['briefing', 'radio'], ['focus-radio'], { durationSeconds: 22, effect: 'hold', note: 'Interface de démonstration · parole Radio non générée dans ce montage.' }),
  focus('focus-routines', 'routines', 'routines', ['Une heure.', 'Ou une condition.'], 'Les rappels et routines attendent le moment choisi.', ['reminders_scheduling', 'conditional_routines'], ['routines'], ['focus-routines'], { effect: 'hold', accent: '#2c56c4' }),
  focus('focus-proactive', 'routines', 'proactive', ['Un suivi', 'aux bons moments.'], 'Sources, sujets et plages horaires que tu peux choisir.', ['proactive', 'proactive_wake', 'proactive_moments', 'interests'], ['heartbeat', 'routines'], ['focus-proactive'], { availability: 'configured', effect: 'hold', accent: '#2c56c4', note: 'Suivi selon activation et sources autorisées · aucun déclenchement réel exercé.' }),
  focus('focus-habits', 'routines', 'habits', ['Ton rythme,', 'à ton choix.'], 'Des observations visibles, des habitudes que tu peux mettre en pause.', ['habits', 'habits_lifecycle'], ['habits'], ['focus-habits'], { availability: 'opt-in', effect: 'hold', accent: '#2c56c4', note: 'Apprentissage des habitudes désactivé par défaut.' }),
  focus('focus-workboard', 'workboard', 'workboard', ['Confie le travail.', 'Suis le résultat.'], 'Un ticket, un porteur, des échanges et une décision.', ['workboard', 'workboard_delegation'], ['workboard'], ['focus-workboard'], { effect: 'hold', accent: '#2c56c4' }),
  focus('focus-voice', 'voice-meetings', 'voice', ['La voix,', 'dans le même fil.'], 'Transcription, lecture et conversation Live selon ton mode.', ['voice_mode', 'live_voice'], ['voice', 'live'], ['focus-voice'], { availability: 'configured', effect: 'hold', note: 'Modes et fournisseurs selon configuration · aucune session Live exercée.' }),
  focus('focus-phone', 'voice-meetings', 'phone', ['Un appel confié.', 'Un débrief retrouvé.'], 'Objectif, identité et compte rendu restent à portée.', ['telephony', 'telephony_callback'], ['phone', 'phone-identity'], ['focus-voice'], { availability: 'configured', effect: 'hold', note: 'Débrief fictif · aucun appel placé · rappel vers ton numéro vérifié.' }),
  focus('focus-meetings', 'voice-meetings', 'meetings', ['Les échanges', 'deviennent des décisions.'], 'Transcription, compte rendu et modèle choisi.', ['meetings', 'meeting_templates'], ['meetings'], ['focus-meetings'], { durationSeconds: 22, effect: 'hold', note: 'Compte rendu fictif · aucun enregistrement ou traitement fournisseur exercé.' }),
  focus('focus-knowledge', 'knowledge', 'knowledge', ['Une décision.', 'Sa source retrouvée.'], 'Documents, dossiers Drive et fils sous un libellé Gmail.', ['rag_spaces', 'mail_label_spaces'], ['knowledge'], ['focus-knowledge'], { effect: 'hold', accent: '#7c5cf6', note: 'Sources choisies et synchronisation selon les accès.' }),
  focus('focus-creation', 'creation', 'creation', ['Du résultat', 'au fichier.'], 'Documents, images, schémas, galerie et partage par e-mail.', ['generated_files', 'document_generation', 'image_generation', 'excalidraw', 'email_share'], ['files', 'images'], ['focus-creation'], { availability: 'configured', effect: 'hold', note: 'Fichiers locaux de démonstration · aucune génération image fournisseur exercée.' }),
  focus('focus-extensions', 'ecosystem', 'extensions', ['Une compétence', 'pour ton besoin.'], 'Skills, plugins, outils MCP et interfaces dans la conversation.', ['skills', 'plugins', 'mcp', 'mcp_apps', 'sub_agents'], ['skill', 'extensions', 'plugins', 'mcp'], ['focus-extensions'], { durationSeconds: 24, availability: 'configured', effect: 'hold', accent: '#7c5cf6', note: 'Capacités selon serveur et droits · aucun outil externe ou sous-agent exercé.' }),
  focus('focus-connected-services', 'ecosystem', 'connectors', ['Ton quotidien,', 'relié.'], 'Tes comptes, les sources publiques et la maison Philips Hue.', ['connected_services', 'web_intelligence', 'environment', 'smart_home'], ['connections', 'briefing'], ['focus-connected-services'], { durationSeconds: 22, availability: 'configured', effect: 'hold', note: 'Services disponibles selon les connexions et accès · aucune commande Hue exécutée.' }),
  focus('focus-health', 'briefing-radio', 'health', ['Tes mesures,', 'dans leur contexte.'], 'Pas et fréquence cardiaque par période, avec les trous de données.', ['health_metrics'], ['health', 'briefing'], ['focus-health'], { availability: 'opt-in', effect: 'hold', accent: '#2c56c4', note: 'Vue descriptive de mesures de démonstration.' }),
  focus('focus-journals', 'memory', 'journals', ['Ce qu’elle observe,', 'tu peux le corriger.'], 'Thèmes, sources et confiance consultables.', ['journals'], ['journals'], ['focus-journals'], { effect: 'hold', accent: '#7c5cf6' }),
  focus('focus-control', 'ecosystem', 'control', ['Tu confirmes.', 'Tu peux vérifier.'], 'Actions sensibles, dépenses et données administrables.', ['control', 'usage_limits', 'privacy'], ['approval', 'administration'], [], { durationSeconds: 22, effect: 'hold', accent: '#2c56c4', note: 'Le contexte utile va aux fournisseurs configurés ; les données stockées sont accessibles à l’opérateur.' }),
  focus('focus-mobile', 'mobile', 'mobile', ['LIA sur ton mobile.', 'Installe la PWA.'], 'Ajoute LIA à ton écran d’accueil et retrouve tes échanges en un geste.', ['chat_sync', 'multichannel', 'native_apps', 'responsive', 'languages', 'simplicity'], ['mobile', 'chat'], [], { durationSeconds: 24, effect: 'hold', editorialTopics: ['pwa_installation'], note: 'Installation selon ton navigateur · apps et canaux selon activation.' }),
  focus('focus-admin', 'administration', 'admin', ['Les utilisateurs.', 'Les prix des modèles.'], 'Comptes de l’instance et catalogue de tarifs LLM dans leurs vues natives.', ['devops_cli'], ['administration', 'agents'], [], { durationSeconds: 24, availability: 'admin-only', effect: 'hold', editorialTopics: ['admin_users', 'llm_pricing'], note: 'Administration réservée · données fictives · DevOps CLI non illustré.' }),
  focus('focus-speaking-avatar', 'voice-meetings', 'simli', ['Un visage parlant,', 'en option.'], 'Réglages Simli, connexion personnelle et contrôle d’arrêt.', ['mood_face', 'voice_mode', 'live_voice'], ['simli'], ['focus-speaking-avatar'], { availability: 'experimental', coverageOwner: false, effect: 'hold', note: 'Expérimental · clé et crédits Simli personnels · qualification fournisseur et appareils en cours.' }),
  focus('focus-display', 'appearance', 'display', ['Le même résultat.', 'Ta façon de le lire.'], 'Les quatre modes natifs : cartes, HTML, HTML + cartes et Markdown.', ['rich_responses', 'simplicity'], [], [], { durationSeconds: 22, coverageOwner: false, effect: 'hold', editorialTopics: ['response_display_modes'], note: 'Sélecteur natif reconstitué · aucune réponse reformatée ou préférence sauvegardée.' }),
  focus('focus-notifications', 'notifications', 'notifications', ['Un rappel.', 'Le rendez-vous retrouvé.'], 'Une notification de démonstration prolonge l’action planifiée.', ['reminders_scheduling'], [], [], { coverageOwner: false, effect: 'hold', accent: '#2c56c4', editorialTopics: ['reminder_notification'], note: 'Notification scénarisée · aucun rappel ou push réellement livré.' }),
  focus('focus-planning', 'routines', 'planning', ['Tout est prévu.', 'Le planning reste lisible.'], 'Actions, horaires et récurrences réunis dans le planning natif.', ['reminders_scheduling'], ['routines'], [], { durationSeconds: 22, coverageOwner: false, effect: 'hold', accent: '#2c56c4', editorialTopics: ['planned_actions'], note: 'Actions planifiées fictives · aucune routine déclenchée.' }),
  focus('focus-registry', 'ecosystem', 'registry', ['Ce qui a été demandé.', 'Ce qui est suivi.'], 'Le registre garde les actions, leurs états et leurs repères.', ['control', 'usage_limits'], [], [], { durationSeconds: 22, coverageOwner: false, effect: 'hold', accent: '#2c56c4', editorialTopics: ['action_registry'], note: 'Registre de démonstration · aucun historique d’exécution réel attribué au film.' }),
  focus('focus-llm-config', 'administration', 'llm-config', ['Le bon modèle.', 'Au bon endroit.'], 'La configuration LLM distingue les usages et leurs paramètres natifs.', [], [], [], { durationSeconds: 24, coverageOwner: false, availability: 'admin-only', effect: 'hold', editorialTopics: ['llm_configuration'], note: 'Configuration fictive · aucun modèle, routage ou paramètre sauvegardé.' }),
  focus('focus-platform', 'administration', 'platform', ['Ta plateforme.', 'Son état visible.'], 'La santé de l’instance se lit dans la vue administrateur native.', [], [], [], { durationSeconds: 22, coverageOwner: false, availability: 'admin-only', effect: 'hold', accent: '#2c56c4', editorialTopics: ['platform_health'], note: 'États de démonstration · aucune sonde de plateforme exécutée.' }),
];

/** Exact editorial ownership is useful for handoff; it is not visual coverage. */
export const FOCUS_FEATURE_OWNERS: Readonly<Partial<Record<FeatureKey, string>>> = Object.fromEntries(
  PRESENTATION_FOCUS_PLAN.filter(item => item.coverageOwner).flatMap(item => item.features.map(feature => [feature, item.id])),
);

export const MAIN_DECLARED_FEATURES: readonly FeatureKey[] = [...new Set(PRESENTATION_CHAPTERS.flatMap(chapter => chapter.features))];

export const PRESENTATION_TREATMENT = {
  mascot: 'BIP uniquement sur le canevas de présentation ; regards, petits pivots, appuis et réactions brefs liés aux événements.',
  backdrop: 'Fond clair de la landing : halos, grain et motif attention natifs, adaptés à une horloge Remotion déterministe.',
  typography: 'Inter de LIA ; titres 1–2 lignes, détail court, trois tailles utiles ; des blocs pleins avec une marge constante, pas des mots éparpillés.',
  occupancy: 'Fenêtres et textes à position fixe ; focus déclarés lisibles sur un élément natif. Aucune caméra interne, rotation, translation ou variation d’échelle du cadre.',
  pacing: 'Coupes musicales et apparitions par opacité uniquement. Les vues gardent leur géométrie pendant toute la lecture ; les expressions de BIP accompagnent les événements.',
  extraction: 'Un focus reprend exactement le rectangle déclaré d’un élément natif, à largeur source inchangée. Aucune réécriture, reflow, déplacement du parent ou cible implicite.',
  continuity: 'Le rappel, Morgan, les sources et l’accord portent les usages ; chaque coupe présente une vue utile et une promesse concrète au tutoiement.',
  qualification: 'Données fictives déclarées discrètement ; options, expérimental et limites spécifiques visibles quand l’image pourrait induire une exécution réelle.',
} as const;
