import { tube } from './solid';
/** Original small paintings and brass optics, never remote or generated content. */
import type { WorldProp } from '../types';
import type { Painter } from './painter';
import { project } from '../geometry';
import { propStyleVariant } from './prop-style';
import { WOOD, DARK } from './palette';

export function paintEasel(p: Painter, o: WorldProp): void {
  p.box(0.1, 0.2, 0, 0.12, 0.13, 1.9, WOOD);
  p.box(0.82, 0.2, 0, 0.12, 0.13, 1.9, WOOD);
  p.box(0.04, 0.14, 0.6, 0.97, 0.18, 1.2, '#d4b78a');
  const variant = propStyleVariant(o);
  const panel = (x: number, z: number, w: number, h: number, color: string) =>
    p.panel(x, 0.335, z, w, h, color);
  panel(0.11, 0.68, 0.83, 1.04, '#f0e6d0');
  panel(0.16, 0.73, 0.73, 0.94, ['#adc8bc', '#e4b67e', '#526981'][variant]);
  if (variant === 0) {
    panel(0.64, 1.37, 0.13, 0.13, '#f1ddac');
    p.polygon(
      [
        [0.16, 0.78],
        [0.16, 1.12],
        [0.43, 1.4],
        [0.67, 1.12],
        [0.89, 1.28],
        [0.89, 0.78],
      ].map(([x, z]) => project({ x, y: 0.34 }, z)),
      '#5d8a7e'
    );
    p.polygon(
      [
        [0.16, 0.73],
        [0.16, 0.98],
        [0.52, 1.15],
        [0.89, 0.98],
        [0.89, 0.73],
      ].map(([x, z]) => project({ x, y: 0.345 }, z)),
      '#3d6d66'
    );
    panel(0.2, 0.8, 0.28, 0.035, '#97bdab');
  } else if (variant === 1) {
    panel(0.22, 0.81, 0.23, 0.65, '#b66d5c');
    panel(0.49, 1.18, 0.3, 0.37, '#f0d6a4');
    panel(0.51, 0.81, 0.28, 0.28, '#5f8981');
    panel(0.28, 1.19, 0.12, 0.21, '#e7c895');
  } else {
    panel(0.23, 1.38, 0.16, 0.17, '#efe0b8');
    panel(0.32, 1.42, 0.09, 0.17, '#526981');
    for (const [x, z] of [
      [0.52, 1.48],
      [0.74, 1.3],
      [0.48, 1.15],
      [0.25, 1.09],
    ])
      panel(x, z, 0.025, 0.035, '#e9dbb6');
    panel(0.16, 0.73, 0.73, 0.22, '#374e61');
  }
  p.box(0.025, 0.3, 0.57, 1.01, 0.16, 0.07, WOOD);
  p.box(0.44, 0.24, 1.76, 0.2, 0.15, 0.07, '#a77b54');
}
export function paintTelescope(p: Painter): void {
  const hub = { x: 0.95, y: 0.9, z: 1.02 };
  // Three metal struts really meet at the mount, with rubber feet and a spreader.
  for (const [x, y] of [
    [0.24, 0.38],
    [1.65, 0.62],
    [0.92, 1.65],
  ]) {
    const foot = { x, y, z: 0.08 };
    tube(p, foot, hub, 0.035, '#536865', 8);
    p.box(x - 0.075, y - 0.075, 0, 0.15, 0.15, 0.065, DARK);
    tube(
      p,
      { x: (x + hub.x) / 2, y: (y + hub.y) / 2, z: (foot.z + hub.z) / 2 },
      { ...hub, z: 0.4 },
      0.018,
      '#83938a',
      6
    );
  }
  tube(p, { ...hub, z: 0.95 }, { ...hub, z: 1.38 }, 0.075, '#a27e43');
  p.box(0.81, 0.78, 1.14, 0.28, 0.24, 0.13, '#b48f53');
  const at = (t: number) => ({ x: 0.27 + t * 1.4, y: 0.9, z: 1.08 + t * 0.95 });
  tube(p, at(-0.16), at(0), 0.085, DARK);
  // Consecutive coaxial sections: a collar's solid end cap must never cover
  // the barrel which continues in front of it.
  for (const [start, end, radius, color] of [
    [0, 0.16, 0.22, '#c7a66d'],
    [0.16, 0.22, 0.24, '#8e743f'],
    [0.22, 0.66, 0.22, '#c7a66d'],
    [0.66, 0.72, 0.24, '#8e743f'],
    [0.72, 0.94, 0.22, '#c7a66d'],
  ] as const)
    tube(p, at(start), at(end), radius, color);
  tube(p, at(0.94), at(1.09), 0.265, '#344c50');
  tube(p, at(1.091), at(1.096), 0.215, '#448597');
  tube(p, at(1.097), at(1.1), 0.145, '#74bac3');
  const finder = (t: number) => ({ ...at(t), z: at(t).z + 0.3 });
  for (const t of [0.25, 0.48])
    tube(p, { ...at(t), z: at(t).z + 0.18 }, finder(t), 0.025, '#8e743f', 6);
  tube(p, finder(0.2), finder(0.53), 0.055, DARK);
}
