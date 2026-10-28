/** Small local responses, painted inside the existing object's depth layer. */
import { project } from '../geometry';
import type { CosmeticFrame } from '../cosmetic-effects';
import type { Point, WorldProp } from '../types';
import type { CosmeticActionId } from '../cosmetic-interactions';
import { canonicalSize, rotateModelPoint } from './model';
import { paintFountainToss } from './fountain-toss';
import { paintFishing } from './fishing';

export function reactionAmount(phase: number): number {
  if (phase <= 0 || phase >= 1) return 0;
  if (phase < 0.08) return -Math.sin((phase / 0.08) * Math.PI) * 0.15;
  const progress = (phase - 0.08) / 0.92;
  return Math.sin(progress * Math.PI * 2) * (1 - progress) ** 2;
}
export function paintBilliardBall(
  c: CanvasRenderingContext2D,
  prop: WorldProp,
  beat?: CosmeticFrame,
  reduced = false
): void {
  const { w, d } = canonicalSize(prop);
  const offset = beat && !reduced ? Math.sin(beat.phase * Math.PI) * 0.35 : 0;
  const local = rotateModelPoint(
    { x: w / 2 + 0.065 - offset, y: 1.065, z: 1.22 },
    w,
    d,
    prop.facing ?? 1
  );
  const at = project({ x: prop.x + local.x, y: prop.y + local.y }, local.z);
  c.save();
  c.fillStyle = '#fff6d6';
  c.beginPath();
  c.ellipse(at.x, at.y, 2.4, 2, 0, 0, Math.PI * 2);
  c.fill();
  c.fillStyle = '#ffffff';
  c.fillRect(at.x - 0.8, at.y - 1.2, 1, 1);
  c.restore();
}
type ResponsePainter = (
  c: CanvasRenderingContext2D,
  at: Point,
  phase: number,
  reduced: boolean
) => void;
const purr: ResponsePainter = (c, at, phase) => {
  for (const side of [-1, 1]) {
    c.beginPath();
    c.arc(at.x + side * 7, at.y - 6, 3 + phase * 3, -1, 1);
    c.stroke();
  }
};
const leaf: ResponsePainter = (c, at, _phase, reduced) => {
  if (reduced) {
    c.beginPath();
    c.ellipse(at.x, at.y - 4, 4, 2, -0.5, 0, Math.PI * 2);
    c.stroke();
  }
};
const RESPONSES: Partial<Record<CosmeticActionId, ResponsePainter>> = {
  cat: purr,
  plant: leaf,
};
export function paintCosmeticResponse(
  c: CanvasRenderingContext2D,
  beat: CosmeticFrame,
  reduced: boolean
): void {
  if (beat.action === 'pond') {
    paintFishing(c, beat, reduced);
    return;
  }
  if (beat.action === 'fountain') {
    paintFountainToss(c, beat, reduced);
    return;
  }
  const paint = RESPONSES[beat.action];
  if (!paint) return;
  const phase = reduced ? 0.4 : beat.phase;
  const at = project(beat.point, beat.elevation);
  c.save();
  c.globalAlpha = reduced ? 0.8 : Math.min(1, phase * 10, (1 - phase) * 5);
  c.lineWidth = 1.4;
  c.strokeStyle = '#f1cf7d';
  paint(c, at, phase, reduced);
  c.restore();
}
