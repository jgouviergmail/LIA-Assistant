/** One finite owner-local fishing sequence: take rod, cast, wait, reel. */
import type { CosmeticFrame } from '../cosmetic-effects';
import type { Point } from '../types';
import { project } from '../geometry';
import { FISHING_IMPACT } from '../decor-presentation';
interface FishingFrame {
  hand: Point;
  tip: Point;
  float: Point | null;
  state: 'preparing' | 'casting' | 'waiting' | 'reeling';
}
export function fishingFrame(beat: CosmeticFrame, reduced = false): FishingFrame | null {
  if (!beat.origin) return null;
  const from = beat.origin,
    to = beat.point,
    phase = beat.phase;
  const distance = Math.max(0.01, Math.hypot(to.x - from.x, to.y - from.y));
  const direction = { x: (to.x - from.x) / distance, y: (to.y - from.y) / distance };
  const reach = reduced ? 1.2 : 0.6 + Math.min(1, phase / 0.2) * 0.8;
  const hand = project({ x: from.x + direction.x * 0.25, y: from.y + direction.y * 0.25 }, 1.05),
    tip = project({ x: from.x + direction.x * reach, y: from.y + direction.y * reach }, 2.5);
  if (phase < 0.18) return { hand, tip, float: null, state: 'preparing' };
  const state = phase < FISHING_IMPACT ? 'casting' : phase < 0.78 ? 'waiting' : 'reeling';
  const progress =
    state === 'casting'
      ? (phase - 0.18) / (FISHING_IMPACT - 0.18)
      : state === 'waiting'
        ? 1
        : Math.max(0, 1 - (phase - 0.78) / 0.22);
  const point = { x: from.x + (to.x - from.x) * progress, y: from.y + (to.y - from.y) * progress };
  const height =
    state === 'casting'
      ? 0.12 + Math.sin(progress * Math.PI) * 1.8
      : state === 'waiting'
        ? 0.12
        : 0.12 + (1 - progress) * 1.3;
  const float = reduced ? project(to, 0.12) : project(point, height);
  if (state === 'waiting' && !reduced) float.y += Math.sin(phase * 65) * 1.2;
  return { hand, tip, float, state };
}
export function paintFishing(
  c: CanvasRenderingContext2D,
  beat: CosmeticFrame,
  reduced: boolean
): void {
  const frame = fishingFrame(beat, reduced);
  if (!frame) return;
  c.save();
  c.lineCap = 'round';
  c.strokeStyle = '#c49b65';
  c.lineWidth = 3;
  c.beginPath();
  c.moveTo(frame.hand.x, frame.hand.y);
  c.quadraticCurveTo(frame.tip.x + 3, frame.hand.y - 25, frame.tip.x, frame.tip.y);
  c.stroke();
  c.strokeStyle = '#344d55';
  c.lineWidth = 4;
  c.beginPath();
  c.moveTo(frame.hand.x, frame.hand.y);
  c.lineTo(
    frame.hand.x + (frame.tip.x - frame.hand.x) * 0.18,
    frame.hand.y + (frame.tip.y - frame.hand.y) * 0.18
  );
  c.stroke();
  if (frame.float) {
    c.strokeStyle = 'rgba(238,242,218,.9)';
    c.lineWidth = 0.9;
    c.beginPath();
    c.moveTo(frame.tip.x, frame.tip.y);
    c.quadraticCurveTo(frame.tip.x, frame.float.y - 8, frame.float.x, frame.float.y);
    c.stroke();
    c.fillStyle = '#df795d';
    c.beginPath();
    c.ellipse(frame.float.x, frame.float.y, 2.5, 3.5, 0, 0, Math.PI * 2);
    c.fill();
    c.fillStyle = '#f6efd2';
    c.fillRect(frame.float.x - 1.5, frame.float.y - 3.5, 3, 2);
    if (frame.state === 'waiting') {
      c.strokeStyle = 'rgba(218,249,234,.7)';
      c.lineWidth = 1;
      c.beginPath();
      c.ellipse(frame.float.x, frame.float.y + 3, 8, 3, 0, 0, Math.PI * 2);
      c.stroke();
    }
  }
  c.restore();
}
