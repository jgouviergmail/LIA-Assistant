import type { ExpressionInputs } from '../../../apps/web/src/components/eyes/expression-engine';
import type { EyeStyleId } from '../../../apps/web/src/components/eyes/eye-styles';

/** Mirrors the selectable registry and its French names. BIP is represented
 * once by the stage mascot, so the gallery renders the other fourteen looks. */
export const AVATAR_PRESENTATION_CATALOGUE = [
  { id:'cozmo', name:'Cozmo', renderer:'rig' },
  { id:'capsules', name:'Capsules', renderer:'rig' },
  { id:'billes', name:'Billes', renderer:'rig' },
  { id:'amande', name:'Amande', renderer:'rig' },
  { id:'traits', name:'Traits', renderer:'rig' },
  { id:'anneaux', name:'Anneaux', renderer:'rig' },
  { id:'smiley', name:'Smiley', renderer:'character' },
  { id:'spirit', name:'Esprit de LIA', renderer:'character' },
  { id:'moss', name:'Mousse', renderer:'character' },
  { id:'lumen', name:'Lumo', renderer:'character' },
  { id:'nimbo', name:'Nimbo', renderer:'character' },
  { id:'orbit', name:'Orbit', renderer:'character' },
  { id:'bip', name:'Bip', renderer:'mascot' },
  { id:'boulon', name:'Boulon', renderer:'character' },
  { id:'oscar', name:'Oscar', renderer:'character' },
] as const satisfies readonly {id:EyeStyleId;name:string;renderer:'rig'|'character'|'mascot'}[];

export const AVATAR_GALLERY_CHARACTERS = AVATAR_PRESENTATION_CATALOGUE.filter(character=>character.renderer!=='mascot');

/** These are product inputs, not invented expressions. The native expression
 * engine decides what face each context receives. "Listening" is the actual
 * recording state and therefore resolves to the native attentive pose. */
export const AVATAR_CONTEXTS = [
  { id: 'neutral', title: 'Prêt à t’accompagner', detail: 'Une présence calme, entre deux échanges.', inputs: {} },
  { id: 'attentive', title: 'Tu écris', detail: 'Son regard suit ta demande.', inputs: { userTyping: true } },
  { id: 'thinking', title: 'LIA réfléchit', detail: 'L’expression accompagne la recherche.', inputs: { chatStatus: 'streaming', streamPhase: 'progress', lastStepKind: 'reasoning' } },
  { id: 'joy', title: 'Une bonne nouvelle', detail: 'Un sourire vient ponctuer la réponse.', inputs: { reaction: 'joy' } },
  { id: 'listening', title: 'Tu parles', detail: 'Lumo reste attentif pendant l’écoute.', inputs: { voiceState: 'recording' } },
  { id: 'speaking', title: 'LIA répond à voix haute', detail: 'Son visage accompagne la parole.', inputs: { voiceState: 'speaking' } },
] as const;

const BASE_INPUTS: ExpressionInputs = {
  chatStatus: 'idle', streamPhase: 'answer', lastStepKind: null,
  hitlAwaiting: false, voiceState: 'idle', reaction: null,
  notificationPing: false, userTyping: false, moodLabel: 'neutral',
  hourOfDay: 11, inactivityStage: 0,
};

export function avatarContextAt(seconds: number, durationSeconds: number) {
  const sequence = durationSeconds <= 10 ? [1, 2, 3] : [0, 1, 2, 3, 4, 5];
  const span = Math.max(0.1, durationSeconds) / sequence.length;
  const index = Math.min(sequence.length - 1, Math.floor(Math.max(0, seconds) / span));
  const context = AVATAR_CONTEXTS[sequence[index]];
  return {
    ...context,
    at: index * span,
    index,
    inputs: { ...BASE_INPUTS, ...context.inputs } as ExpressionInputs,
  };
}

export const AVATAR_DEMONSTRATION_PROVENANCE = {
  lumo: 'apps/web/public/avatars/lumen/v2/male/body.webp',
  catalogue: 'apps/web/src/components/eyes/eye-styles.ts#EYE_STYLE_IDS',
  selections: 'apps/web/src/components/settings/EyesStyleSettings.tsx',
  companions: 'apps/web/src/components/spirit/companion-catalogue.ts#COMPANION_CHARACTERS',
  names: 'apps/web/locales/fr/translation.json#eyes.styles',
  expressions: 'apps/web/src/components/eyes/expression-engine.ts#deriveExpression',
  poses: 'apps/web/src/components/eyes/rig/poses.ts#resolvePose',
  springs: 'apps/web/src/components/eyes/rig/spring.ts#springStep',
  speech: 'apps/web/src/components/eyes/rig/speech.ts#speechTapes',
  providerExecution: false,
} as const;
