import type { CosmeticActionId } from '../cosmetic-interactions';
import type { EffectSoundId } from './catalogue';
import { WORLD } from '../definition';
const MACHINES = new Map<string, EffectSoundId>(
  WORLD.props
    .filter(prop => prop.kind === 'machine')
    .map(prop => [
      prop.id,
      prop.tone === 'teal'
        ? 'machine-start'
        : prop.tone === 'violet'
          ? 'machine-gantry'
          : 'machine-printer',
    ])
);
const CUES: Partial<Record<CosmeticActionId, EffectSoundId>> = {
  plant: 'leaves',
  billiards: 'billiards',
  fountain: 'splash',
  pond: 'splash',
  cat: 'cat-meow',
  workout: 'workout-effort',
};
export function cosmeticCue(action: CosmeticActionId, targetId?: string): EffectSoundId | null {
  if (action === 'machine') return targetId ? (MACHINES.get(targetId) ?? null) : null;
  return CUES[action] ?? null;
}
