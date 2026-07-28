/**
 * Merged scene registry of the /more page — one SceneComponent per card key.
 *
 * Completeness is guard-enforced in `__tests__/scenes.test.tsx`: the merged
 * keys must equal MORE_CARD_KEYS exactly (no cardless scene, no sceneless
 * card). Kept separate from `more-data.ts` so pure data consumers (guards,
 * headers) never pull the whole scene bundle.
 */

import type { SceneComponent } from './scene-types';
import { DAILY_SCENES } from './scenes-daily';
import { FIND_SCENES } from './scenes-find';
import { RECOVER_SCENES } from './scenes-recover';
import { RESPOND_SCENES } from './scenes-respond';
import { UNSEEN_SCENES } from './scenes-unseen';
import { WRITE_SCENES } from './scenes-write';

export const SCENE_REGISTRY: Readonly<Record<string, SceneComponent>> = {
  ...WRITE_SCENES,
  ...RESPOND_SCENES,
  ...RECOVER_SCENES,
  ...FIND_SCENES,
  ...DAILY_SCENES,
  ...UNSEEN_SCENES,
};
