/**
 * The only place in the rig that touches the DOM.
 *
 * Each frame it pushes the channel values onto the root element as `--rig-*`
 * custom properties. Two filters keep the cost near zero on a widget that is
 * on screen permanently:
 *
 *  1. a value whose change is smaller than its own display precision is not
 *     even formatted (a breathing sine moves by ~2e-5 per frame — formatting
 *     forty-odd of those every frame would be pure garbage);
 *  2. a formatted value identical to the one already on the element is not
 *     written, so a settled channel costs one float comparison per frame.
 */

import {
  CHANNELS,
  CHANNEL_KEYS,
  formatChannel,
  type ChannelValues,
} from '@/components/eyes/rig/channels';

export interface RigWriter {
  /** Push the frame onto the element. */
  write(values: Readonly<ChannelValues>): void;
  /** Forget what was written — the next `write` re-emits everything. */
  reset(): void;
}

/** Half a display step: below this, the channel cannot change its own text. */
const thresholds = CHANNEL_KEYS.map(key => 0.5 * 10 ** -CHANNELS[key].precision);

export function createRigWriter(element: HTMLElement): RigWriter {
  // NaN never compares equal, so the first frame always writes everything.
  const lastRaw = CHANNEL_KEYS.map(() => Number.NaN);
  const lastText = CHANNEL_KEYS.map(() => '');

  return {
    write(values) {
      for (let index = 0; index < CHANNEL_KEYS.length; index += 1) {
        const key = CHANNEL_KEYS[index];
        const value = values[key];
        if (Math.abs(value - lastRaw[index]) < thresholds[index]) continue;
        lastRaw[index] = value;
        const text = formatChannel(key, value);
        if (text === lastText[index]) continue;
        lastText[index] = text;
        element.style.setProperty(CHANNELS[key].cssVar, text);
      }
    },
    reset() {
      for (let index = 0; index < CHANNEL_KEYS.length; index += 1) {
        lastRaw[index] = Number.NaN;
        lastText[index] = '';
      }
    },
  };
}
