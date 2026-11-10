/** Project supported body motion once; the native CSS stage consumes its result. */
import { projectBodyMotion, type BodyBox, type BodyViewport } from '../body-motion-geometry';
import { bodySupportFootprint, supportBodyMotion } from '../body-support';
import { CHANNELS, formatChannel, type ChannelValues } from './channels';

export const BODY_STAGE_CHANNELS = [
  'bodyX',
  'bodyY',
  'bodyRoll',
  'bodySx',
  'bodySy',
  'bodyShadowX',
] as const;
export const BODY_SUPPORT_CHANNELS = ['bodySupport', 'bodySupportSide'] as const;
const INPUTS = [...BODY_STAGE_CHANNELS, ...BODY_SUPPORT_CHANNELS] as const;

export function createBodyStageWriter(element: HTMLElement) {
  let frame: { box: BodyBox; viewport: BodyViewport } | null = null;
  const raw = INPUTS.map(() => NaN);
  const text = BODY_STAGE_CHANNELS.map(() => '');
  let identity = '';
  let feet = bodySupportFootprint(undefined, undefined);
  let dirty = true;

  function updateInputs(values: Readonly<ChannelValues>): boolean {
    const character = element.dataset.volumeCharacter ?? element.dataset.style;
    const variant = element.dataset.volumeVariant;
    const nextIdentity = `${character}/${variant}`;
    let changed = dirty || identity !== nextIdentity;
    if (identity !== nextIdentity) {
      identity = nextIdentity;
      feet = bodySupportFootprint(character, variant);
    }
    INPUTS.forEach((key, index) => {
      if (Math.abs(values[key] - raw[index]) < 0.0001) return;
      raw[index] = values[key];
      changed = true;
    });
    dirty = false;
    return changed;
  }

  return {
    setFrame(box: BodyBox, viewport: BodyViewport) {
      frame = { box, viewport };
      dirty = true;
    },
    reset() {
      dirty = true;
      raw.fill(NaN);
      text.fill('');
    },
    write(values: Readonly<ChannelValues>) {
      if (!updateInputs(values)) return;
      const desired = supportBodyMotion(
        {
          x: values.bodyX,
          y: values.bodyY,
          roll: values.bodyRoll,
          sx: values.bodySx,
          sy: values.bodySy,
        },
        feet,
        values.bodySupport,
        values.bodySupportSide
      );
      const drawn = frame ? projectBodyMotion(desired, frame.box, frame.viewport) : desired;
      const shadowX = drawn.x - desired.x + values.bodyShadowX;
      const numbers = [drawn.x, drawn.y, drawn.roll, drawn.sx, drawn.sy, shadowX];
      BODY_STAGE_CHANNELS.forEach((key, index) => {
        const next = formatChannel(key, numbers[index]);
        if (next === text[index]) return;
        text[index] = next;
        element.style.setProperty(CHANNELS[key].cssVar, next);
      });
      const moving =
        Math.abs(desired.x) +
          Math.abs(desired.y) +
          Math.abs(desired.roll) +
          Math.abs(desired.sx - 1) +
          Math.abs(desired.sy - 1) >
        0.002;
      const state = String(moving);
      if (element.dataset.bodyMoving !== state) element.dataset.bodyMoving = state;
    },
  };
}
