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
  type EyeSide,
} from '@/components/eyes/rig/channels';
import {
  browPath,
  mouthPath,
  sculptedBrowPath,
  sculptedMouthContours,
  SVG_CHANNELS,
} from './face-geometry';
import { strokeContours } from './stroke-geometry';
import { createSmileySurfaceWriter } from '../smiley/sphere-writer';
import { projectBodyMotion, type BodyBox, type BodyViewport } from '../body-motion-geometry';
import { createAmbientPropWriter } from './ambient-prop-writer';
import { createVolumeSurfaceWriter } from '../volume/volume-writer';

export interface RigWriter {
  /** Push the frame onto the element. */
  write(values: Readonly<ChannelValues>): void;
  setBodyFrame(box: BodyBox, viewport: BodyViewport): void;
  /** Forget what was written — the next `write` re-emits everything. */
  reset(): void;
  /** Release the native renderer's references; disposed writers cannot paint. */
  dispose(): void;
}

/** Half a display step: below this, the channel cannot change its own text. */
const thresholds = CHANNEL_KEYS.map(key => 0.5 * 10 ** -CHANNELS[key].precision);

function browShape(path: SVGPathElement | null): string {
  return path?.dataset.rigBrowShape ?? '';
}

function projectBrow(values: Readonly<ChannelValues>, path: SVGPathElement | null, side: EyeSide) {
  return (browShape(path) === 'sculpted' ? sculptedBrowPath : browPath)(values, side);
}

/** Stroke skins have their own SVG paint and cache, independent of the facial ribbons. */
function createStrokeWriter(root: HTMLElement) {
  const strokes = (['L', 'R'] as const).map(side => ({
    side,
    upper: root.querySelector<SVGPathElement>(`[data-rig-stroke="${side}"]`),
    lower: root.querySelector<SVGPathElement>(`[data-rig-ring="${side}"]`),
    contour: '',
    width: '',
    opacity: '',
  }));
  return {
    reset() {
      for (const stroke of strokes) stroke.contour = stroke.width = stroke.opacity = '';
    },
    write(values: Readonly<ChannelValues>) {
      if (root.dataset.style !== 'traits' && root.dataset.style !== 'anneaux') return;
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
    },
  };
}

function createFaceWriter(root: HTMLElement) {
  const strokeWriter = createStrokeWriter(root);
  const paths = [
    root.querySelector<SVGPathElement>('[data-rig-mouth]'),
    root.querySelector<SVGPathElement>('[data-rig-brow="L"]'),
    root.querySelector<SVGPathElement>('[data-rig-brow="R"]'),
    root.querySelector<SVGPathElement>('[data-rig-mouth-teeth]'),
    root.querySelector<SVGPathElement>('[data-rig-mouth-tongue]'),
  ];
  const previous = new Float64Array(SVG_CHANNELS.length).fill(NaN);
  const drawn = new Array<string | undefined>(paths.length);
  let previousLeftShape = '';
  let previousRightShape = '';
  let previousMouthShape = '';
  return {
    reset() {
      previous.fill(NaN);
      drawn.fill(undefined);
      previousLeftShape = previousRightShape = '';
      previousMouthShape = '';
      strokeWriter.reset();
    },
    write(values: Readonly<ChannelValues>) {
      const currentLeftShape = browShape(paths[1]);
      const currentRightShape = browShape(paths[2]);
      const currentMouthShape = paths[0]?.dataset.rigMouthShape ?? '';
      if (currentMouthShape !== previousMouthShape) {
        // A material can add or remove these paths while the same native skin
        // and clock remain mounted. Query only at that presentation boundary.
        paths[0] = root.querySelector<SVGPathElement>('[data-rig-mouth]');
        paths[3] = root.querySelector<SVGPathElement>('[data-rig-mouth-teeth]');
        paths[4] = root.querySelector<SVGPathElement>('[data-rig-mouth-tongue]');
        drawn[0] = drawn[3] = drawn[4] = undefined;
      }
      let changed =
        currentLeftShape !== previousLeftShape ||
        currentRightShape !== previousRightShape ||
        currentMouthShape !== previousMouthShape;
      previousLeftShape = currentLeftShape;
      previousRightShape = currentRightShape;
      previousMouthShape = currentMouthShape;
      for (let i = 0; i < SVG_CHANNELS.length; i++) {
        const value = values[SVG_CHANNELS[i]];
        if (Math.abs(value - previous[i]) < 0.0001) continue;
        previous[i] = value;
        changed = true;
      }
      if (!changed) return;
      strokeWriter.write(values);
      const mouth =
        currentMouthShape === 'sculpted'
          ? sculptedMouthContours(values)
          : { cavity: mouthPath(values), teeth: '', tongue: '' };
      const contours = [
        mouth.cavity,
        projectBrow(values, paths[1], 'L'),
        projectBrow(values, paths[2], 'R'),
        mouth.teeth,
        mouth.tongue,
      ];
      contours.forEach((contour, i) => {
        if (drawn[i] === contour) return;
        paths[i]?.setAttribute('d', contour);
        drawn[i] = contour;
      });
    },
  };
}

export function createRigWriter(element: HTMLElement): RigWriter {
  let writeFace = createFaceWriter(element);
  let style = element.dataset.style;
  const writeSphere = createSmileySurfaceWriter(element);
  const writeVolume = createVolumeSurfaceWriter(element);
  const ambient = createAmbientPropWriter(element);
  let active = true;
  // NaN never compares equal, so the first frame always writes everything.
  const lastRaw = CHANNEL_KEYS.map(() => Number.NaN);
  const lastText = CHANNEL_KEYS.map(() => '');
  const bodyKeys = ['bodyX', 'bodyY', 'bodyRoll', 'bodySx', 'bodySy'] as const;
  let bodyFrame: { box: BodyBox; viewport: BodyViewport } | null = null;
  const bodyRaw = bodyKeys.map(() => NaN);
  const bodyText = bodyKeys.map(() => '');
  let bodyDirty = true;

  function writeBody(values: Readonly<ChannelValues>) {
    let changed = bodyDirty;
    bodyKeys.forEach((key, i) => {
      if (Math.abs(values[key] - bodyRaw[i]) < 0.0001) return;
      bodyRaw[i] = values[key];
      changed = true;
    });
    if (!changed) return;
    bodyDirty = false;
    const desired = {
      x: values.bodyX,
      y: values.bodyY,
      roll: values.bodyRoll,
      sx: values.bodySx,
      sy: values.bodySy,
    };
    const drawn = bodyFrame
      ? projectBodyMotion(desired, bodyFrame.box, bodyFrame.viewport)
      : desired;
    const numbers = [drawn.x, drawn.y, drawn.roll, drawn.sx, drawn.sy];
    bodyKeys.forEach((key, i) => {
      const text = formatChannel(key, numbers[i]);
      if (text === bodyText[i]) return;
      bodyText[i] = text;
      element.style.setProperty(CHANNELS[key].cssVar, text);
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
  }

  return {
    setBodyFrame(box, viewport) {
      bodyFrame = { box, viewport };
      bodyDirty = true;
    },
    write(values) {
      if (!active) return;
      if (style !== element.dataset.style) {
        style = element.dataset.style;
        writeFace = createFaceWriter(element);
      }
      writeFace.write(values);
      writeSphere.write(values);
      writeVolume.write(values);
      ambient.write(values);
      writeBody(values);
      for (let index = 0; index < CHANNEL_KEYS.length; index += 1) {
        const key = CHANNEL_KEYS[index];
        if ((bodyKeys as readonly string[]).includes(key)) continue;
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
      bodyDirty = true;
      bodyRaw.fill(NaN);
      bodyText.fill('');
      writeFace.reset();
      writeSphere.reset();
      writeVolume.reset();
      ambient.reset();
      for (let index = 0; index < CHANNEL_KEYS.length; index += 1) {
        lastRaw[index] = Number.NaN;
        lastText[index] = '';
      }
    },
    dispose() {
      active = false;
      ambient.dispose();
      writeVolume.dispose();
    },
  };
}
