import { canonicalSize, rotateModelPoint } from './model';
import { project } from '../geometry';
import type { Atmosphere } from '../atmosphere';
import type { WorldProp } from '../types';
let civilClock: { minute: number; zone: string; text: string } | null = null;
function clockText(a: Atmosphere | undefined): string {
  if (a?.time === null || a?.time === undefined || !a.timezone) return '--:--';
  const minute = Math.floor(a.time / 60000);
  if (civilClock?.minute === minute && civilClock.zone === a.timezone) return civilClock.text;
  const text = new Intl.DateTimeFormat('en-GB', {
    timeZone: a.timezone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(a.time);
  civilClock = { minute, zone: a.timezone, text };
  return text;
}
export function paintRoomMotion(
  c: CanvasRenderingContext2D,
  o: WorldProp,
  time: number,
  reduced: boolean,
  a?: Atmosphere
): void {
  // These decorations belong to the front panel, not to the rear casing.
  if ((o.facing ?? 1) >= 2) return;
  if (o.kind === 'alarm') {
    const at = project({ x: o.x + 0.06, y: o.y + o.depth + 0.01 }, 0.87);
    c.save();
    c.translate(at.x, at.y);
    c.transform(1, 0.5, 0, 1, 0, 0);
    c.fillStyle = '#163c42';
    c.fillRect(0, -6.6, 22, 7.2);
    c.fillStyle = '#85ead3';
    c.font = '8px monospace';
    c.fillText(clockText(a), 0, 0);
    c.restore();
    return;
  }
  if (reduced) return;
  if (o.kind !== 'arcade' && o.kind !== 'display' && o.kind !== 'machine' && o.kind !== 'jukebox')
    return;
  const { w, d } = canonicalSize(o);
  const at = (x: number, z: number) => {
    const p = rotateModelPoint(
      { x, y: o.kind === 'display' || o.kind === 'jukebox' ? d + 0.009 : 0.836, z },
      w,
      d,
      o.facing ?? 1
    );
    return project({ x: o.x + p.x, y: o.y + p.y }, p.z);
  };
  c.save();
  c.strokeStyle = '#a9ebdd';
  c.fillStyle = '#f4d474';
  c.lineWidth = 1.2;
  if (o.kind === 'arcade') {
    c.beginPath();
    for (const [i, [x, z]] of [
      [0.2, 1.28],
      [w - 0.2, 1.28],
      [w - 0.2, 1.88],
      [0.2, 1.88],
    ].entries()) {
      const point = at(x, z);
      if (i) c.lineTo(point.x, point.y);
      else c.moveTo(point.x, point.y);
    }
    c.closePath();
    c.clip();
    const p = at(
      0.3 + ((time * 0.2 + o.x * 0.1) % 1) * (w - 0.7),
      1.55 + Math.sin(time * 1.7) * 0.08
    );
    c.fillRect(p.x, p.y, 3, 3);
  } else if (o.kind === 'display') {
    const phase = (time * 0.15) % 1,
      p = at(0.3 + phase * (w - 0.6), 1.6);
    c.beginPath();
    c.moveTo(p.x, p.y);
    c.lineTo(p.x, p.y - 7);
    c.stroke();
  } else if (o.kind === 'jukebox') {
    const p = at(w / 2, 2.1);
    c.globalAlpha = 0.35 + Math.sin(time * 1.5) * 0.12;
    c.fillStyle = '#ffe0a0';
    c.beginPath();
    c.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
    c.fill();
  } else {
    const p = at(0.55, 1.85 + Math.sin(time * 1.4) * 0.09);
    c.globalAlpha = 0.55;
    c.beginPath();
    c.arc(p.x, p.y, 2.5, 0, Math.PI * 2);
    c.fill();
  }
  c.restore();
}
