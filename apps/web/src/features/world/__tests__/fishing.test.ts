import { expect, it } from 'vitest';
import { fishingFrame } from '../art/fishing';
import { CosmeticEffects } from '../cosmetic-effects';
it('takes out a rod before casting, keeps the float on water while waiting and reels back once', () => {
  const beat = {
    id: 'pond',
    action: 'pond' as const,
    point: { x: 20, y: 10 },
    origin: { x: 14, y: 10 },
    elevation: 0.12,
    phase: 0,
  };
  const preparing = fishingFrame({ ...beat, phase: 0.1 });
  const casting = fishingFrame({ ...beat, phase: 0.25 });
  const waiting = fishingFrame({ ...beat, phase: 0.5 });
  const reeling = fishingFrame({ ...beat, phase: 0.9 });
  expect(preparing?.float).toBeNull();
  expect(casting?.float).not.toBeNull();
  expect(waiting?.state).toBe('waiting');
  expect(reeling?.state).toBe('reeling');
  expect(waiting?.float).not.toEqual(reeling?.float);
  expect(fishingFrame({ ...beat, origin: undefined })).toBeNull();
  const effects = new CosmeticEffects();
  expect(effects.activate(beat, 0, true, 'low')).toBe(true);
  const middle = effects.frames(5000, 'low')[0];
  expect(fishingFrame(middle)?.state).toBe('waiting');
  expect(effects.frames(8000, 'low')).toEqual([]);
});
