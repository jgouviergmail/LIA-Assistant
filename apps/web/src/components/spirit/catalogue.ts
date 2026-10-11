import type { MoodLabel } from '@/types/psyche';

export type SpiritVariant = 'female' | 'male';
/** Independent of the eyes engine: both rendering surfaces share this vocabulary. */
export const SPIRIT_EXPRESSIONS = [
  'neutral',
  'joy',
  'excited',
  'tender',
  'surprise',
  'fear',
  'anger',
  'sad',
  'worried',
  'question',
  'thinking',
  'searching',
  'focused',
  'attentive',
  'speaking',
  'bored',
  'tired',
  'sleepy',
  'sleep',
  'wink',
] as const;
export type SpiritExpression = (typeof SPIRIT_EXPRESSIONS)[number];

const MOOD_EXPRESSIONS: Record<MoodLabel, SpiritExpression> = {
  serene: 'neutral',
  curious: 'attentive',
  energized: 'excited',
  playful: 'joy',
  reflective: 'thinking',
  agitated: 'worried',
  melancholic: 'sad',
  neutral: 'neutral',
  content: 'joy',
  determined: 'focused',
  defiant: 'anger',
  resigned: 'tired',
  overwhelmed: 'fear',
  tender: 'tender',
};

export function spiritExpressionForMood(mood: MoodLabel): SpiritExpression {
  return MOOD_EXPRESSIONS[mood] ?? 'neutral';
}

export function spiritAsset(
  variant: SpiritVariant,
  expression: SpiritExpression,
  animated: boolean
) {
  return `/avatars/spirit/v1/compact/${variant}/${expression}${animated ? '' : '-still'}.webp`;
}
