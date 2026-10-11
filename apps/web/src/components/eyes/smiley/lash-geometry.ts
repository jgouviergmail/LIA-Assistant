/** Curves follow the original sculpt's upper rim, intersected by native lids. */
import type { ChannelValues, EyeSide } from '../rig/channels';
import { finite } from './sphere-geometry';

const EYE_HEIGHT = 0.84;
const SCULPT_RX = 0.422 / 1.18;
const SCULPT_RY = 0.448 / 1.18;
const ROOTS = [17, 27, 50, 73, 83];
const FANS = [-14, -8, 1, 8, 14];
const KEYS = ['lidTop', 'lidR', 'sy', 'oy', 'blink'] as const;

function upperRim(x: number, top: number, radius: number): number {
  const circle = 0.5 - SCULPT_RY * Math.sqrt(Math.max(0, 1 - ((x - 0.5) / SCULPT_RX) ** 2));
  const corner = Math.max(0, radius - Math.min(x, 1 - x));
  const rounded = top + radius - Math.sqrt(Math.max(0, radius ** 2 - corner ** 2));
  return Math.max(top, circle, rounded);
}

function lashState(values: Readonly<ChannelValues>, side: EyeSide) {
  const squint = Math.max(0, Math.min(0.5, 1 - finite(values[`sy${side}`])));
  const top = finite(values[`lidTop${side}`]) / 100 + (squint * finite(values[`oy${side}`])) / 100;
  return {
    top,
    edge: Math.max(top, Math.max(0, Math.min(1, finite(values[`blink${side}`]))) * 0.5),
    radius: (squint * 0.35 + Math.min(finite(values[`lidR${side}`]), 0.3)) / EYE_HEIGHT,
  };
}

export function upperLashPath(values: Readonly<ChannelValues>, side: EyeSide): string {
  const state = lashState(values, side);
  const n = (value: number) => String(Number(value.toFixed(3)));
  return ROOTS.map((x, index) => {
    if (index === (side === 'L' ? ROOTS.length - 1 : 0)) return '';
    const root =
      37 +
      (((Math.max(state.edge, upperRim(x / 100, state.top, state.radius)) - state.edge) *
        EYE_HEIGHT) /
        0.3) *
        80;
    const fan = FANS[index];
    // The tip curls back towards the eye, retaining the same root and endpoint.
    return `M ${x} ${n(root)} C ${n(x + fan * 0.84)} ${n(root - 12)} ${n(x + fan * 1.58)} ${n(root - 27)} ${x + fan} ${n(root - 31)}`;
  })
    .filter(Boolean)
    .join(' ');
}

/** Nothing changes for idle frames; the native writer owns these two paths. */
export function createLashWriter(root: HTMLElement) {
  const lashes = (['L', 'R'] as const).map(side => ({
    side,
    path: root.querySelector<SVGPathElement>(`[data-smiley-lashes="${side}"]`),
    previous: new Float64Array(KEYS.length).fill(NaN),
    drawn: '',
  }));
  return {
    write(values: Readonly<ChannelValues>) {
      for (const lash of lashes) {
        if (!lash.path) continue;
        let changed = false;
        KEYS.forEach((key, index) => {
          const value = values[`${key}${lash.side}`];
          if (Math.abs(value - lash.previous[index]) < 0.0001) return;
          lash.previous[index] = value;
          changed = true;
        });
        if (!changed) continue;
        const contour = upperLashPath(values, lash.side);
        if (contour === lash.drawn) continue;
        lash.path.setAttribute('d', contour);
        lash.drawn = contour;
      }
    },
  };
}
