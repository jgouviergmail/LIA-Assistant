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
import { browPath, mouthPath, SVG_CHANNELS } from './face-geometry';
import { strokeContours } from './stroke-geometry';

export interface RigWriter {
  /** Push the frame onto the element. */
  write(values: Readonly<ChannelValues>): void;
  /** Forget what was written — the next `write` re-emits everything. */
  reset(): void;
}

/** Half a display step: below this, the channel cannot change its own text. */
const thresholds = CHANNEL_KEYS.map(key => 0.5 * 10 ** -CHANNELS[key].precision);

function createFaceWriter(root: HTMLElement) {
  const strokes = (['L', 'R'] as const).map(side => ({
    side,
    upper: root.querySelector<SVGPathElement>(`[data-rig-stroke="${side}"]`),
    lower: root.querySelector<SVGPathElement>(`[data-rig-ring="${side}"]`),
    contour: '',
    width: '',
    opacity: '',
  }));
  const paths = [
    root.querySelector<SVGPathElement>('[data-rig-mouth]'),
    root.querySelector<SVGPathElement>('[data-rig-brow="L"]'),
    root.querySelector<SVGPathElement>('[data-rig-brow="R"]'),
  ];
  const previous = new Float64Array(SVG_CHANNELS.length).fill(NaN);
  const drawn = ['', '', ''];
  return {
    reset() {
      previous.fill(NaN);
      drawn.fill('');
      for (const stroke of strokes) {
        stroke.contour = stroke.width = stroke.opacity = '';
      }
    },
    write(values: Readonly<ChannelValues>) {
      let changed = false;
      for (let i = 0; i < SVG_CHANNELS.length; i++) {
        const value = values[SVG_CHANNELS[i]];
        if (Math.abs(value - previous[i]) < 0.0001) continue;
        previous[i] = value;
        changed = true;
      }
      if (!changed) return;
      if (root.dataset.style === 'traits' || root.dataset.style === 'anneaux') {
        for (const drawnStroke of strokes) {
          const stroke = strokeContours(values, drawnStroke.side);
          const width = String(stroke.width);
          const opacity = String(stroke.lowerOpacity);
          if (drawnStroke.contour !== stroke.upper) {
            drawnStroke.upper?.setAttribute('d', stroke.upper);
            drawnStroke.contour = stroke.upper;
          }
          if (drawnStroke.width !== width) {
            drawnStroke.upper?.setAttribute('stroke-width', width);
            drawnStroke.lower?.setAttribute('stroke-width', width);
            drawnStroke.width = width;
          }
          if (drawnStroke.opacity !== opacity) {
            drawnStroke.lower?.setAttribute('opacity', opacity);
            drawnStroke.opacity = opacity;
          }
        }
      }
      const contours = [mouthPath(values), browPath(values, 'L'), browPath(values, 'R')];
      contours.forEach((contour, i) => {
        if (drawn[i] === contour) return;
        paths[i]?.setAttribute('d', contour);
        drawn[i] = contour;
      });
    },
  };
}

export function createRigWriter(element: HTMLElement): RigWriter {
  const writeFace = createFaceWriter(element);
  // NaN never compares equal, so the first frame always writes everything.
  const lastRaw = CHANNEL_KEYS.map(() => Number.NaN);
  const lastText = CHANNEL_KEYS.map(() => '');

  return {
    write(values) {
      writeFace.write(values);
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
      writeFace.reset();
      for (let index = 0; index < CHANNEL_KEYS.length; index += 1) {
        lastRaw[index] = Number.NaN;
        lastText[index] = '';
      }
    },
  };
}
