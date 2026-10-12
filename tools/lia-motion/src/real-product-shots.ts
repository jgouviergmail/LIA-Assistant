import type { FeatureKey, MotionScene } from './content';

/** Camera centres and widths are fractions of the ORIGINAL captured surface. */
export type Camera = { x: number; y: number; width: number; roll?: number };
export interface NativeCapture {
  id: string;
  kind: 'image' | 'video';
  path: string;
  width: number;
  height: number;
  provenance: string;
  visibleFeatures: readonly FeatureKey[];
  /** A cursor/action is shown only when it belongs to the original recording. */
  capturedActions?: readonly string[];
  durationSeconds?: number;
  clipFromSeconds?: number;
}

const capture = (id: string, visibleFeatures: readonly FeatureKey[]): NativeCapture => ({
  id,
  kind: 'image',
  path: `capture-v2/native-proof/${id}.png`,
  width: 1440,
  height: 960,
  provenance: 'capture-v2/native-proof/manifest.json',
  visibleFeatures,
});

/** Replaced by fresh FR clips through the Film's `captures` prop, never by mock UI. */
export const NATIVE_CAPTURES: Readonly<Record<string, NativeCapture>> = {
  dossier: capture('dossier', ['natural_language', 'rich_responses', 'rag_spaces']),
  chat: capture('chat', ['natural_language', 'rich_responses']),
  'dossier-still': capture('dossier-still', ['rich_responses', 'rag_spaces']),
  approval: capture('approval', ['control']),
  knowledge: capture('knowledge', ['rag_spaces', 'mail_label_spaces']),
  skill: capture('skill', ['skills', 'computed_answers']),
  memory: capture('memory', ['memory']),
  administration: capture('administration', ['usage_limits']),
  relations: capture('relations', ['personal_crm']),
  meetings: capture('meetings', ['meetings', 'meeting_templates']),
  radio: capture('radio', ['personal_radio']),
  briefing: capture('briefing', ['briefing']),
  workboard: capture('workboard', ['workboard', 'workboard_delegation']),
  routines: capture('routines', ['reminders_scheduling']),
  habits: capture('habits', ['habits', 'habits_lifecycle']),
  journals: capture('journals', ['journals']),
  health: capture('health', ['health_metrics']),
  voice: capture('voice', ['voice_mode']),
  connections: capture('connections', ['connected_services']),
  avatars: capture('avatars', ['mood_face']),
  extensions: capture('extensions', ['skills']),
  mcp: capture('mcp', ['mcp']),
  plugins: capture('plugins', ['plugins']),
  peers: capture('peers', ['peers', 'peer_shares', 'peer_safety']),
  live: capture('live', ['live_voice']),
  phone: capture('phone', ['telephony']),
  'phone-identity': capture('phone-identity', ['telephony_callback']),
  heartbeat: capture('heartbeat', ['proactive']),
  images: capture('images', ['image_generation']),
  files: capture('files', ['generated_files']),
  simli: capture('simli', []),
};

export interface ProductShot {
  id: string;
  kind: 'screen' | 'type' | 'companions' | 'extracts';
  weight: number;
  assetId?: string;
  start?: Camera;
  end?: Camera;
  headline?: string;
  caption?: string;
  /** Editorial coverage. Screenshot proof is separately declared by each capture. */
  featureKeys?: readonly FeatureKey[];
  accent?: string;
  transition?: 'cut' | 'push' | 'iris';
  videoStartSeconds?: number;
  clipRate?: number;
  character?: 'bip' | 'smiley' | 'moss' | 'lumen' | 'nimbo' | 'orbit' | 'boulon' | 'oscar';
  extracts?: readonly { x: number; y: number; width: number; height: number }[];
  /** A declaration sourced in code; it never masquerades as a recorded UI result. */
  evidence?: readonly string[];
}

const wide: Camera = { x: 0.5, y: 0.5, width: 1.06 };
const camera = (x: number, y: number, width: number): Camera => ({ x, y, width });
const screen = (
  id: string,
  assetId: string,
  start: Camera,
  end: Camera,
  weight = 2,
  caption?: string
): ProductShot => ({
  id,
  kind: 'screen',
  assetId,
  start,
  end,
  weight,
  caption,
  transition: 'push',
});
const type = (id: string, headline: string, weight = 0.85): ProductShot => ({
  id,
  kind: 'type',
  headline,
  weight,
});

/**
 * Native pixels remain untouched. These are editorial reframings of real screens;
 * no cursor, loading state, click, answer, control or provider result is invented.
 * Fresh clips replace an asset by id and carry their own captured-action metadata.
 */
export const CHAPTER_SHOTS: Readonly<Record<string, readonly ProductShot[]>> = {
  'your-day': [
    screen('open-product', 'dossier', wide, camera(0.5, 0.32, 0.77), 2.4),
    type('one-request', 'Une demande.'),
    {
      ...screen('the-request', 'chat', camera(0.5, 0.87, 0.8), camera(0.5, 0.85, 0.75), 2.1),
      videoStartSeconds: 5.1,
    },
    type('one-context', 'Ton contexte.'),
    {
      ...screen('the-answer', 'chat', camera(0.53, 0.73, 0.8), camera(0.53, 0.74, 0.73), 2.5),
      videoStartSeconds: 7.3,
    },
  ],
  'connected-dossier': [
    type('connect-sources', 'LIA relie les sources.'),
    screen(
      'native-space',
      'knowledge',
      wide,
      camera(0.5, 0.24, 0.82),
      2.5,
      'Espaces de connaissances'
    ),
    screen('source-connections', 'knowledge', camera(0.5, 0.54, 0.89), camera(0.5, 0.73, 0.87), 3),
    screen('dossier-answer', 'dossier', camera(0.53, 0.43, 0.75), camera(0.53, 0.43, 0.7), 2.5),
    screen(
      'dossier-references',
      'dossier-still',
      camera(0.5, 0.71, 0.74),
      camera(0.5, 0.74, 0.72),
      2.5
    ),
  ],
  'living-companions': [
    type('presence', 'Un compagnon qui s’anime.'),
    { id: 'bip-close', kind: 'companions', weight: 3.6, character: 'bip' },
    { id: 'smiley-match', kind: 'companions', weight: 2.8, character: 'smiley' },
    screen(
      'native-avatar-gallery',
      'avatars',
      wide,
      camera(0.6, 0.44, 0.75),
      2.6,
      'Choisis ton compagnon'
    ),
    {
      ...screen(
        'native-avatar-choices',
        'avatars',
        camera(0.6, 0.47, 0.72),
        camera(0.6, 0.66, 0.72),
        2.6
      ),
      videoStartSeconds: 4,
    },
    {
      id: 'native-character-range',
      kind: 'companions',
      weight: 2.4,
      caption: 'Des personnages à ton image',
    },
  ],
  'remember-people': [
    type('keep-thread', 'LIA garde le fil.'),
    screen(
      'native-memory',
      'memory',
      camera(0.5, 0.48, 0.75),
      camera(0.5, 0.41, 0.64),
      2.8,
      'Mémoire contextuelle'
    ),
    screen('native-relations', 'relations', wide, camera(0.5, 0.32, 0.9), 2.8, 'Relations'),
    screen('relationship-next', 'relations', camera(0.5, 0.4, 0.82), camera(0.5, 0.43, 0.78), 2.4),
    screen('commitments', 'relations', camera(0.48, 0.82, 0.84), camera(0.48, 0.84, 0.84), 2.1),
  ],
  'personal-radio': [
    type('listen-day', 'Ta journée s’écoute.'),
    screen('native-radio', 'radio', wide, camera(0.5, 0.32, 0.95), 3.3, 'Radio personnelle'),
    screen('radio-transcript', 'radio', camera(0.5, 0.4, 0.93), camera(0.5, 0.53, 0.9), 3),
    screen('radio-sources', 'radio', camera(0.5, 0.65, 0.92), camera(0.5, 0.69, 0.88), 3),
  ],
  'right-moment': [
    type('right-time', 'Au bon moment.'),
    screen('native-briefing', 'briefing', wide, camera(0.5, 0.66, 0.84), 2.5, 'Le briefing de ta journée'),
    screen(
      'native-routines',
      'routines',
      wide,
      camera(0.6, 0.43, 0.72),
      2.5,
      'Les routines que tu choisis'
    ),
    screen('native-proactive-window', 'heartbeat', camera(0.6, 0.23, 0.72), camera(0.6, 0.24, 0.68), 2.5, 'Proactivité · réglages des horaires'),
    screen('native-habits', 'habits', camera(0.6, 0.44, 0.73), camera(0.6, 0.5, 0.7), 2, 'Habitudes observées'),
    screen('native-health', 'health', camera(0.6, 0.46, 0.74), camera(0.6, 0.5, 0.7), 2, 'Tes mesures santé'),
  ],
  'delegated-work': [
    type('give-ticket', 'Confie un objectif.'),
    screen(
      'native-workboard',
      'workboard',
      wide,
      camera(0.52, 0.44, 0.82),
      3,
      'Ton tableau de travail'
    ),
    screen(
      'native-ticket',
      'workboard',
      camera(0.54, 0.48, 0.79),
      camera(0.54, 0.66, 0.77),
      3,
      'Confier un ticket à LIA'
    ),
  ],
  'voice-and-phone': [
    type('speak', 'Parle avec LIA.'),
    screen('native-voice-control', 'voice', camera(0.6, 0.32, 0.76), camera(0.6, 0.42, 0.72), 2.4, 'Transcription · réglages'),
    screen('native-live-control', 'live', camera(0.6, 0.43, 0.74), camera(0.6, 0.55, 0.7), 2.4, 'Conversation Live · réglages'),
    type('native-phone-bridge', 'Des appels, avec ton accord.', 1),
    screen('native-phone-debrief', 'phone', camera(0.6, 0.31, 0.75), camera(0.6, 0.41, 0.7), 3.6, 'Téléphonie · historique de démonstration'),
    screen('native-phone-control', 'phone-identity', camera(0.6, 0.3, 0.71), camera(0.6, 0.36, 0.69), 2, 'Ton numéro, après vérification'),
  ],
  'meeting-to-results': [
    type('meeting-to-work', 'Des comptes rendus. Des fichiers.'),
    screen('meeting-wide', 'meetings', wide, camera(0.5, 0.36, 0.88), 2.2, 'Réunions'),
    screen('meeting-actions', 'meetings', camera(0.5, 0.59, 0.85), camera(0.5, 0.7, 0.82), 2.8),
    { ...type('native-creation-bridge', 'Images, documents et schémas.', 1.1), featureKeys: ['image_generation', 'document_generation', 'excalidraw'], evidence: ['apps/api/src/domains/agents/tools/image_tools.py', 'apps/api/src/domains/agents/tools/document_tools.py', 'apps/api/src/domains/agents/tools/excalidraw_tools.py'] },
    screen('native-generated-gallery', 'files', camera(0.6, 0.4, 0.78), camera(0.6, 0.54, 0.74), 3, 'Galerie des fichiers · démonstration'),
    screen('native-image-preferences', 'images', camera(0.6, 0.4, 0.74), camera(0.6, 0.57, 0.7), 2.5, 'Création d’images · réglages'),
  ],
  'knowledge-and-tools': [
    type('tools-in-thread', 'Des outils dans la conversation.'),
    screen('converter-context', 'skill', wide, camera(0.55, 0.46, 0.79), 2.6, 'Skills interactifs'),
    { ...screen('converter-interactive', 'skill', camera(0.52, 0.67, 0.61), camera(0.52, 0.68, 0.59), 3.7), videoStartSeconds: 4.7 },
    screen(
      'native-skills-library',
      'extensions',
      wide,
      camera(0.6, 0.3, 0.75),
      2,
      'Compétences LIA'
    ),
    screen(
      'native-mcp-dialog',
      'mcp',
      camera(0.5, 0.45, 0.78),
      camera(0.5, 0.5, 0.72),
      2.3,
      'Serveurs MCP · configuration'
    ),
    screen('native-plugin-import', 'plugins', camera(0.6, 0.24, 0.76), camera(0.6, 0.25, 0.7), 2.2, 'Plugins · import ZIP ou URL'),
    { ...type('native-subagents-declaration', 'Plusieurs spécialistes. Des budgets bornés.', 1.1), featureKeys: ['sub_agents'], evidence: ['apps/api/src/domains/agents/tools/sub_agent_tools.py'] },
  ],
  'assistant-circle': [
    type('circle', 'Les bonnes personnes. Le bon contexte.'),
    screen('native-peers', 'peers', wide, camera(0.54, 0.44, 0.83), 2.5, 'Assistants connectés'),
    screen('native-peer-sharing', 'peers', camera(0.54, 0.45, 0.83), camera(0.54, 0.64, 0.81), 3),
    screen('native-peer-overview', 'peers', camera(0.54, 0.55, 0.81), wide, 2),
  ],
  'your-control': [
    type('you-decide', 'Tu gardes la main.'),
    screen(
      'draft-review',
      'approval',
      wide,
      camera(0.52, 0.77, 0.83),
      3,
      'Confirmation avant action'
    ),
    screen(
      'native-decision-controls',
      'approval',
      camera(0.49, 0.82, 0.71),
      camera(0.49, 0.82, 0.68),
      2.5
    ),
    screen(
      'native-quotas',
      'administration',
      wide,
      camera(0.54, 0.55, 0.84),
      3,
      'Coûts et limites'
    ),
    screen('back-to-you', 'mobile', camera(0.5, 0.5, 4.4), camera(0.5, 0.5, 4.15), 2.3, 'La conversation te suit'),
  ],
};

export const FOCUS_SHOTS: Readonly<Record<string, readonly ProductShot[]>> = {
  'focus-avatars': CHAPTER_SHOTS['living-companions'],
  'focus-speaking-avatar': [
    type('speaking-intro', 'Un avatar vidéo personnel.'),
    screen(
      'simli-native-wide',
      'simli',
      wide,
      camera(0.55, 0.38, 0.85),
      3,
      'Option Simli · expérimentale'
    ),
    screen('simli-native-controls', 'simli', camera(0.55, 0.4, 0.84), camera(0.55, 0.48, 0.8), 3),
    screen(
      'simli-native-account',
      'simli',
      camera(0.55, 0.5, 0.8),
      camera(0.55, 0.6, 0.8),
      3,
      'Compte fournisseur personnel'
    ),
    screen('simli-native-options', 'simli', camera(0.55, 0.64, 0.82), camera(0.55, 0.7, 0.84), 3),
    screen('simli-native-overview', 'simli', camera(0.55, 0.52, 0.9), wide, 2),
  ],
  'focus-relations': CHAPTER_SHOTS['remember-people'],
  'focus-radio': CHAPTER_SHOTS['personal-radio'],
  'focus-routines': [
    type('routine-intro', 'Tes routines. Tes conditions.'),
    screen(
      'routine-native-wide',
      'routines',
      wide,
      camera(0.53, 0.4, 0.86),
      4,
      'Rappels et routines'
    ),
    screen(
      'routine-native-details',
      'routines',
      camera(0.54, 0.4, 0.82),
      camera(0.54, 0.54, 0.8),
      3
    ),
    screen(
      'routine-native-conditions',
      'routines',
      camera(0.54, 0.54, 0.8),
      camera(0.54, 0.66, 0.8),
      3
    ),
    screen(
      'routine-native-control',
      'routines',
      camera(0.55, 0.64, 0.79),
      camera(0.55, 0.7, 0.8),
      3
    ),
    screen('routine-native-return', 'routines', camera(0.54, 0.6, 0.89), wide, 3),
  ],
  'focus-workboard': CHAPTER_SHOTS['delegated-work'],
  'focus-meetings': CHAPTER_SHOTS['meeting-to-results'],
  'focus-knowledge': [
    type('knowledge-intro', 'Retrouve la source.'),
    screen(
      'knowledge-native-wide',
      'knowledge',
      wide,
      camera(0.5, 0.26, 0.86),
      3,
      'Espaces de connaissances'
    ),
    screen(
      'knowledge-native-drive',
      'knowledge',
      camera(0.5, 0.58, 0.92),
      camera(0.5, 0.66, 0.89),
      3
    ),
    screen(
      'knowledge-native-documents',
      'knowledge',
      camera(0.5, 0.77, 0.89),
      camera(0.5, 0.83, 0.86),
      3
    ),
    screen(
      'knowledge-native-answer',
      'dossier',
      camera(0.53, 0.71, 0.69),
      camera(0.53, 0.74, 0.69),
      2
    ),
  ],
  'focus-extensions': CHAPTER_SHOTS['knowledge-and-tools'],
  'focus-connected-services': [
    type('connections-intro', 'Tes services connectés.'),
    screen(
      'connections-native-wide',
      'connections',
      wide,
      camera(0.54, 0.4, 0.86),
      4,
      'Choisir les services de LIA'
    ),
    screen(
      'connections-native-provider',
      'connections',
      camera(0.54, 0.42, 0.8),
      camera(0.54, 0.54, 0.8),
      3
    ),
    screen(
      'connections-native-services',
      'connections',
      camera(0.54, 0.54, 0.8),
      camera(0.54, 0.66, 0.8),
      3
    ),
    screen(
      'connections-native-context',
      'knowledge',
      camera(0.5, 0.58, 0.88),
      camera(0.5, 0.71, 0.86),
      3
    ),
    screen(
      'connections-native-documents',
      'knowledge',
      camera(0.5, 0.71, 0.86),
      camera(0.5, 0.8, 0.84),
      3
    ),
  ],
  'focus-peers': CHAPTER_SHOTS['assistant-circle'],
  'focus-health': [
    type('health-intro', 'Tes mesures santé.'),
    screen('health-native-wide', 'health', wide, camera(0.54, 0.42, 0.87), 4, 'Suivi des mesures'),
    screen(
      'health-native-measures',
      'health',
      camera(0.54, 0.45, 0.84),
      camera(0.54, 0.54, 0.8),
      3
    ),
    screen('health-native-details', 'health', camera(0.54, 0.54, 0.8), camera(0.54, 0.66, 0.8), 3),
    screen(
      'health-native-settings',
      'health',
      camera(0.54, 0.62, 0.81),
      camera(0.54, 0.7, 0.84),
      3
    ),
    screen('health-native-return', 'health', camera(0.54, 0.6, 0.89), wide, 3),
  ],
  'focus-journals': [
    type('journal-intro', 'Le fil de tes journées.'),
    screen(
      'journals-native-wide',
      'journals',
      wide,
      camera(0.54, 0.43, 0.85),
      4,
      'Journaux personnels'
    ),
    screen(
      'journals-native-entry',
      'journals',
      camera(0.54, 0.45, 0.82),
      camera(0.54, 0.54, 0.8),
      3
    ),
    screen(
      'journals-native-context',
      'journals',
      camera(0.54, 0.54, 0.8),
      camera(0.54, 0.66, 0.8),
      3
    ),
    screen(
      'journals-native-control',
      'journals',
      camera(0.54, 0.62, 0.8),
      camera(0.54, 0.7, 0.84),
      3
    ),
    screen('journals-native-return', 'journals', camera(0.54, 0.6, 0.89), wide, 3),
  ],
  'focus-habits': [
    type('habits-intro', 'Comprendre tes habitudes.'),
    screen(
      'habits-native-wide',
      'habits',
      wide,
      camera(0.54, 0.41, 0.85),
      4,
      'Habitudes observées'
    ),
    screen('habits-native-detail', 'habits', camera(0.54, 0.44, 0.82), camera(0.54, 0.54, 0.8), 3),
    screen('habits-native-cycle', 'habits', camera(0.54, 0.54, 0.8), camera(0.54, 0.66, 0.8), 3),
    screen('habits-native-control', 'habits', camera(0.54, 0.62, 0.8), camera(0.54, 0.7, 0.84), 3),
    screen('habits-native-return', 'habits', camera(0.54, 0.6, 0.89), wide, 3),
  ],
};

export function shotsForScene(sceneId: string): readonly ProductShot[] {
  const shots = FOCUS_SHOTS[sceneId] ?? CHAPTER_SHOTS[sceneId];
  if (!shots) throw new Error(`No native shot plan for ${sceneId}; capture its real route first`);
  return shots;
}

export interface TimedProductShot {
  shot: ProductShot;
  from: number;
  durationInFrames: number;
  chapterId: string;
  accent: string;
  declaredFeatureKeys: readonly FeatureKey[];
}

/** The last shot absorbs frame rounding, so the authored chapter never has gaps. */
export function timeChapterShots(
  scene: MotionScene,
  from: number,
  durationInFrames: number,
  shots: readonly ProductShot[] = shotsForScene(scene.id),
  beats: readonly number[] = [],
  fps = 30
): TimedProductShot[] {
  if (!shots.length || shots.some(shot => !Number.isFinite(shot.weight) || shot.weight <= 0)) {
    throw new RangeError('Native shot weights must be finite and positive');
  }
  if (!Number.isInteger(durationInFrames) || durationInFrames < shots.length) {
    throw new RangeError('A native chapter needs at least one frame per shot');
  }
  const weight = shots.reduce((sum, shot) => sum + shot.weight, 0);
  let cursor = from;
  let cumulative = 0;
  return shots.map((shot, index) => {
    cumulative += shot.weight;
    const desiredEnd = from + Math.round((cumulative / weight) * durationInFrames);
    const minimumGap = Math.min(4, Math.floor(durationInFrames / shots.length));
    const firstLegalFrame = cursor + minimumGap;
    const lastLegalFrame = from + durationInFrames - (shots.length - index - 1) * minimumGap;
    const legalBeats = beats
      .map(at => Math.round(at * fps))
      .filter(at => at >= firstLegalFrame && at <= lastLegalFrame);
    const nearest = legalBeats.reduce(
      (best, at) => (Math.abs(at - desiredEnd) < Math.abs(best - desiredEnd) ? at : best),
      Infinity
    );
    const end =
      index === shots.length - 1 || Math.abs(nearest - desiredEnd) > fps * 0.35
        ? desiredEnd
        : nearest;
    const result = {
      shot,
      from: cursor,
      durationInFrames: end - cursor,
      chapterId: scene.id,
      accent: shot.accent ?? scene.accent,
      declaredFeatureKeys: index === 0 ? scene.featureKeys : (shot.featureKeys ?? []),
    };
    if (result.durationInFrames < 1)
      throw new RangeError(`Shot ${shot.id} was rounded to zero frames`);
    cursor = end;
    return result;
  });
}

/** Thirty-second motion proof: native UI, deliberate reframings, animated characters. */
export const PROOF_SHOTS: readonly ProductShot[] = [
  screen('proof-open', 'chat', wide, camera(0.5, 0.85, 0.77), 2.4),
  type('proof-request', 'Une demande.', 0.8),
  {
    ...screen('proof-question', 'chat', camera(0.5, 0.84, 0.77), camera(0.5, 0.83, 0.72), 2),
    videoStartSeconds: 5.1,
  },
  type('proof-context', 'Ton contexte.', 0.8),
  {
    ...screen('proof-result', 'chat', camera(0.53, 0.7, 0.8), camera(0.53, 0.73, 0.73), 2.8),
    videoStartSeconds: 7.3,
  },
  {
    id: 'proof-sources',
    kind: 'extracts',
    assetId: 'dossier-still',
    weight: 2.6,
    transition: 'push',
    extracts: [{ x: 279, y: 665, width: 884, height: 88 }],
  },
  type('proof-presence', 'Une présence.', 0.8),
  { id: 'proof-bip', kind: 'companions', weight: 3, character: 'bip' },
  { id: 'proof-smiley', kind: 'companions', weight: 2, character: 'smiley' },
  screen('proof-radio', 'radio', wide, camera(0.5, 0.37, 0.93), 3),
  {
    ...screen('proof-skill', 'skill', camera(0.52, 0.67, 0.61), camera(0.52, 0.68, 0.59), 3.5),
    videoStartSeconds: 4.7,
  },
  type('proof-control', 'Tu décides.', 0.8),
  {
    ...screen(
      'proof-approval',
      'approval',
      camera(0.61, 0.62, 0.89),
      camera(0.58, 0.73, 0.84),
      3.3
    ),
    videoStartSeconds: 2.3,
  },
];
