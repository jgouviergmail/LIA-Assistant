import type { WorldProp } from '../types';
import { Model } from './model';
import { FURNITURE } from './furniture-materials';
import { propStyleVariant } from './prop-style';
import { shade } from './painter';

const TASK_ACTIVITIES = new Set(['meetings', 'relations', 'skills', 'mcp', 'plugins']);

function taskBase(m: Model, frame: string): void {
  m.box(0.08, 0.43, 0.04, 0.84, 0.12, 0.07, frame);
  m.box(0.43, 0.08, 0.04, 0.12, 0.84, 0.07, frame);
  for (const [x, y] of [
    [0.08, 0.44],
    [0.8, 0.44],
    [0.44, 0.08],
    [0.44, 0.8],
  ])
    m.box(x, y, 0, 0.1, 0.1, 0.08, '#263039');
  m.box(0.455, 0.455, 0.12, 0.09, 0.09, 0.35, '#99afb2');
}

function fixedBase(m: Model, frame: string): void {
  for (const x of [0.16, 0.76])
    for (const y of [0.16, 0.74]) m.box(x, y, 0.015, 0.085, 0.085, 0.48, frame);
  for (const x of [0.17, 0.77]) m.box(x, 0.19, 0.22, 0.065, 0.58, 0.055, frame);
}

function backrest(m: Model, o: WorldProp, task: boolean, fabric: string): void {
  const { frame, trim } = FURNITURE[o.tone],
    variant = propStyleVariant(o);
  const top = Math.max(1.05, o.height - 0.04);
  for (const x of [0.15, 0.77]) m.box(x, 0.13, 0.46, 0.075, 0.1, top - 0.46, frame);
  if (task) {
    m.box(0.16, 0.12, 0.77, 0.68, 0.12, top - 0.77, frame);
    m.panel(0.2, 0.245, 0.81, 0.6, top - 0.85, fabric);
    m.panel(0.23, 0.247, 0.84, 0.54, 0.02, trim);
  } else {
    const slats = variant === 1 ? 3 : 2;
    for (let i = 0; i < slats; i++)
      m.box(0.19, 0.14, 0.8 + (i * (top - 0.9)) / Math.max(1, slats - 1), 0.6, 0.08, 0.08, trim);
  }
}

/** Shared seat footprint and elevation; task, reading and terrace silhouettes differ. */
export function chairModel(m: Model, o: WorldProp): void {
  const { frame, fabric, trim } = FURNITURE[o.tone];
  const task = TASK_ACTIVITIES.has(o.activity ?? '');
  const upholstery = o.activity === 'meetings' ? '#e0d6b9' : fabric;
  if (task) taskBase(m, frame);
  else fixedBase(m, frame);
  if ((o.facing ?? 1) === 1) backrest(m, o, task, upholstery);
  m.box(0.12, 0.12, 0.46, 0.76, 0.76, 0.09, frame);
  m.box(0.16, 0.22, 0.55, 0.68, 0.6, 0.115, upholstery);
  m.panel(0.2, 0.824, 0.585, 0.6, 0.012, shade(upholstery, 28));
  if ((o.facing ?? 1) !== 1) backrest(m, o, task, upholstery);
  if (o.activity === 'routines') m.box(0.3, 0.19, 0.84, 0.4, 0.075, 0.2, '#e0bb63');
  if (task && o.height >= 1.3) {
    for (const x of [0.08, 0.85]) {
      m.box(x, 0.42, 0.5, 0.07, 0.07, 0.28, frame);
      m.box(x - 0.01, 0.28, 0.78, 0.09, 0.44, 0.065, trim);
    }
  }
}
