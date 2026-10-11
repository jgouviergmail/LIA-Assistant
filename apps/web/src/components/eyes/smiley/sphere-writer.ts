/** Tangent planes are anchored on the same actual sphere the GPU intersects. */
import type { ChannelValues } from '../rig/channels';
import {
  finite,
  projectSmileyCrown,
  projectSmileySurface,
  spherePose,
  type SpherePoint,
} from './sphere-geometry';
import { paintSmileySphere, resetSmileySphere } from './sphere-binding';
import { smileyMouthWidth } from './rest-mouth';
import { createLashWriter } from './lash-geometry';

function organPoint(kind: string, values: Readonly<ChannelValues>) {
  if (kind === 'bow')
    return { rest: { x: 0, y: -1.3 }, gaze: { x: 0, y: 0 }, shift: { x: 0, y: 0 } };
  const gaze = { x: finite(values.gazeX) * 0.065, y: finite(values.gazeY) * 0.045 };
  if (kind === 'mouth')
    return {
      rest: { x: 0, y: 0.485 },
      gaze,
      shift: {
        x: finite(values.mouthX),
        y: finite(values.mouthY) + finite(values.mouthOpen) * 0.035,
      },
    };
  const side = kind === 'left' ? 'L' : 'R';
  return {
    rest: { x: side === 'L' ? -0.48 : 0.48, y: -0.23 },
    gaze,
    shift: { x: finite(values[`tx${side}`]), y: finite(values[`ty${side}`]) },
  };
}

function sum(...points: SpherePoint[]): SpherePoint {
  return points.reduce((total, point) => ({ x: total.x + point.x, y: total.y + point.y }), {
    x: 0,
    y: 0,
  });
}

function surfaceTransform(kind: string, values: Readonly<ChannelValues>): string {
  const { rest, gaze, shift } = organPoint(kind, values);
  const pose = spherePose(values);
  const projected =
    kind === 'bow' ? projectSmileyCrown(pose) : projectSmileySurface(sum(rest, gaze, shift), pose);
  const x = projected.x - rest.x - gaze.x - projected.a * shift.x - projected.c * shift.y;
  const y = projected.y - rest.y - gaze.y - projected.b * shift.x - projected.d * shift.y;
  const format = (value: number) => String(Number(value.toFixed(4)));
  return `translate(${format(x)}em, ${format(y)}em) matrix(${[projected.a, projected.b, projected.c, projected.d].map(format).join(', ')}, 0, 0)`;
}

export function createSmileySurfaceWriter(root: HTMLElement) {
  let style: string | undefined;
  let previousWidth = '';
  let lashes = createLashWriter(root);
  let organs: { element: HTMLElement; previous: string }[] = [];
  return {
    reset() {
      for (const organ of organs) organ.previous = '';
      previousWidth = '';
      lashes = createLashWriter(root);
      resetSmileySphere(root);
    },
    write(values: Readonly<ChannelValues>) {
      const appearance = `${root.dataset.style}-${root.dataset.smileyVariant}`;
      if (style !== appearance) {
        style = appearance;
        lashes = createLashWriter(root);
        organs = [...root.querySelectorAll<HTMLElement>('[data-smiley-surface]')].map(element => ({
          element,
          previous: '',
        }));
      }
      if (root.dataset.style !== 'smiley') return;
      const width = String(Number(smileyMouthWidth(values).toFixed(4)));
      if (width !== previousWidth) {
        root.style.setProperty('--smiley-mouth-width', width);
        previousWidth = width;
      }
      paintSmileySphere(root, values);
      lashes.write(values);
      for (const organ of organs) {
        const text = surfaceTransform(organ.element.dataset.smileySurface ?? '', values);
        if (text === organ.previous) continue;
        organ.element.style.setProperty('transform', text);
        organ.previous = text;
      }
    },
  };
}
